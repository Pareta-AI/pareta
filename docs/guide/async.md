# Async usage

`AsyncPareta` is the asyncio-native client. It mirrors the synchronous [`Pareta`](./quickstart.md) client method-for-method: same constructor, same resource namespaces (`chat`, `models`, `endpoints`, `tasks`, `evals`), same return types. The difference is that request methods are coroutines you `await`, streams are async iterators you drive with `async for`, and many independent calls can run concurrently under one event loop instead of blocking one after another.

Reach for it when you are inside an async app (FastAPI, an aiohttp worker, a Discord bot) or when you want to fan out work: score ten models in parallel, deploy several endpoints at once, or run inference against a batch of inputs without waiting on each round trip.

## The client

Build it from the environment, exactly like the sync client. `from_env()` reads `PARETA_API_KEY` and the optional `PARETA_BASE_URL`.

**Python**

```python
import asyncio
from pareta import AsyncPareta


async def main():
    pa = AsyncPareta.from_env()  # reads PARETA_API_KEY
    try:
        models = await pa.models.list()
        for m in models:
            print(m.id, m.owned_by)
    finally:
        await pa.aclose()


asyncio.run(main())
```

**TypeScript**

In TypeScript there is one client and it is already async — every I/O method returns a Promise you `await`. There is no `AsyncPareta`, no event loop to manage, and no `aclose()`: the client holds no owned connection.

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv(); // reads PARETA_API_KEY

const models = await pa.models.list();
for (const m of models) {
  console.log(m.id, m.ownedBy);
}
```

`models.list()` returns the same `ModelList` as the sync path: only deployed, url-bearing endpoints, OpenAI-compatible. The `id` of each is what you pass to `chat.completions.create(model=...)`.

### Lifecycle: prefer `async with`

The client owns an `httpx.AsyncClient` and you must release it. Use `async with` and cleanup is automatic; otherwise call `await pa.aclose()` in a `finally`.

**Python**

```python
import asyncio
from pareta import AsyncPareta


async def main():
    async with AsyncPareta.from_env() as pa:
        models = await pa.models.list()
        print(len(models), "endpoints")
    # the underlying HTTP client is closed here


asyncio.run(main())
```

**TypeScript**

The TypeScript client owns no connection, so there is nothing to release — no `async with`, no `aclose()`. Build it once and use it; native `fetch` manages its own pooling. If you need a custom transport (tests, a polyfill), pass `fetch:`.

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();
const models = await pa.models.list();
console.log(models.length, "endpoints");
// nothing to close
```

The async lifecycle methods are `await pa.aclose()`, `async with` (which calls `__aenter__` / `__aexit__`). There is no sync `close()` on the async client. If you pass your own `http_client=httpx.AsyncClient(...)`, the SDK will not close it for you; that one is yours to manage.

You can also pass `api_key=`, `base_url=`, `timeout=`, and `max_retries=` directly, same as the sync client:

**Python**

```python
from pareta import AsyncPareta

pa = AsyncPareta(api_key="pareta_sk_...", max_retries=4)
```

**TypeScript**

