# Concurrent calls with AsyncPareta

`AsyncPareta` lets you fire many requests at once instead of one at a time. When
you have a batch of inference prompts to score, or several eval runs to kick off,
running them concurrently turns a wall of sequential round-trips into a single
`asyncio.gather`. The same surface as the sync [`Pareta`](../reference/client.md)
client, with every resource method `async def` and the streaming iterators
async.

This page shows how to:

- run a batch of `chat.completions` concurrently and collect results
- bound concurrency so you do not hammer an endpoint (backpressure)
- handle errors per task so one failure does not sink the batch
- launch and await several eval runs at once

One `AsyncPareta` instance wraps a single pooled `httpx.AsyncClient`. Build it
once, share it across all your coroutines, and close it once. Do not make a
client per request.

**Python**

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:   # reads PARETA_API_KEY
        resp = await pa.chat.completions.create(
            model="ep_invoice_extract",
            messages=[{"role": "user", "content": "Extract the total."}],
        )
        print(resp.choices[0].message.content)

asyncio.run(main())
```

**TypeScript**

The TS SDK has no sync/async split — there is one `Pareta` class, and every
I/O method already returns a `Promise` you `await`. No `AsyncPareta`, no
`asyncio.run`, no `async with`: build one client and share it.

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();                  // reads PARETA_API_KEY

const resp = await pa.chat.completions.create({
  model: "ep_invoice_extract",
  messages: [{ role: "user", content: "Extract the total." }],
});
console.log(resp.choices[0].message.content);
```

Inference is OpenAI-compatible and metered: each successful completion debits
your org balance, and a zero balance raises `InsufficientCreditsError` (402).
Top-up is browser-only, so the SDK never exposes balance or payment. `model` is
an endpoint id from [`endpoints.deploy()`](../guide/deploying-endpoints.md) (or any model
id your org can reach); Pareta hides the hardware, so there is no GPU knob to
pass.

## Fan out a batch of completions

`asyncio.gather` runs every coroutine concurrently and returns results in input
order. Because all calls share the same client, httpx pools and reuses
connections for you.

**Python**

```python
import asyncio
from pareta import AsyncPareta

PROMPTS = [
    "Extract the invoice total.",
    "Extract the vendor name.",
    "Extract the due date.",
    "Extract the line-item count.",
]

async def classify_one(pa, prompt, document):
    resp = await pa.chat.completions.create(
        model="ep_invoice_extract",
        messages=[
            {"role": "system", "content": "You are an invoice parser."},
            {"role": "user", "content": f"{prompt}\n\n{document}"},
        ],
        temperature=0,
        max_tokens=64,
    )
    return resp.choices[0].message.content

async def main():
    document = "INVOICE #4471 ... TOTAL $1,240.00 ..."
    async with AsyncPareta.from_env() as pa:
        answers = await asyncio.gather(
            *(classify_one(pa, p, document) for p in PROMPTS)
        )
    for prompt, answer in zip(PROMPTS, answers):
        print(f"{prompt} -> {answer}")

asyncio.run(main())
```

**TypeScript**

`Promise.all` is the direct analog of `asyncio.gather`: it runs every promise
concurrently and resolves to results in input order. The shared `fetch` keep-alive
pool reuses connections for you.

```typescript
import { Pareta } from "pareta";

const PROMPTS = [
  "Extract the invoice total.",
  "Extract the vendor name.",
  "Extract the due date.",
  "Extract the line-item count.",
];

async function classifyOne(pa: Pareta, prompt: string, document: string) {
  const resp = await pa.chat.completions.create({
    model: "ep_invoice_extract",
    messages: [
      { role: "system", content: "You are an invoice parser." },
      { role: "user", content: `${prompt}\n\n${document}` },
    ],
    temperature: 0,
    max_tokens: 64,
  });
  return resp.choices[0].message.content;
}

const document = "INVOICE #4471 ... TOTAL $1,240.00 ...";
const pa = Pareta.fromEnv();
const answers = await Promise.all(
  PROMPTS.map((p) => classifyOne(pa, p, document)),
);
for (let i = 0; i < PROMPTS.length; i++) {
  console.log(`${PROMPTS[i]} -> ${answers[i]}`);
}
```

