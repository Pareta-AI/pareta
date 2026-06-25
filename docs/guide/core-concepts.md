# Core concepts

Pareta deploys open-weights models as endpoints, lets you evaluate them on your
own data, and serves OpenAI-compatible inference. This page covers the handful
of ideas the rest of the SDK assumes you understand: **tasks** (the benchmark
catalog), **open vs frontier** models, **per-task aliases**, why **hardware is
hidden**, how **metering** works, and the **discovery funnel** that ties them
together (match a task, read its leaderboard, eval candidates on your data,
deploy the winner).

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

## Tasks: the benchmark catalog

A **task** is a concrete, benchmarked job: "extract the key fields from a
contract," "classify a support ticket," "moderate a comment." Pareta has
measured open and frontier models against each task on real data, so a task is
the unit you pick a model *for*, evaluate *against*, and deploy *into*.

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

If you do not know the task id, describe the job in plain English and let the
matcher rank candidates:

**Python**

```python
m = pa.tasks.match("pull totals and dates out of vendor invoices", top_k=5)
if m.matched and m.chosen:
    print("best:", m.chosen.task_id, m.chosen.score, m.chosen.confidence)
else:
    for c in m.candidates:          # ranked alternates to choose from
        print(c.task_id, c.score, c.confidence)
print("ambiguous?", m.ambiguous, "via", m.matcher)
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
console.log("ambiguous?", m.ambiguous, "via", m.matcher);
```

