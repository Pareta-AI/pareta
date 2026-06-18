# Configuration

Every Pareta call goes through one client object. Configuration is just how you build that client: which API key it sends, which environment it points at, how patient it is on slow or flaky requests, and (optionally) what HTTP stack it rides on. This page covers all of it for both `Pareta` (sync) and `AsyncPareta` (async).

The short version: set `PARETA_API_KEY` and use `Pareta.from_env()`. Everything below is for when the defaults are not enough.

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()
print(pa.models.list())
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();
console.log(await pa.models.list());
```

## The fast path: `from_env()`

`from_env()` reads two environment variables and builds the client for you:

- `PARETA_API_KEY` — your `pareta_sk_…` key (required)
- `PARETA_BASE_URL` — optional environment override (defaults to production)

```bash
export PARETA_API_KEY="pareta_sk_live_…"
```

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();
```

`from_env()` forwards any extra keyword arguments straight to the constructor, so you can keep the key in the environment while overriding everything else in code:

**Python**

```python
pa = Pareta.from_env(max_retries=5, timeout=120.0)
```

**TypeScript**

```typescript
// timeout is milliseconds in TS (120 seconds → 120_000).
const pa = Pareta.fromEnv({ maxRetries: 5, timeout: 120_000 });
```

There is no separate async client in TypeScript — there is one `Pareta` class and every I/O method returns a `Promise` you `await`:

**Python**

```python
from pareta import AsyncPareta

pa = AsyncPareta.from_env()
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

// Same client; await the calls (e.g. await pa.models.list()).
const pa = Pareta.fromEnv();
```

Prefer `from_env()` over hardcoding keys. It keeps `pareta_sk_…` secrets out of source control and lets the same code run against staging or production by flipping one environment variable.

## Constructor parameters

Both clients take the same arguments:

**Python**

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

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = new Pareta({
  apiKey: "pareta_sk_live_…",
  baseURL: "https://api.pareta.ai",
  timeout: 60_000, // milliseconds
  maxRetries: 2,
  // fetch: customFetch, // bring your own fetch instead of http_client
});
```

| Parameter | Type | Default | What it does |
|-----------|------|---------|--------------|
| `api_key` | `str \| None` | `None` | Your `pareta_sk_…` key. Sent as a Bearer token. Required. |
| `base_url` | `str \| None` | `"https://api.pareta.ai"` | API root. Use the staging URL to point at the staging environment. |
| `timeout` | `httpx.Timeout \| float \| None` | `httpx.Timeout(60.0, connect=10.0)` | Per-request timeout. |
| `max_retries` | `int` | `2` | Automatic retries on transient failures. |
| `http_client` | `httpx.Client \| httpx.AsyncClient \| None` | `None` | Bring your own httpx client (proxies, custom transports, connection pools). |

`AsyncPareta` is identical except `http_client` takes an `httpx.AsyncClient`.

## `api_key`

The key is the one required piece of configuration. Pass it explicitly or via `PARETA_API_KEY`; the SDK sends it as `Authorization: Bearer <key>` on every request.

**Python**

```python
from pareta import Pareta

pa = Pareta(api_key="pareta_sk_live_…")
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = new Pareta({ apiKey: "pareta_sk_live_…" });
```

If the key is missing or empty (and the env var is unset when using `from_env()`), the constructor raises `ParetaError` before any network call:

**Python**

```python
from pareta import Pareta, ParetaError

try:
    pa = Pareta(api_key="")
except ParetaError as e:
    print(e)
    # missing API key. Pass api_key=… or set PARETA_API_KEY
    # (mint a pareta_sk_ key in the dashboard).
```

**TypeScript**

```typescript
import { Pareta, ParetaError } from "pareta";

try {
  const pa = new Pareta({ apiKey: "" });
} catch (e) {
  if (e instanceof ParetaError) {
    console.log(e.message);
    // missing API key. Pass apiKey: … or use Pareta.fromEnv() with PARETA_API_KEY
    // (mint a pareta_sk_ key in the dashboard).
  }
}
```

Mint keys in the dashboard. If the key is present but rejected by the server, you get a `401` as `AuthenticationError` on the first request, not at construction time. See [Errors](errors-and-retries.md) for the full exception hierarchy.

## `base_url` (production vs staging)

`base_url` selects the environment. It defaults to production and is normalized with a trailing-slash strip, so `https://api.pareta.ai/` and `https://api.pareta.ai` behave identically.

