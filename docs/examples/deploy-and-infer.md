# Deploy a model and call it

This is the shortest path from "I have a task" to "I'm getting completions back": pick a task, deploy the recommended open-weights model for it, then call the live endpoint with OpenAI-compatible inference. Pareta picks the GPU and serving config for you, so deploy takes a task and a model alias and nothing about hardware.

The whole flow is two calls:

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()  # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)

# 1. Deploy the recommended model for a task and block until it is live.
endpoint = pa.endpoints.deploy(
    task="contract-key-fields",
    model="recommended",
    wait=True,
)

# 2. Call it. The endpoint id is what you pass as `model`.
resp = pa.chat.completions.create(
    model=endpoint.id,
    messages=[
        {"role": "user", "content": "Extract the parties and effective date from this clause: ..."},
    ],
)
print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv(); // reads PARETA_API_KEY (+ optional PARETA_BASE_URL)

// 1. Deploy the recommended model for a task and block until it is live.
const endpoint = await pa.endpoints.deploy({
  task: "contract-key-fields",
  model: "recommended",
  wait: true,
});

// 2. Call it. The endpoint id is what you pass as `model`.
const resp = await pa.chat.completions.create({
  model: endpoint.id,
  messages: [
    { role: "user", content: "Extract the parties and effective date from this clause: ..." },
  ],
});
console.log(resp.choices[0].message.content);
```

That is the entire happy path. The rest of this page unpacks each step and the platform facts you should know before you run it for real.

## Before you start

You need a `pareta_sk_` API key. Mint one in the dashboard (key management is browser-only) and either pass it as `api_key=` or set `PARETA_API_KEY`. `Pareta.from_env()` reads `PARETA_API_KEY` and the optional `PARETA_BASE_URL`; the base URL defaults to `https://api.pareta.ai`.

**Python**

```python
from pareta import Pareta

# Preferred: pull credentials from the environment.
pa = Pareta.from_env()

# Or pass them explicitly.
pa = Pareta(api_key="pareta_sk_...", base_url="https://api.pareta.ai")
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

// Preferred: pull credentials from the environment.
const pa = Pareta.fromEnv();

// Or pass them explicitly.
const pa = new Pareta({ apiKey: "pareta_sk_...", baseURL: "https://api.pareta.ai" });
```

The client is a context manager, which is the clean way to release the HTTP connection when you are done:

**Python**

```python
with Pareta.from_env() as pa:
    endpoint = pa.endpoints.deploy(task="contract-key-fields", wait=True)
    resp = pa.chat.completions.create(
        model=endpoint.id,
        messages=[{"role": "user", "content": "..."}],
    )
```

**TypeScript**

```typescript
// TS has no context manager / owned connection — fetch needs no teardown.
// One Promise-only client; just await each call.
const pa = Pareta.fromEnv();
const endpoint = await pa.endpoints.deploy({ task: "contract-key-fields", wait: true });
const resp = await pa.chat.completions.create({
  model: endpoint.id,
  messages: [{ role: "user", content: "..." }],
});
```

## Step 1: Deploy

**Python**

```python
endpoint = pa.endpoints.deploy(
    task="contract-key-fields",   # required: a subtask id from the catalog
    model="recommended",          # default; resolves to the task's curated pick
    wait=True,                    # block until the endpoint is live
)
```

**TypeScript**

```typescript
const endpoint = await pa.endpoints.deploy({
  task: "contract-key-fields", // required: a subtask id from the catalog
  model: "recommended",        // default; resolves to the task's curated pick
  wait: true,                  // block until the endpoint is live
});
```

`deploy()` takes a `task` and a `model`. There is no GPU, tensor-parallel, quantization, or run-mode knob. Pareta resolves the serving class from its registry, so you describe what you want to run, not the hardware to run it on.

A few things worth knowing:

