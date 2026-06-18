# Response types

Every method that talks to the API hands you back a typed object, not a bare
dict. These objects give you attribute access and autocomplete over the shapes
the API returns: a chat completion's `choices`, an endpoint's `status`, an eval
run's `cost`. They are thin: each one wraps the raw server JSON and exposes the
fields you actually use as properties.

This page is the field-by-field reference for those objects. For how the methods
that return them work, see [Running inference](../guide/inference.md),
[Deploying endpoints](../guide/deploying-endpoints.md),
[Finding the right model](../guide/discovery.md), and
[Evaluating models](../guide/evaluation.md).

## The shared base: every object keeps the raw JSON

All response objects inherit from one base. Two things are true of every object
on this page:

- `.to_dict()` returns the exact JSON the server sent, losslessly. The typed
  properties are a convenience layer over it; nothing is dropped.
- `obj["some_key"]` and `obj.get("some_key", default)` read raw fields directly.
  This is the escape hatch for any field the platform adds before the typed layer
  catches up.

```python
from pareta import Pareta

pa = Pareta.from_env()   # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)

resp = pa.chat.completions.create(
    model="ep_contract_qwen",
    messages=[{"role": "user", "content": "ping"}],
)

resp.choices[0].message.content   # typed access
resp.to_dict()                    # the full raw JSON, lossless
resp["id"]                        # raw-key access for anything not yet typed
```

Properties return `None` (or an empty list) when a field is absent rather than
raising, so reading an optional field is always safe.

## Inference types

These come back from `chat.completions.create` (route `POST /v1/chat/completions`).
Inference is OpenAI-compatible, so the schema matches the OpenAI chat objects.

### ChatCompletion

The non-streaming result of `chat.completions.create(...)`.

| Property | Type | Notes |
|---|---|---|
| `id` | `str \| None` | Completion id |
| `model` | `str \| None` | The model/endpoint id that served the request |
| `created` | `int \| None` | Unix timestamp |
| `choices` | `list[Choice]` | One entry per generated choice |
| `usage` | `Usage` | Token counts |

```python
resp = pa.chat.completions.create(
    model="ep_contract_qwen",
    messages=[{"role": "user", "content": "Extract the effective date."}],
    temperature=0,
)
print(resp.choices[0].message.content)
print(resp.usage.total_tokens)
```

### ChatCompletionChunk

One delta from a streaming completion. Returned (one per SSE event) when you pass
`stream=True`. It has the same schema as `ChatCompletion`; it is a distinct type
purely for hinting. The incremental text lives on `choices[0].delta.content`, not
`choices[0].message`.

```python
for chunk in pa.chat.completions.create(
    model="ep_contract_qwen",
    messages=[{"role": "user", "content": "Summarize this contract."}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

The `or ""` guard matters: the first and last chunks often carry no content (role
preamble, finish marker), so `delta.content` can be `None` mid-stream.

### Choice

One element of `completion.choices`.

| Property | Type | Notes |
|---|---|---|
| `index` | `int \| None` | Position in the choices list |
| `finish_reason` | `str \| None` | `"stop"`, `"length"`, etc. |
| `message` | `Message` | The full message. Populated on **non-streaming** results |
| `delta` | `Message` | The incremental token. Populated on **streaming** chunks |

`message` and `delta` always return a `Message` (empty if absent), so reading
`choice.delta.content` on a non-streaming result, or vice versa, returns `None`
rather than blowing up.

### Message

The content of a `Choice`.

| Property | Type | Notes |
|---|---|---|
| `role` | `str \| None` | `"assistant"`, `"user"`, etc. |
| `content` | `str \| None` | The text |

### Usage

Token accounting on a `ChatCompletion`.

| Property | Type |
|---|---|
| `prompt_tokens` | `int \| None` |
| `completion_tokens` | `int \| None` |
| `total_tokens` | `int \| None` |

## Model listing types

Returned from `models.list()` (route `GET /v1/models`). This is the
OpenAI-compatible model listing: it returns only your deployed endpoints that
have a live inference URL, so you can point any OpenAI-style tooling at Pareta and
get a sensible `/models` response.

### ModelList

| Property | Type |
|---|---|
| `data` | `list[Model]` |

`ModelList` is directly iterable and has a length, so you usually skip `.data`:

```python
models = pa.models.list()
print(len(models))
for m in models:                       # iterates m in models.data
    print(m.id, m.owned_by)