If any coroutine raises, `gather` propagates the first exception and the rest are
cancelled. That is rarely what you want for a batch. The next two sections fix
both halves of the problem: capacity (backpressure) and partial failure.

## Bound concurrency with a semaphore

Firing 5,000 prompts at `gather` opens as many tasks at once, overruns the
connection pool, and is the fastest way to earn a `RateLimitError` (429) or push
a cold endpoint into `EndpointNotReadyError` (503). An `asyncio.Semaphore` caps
how many calls are in flight at any moment. The rest queue and drain as slots
free up.

**Python**

```python
import asyncio
from pareta import AsyncPareta

MAX_IN_FLIGHT = 16

async def complete(pa, sem, messages):
    async with sem:                       # acquire a slot; release on exit
        resp = await pa.chat.completions.create(
            model="ep_invoice_extract",
            messages=messages,
            temperature=0,
        )
        return resp.choices[0].message.content

async def run_batch(documents):
    sem = asyncio.Semaphore(MAX_IN_FLIGHT)
    async with AsyncPareta.from_env() as pa:
        tasks = [
            complete(pa, sem, [{"role": "user", "content": f"Summarize:\n{d}"}])
            for d in documents
        ]
        return await asyncio.gather(*tasks)

# 1,000 docs, but never more than 16 concurrent requests
results = asyncio.run(run_batch([f"doc {i}" for i in range(1000)]))
print(len(results))
```

**TypeScript**

JS has no built-in `asyncio.Semaphore`, so a small worker-pool does the same job:
spin up `MAX_IN_FLIGHT` workers that each pull from a shared cursor until the
queue drains. That caps in-flight calls without pulling in a dependency.

```typescript
import { Pareta } from "pareta";

const MAX_IN_FLIGHT = 16;

async function complete(pa: Pareta, messages: Array<{ role: string; content: string }>) {
  const resp = await pa.chat.completions.create({
    model: "ep_invoice_extract",
    messages,
    temperature: 0,
  });
  return resp.choices[0].message.content;
}

async function runBatch(documents: string[]): Promise<Array<string | null>> {
  const pa = Pareta.fromEnv();
  const results: Array<string | null> = new Array(documents.length);
  let cursor = 0;
  // N workers drain a shared cursor → never more than N requests in flight.
  const worker = async () => {
    for (let i = cursor++; i < documents.length; i = cursor++) {
      results[i] = await complete(pa, [
        { role: "user", content: `Summarize:\n${documents[i]}` },
      ]);
    }
  };
  await Promise.all(
    Array.from({ length: Math.min(MAX_IN_FLIGHT, documents.length) }, worker),
  );
  return results;
}

// 1,000 docs, but never more than 16 concurrent requests
const docs = Array.from({ length: 1000 }, (_, i) => `doc ${i}`);
const results = await runBatch(docs);
console.log(results.length);
```

Pick `MAX_IN_FLIGHT` to match what the endpoint can sustain. 8 to 32 is a sane
starting band; tune it against the endpoint's latency from
[`endpoints.metrics()`](cost-and-metrics.md). The SDK already retries `429`,
`503`, and `5xx` with exponential backoff (`max_retries`, default 2), so the
semaphore is your first line of defense and retries are the backstop.

## Handle errors per task

Pass `return_exceptions=True` to `gather` and every coroutine resolves to either
its result or the exception it raised, in order. The batch always completes; you
decide what to do with the failures. This is the right default for fan-out work.

**Python**

