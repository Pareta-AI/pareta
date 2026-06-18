# From a sentence to a deployed winner

You have a job to do ("pull the key fields out of these contracts") and a pile of
your own examples. You want the cheapest open-weights model that actually does
the job well, serving live inference, without ever touching a GPU console.

This page walks the whole funnel, end to end:

1. **`tasks.match`** turns your plain-English intent into a benchmark task id.
2. **`tasks.leaderboard`** shows you which models lead that task and what the
   recommended pick is.
3. **`evals.runs.create`** scores a shortlist on *your* data, with frontier
   baselines for context.
4. You **pick the best open model** from the results (`kind == "open"`).
5. **`endpoints.deploy`** stands it up. Pareta resolves the hardware.
6. **`chat.completions.create`** runs OpenAI-compatible inference against it.

A few platform truths that shape the code below:

- **GPUs are hidden.** `endpoints.deploy(task=, model=)` takes a task and a model,
  never a GPU, tensor-parallel degree, or quantization knob. Pareta resolves the
  serving class.
- **Models are per-task aliases.** Every open-model id you see (`leaderboard`
  rows, `run.results[].model_id`, `endpoint.model`) is a public per-task alias.
  The real weights id never crosses into the SDK. Pass the alias straight back to
  `deploy(model=...)`.
- **Evals and inference are metered against your org balance.** An eval run debits
  for the open *and* frontier compute it used; `run.cost` is the billed total in
  dollars. A successful completion debits too. An empty balance raises
  `InsufficientCreditsError` (402). Top-up is browser-only; the SDK never exposes
  balance or payment.
- **Inference is OpenAI-compatible.** Once deployed, the endpoint behaves like any
  OpenAI chat endpoint.

## Setup

```python
from pareta import Pareta

pa = Pareta.from_env()   # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
```

`from_env()` is the preferred constructor. To pass the key explicitly:
`Pareta(api_key="pareta_sk_...")`.

## Step 1: Intent to task with `tasks.match`

`match` takes free text and returns a ranked `TaskMatch`. Use `.matched` to gate
on a confident hit and `.chosen` for the best candidate.

```python
m = pa.tasks.match("extract the key fields from a contract", top_k=5)

if not m.matched:
    # No confident hit. Inspect the alternates and pick one, or rephrase.
    for c in m.candidates:
        print(f"{c.task_id:30}  score={c.score:.2f}  ({c.confidence})")
    raise SystemExit("No confident task match. Pick a candidate above.")

task_id = m.chosen.task_id
print(f"matched {task_id}  (score={m.chosen.score:.2f}, via {m.matcher})")
if m.ambiguous:
    print("Heads up: the top two candidates scored close together.")
```

`TaskMatch` fields: `.query`, `.matched` (bool), `.chosen`
(`TaskMatchCandidate | None`), `.candidates` (ranked list), `.ambiguous`,
`.matcher` (`"keyword"` or `"semantic"`). Each `TaskMatchCandidate` has
`.task_id`, `.score` (0 to 1), and `.confidence` (`"high"` / `"medium"` /
`"low"`). `match` raises `ValueError` if the query is empty.

If you already know the task id, skip straight to step 2. Browse the full catalog
with `pa.tasks.list()` (each `Task` has `.id`, `.default_scorer`, and
`.has_blob_input`, where the last tells you whether the task takes documents or
images).

## Step 2: See who leads with `tasks.leaderboard`

The leaderboard ranks models for a task by quality and cost, names the
`recommended` deployable pick, and includes a `frontier` baseline so you know what
you are saving against.

```python
lb = pa.tasks.leaderboard(task_id)

print(f"recommended: {lb.recommended}")
print(f"ranked by {lb.metric}, cost per {lb.cost_unit}\n")

for e in lb.models:
    cost_usd = (e.cost_per_request_micro_usd or 0) / 1_000_000
    print(f"{e.name:24} {e.kind:8} q={e.quality:.3f}  ${cost_usd:.6f}/req  {e.context_k}k ctx")

if lb.frontier:
    f = lb.frontier
    print(f"\nfrontier baseline: {f.name}  q={f.quality:.3f}")
```

`Leaderboard` fields: `.task_id`, `.metric`, `.cost_unit`, `.recommended`
(deployable model alias, or `None`), `.models` (ranked `LeaderboardEntry` list),
and `.frontier` (a single baseline entry, or `None`). Each `LeaderboardEntry` has
`.name`, `.kind` (`"open"` or `"frontier"`), `.quality` (0 to 1),
`.cost_per_request_micro_usd` (raw micro-USD, **not** floored), `.context_k`
(context window in thousands), and `.run_mode`.

