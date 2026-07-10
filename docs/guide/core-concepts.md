# Core concepts

Pareta is one OpenAI-compatible endpoint with one model id: **`"auto"`**. This
page covers the handful of ideas the rest of the SDK assumes you understand:
the **routing brain** behind `model="auto"`, **tasks** (the benchmark catalog
it routes across), **open vs frontier** models, why **models** and **hardware**
are hidden, how **metering** works, and the **funnel** that ties them together
(match your intent, prove `"auto"` on your data, ship it, watch the metrics).

Every code block below is runnable as written. They all start from a client:

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

`from_env()` is the path you want in almost every case. The explicit form is
`Pareta(api_key="pareta_sk_...", base_url="https://api.pareta.ai")`; arguments
are keyword-only. See [Authentication](installation.md) for key minting
(browser-only) and [The client](../reference/client.md) for timeouts, retries, and the
async `AsyncPareta` mirror.

## The routing brain: `model="auto"`

Every request you send with `model="auto"` is **planned**, its parts **routed**
to benchmark-proven open specialists, the output **verified**, with a
**fallback** to a frontier model when that is the right call. One request, one
bill, a frontier model as the built-in quality floor.

There is nothing to deploy and no model to pick — "which model?" is the
question Pareta answers for you, per request. `models.list()` reflects that:
it returns exactly one entry.

**Python**

```python
for m in pa.models.list():
    print(m.id)          # exactly one entry: "auto"
```

**TypeScript**

```typescript
for (const m of await pa.models.list()) {
  console.log(m.id);     // exactly one entry: "auto"
}
```

