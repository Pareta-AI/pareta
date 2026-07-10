# `evals`: evaluate models on your own data

`client.evals` runs the only benchmark that matters: how `model="auto"` scores on **your** rows. You hand Pareta a task and a list of labeled items, name the candidates — `"auto"`, plus the frontier baselines to beat — and get back per-candidate quality with 95% confidence intervals and per-item cost. The platform scores everything with the task's scorer, runs every candidate on the same items, and meters the compute against your org balance. No GPUs to size, no scorer to wire up, no judge to host.

The namespace has three parts:

- [`evals.sets`](#evalssets-evaluation-datasets): turn your rows into a reusable eval set (and attach documents for blob tasks).
- [`evals.runs`](#evalsruns-evaluation-runs): run candidates over a set and read aggregated results.
- [`evals.frontier_models`](#evalsfrontier_models-frontier-baseline-roster): list the vendor baselines you can evaluate against.

All examples use the synchronous `Pareta` client. Every method has an `async` twin with the same signature on `AsyncPareta`; see [Async](#async).

```python
from pareta import Pareta

pa = Pareta.from_env()  # reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

## The shape of an eval

1. Turn your rows into an **eval set** (`evals.sets.create`), or pass them inline to the run.
2. Kick off an **eval run** over a list of models (`evals.runs.create`), optionally blocking until it finishes.
3. Read `run.results` to compare quality and cost; read `run.cost` for the bill.

```python
run = pa.evals.runs.create(
    task="contract-key-fields",
    items=[
        {"input": "Effective as of January 1, 2026, ...", "expected": {"effective_date": "2026-01-01"}},
        {"input": "This Agreement terminates on 2027-12-31 ...", "expected": {"termination_date": "2027-12-31"}},
    ],
    models=["auto"],         # the product under test
    frontier="benchmarked",  # vendor baselines benchmarked on this task
    wait=True,               # block until the run is terminal
)

print(run.status)             # "completed"
print(f"billed ${run.cost}")  # Decimal dollars, floored to cents

for r in run.results:
    print(f"{r.model_id:16} q={r.quality_mean:.3f} "
          f"[{r.quality_ci_low:.3f}, {r.quality_ci_high:.3f}]  "
          f"~{r.mean_cost_micro_usd} uUSD/item  ({r.n_succeeded} ok, {r.error_count} err)")
```

That single call created the eval set inline, started the run, polled it to completion, and returned an `EvalRun` with one aggregate per candidate. The sections below unpack each piece.

The candidates are `"auto"` plus vendor ids: `models=["auto"]` puts the product under test, and `frontier=` adds the vendor baselines to beat. Frontier ids are in the clear because they are public products — take them from [`frontier_models`](#evalsfrontier_models-frontier-baseline-roster). The open specialists auto routes to are never individually named: the thing you measure is the routed product, not its parts.

## `evals.sets`: evaluation datasets

An eval set is your rows bound to a task, stored server-side and reusable across runs. Create one explicitly when you want to reuse it; otherwise pass `task=` + `items=` straight to `runs.create` (see [inline create](#inline-create)).

### `sets.create`

```python
def create(self, *, task: str, items: list[dict], name: str | None = None) -> EvalSet
```

`POST /v1/eval-sets`

- `task` (required): the task id. Carries the scorer and the input schema.
- `items` (required, non-empty): your evaluation rows. Each is a dict in the task's input schema; the SDK serializes them to JSONL on the wire. An empty list raises `ValueError` before any request goes out.
- `name` (optional): defaults to `f"sdk eval set ({len(items)} items)"`.

```python
eval_set = pa.evals.sets.create(
    task="contract-key-fields",
    items=[
        {"input": "Effective as of January 1, 2026, ...", "expected": {"effective_date": "2026-01-01"}},
        {"input": "This Agreement terminates on 2027-12-31 ...", "expected": {"termination_date": "2027-12-31"}},
    ],
    name="Q2 contracts sample",
)

print(eval_set.id)               # pass this to runs.create(eval_set=...)
print(eval_set.task_id)          # "contract-key-fields"
print(eval_set.item_count)       # 2
print(eval_set.scoring_strategy) # e.g. "extraction": how this task is scored
```

The exact row fields (`input`, `expected`, and any others) follow the task you chose. To inspect a task's schema and pull sample rows before formatting yours, use `pa.tasks.retrieve(task_id, examples_n=...)`. See [`tasks`](./tasks.md).

Returns an [`EvalSet`](#evalset).

### `sets.list`

```python
def list(self) -> list[EvalSet]
```

`GET /v1/eval-sets`: every eval set the org can access.

```python
for s in pa.evals.sets.list():
    print(s.id, s.task_id, s.item_count, s.name)
```

### `sets.retrieve`

```python
def retrieve(self, eval_set_id: str) -> EvalSet
```

`GET /v1/eval-sets/{eval_set_id}`: one set by id.

```python
eval_set = pa.evals.sets.retrieve("evalset_abc123")
```

### `sets.delete`

```python
def delete(self, eval_set_id: str) -> None
```

`DELETE /v1/eval-sets/{eval_set_id}`: remove a set.

```python
pa.evals.sets.delete(eval_set.id)
```

### `sets.upload_document`

```python
def upload_document(
    self,
    eval_set_id: str,
    file,
    *,
    idx: int,
    field_name: str,
    mime: str | None = None,
) -> dict
```

Attaches a binary document (PDF, image, scan) to one row's blob field. Use this for tasks where `task.has_blob_input == True`: create the set with each row's labels (and a placeholder for the blob), then attach the file to that row by index.

- `eval_set_id`: the set to attach to.
- `file`: a path (`str` / `pathlib.Path`), raw `bytes`/`bytearray`, or any binary file-like object with `.read()`. Anything else raises `TypeError`.
- `idx` (required): 0-based row index.
- `field_name` (required): the blob input field on the task schema.
- `mime` (optional): MIME type; guessed from the filename when omitted, falling back to `application/octet-stream`.

```python
eval_set = pa.evals.sets.create(
    task="invoice-extraction",
    items=[
        {"expected": {"total": "1240.00", "vendor": "Katana ML"}},  # doc attached next
        {"expected": {"total": "89.50", "vendor": "Acme"}},
    ],
)

# Attach the PDF for row 0's `document` field.
pa.evals.sets.upload_document(
    eval_set.id,
    "invoices/katana-0001.pdf",  # path, bytes, or binary file-like
    idx=0,
    field_name="document",
)

# Bytes or a file handle work too; override the guessed MIME when needed.
with open("invoices/scan.tiff", "rb") as f:
    pa.evals.sets.upload_document(eval_set.id, f, idx=1, field_name="document", mime="image/tiff")
```

`upload_document` collapses the upload into one call. Files under 5 MiB go up inline via `attach-blob`; larger files mint a signed URL (`blob-upload-url`), stream straight to storage with a `PUT`, then confirm (`blob-upload-complete`). Either way it returns the completion endpoint's response dict. A failed storage `PUT` raises `ParetaError`.

Frontier baselines on document tasks are automatically vision-filtered, so you never accidentally score a scan against a text-only model.

## `evals.runs`: evaluation runs

A run evaluates a list of models over an eval set and returns per-model aggregates.

### `runs.create`

```python
def create(
    self,
    *,
    eval_set: str | None = None,
    task: str | None = None,
    items: list[dict] | None = None,
    models,
    frontier=None,
    name: str | None = None,
    wait: bool = False,
    poll_interval: float = 3.0,
    timeout: float = 900.0,
) -> EvalRun
```

`POST /v1/eval-runs`

You drive it one of two ways. Pass **`eval_set=<id>`** to run against an existing set, **or** pass **`task=...` + `items=...`** to create a set inline in the same call. Passing neither raises `ValueError`.

- `models` (required): the candidate list — pass `["auto"]`. Required even when `frontier` is set; an empty `models` with no frontier ids raises `ValueError`.
- `frontier` (default `None`): the vendor baselines to score alongside your candidates. Keyword or explicit list, [resolved SDK-side](#frontier-resolution).
- `name` (optional): run label; also used as the inline set's name.
- `wait` (default `False`): when `False`, returns as soon as the run is queued (status `"running"` or queued). When `True`, blocks via [`runs.wait`](#runswait) and returns the terminal run.
- `poll_interval` (default `3.0`): seconds between polls when `wait=True`.
- `timeout` (default `900.0`): max seconds to wait; exceeding it raises `ParetaError`.

```python
# Against an existing set
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"], wait=True)
```

<a id="inline-create"></a>
**Inline create**: skip `sets.create` entirely and hand the rows to the run; the SDK creates the set for you:

```python
run = pa.evals.runs.create(
    task="contract-key-fields",
    items=[{"input": "...", "expected": {"effective_date": "2026-01-01"}}],
    models=["auto"],
    frontier="benchmarked",
    wait=True,
)
```

**Metering.** Each run is metered: the org balance is debited for the compute across **auto and frontier** candidates. If the balance cannot cover the run, `create` raises `InsufficientCreditsError` (402) before any work is billed. Top-up is browser-only; the SDK never exposes balance or payment methods.

```python
from pareta import InsufficientCreditsError

try:
    run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"],
                               frontier="benchmarked", wait=True)
except InsufficientCreditsError:
    raise SystemExit("Out of credit. Top up in the dashboard (billing is browser-only).")
```

`InsufficientCreditsError` subclasses `APIStatusError`; catch `ParetaError` for one handler over every SDK failure. See [Errors and metering](exceptions.md).

Returns an [`EvalRun`](#evalrun).

#### `frontier=` resolution

`frontier=` controls which vendor models get scored alongside `"auto"`, so the report shows exactly what quality the routing holds and what cost it saves. The SDK resolves the keyword to a concrete list of ids before sending the run:

| `frontier=` | Baselines scored |
| --- | --- |
| `None` or `"none"` (default) | none, your `models=` candidates only (`[]`) |
| `"all"` | every frontier model available for the task |
| `"benchmarked"` | frontier models benchmarked on the task (vision-filtered for document tasks) |
| `["gpt-5.5", "claude-..."]` | exactly these frontier ids, passed through as-is |

```python
# Auto only, no baselines
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"], frontier="none", wait=True)

# Everything in the frontier pool for the task
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"], frontier="all", wait=True)

# A hand-picked baseline
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"], frontier=["gpt-5.5"], wait=True)
```

The `"all"` and `"benchmarked"` keywords need the task to fetch the roster. When you create inline (`task=...`) the SDK already has it; when you pass `eval_set=...` it looks the task up from the set. If it still cannot resolve a task it raises `ValueError`. An unrecognized keyword (anything other than `"all"` / `"benchmarked"` / `"none"`) raises `ValueError`, and a `frontier` that is not `None`, a list/tuple, or a string raises `TypeError`. An explicit list skips the roster lookup entirely.

To enumerate and pin the roster yourself, see [`frontier_models`](#evalsfrontier_models-frontier-baseline-roster).

### `runs.retrieve`

```python
def retrieve(self, run_id: str) -> EvalRun
```

`GET /v1/eval-runs/{run_id}`: full run state, including `results` once the run is terminal.

```python
run = pa.evals.runs.retrieve("evalrun_xyz789")
if run.is_terminal:
    print(run.status, run.results)
```

### `runs.wait`

```python
def wait(self, run_id: str, *, poll_interval: float = 3.0, timeout: float = 900.0) -> EvalRun
```

Polls `runs.retrieve(run_id)` every `poll_interval` seconds until `run.is_terminal` (status `"completed"` or `"failed"`), then returns the final `EvalRun`. Raises `ParetaError` if `timeout` seconds elapse first. This is exactly what `create(..., wait=True)` calls internally, so you can fire a run and block on it later:

```python
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"])   # returns immediately
run = pa.evals.runs.wait(run.id, poll_interval=5.0, timeout=1800.0)  # block on it
```

Or poll on your own schedule without `wait`:

```python
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"])
while not run.is_terminal:
    run = pa.evals.runs.retrieve(run.id)
```

### Reading results

A terminal `EvalRun` carries one [`EvalResult`](#evalresult) per candidate in `run.results`, plus the bill.

```python
run = pa.evals.runs.retrieve(run_id)

if run.status == "failed":
    print("run failed:", run.error_detail)
else:
    ranked = sorted(run.results, key=lambda r: r.quality_mean or 0.0, reverse=True)
    for r in ranked:
        cost_per_item = (r.mean_cost_micro_usd or 0) / 1_000_000  # micro-USD to dollars
        print(f"{r.model_id:24} q={r.quality_mean:.3f} "
              f"[{r.quality_ci_low:.3f}, {r.quality_ci_high:.3f}]  "
              f"${cost_per_item:.6f}/item  ok={r.n_succeeded} err={r.error_count}")

    print(f"run cost: ${run.cost}")          # Decimal dollars, floored to cents
    print(f"raw micro-USD: {run.cost_micro_usd}")
```

Use the confidence interval: two candidates whose CIs overlap are not meaningfully different on this sample, so add rows before calling the comparison. A high `error_count` on one candidate usually means malformed output, not a bad model, so inspect before trusting its quality number. When `"auto"` holds the frontier's quality at a fraction of its per-item cost, production is the call you already have: keep sending `model="auto"`.

**On money.** `run.cost` is a `Decimal` in dollars, **floored to whole cents** (the SDK never rounds a charge up), so a sub-cent run reads `Decimal("0.00")`. `run.cost_micro_usd` is the raw integer (`1_000_000` micro-USD = `$1.00`) for exact accounting. Per-item rates like `result.mean_cost_micro_usd` stay in micro-USD on purpose: flooring sub-cent unit rates to whole cents would erase the auto-vs-frontier cost gap the eval exists to find. Same convention SDK-wide; see [Errors and metering](exceptions.md).

## `evals.frontier_models`: frontier baseline roster

```python
def frontier_models(self, task: str | None = None) -> list[FrontierModel]
```

`GET /v1/eval/frontier-models`: the vendor (frontier) models you can evaluate against. Feed the `.id`s into `runs.create(frontier=[...])`.

- `task` (optional): when given, each entry is annotated `benchmarked` (it has been benchmarked on that task) and the roster is vision-filtered for document tasks. Without a task the full roster comes back unannotated.

```python
roster = pa.evals.frontier_models(task="contract-key-fields")
for m in roster:
    print(m.id, m.vendor, "vision" if m.vision else "text",
          "benchmarked" if m.benchmarked else "-")

# Pin two benchmarked baselines explicitly
ids = [m.id for m in roster if m.benchmarked][:2]
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"], frontier=ids, wait=True)
```

Returns a list of [`FrontierModel`](#frontiermodel).

## Async

Every method above has an `async` twin on `AsyncPareta` with an identical signature; the methods are coroutines (`wait` included). Document uploads are async too.

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        eval_set = await pa.evals.sets.create(
            task="contract-key-fields",
            items=[{"input": "...", "expected": {"effective_date": "2026-01-01"}}],
        )
        run = await pa.evals.runs.create(
            eval_set=eval_set.id,
            models=["auto"],
            frontier="benchmarked",
            wait=True,
        )
        for r in run.results:
            print(r.model_id, r.quality_mean)
        print("billed", run.cost)

asyncio.run(main())
```

`await pa.evals.runs.wait(run_id)`, `await pa.evals.frontier_models(task=...)`, and `await pa.evals.sets.upload_document(...)` all work the same way.

## Response objects

Every object keeps the raw server JSON: call `.to_dict()` for lossless access to anything not yet surfaced as a typed field, and index it dict-style (`run["..."]`) as an escape hatch.

### `EvalSet`

From `sets.create`, `sets.list`, `sets.retrieve`.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | `str \| None` | Pass to `runs.create(eval_set=...)` |
| `task_id` | `str \| None` | The task this set is bound to |
| `name` | `str \| None` | Label |
| `item_count` | `int \| None` | Number of rows |
| `scoring_strategy` | `str \| None` | How the task is scored (e.g. `"extraction"`) |

### `EvalRun`

From `runs.create`, `runs.retrieve`, `runs.wait`. Wraps the `{"run": {...}, "results": [...]}` envelope.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | `str \| None` | Run id; pass to `runs.retrieve` / `runs.wait` |
| `eval_set_id` | `str \| None` | The set evaluated |
| `status` | `str \| None` | `"running"`, `"evaluating"`, `"completed"`, `"failed"` |
| `is_terminal` | `bool` | `True` when status is `"completed"` or `"failed"` |
| `candidate_models` | `list[str]` | The candidates evaluated (`"auto"` + frontier ids) |
| `error_detail` | `str \| None` | Error message when `status == "failed"` |
| `cost` | `Decimal` | Billed total in dollars, floored to cents |
| `cost_micro_usd` | `int` | Raw total cost in micro-USD (`1_000_000` = `$1.00`) |
| `results` | `list[EvalResult]` | One aggregate per model (populated once terminal) |

### `EvalResult`

One candidate's aggregate on a run; from `run.results`.

| Field | Type | Notes |
| --- | --- | --- |
| `model_id` | `str \| None` | `"auto"`, or a frontier vendor id |
| `kind` | `str \| None` | `"frontier"` on vendor baseline rows; unset on `"auto"` rows |
| `quality_mean` | `float \| None` | Mean score in `[0, 1]`, your ranking key |
| `quality_ci_low` | `float \| None` | 95% CI lower bound |
| `quality_ci_high` | `float \| None` | 95% CI upper bound |
| `mean_cost_micro_usd` | `int \| None` | Avg cost per item in micro-USD (not floored) |
| `n_succeeded` | `int \| None` | Rows that scored cleanly |
| `error_count` | `int \| None` | Rows that errored |

### `FrontierModel`

A vendor baseline; from `frontier_models`.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | `str \| None` | Pass to `runs.create(frontier=[...])` |
| `vendor` | `str \| None` | `"openai"`, `"anthropic"`, etc. |
| `vision` | `bool` | `True` if vision-capable |
| `benchmarked` | `bool` | `True` if benchmarked on the task (only set when `task=` is given) |

## See also

- [`tasks`](./tasks.md): match intent to a task, inspect its schema, pull example rows.
- [`chat`](./chat.md): the OpenAI-compatible inference surface, metered the same way evals are — production is the same `model="auto"` call you just benchmarked.
- [Errors and metering](exceptions.md): `InsufficientCreditsError`, the money convention, and the full exception hierarchy.
