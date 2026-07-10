# Response types

Every method that talks to the API hands you back a typed object, not a bare
dict. These objects give you attribute access and autocomplete over the shapes
the API returns: a chat completion's `choices`, a task match's `type`, an eval
run's `cost`. They are thin: each one wraps the raw server JSON and exposes the
fields you actually use as properties.

This page is the field-by-field reference for those objects. For how the methods
that return them work, see [Running inference](../guide/inference.md),
[tasks](./tasks.md), and [Evaluating models](../guide/evaluation.md).

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
    model="auto",
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
| `model` | `str \| None` | The model id on the completion |
| `created` | `int \| None` | Unix timestamp |
| `choices` | `list[Choice]` | One entry per generated choice |
| `usage` | `Usage` | Token counts |

```python
resp = pa.chat.completions.create(
    model="auto",
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
    model="auto",
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
OpenAI-compatible model listing: it returns exactly one entry, `"auto"`, so
any OpenAI-style tooling pointed at Pareta gets a sensible `/models` response
with the one id you send.

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
| `id` | `str \| None` | `"auto"`. Pass straight into `chat.completions.create(model=...)` |
| `owned_by` | `str \| None` | `"pareta"` |
| `created` | `int \| None` | Unix timestamp |

## Discovery types

These come from the `tasks` namespace and name the grading contract before you
send traffic.

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
| `type` | `str \| None` | `"task"`, `"capability"`, `"unsupported"`, or `"none"` |
| `matched` | `bool` | `True` when a high-confidence match was found |
| `chosen` | `TaskMatchCandidate \| None` | The best candidate, or `None` if nothing matched confidently |
| `capability` | `Capability \| None` | The general lane, when `type == "capability"` |
| `candidates` | `list[TaskMatchCandidate]` | Top-K ranked alternates |
| `reasoning` | `str \| None` | The router's rationale (reasoning matcher only) |
| `confidence` | `str \| None` | `"high"` / `"medium"` / `"low"` (reasoning matcher only) |
| `ambiguous` | `bool` | `True` when the top two scores are close |
| `matcher` | `str \| None` | Which strategy answered: `"reason"` (LLM router) or `"keyword"` (fallback) |

```python
m = pa.tasks.match("pull totals and dates out of vendor invoices", top_k=5)
if m.type == "task" and m.chosen:
    print("best:", m.chosen.task_id, m.chosen.score, m.chosen.confidence)
elif m.type == "capability" and m.capability:
    print("capability:", m.capability.id, m.capability.label)
else:
    print(m.type, "—", m.reasoning)         # "unsupported" / "none"
print("via", m.matcher)
```

See [tasks.match](./tasks.md#tasksmatch) for the full matching semantics.

### Capability

The general capability lane a match resolved to — on `TaskMatch.capability` when
`TaskMatch.type == "capability"`.

| Property | Type | Notes |
|---|---|---|
| `id` | `str \| None` | The lane id (`chat`/`coding`/`agentic`/`vision`/`asr`/`tts`) |
| `label` | `str \| None` | Human-readable label |
| `category` | `str \| None` | Catalog category name |
| `category_id` | `str \| None` | Catalog category id |
| `desc` | `str \| None` | One-line description |

### TaskMatchCandidate

An element of `match.candidates` (and the type of `match.chosen`).

| Property | Type | Notes |
|---|---|---|
| `task_id` | `str \| None` | The candidate task's id |
| `score` | `float \| None` | Match score in `[0, 1]` |
| `confidence` | `str \| None` | `"high"`, `"medium"`, or `"low"` |

### FrontierModel

Returned from `evals.frontier_models(task=...)`. A vendor model you can evaluate
against — the baseline `"auto"` is measured by.

| Property | Type | Notes |
|---|---|---|
| `id` | `str \| None` | Vendor model id. Feed into `evals.runs.create(frontier=[...])` |
| `vendor` | `str \| None` | `"openai"`, `"anthropic"`, etc. |
| `vision` | `bool` | `True` if vision-capable |
| `benchmarked` | `bool` | `True` if it is benchmarked on the task. Only meaningful when you passed `task=` |

Frontier ids are shown in the clear because they are public products. The open
specialists auto routes to are not — they never surface as ids.

```python
for fm in pa.evals.frontier_models(task="contract-key-fields"):
    flag = "vision" if fm.vision else "text"
    note = " (benchmarked on this task)" if fm.benchmarked else ""
    print(fm.id, fm.vendor, flag, note)
