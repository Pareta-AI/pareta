# Async usage

`AsyncPareta` is the asyncio-native client. It mirrors the synchronous [`Pareta`](./quickstart.md) client method-for-method: same constructor, same resource namespaces (`chat`, `models`, `endpoints`, `tasks`, `evals`), same return types. The difference is that request methods are coroutines you `await`, streams are async iterators you drive with `async for`, and many independent calls can run concurrently under one event loop instead of blocking one after another.

Reach for it when you are inside an async app (FastAPI, an aiohttp worker, a Discord bot) or when you want to fan out work: score ten models in parallel, deploy several endpoints at once, or run inference against a batch of inputs without waiting on each round trip.

## The client

Build it from the environment, exactly like the sync client. `from_env()` reads `PARETA_API_KEY` and the optional `PARETA_BASE_URL`.

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

`models.list()` returns the same `ModelList` as the sync path: only deployed, url-bearing endpoints, OpenAI-compatible. The `id` of each is what you pass to `chat.completions.create(model=...)`.

### Lifecycle: prefer `async with`

The client owns an `httpx.AsyncClient` and you must release it. Use `async with` and cleanup is automatic; otherwise call `await pa.aclose()` in a `finally`.

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

The async lifecycle methods are `await pa.aclose()`, `async with` (which calls `__aenter__` / `__aexit__`). There is no sync `close()` on the async client. If you pass your own `http_client=httpx.AsyncClient(...)`, the SDK will not close it for you; that one is yours to manage.

You can also pass `api_key=`, `base_url=`, `timeout=`, and `max_retries=` directly, same as the sync client:

```python
from pareta import AsyncPareta

pa = AsyncPareta(api_key="pareta_sk_...", max_retries=4)
```

## Await every request method

Every resource method that hits the API is a coroutine. Await it.

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

`chat.completions.create()` is metered: a successful completion debits your org balance. If the balance is empty it raises `InsufficientCreditsError` (402). Top-up is browser-only; the SDK does not expose balance or payment. See [Errors](errors-and-retries.md) and [Billing](core-concepts.md).

Note one shape difference inside `evals`: `pa.endpoints.metrics(endpoint_id)` is **not** a coroutine. It returns an `AsyncMetrics` object synchronously; the dimension methods on it are what you await.

```python
m = pa.endpoints.metrics("ep_contract_kie_01")   # no await here
cost = await m.cost()                              # await the dimension call
print(cost)
```

## Streaming with `async for`

Streaming chat works in two steps. First `await` the `create(stream=True)` call to get the async iterator, then drive it with `async for`. Each chunk is a `ChatCompletionChunk`; the incremental text is `chunk.choices[0].delta.content` (which can be `None` on non-content frames, so guard it).

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

The stream ends on the wire's `[DONE]` sentinel; the async iterator simply stops. Retries apply only to the initial handshake. Once bytes are flowing, a mid-stream drop raises immediately rather than silently resuming.

### Deploying with progress events

`endpoints.deploy()` takes a task and a model alias and nothing about hardware. Pareta hides GPUs entirely: there is no GPU, tensor-parallel, or quantization knob. `model` defaults to `"recommended"`, the task's curated or top-open pick. Models are addressed by per-task public aliases, never raw weights ids.

With `wait=False` (the default), `await` the call to get an async iterator of `{"event": str, "data": dict}` progress events; the terminal event is `"complete"` (with `data["endpoint"]`) or `"error"`.

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

If you do not want to watch progress, pass `wait=True`. The SDK consumes the stream internally and returns the live `Endpoint` once it is up, raising `ParetaError` on a deploy `"error"` event.

```python
ep = await pa.endpoints.deploy(task="contract-key-fields", model="recommended", wait=True)
print(ep.id, ep.is_live, ep.url)

# then call it
completion = await pa.chat.completions.create(
    model=ep.id,
    messages=[{"role": "user", "content": "Extract the parties."}],
)
```

## Running many calls concurrently

This is the reason to go async. Independent calls can run at the same time under one event loop with `asyncio.gather`, instead of serializing on each network round trip. Reuse one client across all of them so they share the connection pool.

### Fan out inference over a batch

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

Each of those `create()` calls is metered independently and debits the org balance on success. If your balance runs out mid-batch, the in-flight calls that have not yet been billed raise `InsufficientCreditsError`. With `gather`, the first exception propagates and cancels the rest; pass `return_exceptions=True` if you would rather collect partial results and inspect failures per item.

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

### Deploy several endpoints at once

`deploy(..., wait=True)` is a coroutine, so a list of deploys parallelizes cleanly.

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

### Run several eval runs in parallel

`evals.runs.create(..., wait=True)` polls `runs.retrieve()` until the run is terminal using `asyncio.sleep`, so it never blocks the loop. That makes a leaderboard sweep, one run per candidate set, a natural `gather`.

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

Eval runs are metered against the org balance for the compute used (open candidates plus any frontier baselines), and raise `InsufficientCreditsError` on an empty balance. `run.cost` is a `Decimal` in dollars, floored to whole cents (so a sub-cent run reads `Decimal("0.00")`); `run.cost_micro_usd` is the raw integer micro-USD if you need the exact figure. See [Evals](evaluation.md) and [Billing](core-concepts.md).

To add vendor baselines, pass `frontier=`. In the async client, `"all"` and `"benchmarked"` resolve the roster by awaiting `evals.frontier_models()` SDK-side, so they need a task to resolve against (taken from `task=` or looked up from the eval set):

```python
run = await pa.evals.runs.create(
    eval_set=eval_set.id,
    models=["contract-key-fields-open-1"],
    frontier="benchmarked",   # or "all", or an explicit list of frontier ids, or None
    wait=True,
)
```

### Polling a run yourself

If you started a run with `wait=False`, await `runs.wait()` later, or poll `runs.retrieve()` on your own schedule. `wait()` accepts `poll_interval` (default 3.0s) and `timeout` (default 900s), and raises `ParetaError` if the run does not reach a terminal status in time.

```python
run = await pa.evals.runs.create(eval_set=eval_set.id, models=["contract-key-fields-open-1"])
print("queued:", run.id, run.status)
# ... do other work ...
final = await pa.evals.runs.wait(run.id, poll_interval=5.0, timeout=600.0)
print(final.status, final.is_terminal, final.cost)
```

## Bounding concurrency

`gather` launches everything at once. For large batches, cap the in-flight count with an `asyncio.Semaphore` so you do not overwhelm a single endpoint or trip rate limits (which surface as `RateLimitError`, 429; the client already retries those with backoff up to `max_retries`).

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

## Errors

The async client raises the exact same exception hierarchy as the sync client; the only difference is that errors surface out of an awaited call or an `async for`. Catch them the usual way.

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