The constructor takes a single options object with camelCase keys. Note `timeout` is in **milliseconds** here (Python's httpx is seconds).

```typescript
import { Pareta } from "pareta";

const pa = new Pareta({ apiKey: "pareta_sk_...", maxRetries: 4 });
```

## Await every request method

Every resource method that hits the API is a coroutine. Await it.

**Python**

```python
import asyncio
from pareta import AsyncPareta


async def main():
    async with AsyncPareta.from_env() as pa:
        # inference (OpenAI-compatible)
        completion = await pa.chat.completions.create(
            model="ep_contract_kie_01",
            messages=[{"role": "user", "content": "Extract the total due."}],
            temperature=0,
        )
        print(completion.choices[0].message.content)
        print(completion.usage.total_tokens, "tokens")

        # catalog discovery
        match = await pa.tasks.match("pull key fields out of contracts")
        if match.matched:
            print("task:", match.chosen.task_id, match.chosen.confidence)

        # eval roster
        frontier = await pa.evals.frontier_models(task="contract-key-fields")
        print([f.id for f in frontier])


asyncio.run(main())
```

**TypeScript**

Every method already returns a Promise, so `await` is all you need — no coroutine wrapper, no event loop. `chat.completions.create` takes an options object; extra OpenAI params (`temperature`) pass through verbatim.

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

// inference (OpenAI-compatible)
const completion = await pa.chat.completions.create({
  model: "ep_contract_kie_01",
  messages: [{ role: "user", content: "Extract the total due." }],
  temperature: 0,
});
console.log(completion.choices[0].message.content);
console.log(completion.usage.totalTokens, "tokens");

// catalog discovery
const match = await pa.tasks.match("pull key fields out of contracts");
if (match.matched) {
  console.log("task:", match.chosen.taskId, match.chosen.confidence);
}

// eval roster
const frontier = await pa.evals.frontierModels("contract-key-fields");
console.log(frontier.map((f) => f.id));
```

`chat.completions.create()` is metered: a successful completion debits your org balance. If the balance is empty it raises `InsufficientCreditsError` (402). Top-up is browser-only; the SDK does not expose balance or payment. See [Errors](errors-and-retries.md) and [Billing](core-concepts.md).

Note one shape difference inside `evals`: `pa.endpoints.metrics(endpoint_id)` is **not** a coroutine. It returns an `AsyncMetrics` object synchronously; the dimension methods on it are what you await.

**Python**

```python
m = pa.endpoints.metrics("ep_contract_kie_01")   # no await here
cost = await m.cost()                              # await the dimension call
print(cost)
```

**TypeScript**

Same shape: `metrics(id)` returns an `EndpointMetrics` handle synchronously; you await each dimension call.

```typescript
const m = pa.endpoints.metrics("ep_contract_kie_01"); // no await here
const cost = await m.cost(); // await the dimension call
console.log(cost);
```

## Streaming with `async for`

Streaming chat works in two steps. First `await` the `create(stream=True)` call to get the async iterator, then drive it with `async for`. Each chunk is a `ChatCompletionChunk`; the incremental text is `chunk.choices[0].delta.content` (which can be `None` on non-content frames, so guard it).

**Python**

```python
import asyncio
from pareta import AsyncPareta


async def main():
    async with AsyncPareta.from_env() as pa:
        stream = await pa.chat.completions.create(
            model="ep_contract_kie_01",
            messages=[{"role": "user", "content": "Summarize this clause."}],
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                print(delta, end="", flush=True)
        print()


asyncio.run(main())
```

**TypeScript**

With `stream: true` the call returns an `AsyncIterable<ChatCompletionChunk>` directly — no separate await for the handshake. Drive it with `for await`. The incremental text is `chunk.choices[0].delta.content`, which can be `null` on non-content frames, so guard it.

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

const stream = pa.chat.completions.create({
  model: "ep_contract_kie_01",
  messages: [{ role: "user", content: "Summarize this clause." }],
  stream: true,
});
for await (const chunk of stream) {
  const delta = chunk.choices[0].delta.content;
  if (delta) process.stdout.write(delta);
}
console.log();
```

The stream ends on the wire's `[DONE]` sentinel; the async iterator simply stops. Retries apply only to the initial handshake. Once bytes are flowing, a mid-stream drop raises immediately rather than silently resuming.

### Deploying with progress events

`endpoints.deploy()` takes a task and a model alias and nothing about hardware. Pareta hides GPUs entirely: there is no GPU, tensor-parallel, or quantization knob. `model` defaults to `"recommended"`, the task's curated or top-open pick. Models are addressed by per-task public aliases, never raw weights ids.

With `wait=False` (the default), `await` the call to get an async iterator of `{"event": str, "data": dict}` progress events; the terminal event is `"complete"` (with `data["endpoint"]`) or `"error"`.

**Python**

```python
import asyncio
from pareta import AsyncPareta


async def main():
    async with AsyncPareta.from_env() as pa:
        stream = await pa.endpoints.deploy(task="contract-key-fields", model="recommended")
        async for event in stream:
            if event["event"] == "progress":
                print("stage:", event["data"])
            elif event["event"] == "complete":
                ep = event["data"]["endpoint"]
                print("live:", ep["id"], ep["url"])
            elif event["event"] == "error":
                print("failed:", event["data"])


asyncio.run(main())
```

**TypeScript**

`deploy` takes an options object. With `wait` omitted (the default) it returns an `AsyncIterable<{ event, data }>` of progress events; the terminal event is `"complete"` (with `data.endpoint`) or `"error"`. Drive it with `for await`.

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

const stream = pa.endpoints.deploy({ task: "contract-key-fields", model: "recommended" });
for await (const event of stream) {
  if (event.event === "progress") {
    console.log("stage:", event.data);
  } else if (event.event === "complete") {
    const ep = event.data.endpoint;
    console.log("live:", ep.id, ep.url);
  } else if (event.event === "error") {
    console.log("failed:", event.data);
  }
}
```

If you do not want to watch progress, pass `wait=True`. The SDK consumes the stream internally and returns the live `Endpoint` once it is up, raising `ParetaError` on a deploy `"error"` event.

**Python**

```python
ep = await pa.endpoints.deploy(task="contract-key-fields", model="recommended", wait=True)
print(ep.id, ep.is_live, ep.url)

# then call it
completion = await pa.chat.completions.create(
    model=ep.id,
    messages=[{"role": "user", "content": "Extract the parties."}],
)
```

**TypeScript**

With `wait: true`, `deploy` resolves the live `Endpoint` once it is up (throwing `ParetaError` on a deploy `error` event).

```typescript
const ep = await pa.endpoints.deploy({ task: "contract-key-fields", model: "recommended", wait: true });
console.log(ep.id, ep.isLive, ep.url);

// then call it
const completion = await pa.chat.completions.create({
  model: ep.id,
  messages: [{ role: "user", content: "Extract the parties." }],
});
```

## Running many calls concurrently

This is the reason to go async. Independent calls can run at the same time under one event loop with `asyncio.gather`, instead of serializing on each network round trip. Reuse one client across all of them so they share the connection pool.

### Fan out inference over a batch

**Python**

```python
import asyncio
from pareta import AsyncPareta

PROMPTS = [
    "Extract the invoice total.",
    "Extract the due date.",
    "Extract the vendor name.",
    "Extract the PO number.",
]


async def classify(pa: AsyncPareta, model: str, prompt: str) -> str:
    completion = await pa.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return completion.choices[0].message.content


async def main():
    async with AsyncPareta.from_env() as pa:
        results = await asyncio.gather(
            *(classify(pa, "ep_contract_kie_01", p) for p in PROMPTS)
        )
        for prompt, answer in zip(PROMPTS, results):
            print(prompt, "->", answer)


asyncio.run(main())
```

**TypeScript**

In TypeScript every call is already a Promise, so concurrency is just `Promise.all` over the calls you kick off — no `asyncio.gather`, no separate async API. Reuse one client so they share the connection pool.

```typescript
import { Pareta } from "pareta";

const PROMPTS = [
  "Extract the invoice total.",
  "Extract the due date.",
  "Extract the vendor name.",
  "Extract the PO number.",
];

const pa = Pareta.fromEnv();

async function classify(model: string, prompt: string): Promise<string | null> {
  const completion = await pa.chat.completions.create({
    model,
    messages: [{ role: "user", content: prompt }],
    temperature: 0,
  });
  return completion.choices[0].message.content;
}

const results = await Promise.all(PROMPTS.map((p) => classify("ep_contract_kie_01", p)));
PROMPTS.forEach((prompt, i) => console.log(prompt, "->", results[i]));
```

Each of those `create()` calls is metered independently and debits the org balance on success. If your balance runs out mid-batch, the in-flight calls that have not yet been billed raise `InsufficientCreditsError`. With `gather`, the first exception propagates and cancels the rest; pass `return_exceptions=True` if you would rather collect partial results and inspect failures per item.

**Python**

```python
results = await asyncio.gather(
    *(classify(pa, "ep_contract_kie_01", p) for p in PROMPTS),
    return_exceptions=True,
)
for prompt, result in zip(PROMPTS, results):
    if isinstance(result, Exception):
        print(prompt, "FAILED:", result)
    else:
        print(prompt, "->", result)
```

**TypeScript**

`Promise.all` rejects on the first failure, just like `gather`. The equivalent of `return_exceptions=True` is `Promise.allSettled`, which collects a `{ status, value | reason }` per item.

```typescript
const settled = await Promise.allSettled(PROMPTS.map((p) => classify("ep_contract_kie_01", p)));
PROMPTS.forEach((prompt, i) => {
  const result = settled[i];
  if (result.status === "rejected") {
    console.log(prompt, "FAILED:", result.reason);
  } else {
    console.log(prompt, "->", result.value);
  }
});
```

### Deploy several endpoints at once

`deploy(..., wait=True)` is a coroutine, so a list of deploys parallelizes cleanly.

**Python**

```python
import asyncio
from pareta import AsyncPareta

TASKS = ["contract-key-fields", "invoice-extraction", "doc-classification"]


async def main():
    async with AsyncPareta.from_env() as pa:
        endpoints = await asyncio.gather(
            *(pa.endpoints.deploy(task=t, model="recommended", wait=True) for t in TASKS)
        )
        for ep in endpoints:
            print(ep.task, ep.id, ep.is_live)


asyncio.run(main())
```

**TypeScript**

`deploy({ ..., wait: true })` returns a Promise, so a list of deploys parallelizes with `Promise.all`.

```typescript
import { Pareta } from "pareta";

const TASKS = ["contract-key-fields", "invoice-extraction", "doc-classification"];

const pa = Pareta.fromEnv();

const endpoints = await Promise.all(
  TASKS.map((task) => pa.endpoints.deploy({ task, model: "recommended", wait: true })),
);
for (const ep of endpoints) {
  console.log(ep.task, ep.id, ep.isLive);
}
```

### Run several eval runs in parallel

`evals.runs.create(..., wait=True)` polls `runs.retrieve()` until the run is terminal using `asyncio.sleep`, so it never blocks the loop. That makes a leaderboard sweep, one run per candidate set, a natural `gather`.

**Python**

```python
import asyncio
from pareta import AsyncPareta

ITEMS = [
    {"input": "Acme Corp agrees to pay $5,000 net 30.", "expected": {"amount": "5000"}},
    {"input": "Total due: $1,200 by 2026-07-01.", "expected": {"amount": "1200"}},
]


async def main():
    async with AsyncPareta.from_env() as pa:
        # create one shared eval set, then sweep candidate model lists against it
        eval_set = await pa.evals.sets.create(task="contract-key-fields", items=ITEMS)
        print("eval set:", eval_set.id, eval_set.item_count, "items")

        candidate_lists = [
            ["contract-key-fields-open-1"],
            ["contract-key-fields-open-2"],
        ]
        runs = await asyncio.gather(
            *(
                pa.evals.runs.create(eval_set=eval_set.id, models=models, wait=True)
                for models in candidate_lists
            )
        )
        for run in runs:
            print(run.id, run.status, "cost", run.cost)  # run.cost is a Decimal in dollars
            for r in run.results:
                print(" ", r.model_id, r.kind, r.quality_mean)


asyncio.run(main())
```

**TypeScript**

`runs.create({ ..., wait: true })` polls `runs.retrieve()` until terminal, so a sweep is a natural `Promise.all`. Note `run.cost` is a fixed-2dp dollar **string** here (`run.costMicroUsd` is the raw integer).

```typescript
import { Pareta } from "pareta";

const ITEMS = [
  { input: "Acme Corp agrees to pay $5,000 net 30.", expected: { amount: "5000" } },
  { input: "Total due: $1,200 by 2026-07-01.", expected: { amount: "1200" } },
];

const pa = Pareta.fromEnv();

// create one shared eval set, then sweep candidate model lists against it
const evalSet = await pa.evals.sets.create({ task: "contract-key-fields", items: ITEMS });
console.log("eval set:", evalSet.id, evalSet.itemCount, "items");

const candidateLists = [["contract-key-fields-open-1"], ["contract-key-fields-open-2"]];
const runs = await Promise.all(
  candidateLists.map((models) => pa.evals.runs.create({ evalSet: evalSet.id, models, wait: true })),
);
for (const run of runs) {
  console.log(run.id, run.status, "cost", run.cost); // run.cost is a dollar string
  for (const r of run.results) {
    console.log(" ", r.modelId, r.kind, r.qualityMean);
  }
}
```

Eval runs are metered against the org balance for the compute used (open candidates plus any frontier baselines), and raise `InsufficientCreditsError` on an empty balance. `run.cost` is a `Decimal` in dollars, floored to whole cents (so a sub-cent run reads `Decimal("0.00")`); `run.cost_micro_usd` is the raw integer micro-USD if you need the exact figure. See [Evals](evaluation.md) and [Billing](core-concepts.md).

To add vendor baselines, pass `frontier=`. In the async client, `"all"` and `"benchmarked"` resolve the roster by awaiting `evals.frontier_models()` SDK-side, so they need a task to resolve against (taken from `task=` or looked up from the eval set):

**Python**

```python
run = await pa.evals.runs.create(
    eval_set=eval_set.id,
    models=["contract-key-fields-open-1"],
    frontier="benchmarked",   # or "all", or an explicit list of frontier ids, or None
    wait=True,
)
```

**TypeScript**

`"all"` and `"benchmarked"` resolve the roster SDK-side via `evals.frontierModels()`, so they need a task to resolve against (from `task` or looked up from the eval set).

```typescript
const run = await pa.evals.runs.create({
  evalSet: evalSet.id,
  models: ["contract-key-fields-open-1"],
  frontier: "benchmarked", // or "all", an explicit list of frontier ids, or null
  wait: true,
});
```

### Polling a run yourself

If you started a run with `wait=False`, await `runs.wait()` later, or poll `runs.retrieve()` on your own schedule. `wait()` accepts `poll_interval` (default 3.0s) and `timeout` (default 900s), and raises `ParetaError` if the run does not reach a terminal status in time.

**Python**

```python
run = await pa.evals.runs.create(eval_set=eval_set.id, models=["contract-key-fields-open-1"])
print("queued:", run.id, run.status)
# ... do other work ...
final = await pa.evals.runs.wait(run.id, poll_interval=5.0, timeout=600.0)
print(final.status, final.is_terminal, final.cost)
```

**TypeScript**

`runs.wait(id, { pollInterval, timeout })` takes seconds (defaults 3 / 900) and throws `ParetaError` if the run does not finish in time. The run id is positional; the schedule is an options object.

```typescript
const run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["contract-key-fields-open-1"] });
console.log("queued:", run.id, run.status);
// ... do other work ...
const final = await pa.evals.runs.wait(run.id, { pollInterval: 5, timeout: 600 });
console.log(final.status, final.isTerminal, final.cost);
```

## Bounding concurrency

`gather` launches everything at once. For large batches, cap the in-flight count with an `asyncio.Semaphore` so you do not overwhelm a single endpoint or trip rate limits (which surface as `RateLimitError`, 429; the client already retries those with backoff up to `max_retries`).

**Python**

```python
import asyncio
from pareta import AsyncPareta