```

### Model

One element of a `ModelList`.

| Property | Type | Notes |
|---|---|---|
| `id` | `str \| None` | Endpoint id. Pass straight into `chat.completions.create(model=...)` |
| `owned_by` | `str \| None` | `"pareta"` or a vendor name |
| `created` | `int \| None` | Unix timestamp |

## Endpoint

Returned from `endpoints.deploy(..., wait=True)`, `endpoints.list()`, and
`endpoints.retrieve(id)`. A deployed open-weights model serving inference.

| Property | Type | Notes |
|---|---|---|
| `id` | `str \| None` | The endpoint id (== `name`). This is what you pass to `chat.completions.create(model=...)` |
| `name` | `str \| None` | Endpoint name |
| `model` | `str \| None` | The **per-task public alias** of the served model, never the real id |
| `status` | `str \| None` | `"live"`, `"starting"`, `"stopped"`, etc. |
| `task` | `str \| None` | The task this endpoint serves |
| `url` | `str \| None` | Inference URL (set once live) |
| `is_live` | `bool` | Convenience: `status == "live"` |

Two platform truths show up here. There is no GPU, quantization, or
tensor-parallel field, because hardware is hidden: you deploy with a task and a
model and Pareta resolves the serving class. And `model` is the per-task alias,
not the underlying checkpoint id; the real id never crosses into the SDK.

```python
ep = pa.endpoints.deploy(task="contract-key-fields", model="recommended", wait=True)
print(ep.id, ep.model, ep.status, ep.url)

if ep.is_live:
    pa.chat.completions.create(model=ep.id, messages=[{"role": "user", "content": "hi"}])
```

`endpoints.metrics(id)` returns a `Metrics` object (not a response type) whose
`.performance()`, `.uptime()`, `.cost()`, `.quality()`, and `.activity()` methods
return raw JSON dicts. Typed wrappers are planned but not yet shipped.

## Discovery types

These come from the `tasks` namespace and power the match-and-rank funnel.

### Task

Returned from `tasks.list()` and `tasks.retrieve(id)`. One benchmarked job.

| Property | Type | Notes |
|---|---|---|
| `id` | `str \| None` | Stable task id, e.g. `"contract-key-fields"` |
| `default_scorer` | `str \| None` | The function that grades model output for this task |
| `has_blob_input` | `bool` | `True` when the task takes documents or images, not just text |

```python
for t in pa.tasks.list():
    print(t.id, t.default_scorer, "doc" if t.has_blob_input else "text")
```

`has_blob_input` tells you whether you will need
`evals.sets.upload_document(...)` to attach binaries when you evaluate on this
task.

### TaskMatch

Returned from `tasks.match(query, top_k=...)`. The ranked result of matching
free-text intent to a task.

| Property | Type | Notes |
|---|---|---|
| `query` | `str \| None` | The query, echoed back |
| `matched` | `bool` | `True` when a high-confidence match was found |
| `chosen` | `TaskMatchCandidate \| None` | The best candidate, or `None` if nothing matched confidently |
| `candidates` | `list[TaskMatchCandidate]` | Top-K ranked alternates |
| `ambiguous` | `bool` | `True` when the top two scores are close |
| `matcher` | `str \| None` | Which strategy answered: `"keyword"` or `"semantic"` |

```python
m = pa.tasks.match("pull totals and dates out of vendor invoices", top_k=5)
if m.matched and m.chosen:
    print("best:", m.chosen.task_id, m.chosen.score, m.chosen.confidence)
else:
    for c in m.candidates:                  # fall back to ranked alternates
        print(c.task_id, c.score, c.confidence)
print("ambiguous?", m.ambiguous, "via", m.matcher)
```

### TaskMatchCandidate

An element of `match.candidates` (and the type of `match.chosen`).

| Property | Type | Notes |
|---|---|---|
| `task_id` | `str \| None` | The candidate task's id |
| `score` | `float \| None` | Match score in `[0, 1]` |
| `confidence` | `str \| None` | `"high"`, `"medium"`, or `"low"` |

### Leaderboard

Returned from `tasks.leaderboard(task_id)`. Open models ranked for a task, with a
single frontier baseline to beat.

| Property | Type | Notes |
|---|---|---|
| `task_id` | `str \| None` | The task |
| `metric` | `str \| None` | What the ranking optimizes, e.g. `"quality"` |
| `cost_unit` | `str \| None` | Cost basis, e.g. `"per_request"` |
| `recommended` | `str \| None` | The deployable model alias Pareta would pick. Pass straight to `endpoints.deploy(model=...)` |
| `models` | `list[LeaderboardEntry]` | Ranked **open** candidates |
| `frontier` | `LeaderboardEntry \| None` | The vendor baseline (savings reference) |

`recommended` is exactly what `endpoints.deploy(model="recommended")` resolves to,
and `tasks.recommended(task_id)` is a shortcut for `leaderboard(task_id).recommended`.

```python
lb = pa.tasks.leaderboard("contract-key-fields")
print("recommended:", lb.recommended, "| metric:", lb.metric, "| unit:", lb.cost_unit)

