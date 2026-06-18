# `endpoints`

`client.endpoints` is the control plane for serving open-weights models. Hand it a task and a model; it deploys an OpenAI-compatible inference endpoint, hands you back a live `Endpoint`, and lets you start, stop, delete, and measure it from code. There is no infrastructure to reason about.

Three platform truths shape this whole namespace:

- **GPUs are hidden.** `deploy()` takes a task and a model, nothing else. There is no GPU, tensor-parallel, quantization, or run-mode knob. Pareta resolves the serving class from its registry.
- **Models are per-task aliases.** The `model` you deploy and the `Endpoint.model` you read back are public per-task aliases (`{family}-{rank}`), not raw open-weights ids. Real ids never cross into the SDK.
- **Inference is metered against your org balance.** Once an endpoint is live, every [`chat.completions.create()`](chat.md) debits your org balance and raises `InsufficientCreditsError` (402) on an empty balance. Top-up is browser-only; the SDK never exposes balance or payment methods.

```python
from pareta import Pareta

pa = Pareta.from_env()   # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
```

## `deploy()`

```python
endpoints.deploy(
    *,
    task: str,
    model: str = "recommended",
    name: str | None = None,
    wait: bool = False,
    **extra,
) -> Iterator[dict] | Endpoint
```

**Route:** `POST /v1/endpoints` (named-event SSE)

Deploys a model for a task and brings the endpoint live.

- `task` (required) is a catalog subtask id, e.g. `"contract-key-fields"`. Discover one with [`tasks.match()` / `tasks.list()`](tasks.md). Passing an empty `task` raises `ValueError` before any request goes out.
- `model` is a per-task public alias, an explicit real-id-equivalent alias, or `"recommended"` (the default — the task's curated pick, else the leaderboard's top open model). To see what `"recommended"` resolves to before you deploy, read [`pa.tasks.recommended(task)`](tasks.md).
- `name` is optional. Leave it off and Pareta names the endpoint for you.
- `wait` controls the return type (see below).
- `**extra` is passed straight to the backend (e.g. `cost_per_request_micro_usd`, `frontier_cost_per_request_micro_usd`, `region`, `provider`, `quality`, `run_mode`, `taskDisplay`). You never pass hardware.

The return type depends entirely on `wait`.

### `wait=True` — block and get the live `Endpoint`

The simplest path. `deploy(wait=True)` consumes the deploy stream internally, blocks until the endpoint is live, and returns the `Endpoint`. If the deploy emits an `"error"` event (or the stream ends without a `"complete"` event), it raises `ParetaError`.

```python
ep = pa.endpoints.deploy(
    task="contract-key-fields",
    model="recommended",   # Pareta picks the task's best open model
    wait=True,
)

assert ep.is_live              # status == "live"
print(ep.id)                   # pass this to chat.completions.create(model=…)
print(ep.model)                # per-task public alias that got deployed
print(ep.url)                  # OpenAI-compatible inference URL

# Use it immediately — metered against your org balance.
resp = pa.chat.completions.create(
    model=ep.id,
    messages=[{"role": "user", "content": "Extract the parties and effective date."}],
)
print(resp.choices[0].message.content)
```

### `wait=False` — stream deploy progress (default)

With `wait=False` (the default), `deploy()` returns an iterator of named progress events so you can render a deploy UI or log stages. Each event is a `{"event": str, "data": dict}` dict.

```python
endpoint = None
for ev in pa.endpoints.deploy(task="contract-key-fields"):
    if ev["event"] == "progress":
        # data carries the deploy stage status, e.g. {"stage": "pulling weights", "pct": 45}
        print("progress:", ev["data"])
    elif ev["event"] == "complete":
        endpoint = ev["data"]["endpoint"]   # the live endpoint payload (dict)
        print("live:", endpoint)
    elif ev["event"] == "error":
        # wait=True raises ParetaError for you; with wait=False you handle it.
        raise RuntimeError(ev["data"].get("message", "deploy failed"))
```

