# Async usage

`AsyncPareta` is the asyncio-native client. It mirrors the synchronous [`Pareta`](./quickstart.md) client method-for-method: same constructor, same resource namespaces (`chat`, `models`, `tasks`, `evals`, `auto`, `audio`), same return types. The difference is that request methods are coroutines you `await`, streams are async iterators you drive with `async for`, and many independent calls can run concurrently under one event loop instead of blocking one after another.

Reach for it when you are inside an async app (FastAPI, an aiohttp worker, a Discord bot) or when you want to fan out work: run a batch of prompts against `model="auto"` without waiting on each round trip, or kick off several eval runs at once.

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

`models.list()` returns the same `ModelList` as the sync path: exactly one entry, `"auto"` — the only model id you pass to `chat.completions.create(model=...)`.

### Lifecycle: prefer `async with`

The client owns an `httpx.AsyncClient` and you must release it. Use `async with` and cleanup is automatic; otherwise call `await pa.aclose()` in a `finally`.

**Python**

```python
import asyncio
from pareta import AsyncPareta


async def main():
    async with AsyncPareta.from_env() as pa:
        models = await pa.models.list()
        print([m.id for m in models])  # ['auto']
    # the underlying HTTP client is closed here


asyncio.run(main())
```

**TypeScript**

The TypeScript client owns no connection, so there is nothing to release — no `async with`, no `aclose()`. Build it once and use it; native `fetch` manages its own pooling. If you need a custom transport (tests, a polyfill), pass `fetch:`.

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();
const models = await pa.models.list();
console.log([...models].map((m) => m.id)); // ["auto"]
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
            model="auto",
            messages=[{"role": "user", "content": "Extract the total due."}],
            temperature=0,
        )
        print(completion.choices[0].message.content)
        print(completion.usage.total_tokens, "tokens")

        # catalog discovery
        match = await pa.tasks.match("pull key fields out of contracts")
        if match.matched:
            print("task:", match.chosen.task_id, match.chosen.confidence)

        # auto rollup (requests, success, spend, projected savings)
        metrics = await pa.auto.metrics()
        print(metrics["requests_30d"], "requests in 30d")

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
  model: "auto",
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

// auto rollup (requests, success, spend, projected savings)
const metrics = await pa.auto.metrics();
console.log(metrics.requests_30d, "requests in 30d");

// eval roster
const frontier = await pa.evals.frontierModels("contract-key-fields");
console.log(frontier.map((f) => f.id));
```

`chat.completions.create()` is metered: a successful completion debits your org balance — one debit per request, no matter how many internal model calls auto's plan makes. If the balance is empty it raises `InsufficientCreditsError` (402). Top-up is browser-only; the SDK does not expose balance or payment. See [Errors](errors-and-retries.md) and [Billing](core-concepts.md).

## Streaming with `async for`

Streaming chat works in two steps. First `await` the `create(stream=True)` call to get the async iterator, then drive it with `async for`. Each chunk is a `ChatCompletionChunk`; the incremental text is `chunk.choices[0].delta.content` (which can be `None` on non-content frames, so guard it).

**Python**

```python
import asyncio
from pareta import AsyncPareta