for e in lb.models:                         # ranked open aliases
    print(e.name, e.kind, e.quality, e.cost_per_request_micro_usd, f"{e.context_k}k")

if lb.frontier:
    print("baseline:", lb.frontier.name, lb.frontier.quality)
```

`tasks.leaderboard()` and `tasks.recommended()` are sync-only today; the async
`AsyncTasks` namespace does not expose them yet.

### LeaderboardEntry

A row of `leaderboard.models` (and the type of `leaderboard.frontier`).

| Property | Type | Notes |
|---|---|---|
| `name` | `str \| None` | Model name. For open models this is the **per-task alias**; for the frontier row it is the vendor id |
| `kind` | `str \| None` | `"open"` or `"frontier"` |
| `quality` | `float \| None` | Quality score in `[0, 1]` |
| `cost_per_request_micro_usd` | `int \| None` | Unit cost in **micro-USD** (not floored). See [money](#money-cost-vs-cost_micro_usd) |
| `context_k` | `int \| None` | Context window, in thousands of tokens |
| `run_mode` | `str \| None` | Backend benchmark context (`"rte"`, `"twostage"`); not a knob you set |

`name` for an open entry is the alias you feed back into `deploy(model=...)` or an
eval run's `models=[...]`. You never translate ids yourself.

### FrontierModel

Returned from `evals.frontier_models(task=...)`. A vendor model you can evaluate
against (the baseline, never something you deploy).

| Property | Type | Notes |
|---|---|---|
| `id` | `str \| None` | Vendor model id. Feed into `evals.runs.create(frontier=[...])` |
| `vendor` | `str \| None` | `"openai"`, `"anthropic"`, etc. |
| `vision` | `bool` | `True` if vision-capable |
| `benchmarked` | `bool` | `True` if it is on the task's leaderboard. Only meaningful when you passed `task=` |

Frontier ids are shown in the clear because they are public products. Open-model
aliases are not.

```python
for fm in pa.evals.frontier_models(task="contract-key-fields"):
    flag = "vision" if fm.vision else "text"
    note = " (on leaderboard)" if fm.benchmarked else ""
    print(fm.id, fm.vendor, flag, note)
```

## Evaluation types

These come from the `evals` namespace and carry the cost numbers you compare
open against frontier with.

### EvalSet

Returned from `evals.sets.create(...)`, `evals.sets.list()`, and
`evals.sets.retrieve(id)`. A reusable evaluation dataset.

| Property | Type | Notes |
|---|---|---|
| `id` | `str \| None` | Eval set id. Pass to `evals.runs.create(eval_set=...)` |
| `task_id` | `str \| None` | The task this set is graded against |
| `name` | `str \| None` | Label (auto-generated if you did not pass one) |
| `item_count` | `int \| None` | Number of rows |
| `scoring_strategy` | `str \| None` | The strategy used to grade rows, e.g. `"extraction"`, `"classification"` |

```python
es = pa.evals.sets.create(
    task="contract-key-fields",
    items=[{"input": "...contract...", "expected": {"effective_date": "2026-01-01"}}],
    name="my contracts v1",
)
print(es.id, es.task_id, es.item_count, es.scoring_strategy)
```

### EvalRun

Returned from `evals.runs.create(...)`, `evals.runs.retrieve(id)`, and
`evals.runs.wait(id)`. The state of an evaluation, including per-model results
once it is terminal. The object wraps the server's `{"run": {...}, "results":
[...]}` envelope and flattens it for you.

| Property | Type | Notes |
|---|---|---|
| `id` | `str \| None` | Run id |
| `eval_set_id` | `str \| None` | The set being evaluated |
| `status` | `str \| None` | `"running"`, `"evaluating"`, `"completed"`, `"failed"` |
| `is_terminal` | `bool` | `True` when `status` is `"completed"` or `"failed"` |
| `candidate_models` | `list[str]` | The model ids (aliases) that were evaluated |
| `error_detail` | `str \| None` | Failure message when `status == "failed"` |
| `cost_micro_usd` | `int` | Raw total cost in **micro-USD** |
| `cost` | `Decimal` | Billed total in **dollars, floored to cents**. See [money](#money-cost-vs-cost_micro_usd) |
| `results` | `list[EvalResult]` | Per-model aggregates (populated once terminal) |

```python
run = pa.evals.runs.create(
    task="contract-key-fields",
    items=[{"input": "...", "expected": {"effective_date": "2026-01-01"}}],
    models=["qwen-1", "mistral-2"],   # open candidates (per-task aliases)
    frontier="benchmarked",           # baselines on this task's leaderboard
    wait=True,                        # block until terminal
)

