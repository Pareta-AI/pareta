# Core concepts

Pareta deploys open-weights models as endpoints, lets you evaluate them on your
own data, and serves OpenAI-compatible inference. This page covers the handful
of ideas the rest of the SDK assumes you understand: **tasks** (the benchmark
catalog), **open vs frontier** models, **per-task aliases**, why **hardware is
hidden**, how **metering** works, and the **discovery funnel** that ties them
together (match a task, read its leaderboard, eval candidates on your data,
deploy the winner).

Every code block below is runnable as written. They all start from a client:

```python
from pareta import Pareta

pa = Pareta.from_env()   # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
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

```python
for task in pa.tasks.list():
    print(task.id, task.default_scorer, "blob" if task.has_blob_input else "text")

# Fetch one task, optionally with sample rows to see its input shape
t = pa.tasks.retrieve("contract-key-fields", examples_n=3)
print(t.id, t.default_scorer, t.has_blob_input)
```

If you do not know the task id, describe the job in plain English and let the
matcher rank candidates:

```python
m = pa.tasks.match("pull totals and dates out of vendor invoices", top_k=5)
if m.matched and m.chosen:
    print("best:", m.chosen.task_id, m.chosen.score, m.chosen.confidence)
else:
    for c in m.candidates:          # ranked alternates to choose from
        print(c.task_id, c.score, c.confidence)
print("ambiguous?", m.ambiguous, "via", m.matcher)
```

`match()` raises `ValueError` on an empty query. The matcher is a deterministic
keyword scorer today; `m.matcher` tells you which strategy answered.

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

To enumerate the frontier roster you can evaluate against, annotated for a
given task, use `evals.frontier_models`:

```python
for fm in pa.evals.frontier_models(task="contract-key-fields"):
    print(fm.id, fm.vendor, "vision" if fm.vision else "text",
          "(on leaderboard)" if fm.benchmarked else "")
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

```python
task = "contract-key-fields"
pick = pa.tasks.recommended(task)          # a per-task alias, e.g. "qwen-1"
ep = pa.endpoints.deploy(task=task, model=pick, wait=True)
print(ep.model)                            # the same alias, echoed back
```

## Hardware is hidden

You never choose a GPU, tensor-parallel degree, quantization scheme, or serving
mode. `endpoints.deploy()` takes a `task` and a `model` (alias, real-callable
id, or the literal `"recommended"`) and nothing about hardware. Pareta resolves
the serving class from its registry.

```python
# No hardware knobs. task + model is the whole decision.
ep = pa.endpoints.deploy(task="contract-key-fields", model="recommended", wait=True)
print(ep.id, ep.status, ep.url)            # ep.id is what you call for inference
```

`deploy()` streams progress. With `wait=True` it blocks and returns the live
`Endpoint` (raising `ParetaError` if the deploy fails). With `wait=False`
(the default) it returns an iterator of `{"event", "data"}` progress events so
you can render a progress bar:

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

Operate and inspect endpoints with `list`, `retrieve`, `start`, `stop`,
`delete`, and `metrics`. See [Deploying endpoints](deploying-endpoints.md) for the full
lifecycle.

```python
for ep in pa.endpoints.list():
    print(ep.id, ep.task, ep.status, "LIVE" if ep.is_live else "")

perf = pa.endpoints.metrics(ep.id).performance()   # p50/p95/p99 latency (raw JSON)
```

## Inference is OpenAI-compatible

Once an endpoint is live, call it through `chat.completions.create`. The
endpoint id (`ep.id`) is the `model`. The request and response match the OpenAI
chat schema, so the official `openai` client works against the same base URL
and key.

```python
resp = pa.chat.completions.create(
    model=ep.id,
    messages=[{"role": "user", "content": "Extract the contract effective date."}],
    temperature=0,                          # extra OpenAI params pass straight through
)
print(resp.choices[0].message.content)
print(resp.usage.total_tokens)
```

Streaming yields `ChatCompletionChunk` objects; the incremental text is on
`chunk.choices[0].delta.content`:

```python
for chunk in pa.chat.completions.create(model=ep.id, messages=[...], stream=True):
    print(chunk.choices[0].delta.content or "", end="")
```

`create()` raises `ValueError` up front if `model` or `messages` is empty. See
[Running inference](./inference.md) for streaming details and the async
iterator form.

## Metering and billing

Both inference and evals are **metered against your organization's balance**.

- **Inference:** a successful `chat.completions.create()` debits the org
  balance.
- **Evals:** `evals.runs.create()` debits for the compute it spends: both the
  open candidates and any frontier baselines you include.
- **Empty balance:** either path raises `InsufficientCreditsError` (HTTP 402).

```python
from pareta import InsufficientCreditsError

try:
    resp = pa.chat.completions.create(model=ep.id, messages=[{"role": "user", "content": "hi"}])
except InsufficientCreditsError:
    print("Top up the org balance in the dashboard, then retry.")
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

```python
print(run.cost)               # Decimal("0.42"): billed dollars, floored to cents
print(run.cost_micro_usd)     # 420715: raw micro-USD
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

See [Error handling](errors-and-retries.md) for the full hierarchy, the `request_id`
attribute for support, and the retry policy.
