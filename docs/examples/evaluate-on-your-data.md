# Benchmark models on your own data

A public leaderboard tells you which model wins on someone else's data. It does not tell you which model wins on *yours*. This page shows how to take your own labeled rows, score a slate of open-weights candidates against a frontier baseline, and read back a ranked, cost-annotated result, all in one `evals.runs.create(...)` call.

The shape is always the same:

1. Pick a task (it carries the scorer and the input schema).
2. Build an eval set from your rows.
3. Run open candidates against `frontier="benchmarked"`.
4. Read the ranked results and the dollar cost of the run.

Evals are metered: the org balance is debited for the compute you ran (open candidates **and** frontier baselines). `run.cost` is the billed total in dollars; an empty balance raises `InsufficientCreditsError`. Top-up is browser-only.

## Setup

```python
from pareta import Pareta

pa = Pareta.from_env()  # reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

`from_env()` is the path you want; it keeps the key out of your source. See [Authentication](../guide/installation.md) for the constructor form and key formats.

## 1. Pick a task

A task defines what gets scored and how. Every eval set, run, and result is anchored to one task id. The task also owns the `default_scorer` (the metric your candidates are judged on) and tells you, via `has_blob_input`, whether rows carry documents or images.

If you already know the id, skip ahead. Otherwise, match free text against the catalog:

```python
match = pa.tasks.match("extract key fields from a contract", top_k=5)

if match.matched:
    task_id = match.chosen.task_id          # best candidate
    print(task_id, match.chosen.confidence)  # e.g. "contract-key-fields" "high"
else:
    # nothing landed with confidence; inspect the ranked alternates
    for c in match.candidates:
        print(c.task_id, round(c.score, 3), c.confidence)
    raise SystemExit("refine the query")
```

`match.ambiguous` is `True` when the top two scores are close, worth surfacing to a human before committing. Confirm the scorer and input schema before you build a set:

```python
task = pa.tasks.retrieve(task_id)
print(task.default_scorer)   # the metric your run will report (e.g. "macro_joint_f1")
print(task.has_blob_input)   # True → rows attach PDFs/images (see step 2b)
```

See [Discover tasks](../guide/discovery.md) for the full matching and catalog walkthrough.

## 2. Build an eval set from your rows

An eval set is your labeled data, stored server-side and reusable across runs. Each row is a dict whose fields match the task schema. The exact keys are task-specific, but the universal shape is **inputs the model sees** plus a **target** (the gold label the scorer compares against).

```python
items = [
    {
        "text": "This Agreement is made on 3 March 2026 between Acme Corp and Globex LLC...",
        "target": {"effective_date": "2026-03-03", "parties": ["Acme Corp", "Globex LLC"]},
    },
    {
        "text": "Master Services Agreement, dated January 12, 2026, by and between Initech and Hooli...",
        "target": {"effective_date": "2026-01-12", "parties": ["Initech", "Hooli"]},
    },
    # ... more rows. A few dozen labeled rows already give you a usable signal.
]

eval_set = pa.evals.sets.create(task=task_id, items=items)

print(eval_set.id)                # use this in runs.create(eval_set=...)
print(eval_set.item_count)        # 2
print(eval_set.scoring_strategy)  # e.g. "extraction"
```

`items` must be non-empty (an empty list raises `ValueError` before any request goes out). If you omit `name`, the set is labeled `"sdk eval set (N items)"`.

Reuse a set across many runs, or list and prune as you iterate:

```python
for s in pa.evals.sets.list():
    print(s.id, s.task_id, s.item_count, s.name)

# pa.evals.sets.delete(eval_set.id)   # when you are done with it
```

### 2b. Document tasks: attach the file to each row

When `task.has_blob_input` is `True`, the row carries a binary document. Create the set with the row's text/label fields and a placeholder for the blob, then attach the file to that row by index:

```python
doc_task = "invoice-extraction"   # a has_blob_input task

eval_set = pa.evals.sets.create(
    task=doc_task,
    items=[
        {"target": {"invoice_number": "INV-7781", "total": "1240.00"}},
        {"target": {"invoice_number": "INV-7782", "total": "98.50"}},
    ],
)