- **`task` is required** and is a subtask id (for example `"contract-key-fields"`). Omitting it raises `ValueError`. Browse the catalog or turn free-text intent into a task id with the [tasks resource](../guide/discovery.md).
- **`model` defaults to `"recommended"`**, which resolves server-side to the task's curated pick (or the leaderboard's top open model). You can also pass a specific per-task model alias. To see what `"recommended"` will resolve to before you commit, call `pa.tasks.recommended(task_id)`.
- **`model` is always a per-task public alias**, never a raw open-weights model id. Real ids never cross into the SDK. The same is true of `endpoint.model` on the object you get back and of every model id in [evals](evaluate-on-your-data.md) and leaderboards.
- **`name` is optional.** Pareta auto-generates one if you do not pass it.

### wait=True versus the progress stream

With `wait=True` the call blocks through the deploy and returns the live `Endpoint`. If the deploy fails, it raises `ParetaError` with the backend's message.

If you want to surface progress (pulling weights, warming up, and so on), drop `wait` and iterate the event stream instead. Each event is a plain `{"event": str, "data": dict}` dict:

**Python**

```python
endpoint_id = None
for event in pa.endpoints.deploy(task="contract-key-fields", model="recommended"):
    if event["event"] == "progress":
        print("deploying:", event["data"])
    elif event["event"] == "complete":
        endpoint_id = event["data"]["endpoint"]["id"]
        print("live:", endpoint_id)
    elif event["event"] == "error":
        raise RuntimeError(event["data"].get("message"))
```

**TypeScript**

```typescript
let endpointId: string | null = null;
for await (const event of pa.endpoints.deploy({ task: "contract-key-fields", model: "recommended" })) {
  if (event.event === "progress") {
    console.log("deploying:", event.data);
  } else if (event.event === "complete") {
    endpointId = event.data.endpoint.id;
    console.log("live:", endpointId);
  } else if (event.event === "error") {
    throw new Error(event.data.message);
  }
}
```

`wait=True` consumes this exact stream for you and returns the `Endpoint` parsed from the `complete` event, so reach for the raw iterator only when you actually want to render progress.

### What you get back

The `Endpoint` object carries everything you need to call and operate the endpoint:

**Python**

```python
endpoint.id        # the id you pass as `model` to chat.completions.create
endpoint.name      # display name
endpoint.model     # per-task public alias that was deployed
endpoint.status    # "live", "starting", "stopped", ...
endpoint.task      # task name
endpoint.url       # raw inference URL (OpenAI-compatible)
endpoint.is_live   # True when status == "live"
endpoint.to_dict() # the full raw record, nothing dropped
```

**TypeScript**

```typescript
endpoint.id        // the id you pass as `model` to chat.completions.create
endpoint.name      // display name
endpoint.model     // per-task public alias that was deployed
endpoint.status    // "live", "starting", "stopped", ...
endpoint.task      // task name
endpoint.url       // raw inference URL (OpenAI-compatible)
endpoint.isLive    // true when status === "live"
endpoint.toDict()  // the full raw record, nothing dropped
```

Note that `endpoint.id` is the name, and that is the value `chat.completions.create(model=...)` expects, not `endpoint.model` (the alias). After a `wait=True` deploy `endpoint.is_live` is `True`.

## Step 2: Call the endpoint

Inference is OpenAI-compatible. Pass the endpoint id as `model` and a non-empty list of message dicts:

**Python**

```python
resp = pa.chat.completions.create(
    model=endpoint.id,
    messages=[
        {"role": "system", "content": "You extract structured fields from contracts."},
        {"role": "user", "content": "Extract the parties and effective date: ..."},
    ],
    temperature=0,   # extra OpenAI params pass straight through
    max_tokens=512,
)

choice = resp.choices[0]
print(choice.message.content)
print(choice.finish_reason)          # "stop", "length", ...
print(resp.usage.total_tokens)       # prompt_tokens + completion_tokens
```

**TypeScript**

```typescript
const resp = await pa.chat.completions.create({
  model: endpoint.id,
  messages: [
    { role: "system", content: "You extract structured fields from contracts." },
    { role: "user", content: "Extract the parties and effective date: ..." },
  ],
  temperature: 0,    // extra OpenAI params pass straight through
  max_tokens: 512,
});

const choice = resp.choices[0];
console.log(choice.message.content);
console.log(choice.finishReason);    // "stop", "length", ...
console.log(resp.usage.totalTokens); // prompt_tokens + completion_tokens
```