| Environment | `base_url` |
|-------------|------------|
| Production (default) | `https://api.pareta.ai` |
| Staging | `https://api-staging.pareta.ai` |

**Python**

```python
from pareta import Pareta

# Production — base_url omitted, defaults applied.
prod = Pareta(api_key="pareta_sk_live_…")

# Staging — pass it explicitly, or set PARETA_BASE_URL.
staging = Pareta(
    api_key="pareta_sk_test_…",
    base_url="https://api-staging.pareta.ai",
)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

// Production — baseURL omitted, defaults applied.
const prod = new Pareta({ apiKey: "pareta_sk_live_…" });

// Staging — pass it explicitly, or set PARETA_BASE_URL.
const staging = new Pareta({
  apiKey: "pareta_sk_test_…",
  baseURL: "https://api-staging.pareta.ai",
});
```

Via the environment, no code change needed:

```bash
export PARETA_API_KEY="pareta_sk_test_…"
export PARETA_BASE_URL="https://api-staging.pareta.ai"
```

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()   # now talks to staging
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv(); // now talks to staging
```

Keys are environment-scoped: a production key will not authenticate against staging and vice versa. Pair each `base_url` with a key minted for that environment.

## `timeout`

`timeout` caps how long a single request may take. The default is `httpx.Timeout(60.0, connect=10.0)`: up to 10 seconds to establish the connection and 60 seconds overall. A bare float sets the overall timeout for read, write, and connect alike.

**Python**

```python
import httpx
from pareta import Pareta

# Simple: one number for everything.
pa = Pareta(api_key="pareta_sk_live_…", timeout=120.0)

# Granular: long read budget for big generations, short connect budget.
pa = Pareta(
    api_key="pareta_sk_live_…",
    timeout=httpx.Timeout(120.0, connect=10.0),
)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

// One overall budget, in milliseconds (no separate connect budget in TS).
const pa = new Pareta({ apiKey: "pareta_sk_live_…", timeout: 120_000 });
```

When to raise it:

- **Long completions.** A 4096-token generation can run well past 60 seconds. Either raise `timeout` or stream the response so tokens arrive incrementally (see [Inference](inference.md)).
- **Long eval runs.** `evals.runs.create(..., wait=True)` does its own polling and has a separate `timeout` argument (default `900.0` seconds) that governs the wait loop, independent of the per-request HTTP timeout. See [Evals](evaluation.md).

A request that exceeds the timeout raises `APITimeoutError` (a subclass of `APIConnectionError`) after retries are exhausted.

## `max_retries`

The SDK automatically retries transient failures. The default is `2` (so up to 3 attempts total). Values below zero are clamped to `0`.

Retries fire only on these status codes:

```
408  Request Timeout
409  Conflict (transient lock/contention)
429  Too Many Requests
500  Internal Server Error
502  Bad Gateway
503  Service Unavailable
504  Gateway Timeout
```

Backoff is exponential with jitter, capped at 8 seconds: `min(0.5 * 2 ** attempt, 8.0)` plus a small random jitter. When the server sends a `Retry-After` header, the SDK honors it (capped at 30 seconds) instead of computing its own delay.

**Python**

```python
from pareta import Pareta

# More patient: handy for batch jobs against a busy environment.
pa = Pareta(api_key="pareta_sk_live_…", max_retries=5)

# Disable retries entirely: every failure surfaces immediately.
pa = Pareta(api_key="pareta_sk_live_…", max_retries=0)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

// More patient: handy for batch jobs against a busy environment.
const patient = new Pareta({ apiKey: "pareta_sk_live_…", maxRetries: 5 });