`cost_per_request_micro_usd` is raw micro-USD: 1,000,000 micro-USD = $1.00. The
SDK keeps sub-cent unit rates in micro-USD on purpose. Flooring them to whole
cents would erase the open-vs-frontier gap that makes the comparison worth doing.

Want just the deployable pick without the full board:

```python
pick = pa.tasks.recommended(task_id)   # -> str | None, the recommended alias
```

This is exactly what `endpoints.deploy(model="recommended")` resolves to under the
hood. Inspect it here before you commit.

## Step 3: Prove it on your data with `evals.runs.create`

The leaderboard is the catalog's published view. Your contracts are not the
catalog's contracts. Run a real eval on *your* rows before you deploy anything.

Build a shortlist from the leaderboard's open entries, then score them against
your data. You can create the eval set inline in the same call by passing
`task=` + `items=`.

```python
# Shortlist: top open models off the leaderboard (these are deployable aliases).
candidates = [e.name for e in lb.models if e.kind == "open"][:3]

# Your data: one dict per row. Shape depends on the task's scorer; for an
# extraction task each row carries the input plus the expected fields.
items = [
    {"input": "MASTER SERVICES AGREEMENT ... Term: 24 months ... Fee: $48,000",
     "expected": {"term_months": 24, "annual_fee_usd": 48000}},
    {"input": "STATEMENT OF WORK ... Term: 12 months ... Fee: $9,500",
     "expected": {"term_months": 12, "annual_fee_usd": 9500}},
    # ... more rows. More rows means tighter confidence intervals.
]

run = pa.evals.runs.create(
    task=task_id,
    items=items,
    models=candidates,        # open candidates to score
    frontier="benchmarked",   # baselines on this task's leaderboard, for context
    name="contracts shortlist v1",
    wait=True,                # block until terminal, then return the final run
)
```

`evals.runs.create` parameters:

- Provide **either** `eval_set=<id>` (an existing set) **or** `task=` + `items=`
  to create one inline. `models=` is required and is the list of open candidate
  aliases to score.
- `frontier=` controls the vendor baselines, resolved SDK-side:
  - `None` or `"none"` -> no baselines.
  - `"all"` -> every frontier model for the task.
  - `"benchmarked"` -> only the frontier models on the task's leaderboard
    (vision-filtered for document tasks).
  - an explicit list of frontier ids -> passed through as-is.
- `wait=True` polls until the run is terminal (`"completed"` or `"failed"`), every
  `poll_interval` seconds (default 3.0), up to `timeout` seconds (default 900.0),
  then returns the final `EvalRun`. It raises `ParetaError` if the timeout is hit.
  `wait=False` returns immediately with a `"running"`/queued run; poll it yourself
  with `pa.evals.runs.wait(run.id)` or `pa.evals.runs.retrieve(run.id)`.

`create` raises `ValueError` if neither `eval_set` nor `task`+`items` is given,
and `ValueError` if `items` is empty.

This call is metered. The org balance is debited for the open and frontier compute
the run used. If the balance is empty it raises `InsufficientCreditsError`.

```python
from pareta import InsufficientCreditsError

try:
    run = pa.evals.runs.create(task=task_id, items=items, models=candidates,
                               frontier="benchmarked", wait=True)
except InsufficientCreditsError:
    raise SystemExit("Org balance is empty. Top up in the dashboard (browser-only).")
```

### Document and image tasks

If `task.has_blob_input` is true, the rows reference binary documents (PDFs,
scans). Create the set first, attach each file to its row, then start the run
against the set id:

```python
es = pa.evals.sets.create(task=task_id, items=items, name="contracts with PDFs")

# Attach a PDF to row 0's "document" blob field. Files under 5 MiB go inline;
# larger ones use a signed-URL upload. The SDK picks the path for you.
pa.evals.sets.upload_document(es.id, "contracts/0001.pdf", idx=0, field_name="document")

run = pa.evals.runs.create(eval_set=es.id, models=candidates,
                           frontier="benchmarked", wait=True)
```

`upload_document` accepts a path (`str`/`Path`), raw `bytes`, or a binary
file-like object; the MIME type is guessed from the filename unless you pass
`mime=`. `EvalSet` exposes `.id`, `.task_id`, `.name`, `.item_count`, and
`.scoring_strategy`.

