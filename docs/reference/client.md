# Client (`Pareta`, `AsyncPareta`)

The client is the one object you build and the only thing that talks to the network. It holds your API key, the environment URL, the timeout and retry policy, and an HTTP connection pool. Every call you make goes through it: deploying endpoints, running inference, browsing the catalog, evaluating models. There are two of them and they are mirror images: `Pareta` is synchronous, `AsyncPareta` is `async`/`await`. Pick one, build it once, reuse it.

```python
from pareta import Pareta

with Pareta.from_env() as pa:                 # reads PARETA_API_KEY
    print(pa.models.list())
```

Nothing else in the SDK is constructed directly. Resources like `pa.chat`, `pa.endpoints`, and `pa.evals` are attributes that hang off the client; you never instantiate them yourself.

## Build it from the environment

`from_env()` is the recommended constructor. It reads `PARETA_API_KEY` and an optional `PARETA_BASE_URL`, then builds the client for you. It keeps `pareta_sk_…` secrets out of source and lets the same code run against production or staging by flipping one environment variable.

```bash
export PARETA_API_KEY="pareta_sk_live_…"
```

```python
from pareta import Pareta, AsyncPareta

pa = Pareta.from_env()             # sync
apa = AsyncPareta.from_env()       # async — same call, async client
```

```python
@classmethod
Pareta.from_env(**kwargs) -> Pareta
AsyncPareta.from_env(**kwargs) -> AsyncPareta
```

`from_env()` forwards any extra keyword arguments straight to the constructor, so you can keep the key in the environment and still override the rest in code:

```python
pa = Pareta.from_env(max_retries=5, timeout=120.0)
```

An explicit `api_key=` or `base_url=` passed to `from_env()` wins over the environment variable of the same name.

## Construct it directly

When you are not driving config from the environment, call the constructor. Both clients take the same arguments; they differ only in the type of `http_client`.

```python
from pareta import Pareta

pa = Pareta(
    api_key="pareta_sk_live_…",
    base_url="https://api.pareta.ai",
    timeout=60.0,
    max_retries=2,
    http_client=None,
)
```

```python
Pareta(
    api_key: str | None = None,
    base_url: str | None = None,
    timeout=None,
    max_retries: int = 2,            # DEFAULT_MAX_RETRIES
    http_client: httpx.Client | None = None,
)

AsyncPareta(
    api_key: str | None = None,
    base_url: str | None = None,
    timeout=None,
    max_retries: int = 2,
    http_client: httpx.AsyncClient | None = None,
)
```

| Parameter | Type | Default | What it does |
|-----------|------|---------|--------------|
| `api_key` | `str \| None` | `None` | Your `pareta_sk_…` key. Sent as `Authorization: Bearer <key>`. Required (raises `ParetaError` if missing). |
| `base_url` | `str \| None` | `"https://api.pareta.ai"` | API root. Normalized with `rstrip("/")`. Pass the staging URL to point at staging. |
| `timeout` | `httpx.Timeout \| float \| None` | `httpx.Timeout(60.0, connect=10.0)` | Per-request HTTP timeout. |
| `max_retries` | `int` | `2` | Automatic retries on transient failures. Clamped to `>= 0`. |
| `http_client` | `httpx.Client \| httpx.AsyncClient \| None` | `None` | Bring your own httpx client (proxies, custom transports, pools). |

### `api_key`

The key is the one piece of config you cannot skip. The SDK sends it as a Bearer token on every request. Mint keys in the dashboard; key management is browser-only and the SDK only ever consumes a key.

If the key is falsy (and `PARETA_API_KEY` is unset when using `from_env()`), the constructor raises `ParetaError` before any network call:

```python
from pareta import Pareta, ParetaError

try:
    pa = Pareta(api_key="")
except ParetaError as e:
    print(e)
    # missing API key. Pass api_key=… or set PARETA_API_KEY
    # (mint a pareta_sk_ key in the dashboard).
```

A key that is present but rejected by the server surfaces as `AuthenticationError` (401) on the first request, not at construction time.

### `base_url`

`base_url` selects the environment. It defaults to production and is normalized with a trailing-slash strip, so `https://api.pareta.ai/` and `https://api.pareta.ai` behave identically. Keys are environment-scoped: pair each `base_url` with a key minted for that environment.

```python
prod    = Pareta(api_key="pareta_sk_live_…")                                  # default
staging = Pareta(api_key="pareta_sk_test_…", base_url="https://api-staging.pareta.ai")
```

### `timeout`