// Disable retries entirely: every failure surfaces immediately.
const failFast = new Pareta({ apiKey: "pareta_sk_live_…", maxRetries: 0 });
```

What is *not* retried:

- **4xx errors other than 408/409/429** — these are your request, not a transient blip. A `402 InsufficientCreditsError`, `401 AuthenticationError`, or `404 NotFoundError` raises on the first attempt.
- **Connection errors on initial connect** (DNS, TCP, TLS refusal) — raised after the retry budget for the handshake is spent.
- **Mid-stream drops.** Streaming calls (`chat.completions.create(stream=True)`, `endpoints.deploy()`) retry only the initial handshake. Once SSE bytes are flowing, a drop raises immediately, because a partial stream cannot be safely resumed.

A `409` is worth a note: it is in the retry set because some backends use it for transient lock contention. Pareta's own stable `409` (for example, a seed or legacy endpoint) simply exhausts the retries and then raises `ConflictError`, so you see the right error either way. See [Errors](errors-and-retries.md).

## `http_client` (bring your own httpx)

By default the client constructs its own httpx client, configured with your `timeout`, and closes it for you. Pass `http_client=` when you need control over the transport layer: an outbound proxy, a custom transport, mTLS, shared connection pools, or test doubles.

**Python**

```python
import httpx
from pareta import Pareta

# Route through a corporate proxy with a tuned connection pool.
my_client = httpx.Client(
    proxy="http://proxy.internal:8080",
    limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
    timeout=httpx.Timeout(120.0, connect=10.0),
)

pa = Pareta(api_key="pareta_sk_live_…", http_client=my_client)
```

The TS SDK has no owned HTTP client — it uses the global `fetch`. To control the transport (proxy, custom pool, mTLS, test doubles), inject your own `fetch` implementation via `fetch:`. In Node, a proxy/pool is configured on an undici `Agent` and threaded through a wrapper fetch:

**TypeScript**

```typescript
import { Pareta } from "pareta";
import { ProxyAgent } from "undici";

// Route through a corporate proxy with a tuned connection pool.
const agent = new ProxyAgent({
  uri: "http://proxy.internal:8080",
  connections: 50, // pool size
});

const myFetch: typeof fetch = (input, init) =>
  fetch(input, { ...init, dispatcher: agent } as RequestInit);

const pa = new Pareta({ apiKey: "pareta_sk_live_…", fetch: myFetch });
```

There is a single client, so there is no separate async variant to configure — the same injected `fetch` serves every awaited call.

**Ownership matters.** When you inject a client, you own its lifecycle. `pa.close()` (or `await pa.aclose()`) will *not* close a client you passed in. Close it yourself:

**Python**

```python
my_client.close()           # you opened it, you close it
```

**TypeScript**

```typescript
await agent.close(); // you opened it, you close it
```

The TS SDK owns no connection pool of its own, so there is nothing on the client to close — only your injected transport (if any). The Python context-manager forms below rely on the SDK-owned client.

One caveat: an injected client carries its own timeout configuration. The constructor's `timeout` argument is applied to the SDK-owned client only, so set the timeout on your own client when you bring one.

## Lifecycle and cleanup

Each client owns an HTTP connection pool. Release it when you are done.

### Sync

Use the context manager so cleanup happens automatically:

**Python**

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    completion = pa.chat.completions.create(
        model="ep_contract_kie_qwen",
        messages=[{"role": "user", "content": "Extract the parties."}],
    )
    print(completion.choices[0].message.content)
# HTTP client closed on exit
```

The TS client owns no connection pool, so there is no context manager and nothing to close — just construct it and `await` your calls:

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();
const completion = await pa.chat.completions.create({
  model: "ep_contract_kie_qwen",
  messages: [{ role: "user", content: "Extract the parties." }],
});
console.log(completion.choices[0].message.content);
```

Or close it explicitly:

**Python**

```python
pa = Pareta.from_env()
try:
    pa.models.list()
finally:
    pa.close()
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

// No close() — the client holds no pool of its own.
const pa = Pareta.fromEnv();
await pa.models.list();
```

### Async

**Python**

```python
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        models = await pa.models.list()
        print(models)
    # HTTP client closed on exit
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