`match()` raises `ValueError` on an empty query. The matcher is an LLM reasoning
router that maps your intent to one of three outcomes — a benchmarked task, a
general **capability** lane (chat, coding, agentic, vision, speech-to-text,
text-to-speech) when no specific task fits, or `unsupported` when the work is
outside what Pareta does. `m.matcher` tells you which strategy answered
(`"reason"`, or `"keyword"` on the lexical fallback). The richer typed fields
(`m.type`, `m.reasoning`, `m.confidence`, `m.capability`) are populated by the
reasoning router. See [Finding the right model](discovery.md#capabilities) for the
capability lanes.

## Open vs frontier models

Pareta ranks two kinds of model against every task:

- **Open** models are open-weights models Pareta can deploy and serve for you.
  These are the models you deploy and call.
- **Frontier** models are hosted vendor models (OpenAI, Anthropic, and so on).
  You do not deploy these. They exist as the **baseline** you measure against.
  The whole point of Pareta is showing that a cheaper open model matches or
  beats the frontier on *your* task.

A task's leaderboard ranks the open models by quality and cost and carries a
single `frontier` entry as the savings baseline. The `recommended` field is the
deployable model the platform would pick for you.

**Python**

```python
lb = pa.tasks.leaderboard("contract-key-fields")
print("recommended:", lb.recommended, "metric:", lb.metric, "unit:", lb.cost_unit)

for e in lb.models:                 # ranked open candidates
    print(e.name, e.kind, e.quality, e.cost_per_request_micro_usd, f"{e.context_k}k ctx")

if lb.frontier:                     # the vendor baseline to beat
    print("baseline:", lb.frontier.name, lb.frontier.quality,
          lb.frontier.cost_per_request_micro_usd)

# Convenience: just the deployable pick (what deploy(model="recommended") resolves to)
print(pa.tasks.recommended("contract-key-fields"))
```

**TypeScript**

```typescript
const lb = await pa.tasks.leaderboard("contract-key-fields");
console.log("recommended:", lb.recommended, "metric:", lb.metric, "unit:", lb.costUnit);

for (const e of lb.models) {        // ranked open candidates
  console.log(e.name, e.kind, e.quality, e.costPerRequestMicroUsd, `${e.contextK}k ctx`);
}

if (lb.frontier) {                  // the vendor baseline to beat
  console.log("baseline:", lb.frontier.name, lb.frontier.quality,
    lb.frontier.costPerRequestMicroUsd);
}

// Convenience: just the deployable pick (what deploy({ model: "recommended" }) resolves to)
console.log(await pa.tasks.recommended("contract-key-fields"));
```

To enumerate the frontier roster you can evaluate against, annotated for a
given task, use `evals.frontier_models`:

**Python**

```python
for fm in pa.evals.frontier_models(task="contract-key-fields"):
    print(fm.id, fm.vendor, "vision" if fm.vision else "text",
          "(on leaderboard)" if fm.benchmarked else "")
```

**TypeScript**

```typescript
for (const fm of await pa.evals.frontierModels("contract-key-fields")) {
  console.log(fm.id, fm.vendor, fm.vision ? "vision" : "text",
    fm.benchmarked ? "(on leaderboard)" : "");
}
```

Passing `task=` annotates each model's `benchmarked` flag and filters the
roster by capability (for example, only vision-capable models are returned for
document tasks). Feed the `id` values into an eval run's `frontier=` list.

## Per-task aliases: real model ids stay hidden

Open-weights model identities are never exposed. Across the entire SDK surface
(leaderboard rows, `Endpoint.model`, eval `result.model_id`, and the `model=`
argument you pass to `endpoints.deploy()`) open models appear as **per-task
public aliases** (a stable name scoped to the task), not their underlying
repo/checkpoint ids. Frontier (vendor) ids are shown in the clear, since those
are public products.

This matters in practice for two reasons:

1. The string you read off a leaderboard entry or a recommendation is exactly
   the string you pass back into `deploy(model=...)` or an eval's `models=[...]`.
   You never translate ids yourself.
2. Do not hard-code an alias from one task and reuse it on another. Aliases are
   per-task; always source them from that task's leaderboard or recommendation.

**Python**

```python
task = "contract-key-fields"
pick = pa.tasks.recommended(task)          # a per-task alias, e.g. "qwen-1"
ep = pa.endpoints.deploy(task=task, model=pick, wait=True)
print(ep.model)                            # the same alias, echoed back
```

**TypeScript**

```typescript
const task = "contract-key-fields";
const pick = await pa.tasks.recommended(task);    // a per-task alias, e.g. "qwen-1"
const ep = await pa.endpoints.deploy({ task, model: pick, wait: true });
console.log(ep.model);                            // the same alias, echoed back
```

## Hardware is hidden

You never choose a GPU, tensor-parallel degree, quantization scheme, or serving
mode. `endpoints.deploy()` takes a `task` and a `model` (alias, real-callable
id, or the literal `"recommended"`) and nothing about hardware. Pareta resolves
the serving class from its registry.

**Python**

```python
# No hardware knobs. task + model is the whole decision.
ep = pa.endpoints.deploy(task="contract-key-fields", model="recommended", wait=True)
print(ep.id, ep.status, ep.url)            # ep.id is what you call for inference
```

**TypeScript**

```typescript
// No hardware knobs. task + model is the whole decision.
const ep = await pa.endpoints.deploy({ task: "contract-key-fields", model: "recommended", wait: true });
console.log(ep.id, ep.status, ep.url);     // ep.id is what you call for inference
```

`deploy()` streams progress. With `wait=True` it blocks and returns the live
`Endpoint` (raising `ParetaError` if the deploy fails). With `wait=False`
(the default) it returns an iterator of `{"event", "data"}` progress events so
you can render a progress bar:

**Python**

```python
for evt in pa.endpoints.deploy(task="contract-key-fields", model="recommended"):
    if evt["event"] == "progress":
        print(evt["data"])                 # stage status
    elif evt["event"] == "complete":
        ep = evt["data"]["endpoint"]
        print("live:", ep["id"])
    elif evt["event"] == "error":
        # the SDK raises ParetaError on this event when wait=True
        print("failed:", evt["data"])
```

**TypeScript**

```typescript
for await (const evt of pa.endpoints.deploy({ task: "contract-key-fields", model: "recommended" })) {
  if (evt.event === "progress") {
    console.log(evt.data);                 // stage status
  } else if (evt.event === "complete") {
    const ep = evt.data.endpoint;
    console.log("live:", ep.id);
  } else if (evt.event === "error") {
    // the SDK throws ParetaError on this event when wait: true
    console.log("failed:", evt.data);
  }
}
```

Operate and inspect endpoints with `list`, `retrieve`, `start`, `stop`,
`delete`, and `metrics`. See [Deploying endpoints](deploying-endpoints.md) for the full
lifecycle.

**Python**

```python
for ep in pa.endpoints.list():
    print(ep.id, ep.task, ep.status, "LIVE" if ep.is_live else "")

perf = pa.endpoints.metrics(ep.id).performance()   # p50/p95/p99 latency (raw JSON)
```

**TypeScript**

```typescript
for (const ep of await pa.endpoints.list()) {
  console.log(ep.id, ep.task, ep.status, ep.isLive ? "LIVE" : "");
}

const perf = await pa.endpoints.metrics(ep.id).performance();   // p50/p95/p99 latency (raw JSON)
```

## Inference is OpenAI-compatible

Once an endpoint is live, call it through `chat.completions.create`. The
endpoint id (`ep.id`) is the `model`. The request and response match the OpenAI
chat schema, so the official `openai` client works against the same base URL
and key.

**Python**

```python
resp = pa.chat.completions.create(
    model=ep.id,
    messages=[{"role": "user", "content": "Extract the contract effective date."}],
    temperature=0,                          # extra OpenAI params pass straight through
)
print(resp.choices[0].message.content)
print(resp.usage.total_tokens)
```

**TypeScript**

```typescript
const resp = await pa.chat.completions.create({
  model: ep.id,
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
for chunk in pa.chat.completions.create(model=ep.id, messages=[...], stream=True):
    print(chunk.choices[0].delta.content or "", end="")
```

**TypeScript**

```typescript
for await (const chunk of pa.chat.completions.create({ model: ep.id, messages: [...], stream: true })) {
  process.stdout.write(chunk.choices[0].delta.content || "");
}
```

`create()` raises `ValueError` up front if `model` or `messages` is empty. See
[Running inference](./inference.md) for streaming details and the async
iterator form.

## Metering and billing

Both inference and evals are **metered against your organization's balance**.

- **Inference:** a successful `chat.completions.create()` debits the org
  balance. A numbered-task endpoint is billed a **flat per-request** rate;
  a **capability** endpoint (open-ended request shapes) is billed **per token**
  instead, off the model's serving rate.
- **Speech:** the `pa.audio` namespace (`pa.audio.transcriptions(...)`,
  `pa.audio.speech(...)`) is billed **per minute** of audio — see
  [Finding the right model](discovery.md#capabilities).
- **Evals:** `evals.runs.create()` debits for the compute it spends: both the
  open candidates and any frontier baselines you include.
- **Empty balance:** every path raises `InsufficientCreditsError` (HTTP 402).

**Python**

```python
from pareta import InsufficientCreditsError

try:
    resp = pa.chat.completions.create(model=ep.id, messages=[{"role": "user", "content": "hi"}])
except InsufficientCreditsError:
    print("Top up the org balance in the dashboard, then retry.")
```

**TypeScript**

```typescript
import { InsufficientCreditsError } from "pareta";

try {
  const resp = await pa.chat.completions.create({ model: ep.id, messages: [{ role: "user", content: "hi" }] });
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
- Per-item unit rates such as `result.mean_cost_micro_usd` and a leaderboard
  entry's `cost_per_request_micro_usd` stay in **micro-USD**. Flooring them to
  cents would erase the open-vs-frontier comparison that is the whole point.

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

The pieces above compose into one path from "I have a job" to "I have a cheaper
endpoint running it." This is the recommended flow:

```
match  ->  leaderboard  ->  eval on YOUR data  ->  deploy the winner
```

1. **Match** your intent to a task.
2. Read the task's **leaderboard** to see ranked open candidates and the
   frontier baseline.
3. **Eval** the top candidates (plus the frontier baseline) on *your own* data.
   Public benchmarks are a starting point; your rows are the deciding vote.
4. **Deploy** the model that wins on your data.

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()

# 1. Match free-text intent to a task
match = pa.tasks.match("extract key fields from contracts")
task = match.chosen.task_id

# 2. See how open models rank against the frontier baseline
lb = pa.tasks.leaderboard(task)
candidates = [e.name for e in lb.models[:3]]      # top-3 open aliases

# 3. Evaluate those candidates + the benchmarked frontier on YOUR rows.
#    Pass task + items to create the eval set inline, or use an existing set id.
run = pa.evals.runs.create(
    task=task,
    items=[
        {"input": "...your contract text...", "expected": {"effective_date": "2026-01-01"}},
        # ...more rows...
    ],
    models=candidates,            # open candidates (per-task aliases)
    frontier="benchmarked",       # baselines on this task's leaderboard
    wait=True,                    # block until the run is terminal
)

# 4. Read results (quality + cost), then deploy the model that won on your data
for r in sorted(run.results, key=lambda r: (r.quality_mean or 0), reverse=True):
    print(r.model_id, r.kind, r.quality_mean, r.mean_cost_micro_usd, f"n={r.n_succeeded}")

print("eval cost:", run.cost)     # Decimal dollars, floored to cents

winner = run.results[0].model_id
ep = pa.endpoints.deploy(task=task, model=winner, wait=True)
print("serving:", ep.id, ep.url)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

// 1. Match free-text intent to a task
const match = await pa.tasks.match("extract key fields from contracts");
const task = match.chosen!.taskId;

// 2. See how open models rank against the frontier baseline
const lb = await pa.tasks.leaderboard(task);
const candidates = lb.models.slice(0, 3).map((e) => e.name);   // top-3 open aliases

// 3. Evaluate those candidates + the benchmarked frontier on YOUR rows.
//    Pass task + items to create the eval set inline, or use an existing set id.
const run = await pa.evals.runs.create({
  task,
  items: [
    { input: "...your contract text...", expected: { effective_date: "2026-01-01" } },
    // ...more rows...
  ],
  models: candidates,           // open candidates (per-task aliases)
  frontier: "benchmarked",      // baselines on this task's leaderboard
  wait: true,                   // block until the run is terminal
});

// 4. Read results (quality + cost), then deploy the model that won on your data
for (const r of [...run.results].sort((a, b) => (b.qualityMean ?? 0) - (a.qualityMean ?? 0))) {
  console.log(r.modelId, r.kind, r.qualityMean, r.meanCostMicroUsd, `n=${r.nSucceeded}`);
}

console.log("eval cost:", run.cost);   // dollar string, floored to cents

const winner = run.results[0].modelId;
const ep = await pa.endpoints.deploy({ task, model: winner, wait: true });
console.log("serving:", ep.id, ep.url);
```

A few notes on the eval call:

- Provide **either** `eval_set=<id>` (an existing set) **or** `task=... +
  items=...` to create one inline. With neither, `create()` raises `ValueError`.
- `frontier=` accepts `None`/`"none"` (no baselines), an explicit list of
  frontier ids, `"all"` (every frontier model for the task), or `"benchmarked"`
  (only those on the task's leaderboard, vision-filtered for document tasks).
  Keyword resolution needs to know the task; with `eval_set=`, the SDK looks the
  task up for you.
- `wait=True` polls until the run reaches `"completed"` or `"failed"`
  (`run.is_terminal`), then returns the final `EvalRun`. For document tasks,
  attach binaries with `evals.sets.upload_document(...)` before running.

For the full eval API (building sets, attaching documents, inline vs. existing
sets, and polling semantics) see [Evaluating models](evaluation.md). For the
discovery primitives in depth, see [Finding the right model](discovery.md).

## Errors at a glance

Every SDK error subclasses `ParetaError`. The status-mapped subclasses let you
branch on what went wrong without inspecting status codes:

| Exception | Status | When |
|---|---|---|
| `AuthenticationError` | 401 | bad or missing key |
| `InsufficientCreditsError` | 402 | org out of credit (top up in the dashboard) |
| `PermissionDeniedError` | 403 | the user lacks permission |
| `NotFoundError` | 404 | unknown task, endpoint, or run |
| `ConflictError` | 409 | seed/legacy endpoint or transient contention |
| `RateLimitError` | 429 | throttled (auto-retried) |
| `EndpointNotReadyError` | 503 | endpoint stopped, cold, or provider down |
| `BadRequestError` | 400/422 | malformed request |
| `APIConnectionError` / `APITimeoutError` | n/a | transport failure (auto-retried) |

**Python**

```python
import pareta

try:
    resp = pa.chat.completions.create(model=ep.id, messages=[{"role": "user", "content": "hi"}])
except pareta.EndpointNotReadyError:
    pa.endpoints.start(ep.id)            # wake a stopped endpoint, then retry
except pareta.InsufficientCreditsError:
    print("Out of credit. Top up in the dashboard.")
except pareta.ParetaError as e:
    print("request failed:", e)
```

**TypeScript**

```typescript
import { EndpointNotReadyError, InsufficientCreditsError, ParetaError } from "pareta";

try {
  const resp = await pa.chat.completions.create({ model: ep.id, messages: [{ role: "user", content: "hi" }] });
} catch (e) {
  if (e instanceof EndpointNotReadyError) {
    await pa.endpoints.start(ep.id);     // wake a stopped endpoint, then retry
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