Caps how long a single request may take. The default `httpx.Timeout(60.0, connect=10.0)` allows up to 10 seconds to connect and 60 seconds overall. A bare float sets the overall timeout for read, write, and connect alike. Raise it for long completions, or stream the response so tokens arrive incrementally (see [Inference](../guide/inference.md)). Note that `evals.runs.create(..., wait=True)` has its own `timeout` argument governing the poll loop, separate from this HTTP timeout (see [Evals](../guide/evaluation.md)).

```python
import httpx
from pareta import Pareta

pa = Pareta(api_key="pareta_sk_live_…", timeout=httpx.Timeout(120.0, connect=10.0))
```

### `max_retries`

The SDK automatically retries transient failures: HTTP `408, 409, 429, 500, 502, 503, 504`. The default is `2` (up to 3 attempts). Backoff is exponential with jitter, capped at 8 seconds, and honors a server `Retry-After` header when present. Non-transient errors (`401`, `402`, `404`, and so on) raise on the first attempt. Once a stream's bytes are flowing, a mid-stream drop raises immediately and is not retried. See [Errors and retries](../guide/errors-and-retries.md).

```python
pa = Pareta(api_key="pareta_sk_live_…", max_retries=5)   # patient batch job
pa = Pareta(api_key="pareta_sk_live_…", max_retries=0)   # fail fast (tests)
```

### `http_client`

By default the client constructs its own httpx client (configured with your `timeout`) and closes it for you. Pass `http_client=` to control the transport layer: an outbound proxy, mTLS, shared connection pools, or test doubles.

```python
import httpx
from pareta import Pareta

my_client = httpx.Client(
    proxy="http://proxy.internal:8080",
    limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
    timeout=httpx.Timeout(120.0, connect=10.0),
)
pa = Pareta(api_key="pareta_sk_live_…", http_client=my_client)
```

When you inject a client, you own its lifecycle and its timeout. `pa.close()` will not close a client you passed in, and the constructor's `timeout=` applies only to an SDK-owned client. Set the timeout on your own client, and close it yourself.

## Lifecycle and cleanup

Each client owns an HTTP connection pool. Release it when you are done. The cleanly idiomatic way is the context manager, which closes the pool on exit.

### Sync

```python
close() -> None          # close the HTTP client (only if the SDK owns it)
__enter__() -> Pareta
__exit__(*exc) -> None
```

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    completion = pa.chat.completions.create(
        model="ep_a1b2c3",
        messages=[{"role": "user", "content": "Extract the parties."}],
    )
    print(completion.choices[0].message.content)
# HTTP client closed on exit
```

Or close it explicitly:

```python
pa = Pareta.from_env()
try:
    pa.models.list()
finally:
    pa.close()
```

### Async

```python
async aclose() -> None
async __aenter__() -> AsyncPareta
async __aexit__(*exc) -> None
```

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        models = await pa.models.list()
        print(models)
    # HTTP client closed on exit

asyncio.run(main())
```

The ownership rule holds in both: if you passed `http_client=`, neither `close()`/`aclose()` nor exiting the context manager touches it. Close your own client.

## Resource namespaces

The client is a namespace router. Every capability hangs off it as an attribute. The sync client exposes the sync resources; the async client exposes the async mirrors. The method shapes match one-to-one, async methods are `async def`, and streaming methods return async iterators on the async client.

| Namespace | Sync type | Async type | What it does | Reference |
|-----------|-----------|------------|--------------|-----------|
| `chat` | `Chat` | `AsyncChat` | OpenAI-compatible inference via `chat.completions.create(...)`. Metered. | [chat](./chat.md) |
| `models` | `Models` | `AsyncModels` | `models.list()` — the deployed, callable endpoints (OpenAI-compatible subset). | [models](./models.md) |
| `endpoints` | `Endpoints` | `AsyncEndpoints` | `deploy`, `list`, `retrieve`, `start`, `stop`, `delete`, and `metrics(id)`. | [endpoints](./endpoints.md) |
| `tasks` | `Tasks` | `AsyncTasks` | Browse the benchmark catalog: `list`, `retrieve`, `match`, `leaderboard`, `recommended`. | [tasks](./tasks.md) |
| `evals` | `Evals` | `AsyncEvals` | `evals.sets`, `evals.runs`, and `evals.frontier_models(...)`. Metered. | [evals](./evals.md) |
| `audio` | `Audio` | `AsyncAudio` | Speech: `audio.transcriptions(...)` (ASR) and `audio.speech(...)` (TTS). Metered per minute. | [audio example](../examples/audio-transcribe-and-speak.py) |