async def main():
    sem = asyncio.Semaphore(5)  # at most 5 concurrent requests

    async with AsyncPareta.from_env() as pa:
        async def one(prompt: str) -> str:
            async with sem:
                completion = await pa.chat.completions.create(
                    model="ep_contract_kie_01",
                    messages=[{"role": "user", "content": prompt}],
                )
                return completion.choices[0].message.content

        prompts = [f"Extract field {i}." for i in range(100)]
        answers = await asyncio.gather(*(one(p) for p in prompts))
        print(len(answers), "done")


asyncio.run(main())
```

**TypeScript**

`Promise.all` launches everything at once too. There is no built-in semaphore, so cap concurrency by draining a shared work queue from a fixed pool of workers — at most `LIMIT` requests are in flight at any time.

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();
const LIMIT = 5; // at most 5 concurrent requests

const prompts = Array.from({ length: 100 }, (_, i) => `Extract field ${i}.`);

async function one(prompt: string): Promise<string | null> {
  const completion = await pa.chat.completions.create({
    model: "ep_contract_kie_01",
    messages: [{ role: "user", content: prompt }],
  });
  return completion.choices[0].message.content;
}

const answers: (string | null)[] = new Array(prompts.length);
let next = 0;
async function worker() {
  while (next < prompts.length) {
    const i = next++;
    answers[i] = await one(prompts[i]);
  }
}
await Promise.all(Array.from({ length: LIMIT }, () => worker()));
console.log(answers.length, "done");
```