Calling the brain is plain chat — see
[Inference is OpenAI-compatible](#inference-is-openai-compatible) below. The
surfaces *around* that call live on `pa.auto`:

- `auto.metrics()` — your org's `"auto"` traffic, rolled up: requests +
  success rate (30d), spend, hourly p50/p95/error buckets (7d), daily success
  cells (30d), and the projected savings vs frontier.
- `auto.compare_frontier(model=..., messages=...)` (TypeScript
  `auto.compareFrontier({ model, messages })`) — one prompt against a frontier
  vendor for a side-by-side with `"auto"`. Metered at the vendor's actual
  token cost; a failed vendor call bills $0. Allowed models: `gpt-5.5`,
  `gemini-3-5-flash`, `gemini-3-1-pro`, `claude-sonnet-4-6`.

## Tasks: the benchmark catalog

A **task** is a concrete, benchmarked job: "extract the key fields from a
contract," "classify a support ticket," "moderate a comment." Pareta has
measured open and frontier models against each task on real data — that
catalog is what `"auto"` routes across. When your request matches a
benchmarked task, the router knows exactly which open specialist holds
frontier-grade quality on it. A task is the unit auto routes *by* and the unit
you evaluate *against*.

Every task has a stable `id` (e.g. `"contract-key-fields"`), a
`default_scorer` (the function that grades a model's output for that task), and
a `has_blob_input` flag (true when the task takes documents or images, not just
text).

**Python**

```python
for task in pa.tasks.list():
    print(task.id, task.default_scorer, "blob" if task.has_blob_input else "text")

# Fetch one task, optionally with sample rows to see its input shape
t = pa.tasks.retrieve("contract-key-fields", examples_n=3)
print(t.id, t.default_scorer, t.has_blob_input)
```

**TypeScript**

```typescript
for (const task of await pa.tasks.list()) {
  console.log(task.id, task.defaultScorer, task.hasBlobInput ? "blob" : "text");
}

// Fetch one task, optionally with sample rows to see its input shape
const t = await pa.tasks.retrieve("contract-key-fields", { examplesN: 3 });
console.log(t.id, t.defaultScorer, t.hasBlobInput);
```

"Can Pareta do X?" is a question you can ask directly: describe the job in
plain English and `tasks.match` answers with one of four outcomes on `.type`:

- `"task"` — a benchmarked task fits; `.chosen.task_id` names it and
  `.candidates` carries ranked alternates.
- `"capability"` — no specific task fits, but the work lands in a general
  lane `"auto"` still covers (chat, coding, agentic, vision, speech-to-text,
  text-to-speech); `.capability` describes the lane.
- `"unsupported"` — the work is outside what Pareta does. A correct answer,
  not an error; `.reasoning` explains why.
- `"none"` — the reasoning router was unavailable and the lexical fallback
  found nothing confident.

**Python**

```python
m = pa.tasks.match("pull totals and dates out of vendor invoices", top_k=5)
print(m.type)                        # "task" | "capability" | "unsupported" | "none"
if m.type == "task":
    print("best:", m.chosen.task_id, m.chosen.score, m.chosen.confidence)
    for c in m.candidates:           # ranked alternates
        print(c.task_id, c.score, c.confidence)
elif m.type == "capability":
    print("lane:", m.capability.id)  # chat / coding / agentic / vision / asr / tts
elif m.type == "unsupported":
    print(m.reasoning)               # why this is outside what Pareta does
```

**TypeScript**

```typescript
const m = await pa.tasks.match("pull totals and dates out of vendor invoices", { topK: 5 });
if (m.matched && m.chosen) {
  console.log("best:", m.chosen.taskId, m.chosen.score, m.chosen.confidence);
} else {
  for (const c of m.candidates) {        // ranked alternates to choose from
    console.log(c.taskId, c.score, c.confidence);
  }
}
console.log("outcome:", m.get("type"), "via", m.matcher);
```

`match()` raises `ValueError` on an empty query. The matcher is an LLM
reasoning router; `m.matcher` tells you which strategy answered (`"reason"`,
or `"keyword"` on the lexical fallback). The richer fields (`.type`,
`.capability`, `.reasoning`, `.confidence`) are typed properties on the Python
`TaskMatch`; the TypeScript client reads them off the raw payload
(`m.get("type")`). See [Tasks](../reference/tasks.md) for the full matcher
surface.

## Open vs frontier models

Two kinds of model stand behind every task:

- **Open** models are the open-weights specialists `"auto"` routes to. Pareta
  benchmarks them, serves them, and picks between them — you never call one
  directly or learn its identity.
- **Frontier** models are hosted vendor models (OpenAI, Google, Anthropic, and
  so on). They play two roles: the built-in quality floor `"auto"` falls back
  to when no specialist holds the bar, and the **baseline** you measure
  `"auto"` against in evals. The whole point of Pareta is showing that
  `"auto"` matches or beats the frontier on *your* task at a fraction of the
  cost.

Frontier (vendor) ids appear in the clear — those are public products — in
exactly two places: eval baselines and `auto.compare_frontier()`. To enumerate
the frontier roster you can evaluate against, annotated for a given task, use
`evals.frontier_models`:

**Python**

```python
for fm in pa.evals.frontier_models(task="contract-key-fields"):
    print(fm.id, fm.vendor, "vision" if fm.vision else "text",
          "(benchmarked)" if fm.benchmarked else "")
```

**TypeScript**

```typescript
for (const fm of await pa.evals.frontierModels("contract-key-fields")) {
  console.log(fm.id, fm.vendor, fm.vision ? "vision" : "text",
    fm.benchmarked ? "(benchmarked)" : "");
}
```

Passing `task=` annotates each model's `benchmarked` flag (measured on that
task) and filters the roster by capability (for example, only vision-capable
models are returned for document tasks). Feed the `id` values into an eval
run's `frontier=` list.

## Models are hidden

You never pick a model, and open-weights identities never cross the API. The
only model id you send is `"auto"`; the only model ids you read back are
`"auto"` and frontier vendor ids in eval and comparison results
(`result.model_id`).

This is a feature, not an omission. There are no open-model ids to look up,
hard-code, or keep current — when Pareta promotes a better specialist behind a
task, your requests get it on the next call, with no code change and no
migration.

## Hardware is hidden

You never choose a GPU, tensor-parallel degree, quantization scheme, or
serving mode. The specialists behind `"auto"` run on serving classes Pareta
resolves from its registry, and capacity — warm pools, autoscaling, cold
starts — is Pareta's problem. The one place serving infrastructure surfaces in
the SDK is `EndpointNotReadyError` (503): a serving backend behind auto is
warming or briefly unavailable. The SDK retries 503s automatically, so you
rarely see it.

## Inference is OpenAI-compatible

Call the brain through `chat.completions.create` with `model="auto"`. The
request and response match the OpenAI chat schema, so the official `openai`
client works against the same base URL and key.

**Python**

```python
resp = pa.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Extract the contract effective date."}],
    temperature=0,                          # extra OpenAI params pass straight through
)
print(resp.choices[0].message.content)
print(resp.usage.total_tokens)
```

**TypeScript**

```typescript
const resp = await pa.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "Extract the contract effective date." }],
  temperature: 0,                           // extra OpenAI params pass straight through
});
console.log(resp.choices[0].message.content);
console.log(resp.usage.totalTokens);
```

Streaming yields `ChatCompletionChunk` objects; the incremental text is on
`chunk.choices[0].delta.content`:

**Python**

```python
for chunk in pa.chat.completions.create(model="auto", messages=[...], stream=True):
    print(chunk.choices[0].delta.content or "", end="")
```

**TypeScript**

```typescript
for await (const chunk of pa.chat.completions.create({ model: "auto", messages: [...], stream: true })) {
  process.stdout.write(chunk.choices[0].delta.content || "");
}
```

`create()` raises `ValueError` up front if `model` or `messages` is empty. See
[Running inference](./inference.md) for streaming details and the async
iterator form.

## Metering and billing

Both inference and evals are **metered against your organization's balance**.

- **Inference:** a successful `chat.completions.create()` debits the org
  balance **once per request** — no matter how many internal model calls
  auto's plan makes (planning, specialists, verification, fallback).
  Orchestration overhead is Pareta's cost, not yours.
- **Speech:** the `pa.audio` namespace (`pa.audio.transcriptions(...)`,
  `pa.audio.speech(...)`, Python-only) is billed **per minute** of audio — see
  [Audio](../reference/audio.md).
- **Evals:** `evals.runs.create()` debits for the compute it spends: `"auto"`
  and any frontier baselines you include. A FAILED run is not charged.
- **Frontier comparisons:** `auto.compare_frontier()` is metered at the
  vendor's actual token cost; a failed vendor call bills $0.
- **Empty balance:** every path raises `InsufficientCreditsError` (HTTP 402).

**Python**

```python
from pareta import InsufficientCreditsError

try:
    resp = pa.chat.completions.create(model="auto", messages=[{"role": "user", "content": "hi"}])
except InsufficientCreditsError:
    print("Top up the org balance in the dashboard, then retry.")
```

**TypeScript**

```typescript
import { InsufficientCreditsError } from "pareta";

try {
  const resp = await pa.chat.completions.create({ model: "auto", messages: [{ role: "user", content: "hi" }] });
} catch (e) {
  if (e instanceof InsufficientCreditsError) {
    console.log("Top up the org balance in the dashboard, then retry.");
  } else {
    throw e;
  }
}
```

Topping up is **browser-only**. The SDK never exposes the balance, payment
methods, or top-up. It only consumes credit and surfaces the 402 when there is
none.

### Reading cost off an eval run

An eval run reports what it cost. The SDK follows one money convention
(`SDK_PLAN` §6): the **billed total is floored to whole cents** so the SDK never
overstates a charge, while sub-cent precision stays available in micro-USD.

- `run.cost` is a `Decimal` in dollars, floored to cents. A 5 µUSD run reads
  `Decimal("0.00")`.
- `run.cost_micro_usd` is the raw integer (`1_000_000` = `$1.00`).
- Per-item unit rates such as `result.mean_cost_micro_usd` stay in
  **micro-USD**. Flooring them to cents would erase the auto-vs-frontier
  comparison that is the whole point.

**Python**

```python
print(run.cost)               # Decimal("0.42"): billed dollars, floored to cents
print(run.cost_micro_usd)     # 420715: raw micro-USD
```

**TypeScript**

```typescript
console.log(run.cost);          // "0.42": billed dollars (string), floored to cents
console.log(run.costMicroUsd);  // 420715: raw micro-USD
```

## The discovery funnel

The pieces above compose into one path from "I have a job" to "auto is running
it in production, cheaper." This is the recommended flow:

```
match  ->  eval on YOUR data  ->  model="auto" in production  ->  watch the metrics
```

1. **Match** your intent to a task — "can Pareta do X?"
2. **Eval** `"auto"` against frontier baselines on *your own* data. Public
   benchmarks are a starting point; your rows are the deciding vote.
3. **Ship** `model="auto"` — the same call, now carrying production traffic.
4. **Watch** `auto.metrics()` — requests, success rate, spend, projected
   savings vs frontier.

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()

# 1. Match free-text intent to a task
match = pa.tasks.match("extract key fields from contracts")
task = match.chosen.task_id

# 2. Evaluate "auto" against frontier baselines on YOUR rows.
#    Pass task + items to create the eval set inline, or use an existing set id.
run = pa.evals.runs.create(
    task=task,
    items=[
        {"input": "...your contract text...", "expected": {"effective_date": "2026-01-01"}},
        # ...more rows...
    ],
    models=["auto"],
    frontier="benchmarked",       # the frontier baselines measured on this task
    wait=True,                    # block until the run is terminal
)

# 3. Read results (quality + cost), then ship the same call to production
for r in sorted(run.results, key=lambda r: (r.quality_mean or 0), reverse=True):
    print(r.model_id, r.kind, r.quality_mean, r.mean_cost_micro_usd, f"n={r.n_succeeded}")

print("eval cost:", run.cost)     # Decimal dollars, floored to cents

resp = pa.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "...your contract text..."}],
)