A tour of the core namespaces against one client:

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    # tasks — discover what to deploy
    task = "contract-key-fields"
    print("recommended:", pa.tasks.recommended(task))      # a per-task alias

    # endpoints — deploy it (wait=True blocks through the deploy SSE stream)
    ep = pa.endpoints.deploy(task=task, model="recommended", wait=True)
    print("live:", ep.id, ep.status)

    # chat — OpenAI-compatible inference against the endpoint id
    resp = pa.chat.completions.create(
        model=ep.id,
        messages=[{"role": "user", "content": "Say hello."}],
    )
    print(resp.choices[0].message.content)

    # models — the OpenAI-compatible list of callable endpoints
    for m in pa.models.list():
        print(m.id, m.owned_by)

    # evals — score candidates on your own data, billed total in dollars
    run = pa.evals.runs.create(
        task=task,
        items=[{"input": "…", "expected": "…"}],
        models=["qwen-vl-2"],
        frontier="benchmarked",
        wait=True,
    )
    print("run cost:", run.cost)        # Decimal dollars, floored to cents
```

The same code on the async client, with `await` and the async context manager:

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        ep = await pa.endpoints.deploy(
            task="contract-key-fields", model="recommended", wait=True,
        )
        resp = await pa.chat.completions.create(
            model=ep.id,
            messages=[{"role": "user", "content": "Say hello."}],
        )
        print(resp.choices[0].message.content)

asyncio.run(main())
```

Two async differences worth pinning down: `pa.endpoints.metrics(id)` returns an `AsyncMetrics` object directly (not a coroutine), and its dimension methods are the things you await. See [Async](../guide/async.md) for the full sync-vs-async mapping.

## Platform truths the client makes concrete

These hold no matter how you build the client. They are why there is no GPU knob, no balance API, and no real model ids in the SDK.

- **GPUs are hidden.** You configure a key, a URL, timeouts, and retries — never hardware. `endpoints.deploy(task=…, model=…)` takes a task and a model alias; Pareta resolves the GPU, tensor-parallelism, and quantization from its registry. There is no hardware parameter anywhere in the SDK. See [Deploy endpoints](../guide/deploying-endpoints.md).
- **Models are per-task aliases.** Every model id you pass or read — in `deploy(model=…)`, on `tasks.leaderboard()` rows, in `run.results[].model_id`, in `endpoints.list()[].model` — is a per-task public alias like `qwen-vl-2`. Real internal ids never cross into the SDK. Frontier (vendor) ids are in the clear. See [Discovery](../guide/discovery.md).
- **Inference and evals are metered against your org balance.** A successful `pa.chat.completions.create()` debits your balance; `pa.evals.runs.create()` debits for both open and frontier compute. An `EvalRun` reports its billed total on `run.cost` (a `Decimal` in dollars, floored to whole cents, so a sub-cent run reads `Decimal("0.00")`) and the raw value on `run.cost_micro_usd`. When the balance hits zero, both paths raise `InsufficientCreditsError` (402). Top-up is browser-only; the SDK exposes neither balance nor payment methods.

  ```python
  from pareta import InsufficientCreditsError

  try:
      pa.chat.completions.create(model=ep.id, messages=[{"role": "user", "content": "ping"}])
  except InsufficientCreditsError:
      print("Out of credit — top up in the dashboard.")
  ```

- **Inference is OpenAI-compatible.** `base_url` plus your `pareta_sk_…` key is a drop-in OpenAI endpoint. You can point the `openai` SDK at the same `base_url` to call a deployed endpoint; this SDK adds the control plane (deploy, eval, discovery) the `openai` client cannot do. See [Inference](../guide/inference.md).

## See also

- [Configuration](../guide/configuration.md) — the full configuration guide: `from_env`, `base_url`, timeouts, retries, custom transports, and the configuration cookbook.
- [Inference](../guide/inference.md) — `chat.completions.create`, streaming, and metering.
- [Deploy endpoints](../guide/deploying-endpoints.md) — deploy a model to a task and operate it.
- [Discovery](../guide/discovery.md) — browse the catalog, match intent, read leaderboards.
- [Evaluation](../guide/evaluation.md) — score models on your own data, including `run.cost`.
- [Errors and retries](../guide/errors-and-retries.md) — the `ParetaError` hierarchy and retry behavior.
- [Async](../guide/async.md) — the sync-vs-async mapping for every resource.