// One client; every call is already async. No async variant, no aclose().
const pa = Pareta.fromEnv();
const models = await pa.models.list();
console.log(models);
```

Or close it explicitly with `await pa.aclose()`.

Remember the ownership rule: if you passed `http_client=`, neither `close()` nor exiting the context manager touches it. Close your own client.

## Platform truths worth knowing

These hold no matter how you configure the client. They are why there is no GPU knob, no balance API, and no per-environment model catalog to wire up.

- **GPUs are hidden.** You configure a key, a URL, timeouts, and retries — never hardware. `endpoints.deploy(task=…, model=…)` takes a task and a model alias; Pareta resolves the GPU, tensor-parallelism, and quantization from its registry. There is no hardware parameter anywhere in the SDK. See [Deploy endpoints](deploying-endpoints.md).
- **Models are per-task aliases.** Every model id you see or pass — in `deploy(model=…)`, on leaderboard rows, in `run.results[].model_id`, in `endpoints.list()[].model` — is a per-task public alias like `qwen-vl-2`. Real internal ids never cross into the SDK. See [Tasks and the catalog](discovery.md).
- **Inference and evals are metered against your org balance.** A successful `chat.completions.create()` debits your balance; `evals.runs.create()` debits for both open and frontier compute. `run.cost` reports the billed total as a `Decimal` in dollars (floored to whole cents), and `run.cost_micro_usd` the raw micro-USD. When the balance hits zero, both paths raise `InsufficientCreditsError` (402). Top-up is browser-only — the SDK exposes neither balance nor payment methods, by design. See [Evals](evaluation.md).
- **Inference is OpenAI-compatible.** `base_url` plus your `pareta_sk_…` key is a drop-in OpenAI endpoint. You can point the `openai` SDK at the same `base_url` to call a deployed endpoint; Pareta's SDK adds the control plane (deploy, eval, discovery) that `openai` cannot do. See [Inference](inference.md).

## Configuration cookbook

A few complete, runnable setups.

**Production, defaults, env-driven** — the recommended baseline:

**Python**

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    print(pa.models.list())
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();
console.log(await pa.models.list());
```

**Staging, patient retries, long timeout** — for a batch job against a busy environment:

**Python**

```python
import httpx
from pareta import Pareta

pa = Pareta(
    api_key="pareta_sk_test_…",
    base_url="https://api-staging.pareta.ai",
    timeout=httpx.Timeout(180.0, connect=10.0),
    max_retries=5,
)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = new Pareta({
  apiKey: "pareta_sk_test_…",
  baseURL: "https://api-staging.pareta.ai",
  timeout: 180_000, // milliseconds
  maxRetries: 5,
});
```

**Fail fast** — no retries, surface every error on the first attempt (good for tests):

**Python**

```python
from pareta import Pareta

pa = Pareta(api_key="pareta_sk_test_…", max_retries=0)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = new Pareta({ apiKey: "pareta_sk_test_…", maxRetries: 0 });
```

**Async, custom transport** — own the httpx client, own the cleanup:

**Python**

```python
import asyncio
import httpx
from pareta import AsyncPareta

async def main():
    client = httpx.AsyncClient(proxy="http://proxy.internal:8080")
    pa = AsyncPareta.from_env(http_client=client)
    try:
        print(await pa.models.list())
    finally:
        await client.aclose()   # you opened it, you close it

asyncio.run(main())
```

**TypeScript**

```typescript
import { Pareta } from "pareta";
import { ProxyAgent } from "undici";

const agent = new ProxyAgent({ uri: "http://proxy.internal:8080" });
const fetchViaProxy: typeof fetch = (input, init) =>
  fetch(input, { ...init, dispatcher: agent } as RequestInit);

const pa = Pareta.fromEnv({ fetch: fetchViaProxy });
try {
  console.log(await pa.models.list());
} finally {
  await agent.close(); // you opened it, you close it
}
```

## See also

- [Inference](inference.md) — OpenAI-compatible chat completions, streaming, and metering.
- [Deploy endpoints](deploying-endpoints.md) — deploy a model to a task and operate it.
- [Tasks and the catalog](discovery.md) — discover tasks, match intent, read leaderboards.
- [Evals](evaluation.md) — score models on your own data, including `run.cost`.
- [Errors](errors-and-retries.md) — the full exception hierarchy and how retries interact with it.