## Step 4: Read the results, pick the best open model

A terminal `EvalRun` carries per-model aggregates in `.results`. Each `EvalResult`
has `.model_id` (the per-task alias), `.kind` (`"open"` or `"frontier"`),
`.quality_mean`, `.quality_ci_low` / `.quality_ci_high` (95% CI),
`.mean_cost_micro_usd` (raw average cost per item), `.n_succeeded`, and
`.error_count`.

```python
print(f"run {run.id}: {run.status}")
print(f"billed: ${run.cost} ({run.cost_micro_usd} micro-USD)\n")

for r in sorted(run.results, key=lambda r: (r.quality_mean or 0), reverse=True):
    cost_usd = (r.mean_cost_micro_usd or 0) / 1_000_000
    print(f"{r.model_id:24} {r.kind:8} "
          f"q={r.quality_mean:.3f} [{r.quality_ci_low:.3f}, {r.quality_ci_high:.3f}]  "
          f"${cost_usd:.6f}/item  ({r.n_succeeded} ok, {r.error_count} err)")

# The winner: the highest-quality OPEN model. Frontier rows are baselines only:
# they are vendor APIs, not something you deploy here.
open_results = [r for r in run.results if r.kind == "open"]
if not open_results:
    raise SystemExit("No open candidates succeeded. Widen the shortlist.")

winner = max(open_results, key=lambda r: (r.quality_mean or 0))
print(f"\nwinner: {winner.model_id}  (quality {winner.quality_mean:.3f})")
```

Two money fields, two purposes:

- `run.cost` is a `Decimal`, the **billed total in dollars, floored to whole
  cents** (the SDK never rounds a charge up). A run that cost 5 micro-USD reads
  `Decimal("0.00")`.
- `run.cost_micro_usd` is the raw integer total in micro-USD when you need exact
  precision.
- Per-model `mean_cost_micro_usd` stays in raw micro-USD for the same reason the
  leaderboard rates do: flooring sub-cent unit costs would collapse the
  open-vs-frontier comparison.

The frontier rows are there to answer "how much quality am I giving up, and how
much am I saving?" You deploy the open winner, not the frontier baseline.

## Step 5: Deploy the winner with `endpoints.deploy`

Hand the winning alias straight to `deploy`. No hardware knob: Pareta resolves the
serving class for the task and model. With `wait=True`, the call blocks through the
deploy and returns the live `Endpoint`.

```python
ep = pa.endpoints.deploy(
    task=task_id,
    model=winner.model_id,   # the open alias from the eval, deployed as-is
    name="contracts-prod",   # optional; auto-generated if omitted
    wait=True,
)

print(f"endpoint {ep.id}  status={ep.status}  live={ep.is_live}  url={ep.url}")
```

`Endpoint` fields: `.id` (the name you pass to `chat.completions.create(model=...)`),
`.name`, `.model` (the per-task alias), `.status` (`"live"`, `"starting"`,
`"stopped"`, ...), `.task`, `.url`, and `.is_live` (`status == "live"`).

To pass the leaderboard's recommended pick instead of an eval winner, use
`model="recommended"` (the default) and skip the model argument entirely.

### Watching deploy progress

With `wait=False`, `deploy` returns an iterator of progress events. Each event is
a `{"event": str, "data": dict}` dict. The stream ends with a `"complete"` event
(its `data` carries the `Endpoint`) or an `"error"` event.

```python
ep = None
for event in pa.endpoints.deploy(task=task_id, model=winner.model_id):
    if event["event"] == "progress":
        print("...", event["data"])
    elif event["event"] == "complete":
        ep = pa.endpoints.retrieve(event["data"]["endpoint"]["id"])
    elif event["event"] == "error":
        raise SystemExit(f"deploy failed: {event['data']}")
```

With `wait=True` the SDK consumes this stream internally and raises `ParetaError`
on an `"error"` event. `deploy` raises `ValueError` if `task` is missing.

## Step 6: Inference with `chat.completions.create`

The deployed endpoint is OpenAI-compatible. Pass `ep.id` as the `model`:

```python
resp = pa.chat.completions.create(
    model=ep.id,
    messages=[
        {"role": "system", "content": "Extract term_months and annual_fee_usd as JSON."},
        {"role": "user", "content": "MASTER SERVICES AGREEMENT ... Term: 36 months ... Fee: $72,000"},
    ],
    temperature=0,   # any OpenAI chat param passes straight through
)
print(resp.choices[0].message.content)
print(resp.usage.total_tokens, "tokens")
```

