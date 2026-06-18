# Deploying & operating endpoints

`client.endpoints` is the control plane for serving open-weights models. You
hand it a task and a model; it deploys an OpenAI-compatible inference endpoint,
hands you back a live `Endpoint`, and lets you start, stop, delete, and measure
it from code. No infrastructure to reason about.

Three platform truths shape this whole page:

- **GPUs are hidden.** `deploy()` takes a task and a model, nothing else. There
  is no GPU, tensor-parallel, or quantization knob. Pareta resolves the serving
  class from its registry.
- **Models are per-task aliases.** The `model` you deploy and the `Endpoint.model`
  you read back are public per-task aliases (`{family}-{rank}`), not raw
  open-weights ids. Real ids never cross into the SDK.
- **Inference is metered against your org balance.** Once an endpoint is live,
  every `chat.completions.create()` debits your org balance and raises
  [`InsufficientCreditsError`](errors-and-retries.md) (402) on an empty balance.
  Top-up is browser-only.

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()   # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();   // reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
```

## Deploy an endpoint

**Python**

```python
ep = pa.endpoints.deploy(
    task="contract-key-fields",
    model="recommended",   # default — Pareta picks the task's best open model
    wait=True,
)
print(ep.id, ep.status, ep.url)   # e.g. "ep_a1b2c3 live https://…"
```

**TypeScript**

```typescript
const ep = await pa.endpoints.deploy({
  task: "contract-key-fields",
  model: "recommended",   // default — Pareta picks the task's best open model
  wait: true,
});
console.log(ep.id, ep.status, ep.url);   // e.g. "ep_a1b2c3 live https://…"
```

Signature:

**Python**

```python
endpoints.deploy(
    *,
    task: str,                 # required: a subtask id, e.g. "contract-key-fields"
    model: str = "recommended",
    name: str | None = None,   # auto-generated if omitted
    wait: bool = False,
    **extra,                   # passed through to the backend
) -> Iterator[dict] | Endpoint
```

**TypeScript**

```typescript
endpoints.deploy(params: {
  task: string;              // required: a subtask id, e.g. "contract-key-fields"
  model?: string;            // defaults to "recommended"
  name?: string;             // auto-generated if omitted
  wait?: boolean;            // defaults to false
  [key: string]: unknown;    // passed through to the backend
}): AsyncIterable<{ event: string; data: unknown }> | Promise<Endpoint>
```

- `task` (required) is a catalog subtask id. Discover one with
  [`tasks.match()` / `tasks.list()`](discovery.md).
- `model` is a per-task public alias, an explicit real-id-equivalent alias, or
  `"recommended"` (the default — the task's curated pick, else the
  leaderboard's top open model). To see what `"recommended"` resolves to before
  you deploy, read `pa.tasks.recommended(task)`.
- `name` is optional. Leave it off and Pareta names the endpoint for you.
- The return type depends entirely on `wait`. See the next two sections.

You never pass hardware. Pareta resolves the GPU and serving config for the
chosen model.

### `wait=True` — block and get the live `Endpoint`

The simplest path. `deploy(wait=True)` consumes the deploy stream internally,
blocks until the endpoint is live, and returns the `Endpoint`. If the deploy
fails, it raises `ParetaError`.

**Python**

```python
ep = pa.endpoints.deploy(task="contract-key-fields", wait=True)

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

**TypeScript**

```typescript
const ep = await pa.endpoints.deploy({ task: "contract-key-fields", wait: true });

console.assert(ep.isLive);       // status == "live"
console.log(ep.id);              // pass this to chat.completions.create({ model })
console.log(ep.model);           // per-task public alias that got deployed
console.log(ep.url);             // OpenAI-compatible inference URL

// Use it immediately — metered against your org balance.
const resp = await pa.chat.completions.create({
  model: ep.id,
  messages: [{ role: "user", content: "Extract the parties and effective date." }],
});
console.log(resp.choices[0].message.content);
```

### `wait=False` — stream deploy progress (default)

With `wait=False` (the default), `deploy()` returns an iterator of named
progress events so you can render a deploy UI or log stages. Each event is a
`{"event": str, "data": dict}` dict.