## Errors

The async client raises the exact same exception hierarchy as the sync client; the only difference is that errors surface out of an awaited call or an `async for`. Catch them the usual way.

**Python**

```python
from pareta import (
    AsyncPareta,
    InsufficientCreditsError,
    EndpointNotReadyError,
    RateLimitError,
    ParetaError,
)


async def safe_call(pa: AsyncPareta):
    try:
        return await pa.chat.completions.create(
            model="ep_contract_kie_01",
            messages=[{"role": "user", "content": "hi"}],
        )
    except InsufficientCreditsError:
        print("org balance is empty; top up in the dashboard")
    except EndpointNotReadyError:
        print("endpoint is cold or stopped; start it and retry")
    except RateLimitError:
        print("rate limited even after retries")
    except ParetaError as e:
        print("pareta error:", e)
```

**TypeScript**

Same exception hierarchy, surfaced out of an awaited call (or a `for await`). JavaScript has one `catch` clause, so branch on `instanceof` — most specific first, since the subclasses all extend `ParetaError`.

```typescript
import {
  Pareta,
  InsufficientCreditsError,
  EndpointNotReadyError,
  RateLimitError,
  ParetaError,
} from "pareta";

async function safeCall(pa: Pareta) {
  try {
    return await pa.chat.completions.create({
      model: "ep_contract_kie_01",
      messages: [{ role: "user", content: "hi" }],
    });
  } catch (e) {
    if (e instanceof InsufficientCreditsError) {
      console.log("org balance is empty; top up in the dashboard");
    } else if (e instanceof EndpointNotReadyError) {
      console.log("endpoint is cold or stopped; start it and retry");
    } else if (e instanceof RateLimitError) {
      console.log("rate limited even after retries");
    } else if (e instanceof ParetaError) {
      console.log("pareta error:", e);
    } else {
      throw e;
    }
  }
}
```