`create` returns a `ChatCompletion` with `.id`, `.model`, `.created`, `.choices`
(each `Choice` has `.index`, `.finish_reason`, `.message`), and `.usage`
(`.prompt_tokens`, `.completion_tokens`, `.total_tokens`). It raises `ValueError`
if `model` or `messages` is empty, and (like the eval run) debits the org balance
on success, raising `InsufficientCreditsError` if the balance is empty.

### Streaming

Pass `stream=True` for an iterator of `ChatCompletionChunk`. Each chunk's
incremental text is at `.choices[0].delta.content`:

```python
for chunk in pa.chat.completions.create(model=ep.id, messages=[...], stream=True):
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

You never need this SDK to *call* the endpoint. Point the `openai` client at the
same `base_url` + your `pareta_sk_` key. The SDK's value is the control plane you
just walked: match, leaderboard, eval, deploy.

## The whole funnel

```python
from pareta import Pareta, InsufficientCreditsError

pa = Pareta.from_env()

# 1. intent -> task
m = pa.tasks.match("extract the key fields from a contract")
assert m.matched, "no confident task match"
task_id = m.chosen.task_id

# 2. who leads this task
lb = pa.tasks.leaderboard(task_id)
candidates = [e.name for e in lb.models if e.kind == "open"][:3]

# 3. prove it on your data (open candidates + benchmarked frontier baselines)
items = [{"input": "...", "expected": {...}}]  # your rows
try:
    run = pa.evals.runs.create(task=task_id, items=items, models=candidates,
                               frontier="benchmarked", wait=True)
except InsufficientCreditsError:
    raise SystemExit("Top up the org balance in the dashboard (browser-only).")

# 4. pick the best OPEN model
winner = max((r for r in run.results if r.kind == "open"),
             key=lambda r: (r.quality_mean or 0))

# 5. deploy it (Pareta resolves the hardware)
ep = pa.endpoints.deploy(task=task_id, model=winner.model_id, wait=True)

# 6. infer (OpenAI-compatible)
resp = pa.chat.completions.create(
    model=ep.id,
    messages=[{"role": "user", "content": "Extract fields from: ..."}],
)
print(resp.choices[0].message.content)
```

## Operating and measuring the live endpoint

Once it is serving, operate it from code: `pa.endpoints.list()`,
`pa.endpoints.retrieve(ep.id)`, `pa.endpoints.stop(ep.id)`,
`pa.endpoints.start(ep.id)`, `pa.endpoints.delete(ep.id)`. Read its dimensions via
`pa.endpoints.metrics(ep.id).performance()` (and `.uptime()`, `.cost()`,
`.quality()`, `.activity()`). The `.cost()` dimension reports per-endpoint spend
and savings versus the frontier baseline.

## Async

Every step has an async twin on `AsyncPareta`, with the same names and arguments,
all `await`-ed. `wait=True` and `deploy(wait=False)` return awaitables and async
iterators rather than their sync equivalents.

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        m = await pa.tasks.match("extract the key fields from a contract")
        task_id = m.chosen.task_id
        run = await pa.evals.runs.create(
            task=task_id, items=[...], models=[...], frontier="benchmarked", wait=True)
        winner = max((r for r in run.results if r.kind == "open"),
                     key=lambda r: (r.quality_mean or 0))
        ep = await pa.endpoints.deploy(task=task_id, model=winner.model_id, wait=True)
        resp = await pa.chat.completions.create(
            model=ep.id, messages=[{"role": "user", "content": "..."}])
        print(resp.choices[0].message.content)

asyncio.run(main())
```

Note: async `tasks` does not yet expose `leaderboard()` / `recommended()`. Fetch
the catalog or leaderboard with the sync client (or hardcode the shortlist) when
running the async path.

## Related

- [Run an eval on your own data](evaluate-on-your-data.md): the eval set and run
  surface in depth, including document uploads and confidence intervals.
- [Deploy and operate an endpoint](../guide/deploying-endpoints.md): start/stop,
  metrics, and the deploy progress stream.
- [OpenAI-compatible inference](migrate-from-openai.md): streaming, usage,
  and pointing the `openai` client at Pareta.
- [Money and metering](../guide/core-concepts.md): how `run.cost`, micro-USD rates, and
  `InsufficientCreditsError` work.