**Python**

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
        # The SDK raises ParetaError for you on wait=True; here you handle it.
        raise RuntimeError(ev["data"].get("message", "deploy failed"))
```

**TypeScript**

```typescript
let endpoint = null;
for await (const ev of pa.endpoints.deploy({ task: "contract-key-fields" })) {
  if (ev.event === "progress") {
    // data carries the deploy stage status, e.g. { stage: "pulling weights", pct: 45 }
    console.log("progress:", ev.data);
  } else if (ev.event === "complete") {
    endpoint = ev.data.endpoint;   // the live endpoint payload (object)
    console.log("live:", endpoint);
  } else if (ev.event === "error") {
    // The SDK throws ParetaError for you on wait: true; here you handle it.
    throw new Error(ev.data?.message ?? "deploy failed");
  }
}
```

The terminal event is `"complete"` (its `data.endpoint` is the live endpoint)
or `"error"`. The stream always ends on one of them; if it ends without a
`"complete"`, the SDK raises `ParetaError`.

Pick `wait=True` for scripts and notebooks; pick `wait=False` only when you
want to surface live progress.

## List, retrieve, and address endpoints

**Python**

```python
# Every endpoint your org can access.
for ep in pa.endpoints.list():
    print(ep.id, ep.status, ep.task, ep.model)

# One endpoint by id.
ep = pa.endpoints.retrieve("ep_a1b2c3")
print(ep.is_live, ep.url)
```

**TypeScript**

```typescript
// Every endpoint your org can access.
for (const ep of await pa.endpoints.list()) {
  console.log(ep.id, ep.status, ep.task, ep.model);
}

// One endpoint by id.
const ep = await pa.endpoints.retrieve("ep_a1b2c3");
console.log(ep.isLive, ep.url);
```

`Endpoint` fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | `str \| None` | Endpoint id — pass as `chat.completions.create(model=…)` |
| `name` | `str \| None` | Display name |
| `model` | `str \| None` | Per-task public alias serving here |
| `status` | `str \| None` | `"live"`, `"starting"`, `"stopped"`, … |
| `task` | `str \| None` | Task name |
| `url` | `str \| None` | OpenAI-compatible inference URL |
| `is_live` | `bool` | `status == "live"` |

`endpoints.list()` returns every endpoint the org can access. For the
OpenAI-compatible subset (only deployed, url-bearing endpoints, shaped as
`Model` objects), use [`pa.models.list()`](inference.md) instead.

## Start, stop, and delete

A stopped endpoint costs nothing to keep but cannot serve. Stop it to pause
spend, start it to resume, delete it to remove it for good.

**Python**

```python
pa.endpoints.stop("ep_a1b2c3")      # pause a live endpoint
pa.endpoints.start("ep_a1b2c3")     # resume a stopped one
pa.endpoints.delete("ep_a1b2c3")    # remove it (returns None)
```

**TypeScript**

```typescript
await pa.endpoints.stop("ep_a1b2c3");      // pause a live endpoint
await pa.endpoints.start("ep_a1b2c3");     // resume a stopped one
await pa.endpoints.delete("ep_a1b2c3");    // remove it (returns void)
```

While an endpoint is stopped or still cold, inference calls against it raise
[`EndpointNotReadyError`](errors-and-retries.md) (503). Call `start()` and wait
for `retrieve(id).is_live` before sending traffic.

**Python**

```python
pa.endpoints.start("ep_a1b2c3")
while not pa.endpoints.retrieve("ep_a1b2c3").is_live:
    time.sleep(3)
```

**TypeScript**

```typescript
await pa.endpoints.start("ep_a1b2c3");
while (!(await pa.endpoints.retrieve("ep_a1b2c3")).isLive) {
  await new Promise((resolve) => setTimeout(resolve, 3000));
}
```

## Measure an endpoint

`endpoints.metrics(id)` returns a `Metrics` handle with one method per
observability dimension. Each returns raw metric JSON (typed models are coming
in a later slice) and accepts arbitrary query params as keyword arguments.

**Python**

```python
m = pa.endpoints.metrics("ep_a1b2c3")

m.performance()   # p50/p95/p99 latency
m.uptime()        # availability
m.cost()          # per-endpoint spend + vs-frontier savings
m.quality()       # judge windows
m.activity()      # usage stats