```python
import asyncio
from pareta import (
    AsyncPareta,
    ParetaError,
    InsufficientCreditsError,
    EndpointNotReadyError,
    RateLimitError,
    APITimeoutError,
)

MAX_IN_FLIGHT = 16

async def complete(pa, sem, doc):
    async with sem:
        resp = await pa.chat.completions.create(
            model="ep_invoice_extract",
            messages=[{"role": "user", "content": f"Extract the total from:\n{doc}"}],
            temperature=0,
        )
        return resp.choices[0].message.content

async def main(documents):
    sem = asyncio.Semaphore(MAX_IN_FLIGHT)
    async with AsyncPareta.from_env() as pa:
        outcomes = await asyncio.gather(
            *(complete(pa, sem, d) for d in documents),
            return_exceptions=True,
        )

    ok, failed = [], []
    for doc, outcome in zip(documents, outcomes):
        if isinstance(outcome, InsufficientCreditsError):
            # Org balance hit zero mid-batch. Nothing else will succeed —
            # stop and top up in the dashboard.
            raise outcome
        if isinstance(outcome, BaseException):
            failed.append((doc, outcome))
        else:
            ok.append((doc, outcome))

    print(f"{len(ok)} succeeded, {len(failed)} failed")
    for doc, err in failed:
        if isinstance(err, EndpointNotReadyError):
            reason = "endpoint cold/stopped"      # 503
        elif isinstance(err, RateLimitError):
            reason = "rate limited after retries"  # 429
        elif isinstance(err, APITimeoutError):
            reason = "timed out"
        elif isinstance(err, ParetaError):
            reason = str(err)
        else:
            reason = repr(err)
        print(f"  retry {doc!r}: {reason}")
    return ok, failed

asyncio.run(main([f"doc {i}" for i in range(50)]))
```

**TypeScript**

`Promise.allSettled` is the analog of `gather(..., return_exceptions=True)`: it
never short-circuits, and every entry resolves to `{status:"fulfilled", value}`
or `{status:"rejected", reason}`. Switch on the error class with `instanceof`.

```typescript
import {
  Pareta,
  ParetaError,
  InsufficientCreditsError,
  EndpointNotReadyError,
  RateLimitError,
  APITimeoutError,
} from "pareta";

const MAX_IN_FLIGHT = 16;

async function complete(pa: Pareta, doc: string) {
  const resp = await pa.chat.completions.create({
    model: "ep_invoice_extract",
    messages: [{ role: "user", content: `Extract the total from:\n${doc}` }],
    temperature: 0,
  });
  return resp.choices[0].message.content;
}

async function main(documents: string[]) {
  const pa = Pareta.fromEnv();
  // Worker pool bounds in-flight calls (see the semaphore section above).
  const outcomes: Array<{ ok: true; value: string | null } | { ok: false; error: unknown }> =
    new Array(documents.length);
  let cursor = 0;
  const worker = async () => {
    for (let i = cursor++; i < documents.length; i = cursor++) {
      try {
        outcomes[i] = { ok: true, value: await complete(pa, documents[i]) };
      } catch (error) {
        outcomes[i] = { ok: false, error };
      }
    }
  };
  await Promise.all(
    Array.from({ length: Math.min(MAX_IN_FLIGHT, documents.length) }, worker),
  );

  const ok: Array<[string, string | null]> = [];
  const failed: Array<[string, unknown]> = [];
  for (let i = 0; i < documents.length; i++) {
    const outcome = outcomes[i];
    if (outcome.ok) {
      ok.push([documents[i], outcome.value]);
    } else if (outcome.error instanceof InsufficientCreditsError) {
      // Org balance hit zero mid-batch. Nothing else will succeed —
      // stop and top up in the dashboard.
      throw outcome.error;
    } else {
      failed.push([documents[i], outcome.error]);
    }
  }

  console.log(`${ok.length} succeeded, ${failed.length} failed`);
  for (const [doc, err] of failed) {
    let reason: string;
    if (err instanceof EndpointNotReadyError) {
      reason = "endpoint cold/stopped"; // 503
    } else if (err instanceof RateLimitError) {
      reason = "rate limited after retries"; // 429
    } else if (err instanceof APITimeoutError) {
      reason = "timed out";
    } else if (err instanceof ParetaError) {
      reason = err.message;
    } else {
      reason = String(err);
    }
    console.log(`  retry ${JSON.stringify(doc)}: ${reason}`);
  }
  return { ok, failed };
}

const docs = Array.from({ length: 50 }, (_, i) => `doc ${i}`);
await main(docs);
```

Notes on the error types (all subclass `ParetaError`):

- **`InsufficientCreditsError` (402)** is fatal for the whole batch, not just one
  task. The balance is shared across the org, so once it hits zero every
  remaining call fails the same way. Stop early and top up.
