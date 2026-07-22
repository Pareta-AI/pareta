# tasks

`client.tasks` is the **grading-contract directory** for evals. A task names
how a dataset is scored: the input/output shape your rows must follow and the
scorer that grades outputs against your labels (field-F1 for extraction,
nDCG@10 for ranking, WER for transcripts, a judge panel for open-ended text).

You never need a task for inference. Production traffic is
`chat.completions.create(model="auto", ...)` — it takes no task id, and every
routing decision happens on Pareta's side. You need a task in exactly one
moment: **when you benchmark on your own data**, because grading requires a
declared contract — [`evals.runs.create(task=...)`](./evals.md) uses it to
validate your rows and score every candidate the same way.

- `match` maps a plain-English description of your dataset to the right
  right scoring for your data, so you don't read a scorer list.
- `list` / `retrieve` browse the contracts and a contract's row schema.

Catalog reads are free: `list`, `retrieve`, and `match` are not metered. The
meter starts when you run compute (inference and eval runs). See
[Errors](exceptions.md) for `InsufficientCreditsError`.

All snippets assume:

```python
from pareta import Pareta

pa = Pareta.from_env()   # reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

---

## tasks.match

```python
def match(self, query: str, *, top_k: int = 5) -> TaskMatch
```

**Route:** `POST /v1/tasks/match`

Turns a free-text description of your data or job into the task that scores it
that fits it. The matcher is an LLM reasoning router: it reasons about intent
(not keyword overlap). If the router is unavailable it falls back to a
deterministic keyword scorer.

- `query` (required): free-text description, e.g. `"vendor invoices with
  labeled line items and totals"`. Raises `ValueError` if empty or
  whitespace-only.
- `top_k` (default `5`): how many ranked candidates the keyword fallback
  returns. The reasoning router returns a single chosen match (it does not
  rank).

