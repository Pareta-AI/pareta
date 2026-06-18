# Finding the right model

Before you deploy anything, you pick a **task** and a **model**. Pareta does both
for you from the SDK:

1. **Match** a free-text description of what you want to do to a benchmark task
   (`tasks.match`).
2. **Rank** the models on that task by quality and cost, and read off the
   recommended pick (`tasks.leaderboard`, `tasks.recommended`).
3. **List** the frontier (vendor) baselines you can measure that pick against
   (`evals.frontier_models`).

This is the discovery loop: intent -> task -> recommended open model + frontier
baseline. From there you either deploy the recommended model
([Deploying endpoints](deploying-endpoints.md)) or run it head to head against the
frontier on your own data ([Evaluating models](evaluation.md)).

Two platform facts shape everything below:

- **Models are per-task aliases.** Leaderboard rows, recommended picks, and
  result `model_id`s are public aliases like `qwen-1` or `recommended`, never the
  underlying open-weights ids. You pass the alias straight back into
  `endpoints.deploy(model=...)` or `evals.runs.create(models=[...])` - Pareta
  resolves the real model and the hardware. There is no GPU or quantization knob
  anywhere in this flow.
- **Frontier (vendor) ids are in the clear.** OpenAI/Anthropic/etc. model ids
  come back as real ids, because they are the baseline you are paying to beat.

All snippets assume:

```python
from pareta import Pareta

pa = Pareta.from_env()   # reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

---

## 1. Match intent to a task

`tasks.match(query, top_k=5)` turns a plain-English description into ranked
candidate tasks. The matcher is a deterministic keyword scorer (with a semantic
backstop on the backend), so the same query returns the same ranking.

```python
match = pa.tasks.match("pull line items and totals out of vendor invoices")

if match.matched:
    task_id = match.chosen.task_id          # the best task
    print(f"matched {task_id} via {match.matcher} "
          f"(confidence={match.chosen.confidence})")
else:
    # No high-confidence hit - show the user the ranked alternates.
    for cand in match.candidates:
        print(f"  {cand.task_id}  score={cand.score:.2f}  {cand.confidence}")
```

`match` returns a [`TaskMatch`](#taskmatch):

- `matched: bool` - a high-confidence task was found.
- `chosen: TaskMatchCandidate | None` - the best candidate, or `None` if nothing
  cleared the bar.
- `candidates: list[TaskMatchCandidate]` - the top-`top_k` ranked alternates
  (each has `task_id`, `score` in `[0, 1]`, and `confidence` of
  `"high"`/`"medium"`/`"low"`).
- `ambiguous: bool` - `True` when the top two scores are close. A good prompt to
  ask the user to disambiguate.
- `matcher: str | None` - which matcher fired (`"keyword"` or `"semantic"`).

A robust pattern handles the no-match and ambiguous cases instead of blindly
trusting `chosen`:

```python
match = pa.tasks.match("classify support tickets by urgency")

if not match.matched:
    raise SystemExit(f"no task matched; closest: "
                     f"{[c.task_id for c in match.candidates]}")
if match.ambiguous:
    print("ambiguous - top candidates:",
          [(c.task_id, round(c.score or 0, 2)) for c in match.candidates[:2]])

