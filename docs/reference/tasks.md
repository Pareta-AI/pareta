# tasks

`client.tasks` is the catalog layer. Before you deploy or evaluate anything you
need two things: a **task** (which benchmark you are solving) and a **model**
(which model to deploy or measure). `tasks` resolves both for you:

- `list` / `retrieve` browse the benchmark catalog and a task's schema.
- `match` turns a plain-English description of your job into ranked candidate
  tasks.
- `leaderboard` / `recommended` rank the models scored on a task and hand you the
  deployable pick.

Two platform facts run through everything here:

- **Models are per-task aliases.** Leaderboard rows, the `recommended` pick, and
  eval result `model_id`s are public aliases like `qwen-1` or `recommended`,
  never the underlying open-weights ids. You pass the alias straight back into
  [`endpoints.deploy(model=...)`](./endpoints.md) or
  [`evals.runs.create(models=[...])`](./evals.md), and Pareta resolves the real
  model and the hardware. There is no GPU, quantization, or run-mode knob
  anywhere in this flow.
- **Catalog reads are free.** `list`, `retrieve`, `match`, `leaderboard`, and
  `recommended` are not metered. The meter only starts when you run compute
  (inference and eval runs), which is debited against your org balance. See
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

## tasks.leaderboard

```python
def leaderboard(self, task_id: str) -> Leaderboard
```

**Route:** `GET /v1/tasks/{task_id}/leaderboard`

Returns the models scored on a task, ranked by quality, with each model's
per-request cost. This is how you choose between open models and read, concretely,
how far below the frontier the cost sits.

Returns a [`Leaderboard`](#leaderboard).

```python
board = pa.tasks.leaderboard(task_id)

print(f"metric={board.metric}  cost_unit={board.cost_unit}")
print(f"recommended: {board.recommended}")

for entry in board.models:
    cost = entry.cost_per_request_micro_usd or 0
    print(f"  {entry.name:<16} {entry.kind:<8} "
          f"quality={entry.quality:.3f}  "
          f"${cost / 1_000_000:.6f}/req  ctx={entry.context_k}k")

if board.frontier:
    f = board.frontier
    print(f"frontier baseline: {f.name}  quality={f.quality:.3f}  "
          f"${(f.cost_per_request_micro_usd or 0) / 1_000_000:.6f}/req")
```

`board.recommended` is exactly what `endpoints.deploy(model="recommended")`
resolves to: the curated pick, or the top-ranked open model if there is no
curated one. Pass it straight to `deploy(model=...)`.

> **Cost is in micro-USD here, on purpose.** Per-request rates are sub-cent, so
> the leaderboard keeps the raw `cost_per_request_micro_usd` integer
> (1,000,000 micro-USD = $1.00). Flooring to whole cents, which is how billed
> **totals** like `run.cost` behave (see [evals](./evals.md)), would erase the
> open-vs-frontier comparison. Divide by 1,000,000 to display dollars.

---

## tasks.recommended

```python
def recommended(self, task_id: str) -> str | None
```

Convenience wrapper over `leaderboard(task_id).recommended`. Returns the
deployable model alias Pareta recommends for the task (or `None` if the task has
no ranked models yet).

```python
model = pa.tasks.recommended(task_id)        # e.g. "qwen-1" or "recommended"
ep = pa.endpoints.deploy(task=task_id, model=model, wait=True)
print(ep.id, ep.status)
```

Passing `model="recommended"` to `deploy` does the same resolution server-side,
so `recommended` is mainly useful when you want to **see** the pick (log it, show
it, gate on it) before committing to a deploy.

> **Sync only, for now.** `leaderboard` and `recommended` live on the sync `Tasks`
> resource. `AsyncTasks` has `list`, `retrieve`, and `match`; the ranking methods
> land for async in a later slice. From async code, either call them on a
> short-lived sync `Pareta` or run them in a thread.

---

## A full discovery pass

End to end: intent in, recommended open model plus the frontier gap out, ready to
hand to a deploy or an eval.

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

# 3. task -> recommended open model + the open-vs-frontier quality gap
board = pa.tasks.leaderboard(task_id)
pick = board.recommended
frontier_q = board.frontier.quality if board.frontier else None
print(f"recommend={pick}  frontier_quality={frontier_q}")

# now: deploy `pick` (endpoints.deploy), or eval it vs the frontier on your data.
```

From here you either deploy the recommended model
([endpoints](./endpoints.md)) or run it head to head against the frontier on your
own data ([evals](./evals.md)). To pick the vendor baselines to measure against,
see `evals.frontier_models` in [evals](./evals.md).

---

## Async

`AsyncTasks` mirrors the sync surface for the catalog reads. Every method is
`async def` and awaited:

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

`AsyncTasks` does **not** expose `leaderboard` or `recommended` yet. Call those on
a sync `Pareta` (they are non-blocking catalog reads) or run them in a thread. See
the [async guide](../guide/async.md) for the full sync-vs-async story.

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

### Leaderboard

From `GET /v1/tasks/{id}/leaderboard`.

| Field | Type | Notes |
|---|---|---|
| `task_id` | `str \| None` | The task this board ranks |
| `metric` | `str \| None` | What `quality` measures, e.g. `"quality"` |
| `cost_unit` | `str \| None` | Cost unit, e.g. `"per_request"` |
| `recommended` | `str \| None` | The deployable model alias to pass to `deploy(model=...)` |
| `models` | `list[LeaderboardEntry]` | The ranked entries |
| `frontier` | `LeaderboardEntry \| None` | The vendor baseline this task is measured against |

### LeaderboardEntry

| Field | Type | Notes |
|---|---|---|
| `name` | `str \| None` | Model name / alias |
| `kind` | `str \| None` | `"open"` or `"frontier"` |
| `quality` | `float \| None` | Quality score in `[0, 1]` |
| `cost_per_request_micro_usd` | `int \| None` | Raw unit cost in micro-USD (not floored) |
| `context_k` | `int \| None` | Context window in thousands of tokens |
| `run_mode` | `str \| None` | Backend-provided context (`"rte"` / `"twostage"`); not a user knob |

---

See also: [endpoints](./endpoints.md) · [evals](./evals.md) ·
[inference](../guide/inference.md) · [errors](exceptions.md) ·
[discovery guide](../guide/discovery.md)