The terminal event is `"complete"` (its `data.endpoint` is the live endpoint) or `"error"`. Pick `wait=True` for scripts and notebooks; pick `wait=False` only when you want to surface live progress.

## `list()`

```python
endpoints.list() -> list[Endpoint]
```

**Route:** `GET /v1/endpoints`

Returns every endpoint your org can access, in any status.

```python
for ep in pa.endpoints.list():
    print(ep.id, ep.status, ep.task, ep.model)
```

For the OpenAI-compatible subset — only deployed, url-bearing endpoints, shaped as `Model` objects — use [`pa.models.list()`](models.md) instead.

## `retrieve()`

```python
endpoints.retrieve(endpoint_id: str) -> Endpoint
```

**Route:** `GET /v1/endpoints/{endpoint_id}`

Fetches one endpoint by id. Raises `NotFoundError` (404) for an unknown id.

```python
ep = pa.endpoints.retrieve("ep_a1b2c3")
print(ep.is_live, ep.url)
```

## `start()` / `stop()`

```python
endpoints.start(endpoint_id: str)   # POST /v1/endpoints/{id}/start
endpoints.stop(endpoint_id: str)    # POST /v1/endpoints/{id}/stop
```

A stopped endpoint costs nothing to keep but cannot serve. `stop()` pauses spend; `start()` resumes a stopped endpoint.

```python
pa.endpoints.stop("ep_a1b2c3")      # pause a live endpoint
pa.endpoints.start("ep_a1b2c3")     # resume a stopped one
```

While an endpoint is stopped or still cold, inference calls against it raise `EndpointNotReadyError` (503). After `start()`, poll `retrieve(id).is_live` before sending traffic.

```python
import time

pa.endpoints.start("ep_a1b2c3")
while not pa.endpoints.retrieve("ep_a1b2c3").is_live:
    time.sleep(3)
```

## `delete()`

```python
endpoints.delete(endpoint_id: str) -> None
```

**Route:** `DELETE /v1/endpoints/{endpoint_id}`

Removes an endpoint for good. Returns `None`.

```python
pa.endpoints.delete("ep_a1b2c3")
```

## `metrics()`

```python
endpoints.metrics(endpoint_id: str) -> Metrics
```

Returns a `Metrics` handle for querying one endpoint's observability dimensions. This call does not hit the network — each dimension method does.

```python
class Metrics:
    def performance(self, **params) -> dict   # GET /v1/endpoints/{id}/performance
    def uptime(self, **params) -> dict         # GET /v1/endpoints/{id}/uptime
    def cost(self, **params) -> dict           # GET /v1/endpoints/{id}/cost
    def quality(self, **params) -> dict        # GET /v1/endpoints/{id}/quality
    def activity(self, **params) -> dict       # GET /v1/endpoints/{id}/activity
```

Each method returns raw metric JSON (shapes vary by dimension; typed models arrive with the OpenAPI generation) and accepts arbitrary query params as keyword arguments, passed straight through to the query string.

```python
m = pa.endpoints.metrics("ep_a1b2c3")

m.performance()   # p50/p95/p99 latency
m.uptime()        # availability
m.cost()          # per-endpoint spend + vs-frontier savings
m.quality()       # judge windows
m.activity()      # usage stats

# Params pass through to the query string:
m.performance(window="24h")
m.cost(group_by="day")
```

| Method | Returns |
|---|---|
| `performance(**params)` | p50/p95/p99 latency |
| `uptime(**params)` | availability metrics |
| `cost(**params)` | per-endpoint spend and savings versus the frontier baseline |
| `quality(**params)` | judge-window quality scores |
| `activity(**params)` | usage stats |

`metrics(id).cost()` is per-endpoint **observability** — it reports what this endpoint spent and how much you saved against a frontier vendor. It is not your account balance. Balance and top-up live in the dashboard only.