task_id = match.chosen.task_id
```

`match` raises `ValueError` if `query` is empty or whitespace.

### Inspecting the task

Once you have a `task_id`, `tasks.retrieve` gives you the task's schema. The key
field is `has_blob_input`: `True` means the task takes documents or images (PDFs,
scans), which determines how you build eval sets and which frontier models can
run it.

```python
task = pa.tasks.retrieve(task_id, examples_n=3)
print(task.id, task.default_scorer, "blob_input=", task.has_blob_input)
```

- `default_scorer: str | None` - the scorer used to grade outputs on this task.
- `has_blob_input: bool` - the task handles documents/images.
- `examples_n` (optional) - ask for N example items so you can see the input
  shape; pulled from the raw record via `task.to_dict()`.

To browse the whole catalog instead of matching, use `pa.tasks.list()`, which
returns `list[Task]`.

---

## 2. Rank the models on a task

`tasks.leaderboard(task_id)` returns the models scored on a task, ranked by
quality, with the per-request cost for each. This is how you choose between open
models and see, concretely, how far below the frontier the cost sits.

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

`leaderboard` returns a [`Leaderboard`](#leaderboard):

- `recommended: str | None` - the deployable model alias Pareta recommends for
  this task. This is exactly what `endpoints.deploy(model="recommended")`
  resolves to. Pass it straight to `deploy(model=...)`.
- `models: list[LeaderboardEntry]` - the ranked entries. Each `LeaderboardEntry`
  has `name` (the alias / id), `kind` (`"open"` or `"frontier"`),
  `quality` in `[0, 1]`, `cost_per_request_micro_usd` (raw micro-USD,
  **not** floored), and `context_k` (context window in thousands).
- `frontier: LeaderboardEntry | None` - the vendor baseline this task is measured
  against, so you can read the open-vs-frontier gap directly.
- `metric` / `cost_unit` - what `quality` and the cost are measured in (e.g.
  `"quality"` and `"per_request"`).

> **Cost is in micro-USD here, on purpose.** Per-request rates are sub-cent, so
> the leaderboard keeps the raw `cost_per_request_micro_usd` integer
> (1,000,000 micro-USD = $1.00). Flooring to whole cents - which is how billed
> **totals** like `run.cost` work, see [Evaluating models](evaluation.md) - would
> erase the open-vs-frontier comparison. Divide by 1,000,000 to display dollars.

### The shortcut: `recommended`

If you only want the deployable pick and don't need the full ranking,
`tasks.recommended(task_id)` is a convenience wrapper over
`leaderboard(task_id).recommended`:

```python
model = pa.tasks.recommended(task_id)        # e.g. "qwen-1" or "recommended"
ep = pa.endpoints.deploy(task=task_id, model=model, wait=True)
print(ep.id, ep.status)
```

Passing `model="recommended"` to `deploy` does the same resolution server-side,
so `pa.tasks.recommended(task_id)` is mainly useful when you want to **see** the
pick (log it, show it, gate on it) before committing to a deploy.

> **Sync only, for now.** `leaderboard` and `recommended` live on the sync
> `Tasks` resource. `AsyncTasks` has `list`, `retrieve`, and `match`; the ranking
> methods land for async in a later slice. From async code, either call them on a
> short-lived sync `Pareta` or run them in a thread.

---

## 3. List the frontier baselines to eval against

Picking the recommended open model is the start; the point of Pareta is showing
it holds up against the frontier at a fraction of the cost. `evals.frontier_models`
returns the vendor roster you can put in an eval run as baselines.

```python
roster = pa.evals.frontier_models(task=task_id)

for fm in roster:
    flags = []
    if fm.vision:
        flags.append("vision")
    if fm.benchmarked:
        flags.append("benchmarked")
    print(f"  {fm.id:<28} {fm.vendor:<10} {' '.join(flags)}")
```

Each entry is a [`FrontierModel`](#frontiermodel):

- `id: str | None` - the real vendor model id. Pass these into
  `evals.runs.create(frontier=[...])`.
- `vendor: str | None` - `"openai"`, `"anthropic"`, etc.
- `vision: bool` - the model can take images/documents.
- `benchmarked: bool` - the model sits on this task's leaderboard. Only populated
  when you pass `task=`.

**Passing `task=` matters.** Without it you get the full roster, unannotated.
With it, Pareta annotates `benchmarked` and filters the roster by capability - for a document task (`has_blob_input == True`) that means vision-capable models
only, so you won't pick a baseline that physically cannot read the input.

```python
# All frontier models, no task context (no benchmarked flag, no filtering)
everything = pa.evals.frontier_models()

# Scoped to a document task: vision-filtered + benchmarked-annotated
for_task = pa.evals.frontier_models(task=task_id)
```

### Feeding the roster into a run

You can pass explicit frontier ids, or let the SDK resolve a roster keyword for
you. These two are equivalent when the keyword is `"benchmarked"`:

```python
# Explicit: filter the roster yourself
ids = [fm.id for fm in pa.evals.frontier_models(task=task_id) if fm.benchmarked]
run = pa.evals.runs.create(
    eval_set="es_…",
    models=[pa.tasks.recommended(task_id)],   # the open candidate(s)
    frontier=ids,                             # explicit list of vendor ids
    wait=True,
)