if run.status == "failed":
    print("eval failed:", run.error_detail)
else:
    for r in sorted(run.results, key=lambda r: r.quality_mean or 0, reverse=True):
        print(r.model_id, r.kind, r.quality_mean, r.mean_cost_micro_usd, f"n={r.n_succeeded}")
    print("billed:", run.cost, "| raw µUSD:", run.cost_micro_usd)
```

Eval compute is metered against your org balance (both the open candidates and
any frontier baselines). An empty balance raises `InsufficientCreditsError` (402);
top up in the browser, since the SDK never exposes balance or payment.

### EvalResult

One element of `run.results`: a single model's aggregate over the run.

| Property | Type | Notes |
|---|---|---|
| `model_id` | `str \| None` | The model evaluated. Open models appear as **per-task aliases** |
| `kind` | `str \| None` | `"open"` or `"frontier"` |
| `quality_mean` | `float \| None` | Mean score in `[0, 1]` |
| `quality_ci_low` | `float \| None` | 95% CI lower bound |
| `quality_ci_high` | `float \| None` | 95% CI upper bound |
| `mean_cost_micro_usd` | `int \| None` | Average per-item cost in **micro-USD** (not floored) |
| `n_succeeded` | `int \| None` | Rows that scored without error |
| `error_count` | `int \| None` | Rows that errored |

The point of a result row is the comparison: read `quality_mean` against the
confidence interval to know whether a cheaper open model genuinely matches the
frontier on your data, and `mean_cost_micro_usd` to see what each call costs.

```python
for r in run.results:
    cheaper_and_as_good = (
        r.kind == "open"
        and r.quality_ci_low is not None
        and r.quality_ci_low >= 0.9
    )
    print(r.model_id, r.kind, f"{r.quality_mean:.3f}",
          f"[{r.quality_ci_low:.3f}, {r.quality_ci_high:.3f}]",
          r.mean_cost_micro_usd, "<-- candidate" if cheaper_and_as_good else "")
```

## Money: `.cost` vs `.cost_micro_usd`

Money on these objects follows one convention (SDK_PLAN §6): the **billed total
is floored to whole cents**, while sub-cent unit rates stay in micro-USD. The SDK
floors rather than rounds, so it never overstates a charge.

Three fields, two representations:

- `run.cost` is a `Decimal` in **dollars, floored to cents**. A 5 µUSD run reads
  `Decimal("0.00")`; a 420,715 µUSD run reads `Decimal("0.42")`. This is what the
  org is billed.
- `run.cost_micro_usd` is the **raw integer** in micro-USD. `1_000_000` = `$1.00`.
  Use it when you need the exact charge below cent precision.
- Per-item and per-request **unit rates** stay in micro-USD on purpose:
  `result.mean_cost_micro_usd` and `entry.cost_per_request_micro_usd`. Flooring a
  fraction-of-a-cent unit rate to whole cents would collapse it to zero and erase
  the open-vs-frontier comparison that is the whole reason you ran the eval.

```python
from decimal import Decimal

print(run.cost)                       # Decimal("0.42") — billed dollars, floored
print(run.cost_micro_usd)             # 420715 — raw micro-USD
assert run.cost == Decimal("0.42")

# Convert any micro-USD unit rate to dollars yourself when you want to display it:
mean = run.results[0].mean_cost_micro_usd        # e.g. 850 µUSD per item
print(f"${mean / 1_000_000:.6f} per item")       # $0.000850 per item
```

Both inference and evals debit the org balance on success; an empty balance
raises `InsufficientCreditsError`. The SDK only ever consumes credit and surfaces
the 402; topping up is browser-only.

## See also

- [Running inference](../guide/inference.md) — `ChatCompletion`, streaming chunks, and the async iterator form
- [Deploying endpoints](../guide/deploying-endpoints.md) — the `Endpoint` lifecycle and deploy progress events
- [Finding the right model](../guide/discovery.md) — `Task`, `TaskMatch`, and `Leaderboard` in depth
- [Evaluating models](../guide/evaluation.md) — building `EvalSet`s, running evals, and reading `EvalRun` cost
- [Core concepts](../guide/core-concepts.md) — aliases, hidden hardware, and metering, end to end