# Attach one PDF per row. idx is the 0-based row; field_name is the blob input
# field from the task schema. MIME is auto-detected from the filename.
pa.evals.sets.upload_document(eval_set.id, "invoices/7781.pdf", idx=0, field_name="document")
pa.evals.sets.upload_document(eval_set.id, "invoices/7782.pdf", idx=1, field_name="document")
```

`upload_document` accepts a path (`str`/`Path`), raw `bytes`, or any binary file-like object; anything else raises `TypeError`. Files under 5 MiB upload inline; larger ones go through a signed-URL direct-to-storage flow. Either way the call returns the completion response dict. Pass `mime="application/pdf"` to override detection.

## 3. Run open candidates against a frontier baseline

This is the core call. You name the open-weights candidates (per-task public aliases) and let `frontier="benchmarked"` pull the vendor baselines that sit on this task's leaderboard. The run scores everything on the same rows with the same scorer, so the numbers are directly comparable.

```python
run = pa.evals.runs.create(
    eval_set=eval_set.id,
    models=["contract-kie-1", "contract-kie-2"],  # open candidates (aliases)
    frontier="benchmarked",                        # vendor baselines on this leaderboard
    wait=True,                                      # block until the run is terminal
)

print(run.status)  # "completed"
```

The `models` list is the open candidates you want to rank; it is required. `frontier` controls the baselines:

| `frontier=` | Evaluates against |
|---|---|
| `None` or `"none"` | nothing (open candidates only) |
| `"benchmarked"` | frontier models on this task's leaderboard (vision-filtered for document tasks) |
| `"all"` | every frontier model in the eval pool for the task |
| `["gpt-4o", "claude-..."]` | exactly these frontier ids |

The `"benchmarked"` and `"all"` keywords need to know the task. With `eval_set=...` the SDK looks it up from the set; if you pass an explicit list of ids it skips the lookup entirely.

GPUs and serving hardware never enter this call. There is no GPU, quantization, or run-mode knob. You name a task and models; Pareta resolves the rest. Open-weights model ids are per-task aliases, and frontier ids are the vendor names in the clear.

### Inline create (skip step 2)

If you do not need a reusable set, hand the rows straight to the run. Pass `task=` and `items=` instead of `eval_set=`, and the SDK creates the set for you:

```python
run = pa.evals.runs.create(
    task=task_id,
    items=items,
    models=["contract-kie-1", "contract-kie-2"],
    frontier="benchmarked",
    wait=True,
)
```

You must pass either `eval_set=<id>` or both `task=` and `items=`; anything else raises `ValueError`.

### Picking candidates from the leaderboard

If you want the curated pick rather than hand-naming aliases, read the leaderboard and feed its `recommended` id into the run:

```python
lb = pa.tasks.leaderboard(task_id)
print(lb.recommended)                # the deployable alias Pareta curates for this task
print(lb.frontier.name)              # the savings baseline

candidates = [lb.recommended] + [m.name for m in lb.models[:2] if m.kind == "open"]
run = pa.evals.runs.create(eval_set=eval_set.id, models=candidates,
                           frontier="benchmarked", wait=True)
```

To enumerate the frontier roster directly (for example, to build an explicit `frontier=[...]` list), use `pa.evals.frontier_models(task=task_id)`; each entry exposes `.id`, `.vendor`, `.vision`, and `.benchmarked`.

## 4. Read the ranked results

A terminal run carries one `EvalResult` per model. Sort by `quality_mean` to get the ranking, and read `run.cost` to see what the run cost you:

```python
ranked = sorted(run.results, key=lambda r: r.quality_mean or 0, reverse=True)

for r in ranked:
    cost_per_item = (r.mean_cost_micro_usd or 0) / 1_000_000  # micro-USD → dollars
    print(
        f"{r.model_id:24}  "
        f"quality={r.quality_mean:.3f}  "
        f"[{r.quality_ci_low:.3f}, {r.quality_ci_high:.3f}]  "
        f"${cost_per_item:.6f}/item  "
        f"ok={r.n_succeeded} err={r.error_count}"
    )