# Keyword: the SDK fetches + filters the roster for you
run = pa.evals.runs.create(
    eval_set="es_…",
    models=[pa.tasks.recommended(task_id)],
    frontier="benchmarked",                   # "all" | "benchmarked" | "none" | [ids]
    wait=True,
)
```

The `frontier=` keyword resolves SDK-side before the request is sent:

| Value | Resolves to |
|---|---|
| `None` or `"none"` | no baselines (`[]`) |
| `["id1", "id2"]` | the explicit list, passed through |
| `"all"` | every model from `frontier_models(task=...)` |
| `"benchmarked"` | only roster models with `benchmarked == True` |

When you use `"all"`/`"benchmarked"` the SDK needs to know the task: it uses the
`task=` you passed to `runs.create`, else looks it up from the `eval_set`'s task.
If it can't determine the task it raises `ValueError`; an unrecognized string
keyword raises `ValueError` too. See [Evaluating models](evaluation.md) for the full
run lifecycle, results, and cost.

---

## A full discovery pass

End to end: intent in, recommended open model + a benchmarked frontier baseline
out, ready to hand to a deploy or an eval.

```python
from pareta import Pareta

pa = Pareta.from_env()

# 1. intent -> task
match = pa.tasks.match("extract key fields from contracts")
if not match.matched:
    raise SystemExit(f"no task matched: {[c.task_id for c in match.candidates]}")
task_id = match.chosen.task_id

# 2. task -> recommended open model + the open-vs-frontier gap
board = pa.tasks.leaderboard(task_id)
pick = board.recommended
gap = (board.frontier.quality if board.frontier else None)
print(f"task={task_id}  recommend={pick}  frontier_quality={gap}")

# 3. the vendor baselines worth measuring against (vision-filtered, annotated)
baselines = [fm.id for fm in pa.evals.frontier_models(task=task_id) if fm.benchmarked]
print(f"baselines: {baselines}")

# now: deploy `pick`, or eval `pick` vs `baselines` on your own data.
```

Metering note: discovery itself (`match`, `leaderboard`, `recommended`,
`frontier_models`) is free - these are catalog reads. The meter starts when you
actually run compute: inference via `chat.completions.create` and eval runs via
`evals.runs.create` are debited against your org balance, and both raise
`InsufficientCreditsError` (402) on an empty balance. Top-up is browser-only; the
SDK never exposes balance or payment.

---

## Reference

### `tasks.match(query, *, top_k=5) -> TaskMatch`
Free-text intent to ranked candidate tasks. Raises `ValueError` on an empty
query. Deterministic keyword matcher (semantic backstop on the backend).

### `tasks.retrieve(task_id, *, examples_n=None) -> Task`
A task's schema: `id`, `default_scorer`, `has_blob_input`. `examples_n` requests
N example items (read via `task.to_dict()`).

### `tasks.leaderboard(task_id) -> Leaderboard`
Models ranked by quality/cost for a task, plus the `recommended` deployable alias
and the `frontier` baseline. Sync only.

### `tasks.recommended(task_id) -> str | None`
Convenience for `leaderboard(task_id).recommended` - the model alias to pass to
`endpoints.deploy(model=...)`. Sync only.

### `evals.frontier_models(task=None) -> list[FrontierModel]`
The vendor frontier roster. With `task=`, each entry is `benchmarked`-annotated
and the roster is capability-filtered (vision-only for document tasks). Feed `id`s
into `evals.runs.create(frontier=[...])`.

#### `TaskMatch`
`query`, `matched: bool`, `chosen: TaskMatchCandidate | None`,
`candidates: list[TaskMatchCandidate]`, `ambiguous: bool`, `matcher: str | None`.
Each `TaskMatchCandidate` has `task_id`, `score` (`[0, 1]`), `confidence`
(`"high"`/`"medium"`/`"low"`).

#### `Leaderboard`
`task_id`, `metric`, `cost_unit`, `recommended: str | None`,
`models: list[LeaderboardEntry]`, `frontier: LeaderboardEntry | None`. Each
`LeaderboardEntry`: `name`, `kind` (`"open"`/`"frontier"`), `quality` (`[0, 1]`),
`cost_per_request_micro_usd` (raw, not floored), `context_k`.

#### `FrontierModel`
`id`, `vendor`, `vision: bool`, `benchmarked: bool`.

Every response object keeps the raw server JSON: call `.to_dict()` (or index it
like a dict) to reach any field the typed layer doesn't surface yet.

---

See also: [Deploying endpoints](deploying-endpoints.md) · [Evaluating models](evaluation.md)
· [Running inference](./inference.md) · [Errors and retries](errors-and-retries.md)