`model` and `messages` are both required; passing either falsy raises `ValueError` before any request goes out. Any extra OpenAI keyword arguments (`temperature`, `max_tokens`, `top_p`, and so on) pass through as body fields untouched.

### Streaming

Set `stream=True` to get an iterator of `ChatCompletionChunk` objects. The incremental text lives on `chunk.choices[0].delta.content`:

**Python**

```python
for chunk in pa.chat.completions.create(
    model=endpoint.id,
    messages=[{"role": "user", "content": "Summarize this clause: ..."}],
    stream=True,
):
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
```

**TypeScript**

```typescript
const stream = pa.chat.completions.create({
  model: endpoint.id,
  messages: [{ role: "user", content: "Summarize this clause: ..." }],
  stream: true,
});
for await (const chunk of stream) {
  const delta = chunk.choices[0].delta.content;
  if (delta) {
    process.stdout.write(delta);
  }
}
```

The stream ends on its own (the SDK consumes the terminal `[DONE]`). Retries cover only the initial connection; once tokens are flowing, a mid-stream drop raises immediately because it cannot be safely resumed.

### You do not strictly need this SDK to call the endpoint

Because inference is OpenAI-compatible, you can point the `openai` client at your Pareta base URL and key:

**Python**

```python
from openai import OpenAI

client = OpenAI(api_key="pareta_sk_...", base_url="https://api.pareta.ai/v1")
resp = client.chat.completions.create(model=endpoint.id, messages=[...])
```

**TypeScript**

```typescript
import OpenAI from "openai";

const client = new OpenAI({ apiKey: "pareta_sk_...", baseURL: "https://api.pareta.ai/v1" });
const resp = await client.chat.completions.create({ model: endpoint.id, messages: [...] });
```

The Pareta SDK's value is the control plane around inference: deploy, operate, discover, and eval. Use whichever inference client you like once an endpoint is live.

## Cost and billing

Both deploy-driven inference and evals are metered against your org balance.

- **Inference debits on success.** Each completed `chat.completions.create()` call debits your org balance.
- **A zero balance raises `InsufficientCreditsError` (402)** on both inference and eval paths. Catch it and tell the user to top up.
- **Top-up is browser-only.** The SDK consumes credit; it never exposes balance, payment methods, or top-up. There is no API call to add funds.

**Python**

```python
from pareta import InsufficientCreditsError

try:
    resp = pa.chat.completions.create(model=endpoint.id, messages=[...])
except InsufficientCreditsError:
    print("Org balance is empty. Top up in the dashboard, then retry.")
```

**TypeScript**

```typescript
import { InsufficientCreditsError } from "pareta";

try {
  const resp = await pa.chat.completions.create({ model: endpoint.id, messages: [...] });
} catch (e) {
  if (e instanceof InsufficientCreditsError) {
    console.log("Org balance is empty. Top up in the dashboard, then retry.");
  } else {
    throw e;
  }
}
```

When you run an [eval](evaluate-on-your-data.md), the resulting `EvalRun` reports spend in dollars on `run.cost` (a `Decimal`, floored to whole cents) with the raw value on `run.cost_micro_usd`. Inference cost is metered server-side rather than returned on the completion object.

## Errors worth catching

Every SDK error subclasses `ParetaError`. The ones you will hit most around this flow:

**Python**

```python
from pareta import (
    ParetaError,               # base class; also raised on a failed deploy
    AuthenticationError,       # 401 - bad or missing key
    InsufficientCreditsError,  # 402 - org out of credit; top up in the dashboard
    NotFoundError,             # 404 - unknown endpoint or task
    EndpointNotReadyError,     # 503 - endpoint stopped, cold, or provider down
    RateLimitError,            # 429 - throttled (auto-retried)
    BadRequestError,           # 400/422 - malformed request
)
```

**TypeScript**

```typescript
import {
  ParetaError,               // base class; also raised on a failed deploy
  AuthenticationError,       // 401 - bad or missing key
  InsufficientCreditsError,  // 402 - org out of credit; top up in the dashboard
  NotFoundError,             // 404 - unknown endpoint or task
  EndpointNotReadyError,     // 503 - endpoint stopped, cold, or provider down
  RateLimitError,            // 429 - throttled (auto-retried)
  BadRequestError,           // 400/422 - malformed request
} from "pareta";
```