# Params pass straight through to the query string:
m.performance(window="24h")
m.cost(group_by="day")
```

**TypeScript**

```typescript
const m = pa.endpoints.metrics("ep_a1b2c3");   // handle is NOT awaited

await m.performance();   // p50/p95/p99 latency
await m.uptime();        // availability
await m.cost();          // per-endpoint spend + vs-frontier savings
await m.quality();       // judge windows
await m.activity();      // usage stats

// Params pass straight through to the query string:
await m.performance({ window: "24h" });
await m.cost({ group_by: "day" });
```

| Method | Returns |
|---|---|
| `performance(**params)` | p50/p95/p99 latency |
| `uptime(**params)` | availability metrics |
| `cost(**params)` | per-endpoint spend and savings versus the frontier baseline |
| `quality(**params)` | judge-window quality scores |
| `activity(**params)` | usage stats |

`metrics(id).cost()` is per-endpoint **observability** — it tells you what this
endpoint spent and how much you saved against a frontier vendor. It is not your
account balance. Balance and top-up live in the dashboard only.

## End to end

Discover a task, deploy its recommended model, serve traffic, then tear down.

**Python**

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

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

// 1. Find a task for your intent.
const match = await pa.tasks.match("pull key fields out of contracts");
const taskId = match.chosen?.taskId;          // e.g. "contract-key-fields"

// 2. Deploy the recommended open model (no GPU knob).
const ep = await pa.endpoints.deploy({ task: taskId, model: "recommended", wait: true });
console.log(`live: ${ep.id} serving ${ep.model}`);

// 3. Run metered inference (debits the org balance).
const resp = await pa.chat.completions.create({
  model: ep.id,
  messages: [{ role: "user", content: "Extract the governing-law clause." }],
});
console.log(resp.choices[0].message.content);

// 4. Check what it cost and how it performed.
console.log(await pa.endpoints.metrics(ep.id).cost());

// 5. Stop it to pause spend (or delete it to remove it).
await pa.endpoints.stop(ep.id);
```

## Async

`AsyncPareta` mirrors the sync surface. `deploy()`, `list()`, `retrieve()`,
`start()`, `stop()`, and `delete()` are `async def`. `metrics(id)` returns an
`AsyncMetrics` handle synchronously (it is not a coroutine), and its dimension
methods are awaitable.

**Python**

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

**TypeScript**

```typescript
// There is no AsyncPareta in TS — the one `Pareta` client is already
// Promise-based, so the sync/async split simply doesn't exist here.
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

// wait: true awaits the deploy and resolves the live Endpoint.
const ep = await pa.endpoints.deploy({ task: "contract-key-fields", wait: true });

// wait: false returns an async progress-event iterator.
for await (const ev of pa.endpoints.deploy({ task: "contract-key-fields" })) {
  if (ev.event === "complete") {
    console.log("live:", ev.data.endpoint);
  }
}

const m = pa.endpoints.metrics(ep.id);   // NOT awaited — returns the handle
console.log(await m.performance());      // the dimension call IS awaited

await pa.endpoints.stop(ep.id);
```

## Errors you will hit here

| Exception | Status | When |
|---|---|---|
| `BadRequestError` | 400 / 422 | Unknown task, malformed deploy params |
| `InsufficientCreditsError` | 402 | Org balance empty when you run inference against the endpoint |
| `NotFoundError` | 404 | Unknown `endpoint_id` |
| `ConflictError` | 409 | Seed/legacy endpoint conflict, or transient contention |
| `EndpointNotReadyError` | 503 | Endpoint stopped, cold-starting, or provider down |
| `ParetaError` | — | A deploy stream emitted an `"error"` event, or ended without `"complete"` |

`deploy(task="")` raises `ValueError` before any request goes out. See
[Errors & retries](errors-and-retries.md) for the full hierarchy and the
automatic retry policy.

## Related

- [Discovering tasks](discovery.md) — find a `task` id and inspect the recommended model.
- [Running inference](inference.md) — call `chat.completions.create()` against a deployed endpoint id.
- [Evaluating models](evaluation.md) — pick the right open model for a task before you deploy it.
- [Errors & retries](errors-and-retries.md) — the exception hierarchy and retry behavior.