- **`EndpointNotReadyError` (503)** means the endpoint is stopped, cold-starting,
  or its provider is down. Often transient; safe to retry the failed subset after
  a `start()` or a short wait.
- **`RateLimitError` (429)** surfaces only after the SDK exhausts its own
  retries. If you see these, lower `MAX_IN_FLIGHT`.
- **`APITimeoutError`** is raised after `max_retries`. Long generations may need a
  larger `timeout=` on the client (default is 60s, 10s connect).

Because `return_exceptions=True` never cancels siblings, you can re-run just
`failed` on the next pass.

## Streaming under concurrency

Async streaming mirrors the sync path with one twist: `create(...)` is a
coroutine, so you `await` it — and because `stream=True`, the awaited result is
an async iterator you then `async for` over. (Non-streaming `create` is awaited
too, returning the `ChatCompletion`.)

**Python**

```python
import asyncio
from pareta import AsyncPareta

async def stream_into(pa, prompt, sink):
    stream = await pa.chat.completions.create(   # await → returns the async iterator
        model="ep_invoice_extract",
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    async for chunk in stream:
        sink.append(chunk.choices[0].delta.content or "")

async def main():
    sinks = {p: [] for p in ("Summarize doc A.", "Summarize doc B.")}
    async with AsyncPareta.from_env() as pa:
        await asyncio.gather(
            *(stream_into(pa, p, sink) for p, sink in sinks.items())
        )
    for prompt, parts in sinks.items():
        print(prompt, "->", "".join(parts))

asyncio.run(main())
```

**TypeScript**

