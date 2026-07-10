# tasks

`client.tasks` is the catalog layer: the benchmarked jobs `model="auto"` routes
across. You never pick a model — "which model?" is the question auto answers
per request — but the catalog is how you ask, before sending traffic, whether
Pareta covers your job at all:

- `match` is the "can Pareta do X?" surface: it turns a plain-English
  description of your job into an answer — a benchmarked task, a general
  capability lane, or `"unsupported"`.
- `list` / `retrieve` browse the benchmark catalog and a task's schema.

Two platform facts run through everything here:

- **Task ids feed evals, not inference.** Inference is always
  `chat.completions.create(model="auto", ...)`; it takes no task id. A matched
  task id like `"contract-key-fields"` is what you hand to
  [`evals.runs.create(task=...)`](./evals.md) to prove auto against the
  frontier on your own rows.
- **Catalog reads are free.** `list`, `retrieve`, and `match` are not metered.
  The meter only starts when you run compute (inference and eval runs), which
  is debited against your org balance. See [Errors](exceptions.md) for
  `InsufficientCreditsError`.

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

Turns a free-text description of your intent into a single match. The matcher is
an LLM reasoning router: it reasons about intent (not keyword overlap) and maps
the query to exactly one of three outcomes — a benchmarked task, a general
**capability** lane (chat, coding, agentic, vision, speech-to-text,
text-to-speech), or `"unsupported"`. If the router is unavailable it falls back
to a deterministic keyword scorer.

- `query` (required): free-text intent. Raises `ValueError` if empty or
  whitespace-only.
- `top_k` (default `5`): how many ranked candidates the keyword fallback returns.
  The reasoning router returns a single chosen match (it does not rank).

Returns a [`TaskMatch`](#taskmatch). Branch on `match.type` to route every
outcome; the reasoning router also fills `match.reasoning`, `match.confidence`,
and `match.capability` (a typed [`Capability`](types.md#capability)).

```python
match = pa.tasks.match("pull line items and totals out of vendor invoices")

if match.type == "task":
    task_id = match.chosen.task_id          # the best task
    print(f"matched {task_id} via {match.matcher} "
          f"(confidence={match.confidence})")
elif match.type == "capability":
    cap = match.capability                  # typed Capability
    print(f"general lane: {cap.label} ({cap.id})")
else:                                       # "unsupported" / "none"
    print(f"{match.type}: {match.reasoning}")
    for cand in match.candidates:           # keyword fallback may rank some
        print(f"  {cand.task_id}  score={cand.score}  {cand.confidence}")
```

A robust pattern handles both the no-match and the ambiguous cases rather than
blindly trusting `chosen`:

```python
match = pa.tasks.match("classify support tickets by urgency")

if not match.matched:
    raise SystemExit(f"no task matched; closest: "
                     f"{[c.task_id for c in match.candidates]}")
if match.ambiguous:
    # Top two scores are close: a good moment to ask the user to disambiguate.
    print("ambiguous, top candidates:",
          [(c.task_id, round(c.score or 0, 2)) for c in match.candidates[:2]])

task_id = match.chosen.task_id
```

A matched `task_id` goes to [`evals.runs.create(task=task_id, ...)`](./evals.md)
to prove auto on your own rows; inference itself stays `model="auto"` — there is
nothing to switch once you know the job is covered.

---

## tasks.retrieve

```python
def retrieve(self, task_id: str, *, examples_n: int | None = None) -> Task
```

**Route:** `GET /v1/tasks/{task_id}`

Fetches a single task's schema. The field that matters most is `has_blob_input`:
`True` means the task takes documents or images (PDFs, scans), which determines
how you build eval sets and which frontier models can run it (vision-capable
only).

- `examples_n` (optional): request N example items from the task. The typed layer
  surfaces `id`, `default_scorer`, and `has_blob_input`; reach the examples
  through the raw record with `task.to_dict()`.

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

Returns every benchmark task in the catalog as a `list[Task]`. Use this to browse
when you do not have a free-text query to `match`.

```python
for task in pa.tasks.list():
    kind = "document" if task.has_blob_input else "text"
    print(f"  {task.id:<28} {kind:<10} scorer={task.default_scorer}")
```

---

## A full discovery pass

End to end: intent in, a benchmarked task out, proven on your own rows — while
inference stays `model="auto"` throughout.

```python
from pareta import Pareta

pa = Pareta.from_env()

# 1. intent -> task
match = pa.tasks.match("extract key fields from contracts")
if not match.matched:
    raise SystemExit(f"no task matched: {[c.task_id for c in match.candidates]}")
task_id = match.chosen.task_id

# 2. inspect the task (document task? which scorer?)
task = pa.tasks.retrieve(task_id)
print(f"task={task.id}  scorer={task.default_scorer}  blob={task.has_blob_input}")

# 3. prove it: benchmark "auto" against the frontier on your own rows
run = pa.evals.runs.create(
    task=task_id,
    items=[{"input": "…", "expected": {"effective_date": "2026-01-01"}}],
    models=["auto"],
    frontier="benchmarked",
    wait=True,
)
print("billed:", run.cost)

# production is the same call you started with: model="auto"
```

There is nothing to switch on at the end of this pass: production traffic is
the same `chat.completions.create(model="auto", ...)` call, and the eval is the
proof it holds up on your data. To pick the vendor baselines to measure
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
        print(f"{len(catalog)} tasks in the catalog")

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
| `has_blob_input` | `bool` | `True` if the task takes documents/images (vision tasks) |

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