# 4. Watch it in production
m = pa.auto.metrics()
print(m["requests_30d"], m["success_rate_30d"], m["savings_vs_frontier_micro_usd_30d"])
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

// 1. Match free-text intent to a task
const match = await pa.tasks.match("extract key fields from contracts");
const task = match.chosen!.taskId;

// 2. Evaluate "auto" against frontier baselines on YOUR rows.
//    Pass task + items to create the eval set inline, or use an existing set id.
const run = await pa.evals.runs.create({
  task,
  items: [
    { input: "...your contract text...", expected: { effective_date: "2026-01-01" } },
    // ...more rows...
  ],
  models: ["auto"],
  frontier: "benchmarked",      // the frontier baselines measured on this task
  wait: true,                   // block until the run is terminal
});

// 3. Read results (quality + cost), then ship the same call to production
for (const r of [...run.results].sort((a, b) => (b.qualityMean ?? 0) - (a.qualityMean ?? 0))) {
  console.log(r.modelId, r.kind, r.qualityMean, r.meanCostMicroUsd, `n=${r.nSucceeded}`);
}

console.log("eval cost:", run.cost);   // dollar string, floored to cents

const resp = await pa.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "...your contract text..." }],
});

// 4. Watch it in production
const m = await pa.auto.metrics();
console.log(m.requests_30d, m.success_rate_30d, m.savings_vs_frontier_micro_usd_30d);
```

A few notes on the eval call:

- Provide **either** `eval_set=<id>` (an existing set) **or** `task=... +
  items=...` to create one inline. With neither, `create()` raises `ValueError`.
- `frontier=` accepts `None`/`"none"` (no baselines), an explicit list of
  frontier ids, `"all"` (every frontier model for the task), or `"benchmarked"`
  (only the frontier models measured on this task, vision-filtered for
  document tasks). Keyword resolution needs to know the task; with
  `eval_set=`, the SDK looks the task up for you.
- `wait=True` polls until the run reaches `"completed"` or `"failed"`
  (`run.is_terminal`), then returns the final `EvalRun`. For document tasks,
  attach binaries with `evals.sets.upload_document(...)` before running.

For the full eval API (building sets, attaching documents, inline vs. existing
sets, and polling semantics) see [Evaluating models](evaluation.md). For the
catalog and matcher surface in depth, see [Tasks](../reference/tasks.md).

## Errors at a glance

Every SDK error subclasses `ParetaError`. The status-mapped subclasses let you
branch on what went wrong without inspecting status codes:

| Exception | Status | When |
|---|---|---|
| `AuthenticationError` | 401 | bad or missing key |
| `InsufficientCreditsError` | 402 | org out of credit (top up in the dashboard) |
| `PermissionDeniedError` | 403 | the user lacks permission |
| `NotFoundError` | 404 | unknown task or run |
| `ConflictError` | 409 | transient contention (auto-retried) |
| `RateLimitError` | 429 | throttled (auto-retried) |
| `EndpointNotReadyError` | 503 | a serving backend behind auto is warming or briefly unavailable (auto-retried) |
| `BadRequestError` | 400/422 | malformed request |
| `APIConnectionError` / `APITimeoutError` | n/a | transport failure (auto-retried) |

**Python**

```python
import pareta

try:
    resp = pa.chat.completions.create(model="auto", messages=[{"role": "user", "content": "hi"}])
except pareta.EndpointNotReadyError:
    print("A backend is warming; retries are exhausted — try again shortly.")
except pareta.InsufficientCreditsError:
    print("Out of credit. Top up in the dashboard.")
except pareta.ParetaError as e:
    print("request failed:", e)
```

**TypeScript**

```typescript
import { EndpointNotReadyError, InsufficientCreditsError, ParetaError } from "pareta";

try {
  const resp = await pa.chat.completions.create({ model: "auto", messages: [{ role: "user", content: "hi" }] });
} catch (e) {
  if (e instanceof EndpointNotReadyError) {
    console.log("A backend is warming; retries are exhausted — try again shortly.");
  } else if (e instanceof InsufficientCreditsError) {
    console.log("Out of credit. Top up in the dashboard.");
  } else if (e instanceof ParetaError) {
    console.log("request failed:", e);
  } else {
    throw e;
  }
}
```

See [Error handling](errors-and-retries.md) for the full hierarchy, the `request_id`
attribute for support, and the retry policy.