In TS, `stream: true` makes `create(...)` return an `AsyncIterable<ChatCompletionChunk>`
directly (not a `Promise` — don't `await` the call), which you drive with
`for await … of`. Run several at once with `Promise.all`, exactly like the batch.

```typescript
import { Pareta } from "pareta";

async function streamInto(pa: Pareta, prompt: string, sink: string[]) {
  const stream = pa.chat.completions.create({   // stream:true → AsyncIterable, no await
    model: "ep_invoice_extract",
    messages: [{ role: "user", content: prompt }],
    stream: true,
  });
  for await (const chunk of stream) {
    sink.push(chunk.choices[0].delta.content || "");
  }
}

const sinks = new Map<string, string[]>([
  ["Summarize doc A.", []],
  ["Summarize doc B.", []],
]);
const pa = Pareta.fromEnv();
await Promise.all(
  [...sinks].map(([prompt, sink]) => streamInto(pa, prompt, sink)),
);
for (const [prompt, parts] of sinks) {
  console.log(prompt, "->", parts.join(""));
}
```

`chunk.choices[0].delta.content` is the incremental text. Streams end on
`[DONE]`; the SDK closes them for you. Retries only cover the initial handshake,
so a mid-stream drop raises immediately rather than silently resuming.

## Concurrent eval runs

The same pattern launches several [eval runs](../guide/evaluation.md) at once. With
`wait=True`, each `runs.create(...)` polls the run to completion using
`asyncio.sleep` under the hood, so the coroutines yield the event loop while they
wait. That makes a fan-out of `wait=True` runs genuinely concurrent.

**Python**

```python
import asyncio
from pareta import AsyncPareta

# Compare candidate aliases on three tasks, each against its frontier baselines.
JOBS = [
    ("contract-key-fields",   ["qwen-1", "llama-2"]),
    ("invoice-extraction",    ["qwen-1", "pixtral-1"]),
    ("doc-classification",    ["llama-1", "qwen-2"]),
]

async def eval_task(pa, eval_set_id, models):
    run = await pa.evals.runs.create(
        eval_set=eval_set_id,
        models=models,            # per-task open-model aliases
        frontier="benchmarked",   # frontier models on this task's leaderboard
        wait=True,                # polls until terminal (completed/failed)
        timeout=1200.0,
    )
    return run

async def main(eval_set_ids):
    async with AsyncPareta.from_env() as pa:
        runs = await asyncio.gather(
            *(eval_task(pa, sid, models)
              for sid, (_, models) in zip(eval_set_ids, JOBS)),
            return_exceptions=True,
        )

    for outcome in runs:
        if isinstance(outcome, BaseException):
            print("run failed to launch/finish:", outcome)
            continue
        run = outcome
        if run.status == "failed":
            print(f"{run.id}: failed — {run.error_detail}")
            continue
        print(f"{run.id}: {run.status}  cost ${run.cost}")  # Decimal dollars
        for r in run.results:
            print(f"  {r.model_id} ({r.kind}): quality={r.quality_mean}")

# eval_set_ids from earlier pa.evals.sets.create(...) calls
asyncio.run(main(["es_abc", "es_def", "es_ghi"]))
```

**TypeScript**

`runs.create({ wait: true })` returns a `Promise` that polls to terminal, so a
`Promise.allSettled` fans out several runs concurrently. The `timeout` and
`pollInterval` options are in **seconds** (matching the Python eval poller). The
billed total is `run.cost` — a fixed-2dp **string** here, not a `Decimal` — and
`run.costMicroUsd` keeps the raw micro-USD integer.

```typescript
import { Pareta } from "pareta";

// Compare candidate aliases on three tasks, each against its frontier baselines.
const JOBS: Array<[string, string[]]> = [
  ["contract-key-fields", ["qwen-1", "llama-2"]],
  ["invoice-extraction", ["qwen-1", "pixtral-1"]],
  ["doc-classification", ["llama-1", "qwen-2"]],
];

async function evalTask(pa: Pareta, evalSetId: string, models: string[]) {
  return pa.evals.runs.create({
    evalSet: evalSetId,
    models,                  // per-task open-model aliases
    frontier: "benchmarked", // frontier models on this task's leaderboard
    wait: true,              // polls until terminal (completed/failed)
    timeout: 1200,
  });
}

async function main(evalSetIds: string[]) {
  const pa = Pareta.fromEnv();
  const runs = await Promise.allSettled(
    evalSetIds.map((sid, i) => evalTask(pa, sid, JOBS[i][1])),
  );

  for (const outcome of runs) {
    if (outcome.status === "rejected") {
      console.log("run failed to launch/finish:", outcome.reason);
      continue;
    }
    const run = outcome.value;
    if (run.status === "failed") {
      console.log(`${run.id}: failed — ${run.errorDetail}`);
      continue;
    }
    console.log(`${run.id}: ${run.status}  cost $${run.cost}`); // dollars (string)
    for (const r of run.results) {
      console.log(`  ${r.modelId} (${r.kind}): quality=${r.qualityMean}`);
    }
  }
}

// evalSetIds from earlier pa.evals.sets.create(...) calls
await main(["es_abc", "es_def", "es_ghi"]);
```

Eval runs are metered too: the org balance is debited for the compute (open
candidates plus any frontier baselines), and an empty balance raises
`InsufficientCreditsError` (402). `run.cost` is the billed total as `Decimal`
dollars floored to cents; `run.cost_micro_usd` keeps the raw micro-USD integer if
you need sub-cent precision. Result `model_id`s are per-task public aliases, not
real model ids.

If you do not want to block on completion, drop `wait=True` and the call returns
immediately with a queued `EvalRun`; await `pa.evals.runs.wait(run.id)` later, or
poll `pa.evals.runs.retrieve(run.id)` yourself.

## Checklist

- One `AsyncPareta` per process, shared across coroutines. `async with` (or
  `await pa.aclose()`) to release the pool.
- `asyncio.gather(*tasks)` to fan out; `return_exceptions=True` so one failure
  does not cancel the batch.
- `asyncio.Semaphore(N)` to bound in-flight calls — your backpressure valve.
- Treat `InsufficientCreditsError` as batch-fatal; retry `EndpointNotReadyError`
  and the residual `RateLimitError` subset.
- Always `await create()`. For `stream=True` the awaited result is the async
  iterator you `async for` over; for non-streaming it is the `ChatCompletion`.

## See also

- [The client](../reference/client.md) — constructor, `from_env`, retries, timeouts
- [Chat completions](../guide/inference.md) — full inference surface and streaming
- [Endpoints](../guide/deploying-endpoints.md) — deploy, start/stop, and operate endpoints
- [Evals](../guide/evaluation.md) — eval sets, runs, and frontier baselines
- [Errors](../guide/errors-and-retries.md) — the full `ParetaError` hierarchy