print(f"\nrun cost: ${run.cost}")          # Decimal dollars, floored to cents
print(f"raw micro-USD: {run.cost_micro_usd}")
```

What the fields mean:

- **`quality_mean`**: the model's mean score on the task's scorer, in `[0, 1]`. This is your ranking key.
- **`quality_ci_low` / `quality_ci_high`**: the 95% confidence interval. If two models' intervals overlap heavily, your eval set is too small to separate them, so add rows.
- **`mean_cost_micro_usd`**: average cost per item, kept in micro-USD (not floored). This is where the open-vs-frontier comparison lives, so sub-cent precision is preserved: a cheaper open model that matches frontier quality is the whole point.
- **`n_succeeded` / `error_count`**: how many rows scored cleanly. A high `error_count` on one model usually means malformed output, not a bad model, so inspect before trusting its quality number.
- **`model_id`**: the per-task alias (open) or vendor id (frontier). `kind` distinguishes `"open"` from `"frontier"` where the backend populates it.

### A note on money

`run.cost` is a `Decimal` of dollars, floored to whole cents, so the SDK never overstates a charge and a sub-cent run reads `Decimal("0.00")`. For the exact figure use `run.cost_micro_usd` (an integer, where `1_000_000` micro-USD is `$1.00`). The same convention is why per-item rates like `mean_cost_micro_usd` stay in micro-USD: flooring them to cents would erase the open-vs-frontier difference you ran the eval to find.

## Not blocking on the run

`wait=True` polls until the run reaches `"completed"` or `"failed"`, then returns. For long sets, tune the cadence and ceiling:

```python
run = pa.evals.runs.create(
    eval_set=eval_set.id,
    models=["contract-kie-1", "contract-kie-2"],
    frontier="benchmarked",
    wait=True,
    poll_interval=5.0,   # seconds between polls (default 3.0)
    timeout=1800.0,      # give up after 30 min (default 900.0); raises ParetaError on timeout
)
```

Or fire and poll yourself. `wait=False` returns immediately with a run you can retrieve later:

```python
run = pa.evals.runs.create(eval_set=eval_set.id,
                           models=["contract-kie-1"], frontier="benchmarked")
run_id = run.id
# ... later, from anywhere ...
run = pa.evals.runs.retrieve(run_id)
if run.is_terminal:
    print(run.status, run.results)

# equivalently, block on an already-started run:
run = pa.evals.runs.wait(run_id, timeout=1800.0)
```

## Handling an empty balance

Both the open and frontier compute are metered. If the org balance cannot cover the run, `create` raises before any work is billed:

```python
from pareta import InsufficientCreditsError

try:
    run = pa.evals.runs.create(eval_set=eval_set.id,
                               models=["contract-kie-1"], frontier="benchmarked", wait=True)
except InsufficientCreditsError:
    print("Out of credit. Top up in the dashboard (billing is browser-only).")
```

`InsufficientCreditsError` is a subclass of `APIStatusError` (status 402), so you can also catch the broader `ParetaError` if you want one handler for every SDK failure.

## Full example

```python
from pareta import Pareta, InsufficientCreditsError

pa = Pareta.from_env()

# 1. Pick the task.
task_id = "contract-key-fields"
task = pa.tasks.retrieve(task_id)
print("scoring on:", task.default_scorer)

# 2. Build the eval set from your rows.
items = [
    {"text": "This Agreement is made on 3 March 2026 between Acme Corp and Globex LLC...",
     "target": {"effective_date": "2026-03-03", "parties": ["Acme Corp", "Globex LLC"]}},
    {"text": "Master Services Agreement, dated January 12, 2026, by and between Initech and Hooli...",
     "target": {"effective_date": "2026-01-12", "parties": ["Initech", "Hooli"]}},
]
eval_set = pa.evals.sets.create(task=task_id, items=items, name="contract fields v1")

# 3. Run open candidates against the benchmarked frontier baselines.
try:
    run = pa.evals.runs.create(
        eval_set=eval_set.id,
        models=["contract-kie-1", "contract-kie-2"],
        frontier="benchmarked",
        wait=True,
    )
except InsufficientCreditsError:
    raise SystemExit("Out of credit. Top up in the dashboard.")

# 4. Read the ranked results.
for r in sorted(run.results, key=lambda r: r.quality_mean or 0, reverse=True):
    print(f"{r.model_id:24} {r.quality_mean:.3f}  ${(r.mean_cost_micro_usd or 0)/1e6:.6f}/item")

print("run cost:", run.cost)  # Decimal dollars, floored to cents
```

## Async

Every call here has an `async` twin on `AsyncPareta`. The signatures match; the methods are coroutines (`wait` included).

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        eval_set = await pa.evals.sets.create(task="contract-key-fields", items=items)
        run = await pa.evals.runs.create(
            eval_set=eval_set.id,
            models=["contract-kie-1", "contract-kie-2"],
            frontier="benchmarked",
            wait=True,
        )
        for r in run.results:
            print(r.model_id, r.quality_mean)
        print("run cost:", run.cost)

asyncio.run(main())
```

## Next steps

- [Deploy an endpoint](deploy-and-infer.md): take the winner of your eval to a live, OpenAI-compatible endpoint.
- [Run inference](../guide/inference.md): call your deployed model; inference is metered the same way evals are.
- [Discover tasks](../guide/discovery.md): match intent to tasks and read leaderboards in depth.
- [Errors and retries](../guide/errors-and-retries.md): the full exception hierarchy behind `InsufficientCreditsError` and friends.