async def main():
    async with AsyncPareta.from_env() as pa:
        stream = await pa.chat.completions.create(
            model="auto",
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
  model: "auto",
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


async def classify(pa: AsyncPareta, prompt: str) -> str:
    completion = await pa.chat.completions.create(
        model="auto",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return completion.choices[0].message.content


async def main():
    async with AsyncPareta.from_env() as pa:
        results = await asyncio.gather(
            *(classify(pa, p) for p in PROMPTS)
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

async function classify(prompt: string): Promise<string | null> {
  const completion = await pa.chat.completions.create({
    model: "auto",
    messages: [{ role: "user", content: prompt }],
    temperature: 0,
  });
  return completion.choices[0].message.content;
}

const results = await Promise.all(PROMPTS.map((p) => classify(p)));
PROMPTS.forEach((prompt, i) => console.log(prompt, "->", results[i]));
```

Each of those `create()` calls is metered independently and debits the org balance on success. If your balance runs out mid-batch, the in-flight calls that have not yet been billed raise `InsufficientCreditsError`. With `gather`, the first exception propagates and cancels the rest; pass `return_exceptions=True` if you would rather collect partial results and inspect failures per item.

**Python**

```python
results = await asyncio.gather(
    *(classify(pa, p) for p in PROMPTS),
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
const settled = await Promise.allSettled(PROMPTS.map((p) => classify(p)));
PROMPTS.forEach((prompt, i) => {
  const result = settled[i];
  if (result.status === "rejected") {
    console.log(prompt, "FAILED:", result.reason);
  } else {
    console.log(prompt, "->", result.value);
  }
});
```

### Mix resources in one gather

`gather` does not care that the coroutines hit different routes. Kick off an inference call, a catalog match, and your org's auto rollup in one shot:

**Python**

```python
import asyncio
from pareta import AsyncPareta


async def main():
    async with AsyncPareta.from_env() as pa:
        completion, match, metrics = await asyncio.gather(
            pa.chat.completions.create(
                model="auto",
                messages=[{"role": "user", "content": "Extract the parties."}],
            ),
            pa.tasks.match("pull key fields out of contracts"),
            pa.auto.metrics(),
        )
        print(completion.choices[0].message.content)
        if match.matched:
            print("task:", match.chosen.task_id)
        print("requests (30d):", metrics["requests_30d"])


asyncio.run(main())
```

**TypeScript**

`Promise.all` is heterogeneous too — the tuple keeps each result's type.

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

const [completion, match, metrics] = await Promise.all([
  pa.chat.completions.create({
    model: "auto",
    messages: [{ role: "user", content: "Extract the parties." }],
  }),
  pa.tasks.match("pull key fields out of contracts"),
  pa.auto.metrics(),
]);
console.log(completion.choices[0].message.content);
if (match.matched) {
  console.log("task:", match.chosen?.taskId);
}
console.log("requests (30d):", metrics.requests_30d);
```

### Run several eval runs in parallel

`evals.runs.create(..., wait=True)` polls `runs.retrieve()` until the run is terminal using `asyncio.sleep`, so it never blocks the loop. That makes benchmarking `"auto"` on several of your datasets — one run per eval set — a natural `gather`. Passing `intent=` + `items=` creates the eval set and the run in one call.

**Python**

```python
import asyncio
from pareta import AsyncPareta

JOBS = {
    "extract the payment amount from each contract": [
        {"input": "Acme Corp agrees to pay $5,000 net 30.", "expected": {"amount": "5000"}},
        {"input": "Total due: $1,200 by 2026-07-01.", "expected": {"amount": "1200"}},
    ],
    "extract the total from each invoice": [
        {"input": "INVOICE #4471 ... TOTAL $1,240.00 ...", "expected": {"total": "1240.00"}},
    ],
}


async def main():
    async with AsyncPareta.from_env() as pa:
        # one run per dataset: "auto" against the task's frontier baselines
        runs = await asyncio.gather(
            *(
                pa.evals.runs.create(
                    intent=intent, items=items,
                    models=["auto"], frontier="benchmarked", wait=True,
                )
                for intent, items in JOBS.items()
            )
        )
        for run in runs:
            print(run.id, run.status, "cost", run.cost)  # run.cost is a Decimal in dollars
            for r in run.results:
                print(" ", r.model_id, r.kind, r.quality_mean)


asyncio.run(main())
```

**TypeScript**

`runs.create({ ..., wait: true })` polls `runs.retrieve()` until terminal, so the fan-out is a natural `Promise.all`. Note `run.cost` is a fixed-2dp dollar **string** here (`run.costMicroUsd` is the raw integer).

```typescript
import { Pareta } from "pareta";

const JOBS: Record<string, Array<Record<string, unknown>>> = {
  "extract the payment amount from each contract": [
    { input: "Acme Corp agrees to pay $5,000 net 30.", expected: { amount: "5000" } },
    { input: "Total due: $1,200 by 2026-07-01.", expected: { amount: "1200" } },
  ],
  "extract the total from each invoice": [
    { input: "INVOICE #4471 ... TOTAL $1,240.00 ...", expected: { total: "1240.00" } },
  ],
};

const pa = Pareta.fromEnv();

// one run per dataset: "auto" against the task's frontier baselines
const runs = await Promise.all(
  Object.entries(JOBS).map(([intent, items]) =>
    pa.evals.runs.create({ intent, items, models: ["auto"], frontier: "benchmarked", wait: true }),
  ),
);
for (const run of runs) {
  console.log(run.id, run.status, "cost", run.cost); // run.cost is a dollar string
  for (const r of run.results) {
    console.log(" ", r.modelId, r.kind, r.qualityMean);
  }
}
```

Eval runs are metered against the org balance for the compute used (`"auto"` plus any frontier baselines), and raise `InsufficientCreditsError` on an empty balance. `run.cost` is a `Decimal` in dollars, floored to whole cents (so a sub-cent run reads `Decimal("0.00")`); `run.cost_micro_usd` is the raw integer micro-USD if you need the exact figure. See [Evals](evaluation.md) and [Billing](core-concepts.md).

The `frontier=` keywords pick the vendor baselines. In the async client, `"all"` and `"benchmarked"` resolve the roster by awaiting `evals.frontier_models()` SDK-side, so they need a contract to resolve against (a pinned `task=`, or the contract bound to the eval set — including the one the binder chose for an inline `items=… + intent=…` create):

**Python**

```python
run = await pa.evals.runs.create(
    eval_set=eval_set.id,     # an existing set from evals.sets.create(...)
    models=["auto"],
    frontier="benchmarked",   # or "all", or an explicit list of frontier ids, or None
    wait=True,
)
```

**TypeScript**

`"all"` and `"benchmarked"` resolve the roster SDK-side via `evals.frontierModels()`, so they need a task to resolve against (from `task` or looked up from the eval set).

```typescript
const run = await pa.evals.runs.create({
  evalSet: evalSet.id, // an existing set from evals.sets.create(...)
  models: ["auto"],
  frontier: "benchmarked", // or "all", an explicit list of frontier ids, or null
  wait: true,
});
```

### Polling a run yourself

If you started a run with `wait=False`, await `runs.wait()` later, or poll `runs.retrieve()` on your own schedule. `wait()` accepts `poll_interval` (default 3.0s) and `timeout` (default 900s), and raises `ParetaError` if the run does not reach a terminal status in time.

**Python**

```python
run = await pa.evals.runs.create(eval_set=eval_set.id, models=["auto"])
print("queued:", run.id, run.status)
# ... do other work ...
final = await pa.evals.runs.wait(run.id, poll_interval=5.0, timeout=600.0)
print(final.status, final.is_terminal, final.cost)
```

**TypeScript**

`runs.wait(id, { pollInterval, timeout })` takes seconds (defaults 3 / 900) and throws `ParetaError` if the run does not finish in time. The run id is positional; the schedule is an options object.

```typescript
const run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["auto"] });
console.log("queued:", run.id, run.status);
// ... do other work ...
const final = await pa.evals.runs.wait(run.id, { pollInterval: 5, timeout: 600 });
console.log(final.status, final.isTerminal, final.cost);
```

## Bounding concurrency

`gather` launches everything at once. For large batches, cap the in-flight count with an `asyncio.Semaphore` so you do not trip rate limits (which surface as `RateLimitError`, 429; the client already retries those with backoff up to `max_retries`).

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
                    model="auto",
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
    model: "auto",
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
            model="auto",
            messages=[{"role": "user", "content": "hi"}],
        )
    except InsufficientCreditsError:
        print("org balance is empty; top up in the dashboard")
    except EndpointNotReadyError:
        print("a backend behind auto is briefly unavailable; retry in a moment")
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
      model: "auto",
      messages: [{ role: "user", content: "hi" }],
    });
  } catch (e) {
    if (e instanceof InsufficientCreditsError) {
      console.log("org balance is empty; top up in the dashboard");
    } else if (e instanceof EndpointNotReadyError) {
      console.log("a backend behind auto is briefly unavailable; retry in a moment");
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
| Wait on a run | `pa.evals.runs.wait(run_id)` | `await pa.evals.runs.wait(run_id)` |
| Auto metrics | `pa.auto.metrics()` | `await pa.auto.metrics()` |
| Concurrency | thread pool / one at a time | `asyncio.gather`, one event loop |

Same metering, same OpenAI-compatible inference, same hidden models and GPUs. Once you have the sync flow in [Quickstart](./quickstart.md), the async version is the same calls with `await` in front and `async for` over the streams.