Returns a [`TaskMatch`](#taskmatch). Read `match.type` for the outcome:

- `"task"` — Pareta knows how to score this; `.chosen.task_id` names it.
- `"capability"` — the job is a general lane (chat, coding, vision, speech,
  retrieval) rather than a labeled-dataset job; `.capability` describes it.
  General lanes have judge- or metric-scored general tasks when you want to
  benchmark them anyway.
- `"unsupported"` / `"none"` — nothing in the catalog fits the description.
  This is a statement about *scoring*, not about serving: generation work
  can always go to `model="auto"`.

```python
match = pa.tasks.match("pull line items and totals out of vendor invoices")

if match.type == "task":
    task_id = match.chosen.task_id          # how it will be scored
    print(f"grade with {task_id} via {match.matcher} "
          f"(confidence={match.confidence})")
elif match.type == "capability":
    print(f"general lane: {match.capability.label}")
else:
    print(f"{match.type}: {match.reasoning}")
```

A robust pattern handles the no-match and ambiguous cases rather than blindly
trusting `chosen`:

```python
match = pa.tasks.match("classify support tickets by urgency")

if not match.matched:
    raise SystemExit(f"no contract matched; closest: "
                     f"{[c.task_id for c in match.candidates]}")
if match.ambiguous:
    # Top two scores are close: a good moment to ask the user to disambiguate.
    print("ambiguous, top candidates:",
          [(c.task_id, round(c.score or 0, 2)) for c in match.candidates[:2]])

task_id = match.chosen.task_id
```

The matched `task_id` goes to
[`evals.runs.create(task=task_id, ...)`](./evals.md); inference itself stays
`model="auto"` — there is nothing to switch.

---

## tasks.retrieve

```python
def retrieve(self, task_id: str, *, examples_n: int | None = None) -> Task
```

**Route:** `GET /v1/tasks/{task_id}`

Fetches a single contract's row schema. The field that matters most is
`has_blob_input`: `True` means the rows carry documents or images (PDFs,
scans), which determines how you build eval sets and which frontier baselines
can run them (vision-capable only).

- `examples_n` (optional): request N example rows from the task's bundled
  golden set — the fastest way to see the exact input/expected shape your
  rows must follow. The typed layer surfaces `id`, `default_scorer`, and
  `has_blob_input`; reach the examples through the raw record with
  `task.to_dict()`.

Returns a [`Task`](#task).

```python
task = pa.tasks.retrieve(task_id, examples_n=3)
print(task.id, task.default_scorer, "blob_input=", task.has_blob_input)

# examples come back on the raw record:
examples = task.to_dict().get("examples", [])
```

---

## tasks.list

```python
def list(self) -> list[Task]
```

**Route:** `GET /v1/tasks`

Returns the full catalog as a `list[Task]`. Use this to browse when you
do not have a free-text query for `match`.

```python
for task in pa.tasks.list():
    kind = "document" if task.has_blob_input else "text"
    print(f"  {task.id:<28} {kind:<10} scorer={task.default_scorer}")
```

---

## From dataset to proof

End to end: a description of your data in, the right scoring out, `"auto"`
proven against the frontier on your own rows — while inference stays
`model="auto"` throughout.

```python
from pareta import Pareta

pa = Pareta.from_env()

# 1. dataset description -> how it will be scored
match = pa.tasks.match("extract key fields from contracts")
if not match.matched:
    raise SystemExit(f"no contract matched: {[c.task_id for c in match.candidates]}")
task_id = match.chosen.task_id

# 2. inspect the contract (document rows? which scorer?)
task = pa.tasks.retrieve(task_id)
print(f"task={task.id}  scorer={task.default_scorer}  blob={task.has_blob_input}")

# 3. the proof: benchmark "auto" against the frontier on your own rows
run = pa.evals.runs.create(
    prompt="extract the effective date from each contract",
    task=task_id,   # pinned from the match above
    items=[{"input": {"contract_text": "…"}, "expected_output": {"effective_date": "2026-01-01"}}],
    models=["auto"],
    frontier="benchmarked",
    wait=True,
)
print("billed:", run.cost)

# production is the same call you started with: model="auto"
```

There is nothing to switch on at the end of this pass: production traffic is
the same `chat.completions.create(model="auto", ...)` call, and the eval is
the proof it holds up on your data. To pick the vendor baselines to measure
against, see `evals.frontier_models` in [evals](./evals.md).

---

## Async

`AsyncTasks` mirrors the sync surface. Every method is `async def` and awaited:

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        match = await pa.tasks.match("extract key fields from contracts")
        if not match.matched:
            return
        task = await pa.tasks.retrieve(match.chosen.task_id)
        print(task.id, task.default_scorer, task.has_blob_input)

        catalog = await pa.tasks.list()
        print(f"{len(catalog)} tasks")

asyncio.run(main())
```

See the [async guide](../guide/async.md) for the full sync-vs-async story.

---

## Response models

Every response object keeps the raw server JSON: call `.to_dict()` (or index it
like a dict) to reach any field the typed layer does not surface yet.

### Task

From `GET /v1/tasks` and `GET /v1/tasks/{id}`.

| Field | Type | Notes |
|---|---|---|
| `id` | `str \| None` | Task id, e.g. `"contract-key-fields"` |
| `default_scorer` | `str \| None` | The scorer used to grade outputs on this task |
| `has_blob_input` | `bool` | `True` if the rows carry documents/images (vision tasks) |

### TaskMatch

From `POST /v1/tasks/match`.

| Field | Type | Notes |
|---|---|---|
| `query` | `str \| None` | The echoed query |
| `type` | `str \| None` | `"task"`, `"capability"`, `"unsupported"`, or `"none"` |
| `matched` | `bool` | A high-confidence task was found |
| `chosen` | `TaskMatchCandidate \| None` | The best candidate, or `None` if nothing cleared the bar |
| `capability` | `Capability \| None` | The general lane, when `type == "capability"` |
| `candidates` | `list[TaskMatchCandidate]` | The top-`top_k` ranked alternates |
| `reasoning` | `str \| None` | Why the router picked this match (reasoning matcher only) |
| `confidence` | `str \| None` | `"high"` / `"medium"` / `"low"` (reasoning matcher only) |
| `ambiguous` | `bool` | `True` when the top two scores are close |
| `matcher` | `str \| None` | Which matcher answered: `"reason"` (LLM router) or `"keyword"` (fallback) |

See [`Capability`](types.md#capability) for the capability lane fields (`id`,
`label`, `category`, `category_id`, `desc`).

### TaskMatchCandidate

| Field | Type | Notes |
|---|---|---|
| `task_id` | `str \| None` | The candidate task id |
| `score` | `float \| None` | Match score in `[0, 1]` |
| `confidence` | `str \| None` | `"high"`, `"medium"`, or `"low"` |

---

See also: [evals](./evals.md) · [inference](../guide/inference.md) ·
[errors](exceptions.md) · [core concepts](../guide/core-concepts.md)