If you call an endpoint that is stopped or still cold, you get `EndpointNotReadyError` (503). Start a stopped endpoint with `pa.endpoints.start(endpoint.id)`. The client auto-retries 429s and transient 5xx/timeouts with exponential backoff (`max_retries`, default 2).

## Operating the endpoint afterward

Once deployed, the endpoint persists. You can stop it to save spend and start it again later:

**Python**

```python
pa.endpoints.stop(endpoint.id)    # take it offline
pa.endpoints.start(endpoint.id)   # bring it back
pa.endpoints.delete(endpoint.id)  # remove it entirely

for ep in pa.endpoints.list():    # everything your org can access
    print(ep.id, ep.status)
```

**TypeScript**

```typescript
await pa.endpoints.stop(endpoint.id);   // take it offline
await pa.endpoints.start(endpoint.id);  // bring it back
await pa.endpoints.delete(endpoint.id); // remove it entirely

for (const ep of await pa.endpoints.list()) { // everything your org can access
  console.log(ep.id, ep.status);
}
```

To see the endpoints you can call right now (the OpenAI-compatible subset with a live URL), use `models.list()`:

**Python**

```python
for m in pa.models.list():
    print(m.id, m.owned_by)
```

**TypeScript**

```typescript
for (const m of await pa.models.list()) {
  console.log(m.id, m.ownedBy);
}
```

Latency, uptime, cost-versus-frontier, and judge-quality readouts live under `pa.endpoints.metrics(endpoint.id)`. See [operate and measure endpoints](../guide/deploying-endpoints.md).

## Async

Everything above mirrors on `AsyncPareta`. The shapes match; methods are `async def` and streams are async iterators.

**Python**

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        endpoint = await pa.endpoints.deploy(
            task="contract-key-fields",
            model="recommended",
            wait=True,
        )
        resp = await pa.chat.completions.create(
            model=endpoint.id,
            messages=[{"role": "user", "content": "Extract the total: ..."}],
        )
        print(resp.choices[0].message.content)

        # Streaming: await create() once, then `async for` the chunks.
        stream = await pa.chat.completions.create(
            model=endpoint.id,
            messages=[{"role": "user", "content": "Summarize: ..."}],
            stream=True,
        )
        async for chunk in stream:
            print(chunk.choices[0].delta.content or "", end="")

asyncio.run(main())
```

**TypeScript**

```typescript
// There is no AsyncPareta in TS: the single `Pareta` client is already
// Promise-only, so the sync/async split simply does not exist. Every I/O
// method returns a Promise you `await`; every stream is an async iterable you
// `for await`. The code above IS the async code.
const pa = Pareta.fromEnv();

const endpoint = await pa.endpoints.deploy({
  task: "contract-key-fields",
  model: "recommended",
  wait: true,
});
const resp = await pa.chat.completions.create({
  model: endpoint.id,
  messages: [{ role: "user", content: "Extract the total: ..." }],
});
console.log(resp.choices[0].message.content);

// Streaming: create() returns the async iterable; `for await` the chunks.
const stream = pa.chat.completions.create({
  model: endpoint.id,
  messages: [{ role: "user", content: "Summarize: ..." }],
  stream: true,
});
for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0].delta.content ?? "");
}

// Concurrency is just Promise.all over the same client — no parallel API:
const [a, b] = await Promise.all([
  pa.chat.completions.create({ model: endpoint.id, messages: [{ role: "user", content: "A" }] }),
  pa.chat.completions.create({ model: endpoint.id, messages: [{ role: "user", content: "B" }] }),
]);
```

For the async deploy progress stream (without `wait=True`), `deploy()` returns an async iterator you consume with `async for`, yielding the same `{"event", "data"}` dicts as the sync version.

## Next steps

- [Discover tasks](../guide/discovery.md): find the right task id from free-text intent before you deploy.
- [Evaluate models](evaluate-on-your-data.md): compare open models against frontier baselines on your own data before committing.
- [Operate and measure endpoints](../guide/deploying-endpoints.md): start, stop, and read latency, cost, and quality metrics.