Pre-flight validation (empty `model`/`messages`, empty `items`, an unparseable `frontier`) raises `ValueError`/`TypeError` when you `await` the call — the check runs at the top of the coroutine, before any network I/O (not when the coroutine object is first created). See [Errors](errors-and-retries.md) for the full mapping.

## Sync and async, side by side

| Concern | `Pareta` (sync) | `AsyncPareta` (async) |
|---|---|---|
| Build | `Pareta.from_env()` | `AsyncPareta.from_env()` |
| Cleanup | `pa.close()` / `with pa:` | `await pa.aclose()` / `async with pa:` |
| Request method | `pa.models.list()` | `await pa.models.list()` |
| Streaming chat | `for chunk in pa.chat.completions.create(stream=True)` | `stream = await pa...create(stream=True)` then `async for chunk in stream` |
| Deploy events | `for ev in pa.endpoints.deploy(...)` | `stream = await pa.endpoints.deploy(...)` then `async for ev in stream` |
| Deploy and block | `pa.endpoints.deploy(..., wait=True)` | `await pa.endpoints.deploy(..., wait=True)` |
| Wait on a run | `pa.evals.runs.wait(run_id)` | `await pa.evals.runs.wait(run_id)` |
| Metrics handle | `pa.endpoints.metrics(id)` (sync) | `pa.endpoints.metrics(id)` (sync, returns `AsyncMetrics`) |
| Metrics dimension | `m.cost()` | `await m.cost()` |
| Concurrency | thread pool / one at a time | `asyncio.gather`, one event loop |

Same metering, same aliases, same OpenAI-compatible inference, same hidden GPUs. Once you have the sync flow in [Quickstart](./quickstart.md), the async version is the same calls with `await` in front and `async for` over the streams.