```

## Audio types

The Speech lanes (`asr`, `tts`) return these from the `audio` namespace.

### Transcription

Returned from `audio.transcriptions(audio, language=...)`. Speech-to-text.

| Property | Type | Notes |
|---|---|---|
| `text` | `str \| None` | The transcript (also `str(transcription)`) |
| `language` | `str \| None` | Detected (or supplied) language |
| `duration_s` | `float \| None` | Input audio length, metered per minute |

```python
t = pa.audio.transcriptions("call.wav")   # path | bytes | base64
print(t.text, t.language, t.duration_s)
```

### Speech

Returned from `audio.speech(text, voice=...)`. Text-to-speech.

| Property | Type | Notes |
|---|---|---|
| `audio` | `bytes` | The synthesized audio, base64-decoded |
| `audio_base64` | `str \| None` | The raw base64 the server returned |
| `sample_rate` | `int \| None` | Sample rate of the audio |
| `duration_s` | `float \| None` | Output audio length, metered per minute |
| `format` | `str \| None` | Container/codec (e.g. `"wav"`) |

`save(path)` writes the decoded bytes to a file and returns `self`.

```python
pa.audio.speech("Hello from Pareta.").save("out.wav")
```

## Evaluation types

These come from the `evals` namespace and carry the cost numbers you compare
`"auto"` against the frontier with.

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
| `candidate_models` | `list[str]` | The candidates evaluated: `"auto"` and any frontier ids |
| `error_detail` | `str \| None` | Failure message when `status == "failed"` |
| `cost_micro_usd` | `int` | Raw total cost in **micro-USD** |
| `cost` | `Decimal` | Billed total in **dollars, floored to cents**. See [money](#money-cost-vs-cost_micro_usd) |
| `results` | `list[EvalResult]` | Per-model aggregates (populated once terminal) |

```python
run = pa.evals.runs.create(
    task="contract-key-fields",
    items=[{"input": "...", "expected": {"effective_date": "2026-01-01"}}],
    models=["auto"],                  # the product under test
    frontier="benchmarked",           # vendor baselines benchmarked on this task
    wait=True,                        # block until terminal
)

if run.status == "failed":
    print("eval failed:", run.error_detail)
else:
    for r in sorted(run.results, key=lambda r: r.quality_mean or 0, reverse=True):
        print(r.model_id, r.kind, r.quality_mean, r.mean_cost_micro_usd, f"n={r.n_succeeded}")
    print("billed:", run.cost, "| raw µUSD:", run.cost_micro_usd)
```

Eval compute is metered against your org balance (both the auto runs and any
frontier baselines). An empty balance raises `InsufficientCreditsError` (402);
top up in the browser, since the SDK never exposes balance or payment.

### EvalResult

One element of `run.results`: a single candidate's aggregate over the run.

| Property | Type | Notes |
|---|---|---|
| `model_id` | `str \| None` | The candidate evaluated: `"auto"` or a frontier vendor id |
| `kind` | `str \| None` | `"frontier"` on vendor baseline rows; unset on `"auto"` rows |
| `quality_mean` | `float \| None` | Mean score in `[0, 1]` |
| `quality_ci_low` | `float \| None` | 95% CI lower bound |
| `quality_ci_high` | `float \| None` | 95% CI upper bound |
| `mean_cost_micro_usd` | `int \| None` | Average per-item cost in **micro-USD** (not floored) |
| `n_succeeded` | `int \| None` | Rows that scored without error |
| `error_count` | `int \| None` | Rows that errored |

The point of a result row is the comparison: read `quality_mean` against the
confidence interval to know whether `"auto"` genuinely matches the frontier on
your data, and `mean_cost_micro_usd` to see what each call costs.

```python
auto_row = next(r for r in run.results if r.model_id == "auto")

for r in run.results:
    if r.kind != "frontier":
        continue
    matches = (
        auto_row.quality_ci_high is not None
        and r.quality_mean is not None
        and auto_row.quality_ci_high >= r.quality_mean
    )
    print(f"{r.model_id}: q={r.quality_mean:.3f} at {r.mean_cost_micro_usd} µUSD/item"
          f" — auto ({auto_row.quality_mean:.3f}) "
          f"{'matches it within the CI' if matches else 'trails it'}")
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
- Per-item **unit rates** stay in micro-USD on purpose:
  `result.mean_cost_micro_usd` (and the `cost_micro_usd` on an
  `auto.compare_frontier()` result). Flooring a fraction-of-a-cent unit rate to
  whole cents would collapse it to zero and erase the auto-vs-frontier
  comparison that is the whole reason you ran the eval.

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
- [tasks](./tasks.md) — `Task` and `TaskMatch` in depth, and the dataset-to-contract flow
- [Evaluating models](../guide/evaluation.md) — building `EvalSet`s, running evals, and reading `EvalRun` cost
- [Core concepts](../guide/core-concepts.md) — the auto story, hidden hardware, and metering, end to end