## The `Endpoint` object

Returned by `deploy(wait=True)`, `retrieve()`, and each element of `list()`.

| Field | Type | Meaning |
|---|---|---|
| `id` | `str \| None` | Endpoint id (== name) — pass as [`chat.completions.create(model=…)`](chat.md) |
| `name` | `str \| None` | Display name |
| `model` | `str \| None` | Per-task public alias serving here |
| `status` | `str \| None` | `"live"`, `"starting"`, `"stopped"`, … |
| `task` | `str \| None` | Task name |
| `url` | `str \| None` | OpenAI-compatible inference URL |
| `is_live` | `bool` | `status == "live"` |

Every `Endpoint` keeps the full server record on `to_dict()`, so nothing the API returns is lost behind the typed fields.

## End to end

Discover a task, deploy its recommended model, serve traffic, check cost, then tear down.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    # 1. Find a task for your intent.
    match = pa.tasks.match("pull key fields out of contracts")
    task_id = match.chosen.task_id          # e.g. "contract-key-fields"

    # 2. Deploy the recommended open model (no GPU knob).
    ep = pa.endpoints.deploy(task=task_id, model="recommended", wait=True)
    print(f"live: {ep.id} serving {ep.model}")

    # 3. Run metered inference (debits the org balance).
    resp = pa.chat.completions.create(
        model=ep.id,
        messages=[{"role": "user", "content": "Extract the governing-law clause."}],
    )
    print(resp.choices[0].message.content)

    # 4. Check what it cost and how it performed.
    print(pa.endpoints.metrics(ep.id).cost())

    # 5. Stop it to pause spend (or delete it to remove it).
    pa.endpoints.stop(ep.id)
```

## Async

`AsyncPareta` mirrors the sync surface. `deploy()`, `list()`, `retrieve()`, `start()`, `stop()`, and `delete()` are `async def`. `metrics(id)` returns an `AsyncMetrics` handle synchronously (it is not a coroutine), and its dimension methods are awaitable.

```python
from pareta import AsyncPareta

async with AsyncPareta.from_env() as pa:
    # wait=True awaits the deploy and returns the live Endpoint.
    ep = await pa.endpoints.deploy(task="contract-key-fields", wait=True)

    # wait=False returns an async progress-event iterator.
    async for ev in await pa.endpoints.deploy(task="contract-key-fields"):
        if ev["event"] == "complete":
            print("live:", ev["data"]["endpoint"])

    m = pa.endpoints.metrics(ep.id)         # NOT awaited — returns the handle
    print(await m.performance())            # the dimension call IS awaited

    await pa.endpoints.stop(ep.id)
```

## Errors

| Exception | Status | When |
|---|---|---|
| `BadRequestError` | 400 / 422 | Unknown task, malformed deploy params |
| `InsufficientCreditsError` | 402 | Org balance empty when you run inference against the endpoint |
| `NotFoundError` | 404 | Unknown `endpoint_id` |
| `ConflictError` | 409 | Seed/legacy endpoint conflict, or transient contention |
| `EndpointNotReadyError` | 503 | Endpoint stopped, cold-starting, or provider down |
| `ParetaError` | — | A deploy stream emitted an `"error"` event, or ended without `"complete"` |

`deploy(task="")` raises `ValueError` before any request leaves the process.

## Related

- [`tasks`](tasks.md) — find a `task` id and read its recommended model before you deploy.
- [`chat`](chat.md) — call `chat.completions.create()` against a deployed endpoint id.
- [`models`](models.md) — list the OpenAI-compatible subset of deployed endpoints.
- [`evals`](evals.md) — pick the right open model for a task before you deploy it.
- [Deploying & operating endpoints](../guide/deploying-endpoints.md) — the narrative guide.
- [Errors & retries](../guide/errors-and-retries.md) — the exception hierarchy and retry policy.
