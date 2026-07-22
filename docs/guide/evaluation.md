# Evaluating on your own data

Benchmarks tell you which model wins on someone else's data. This page is about the only number that matters: how `model="auto"` scores on *your* rows.

Upload your data and say what you want done with each item — one sentence, like a prompt. Pareta works out how to score the results and shows you before anything runs. Then it runs `"auto"` and the frontier baselines you name on the same items and returns per-contender quality with confidence intervals and cost. No GPUs to size, no scorer to wire up, no judge to host.

An eval set is your rows plus that one sentence (the `prompt` parameter) — required, because the same rows can mean different jobs and only you know which. Each row is a JSON object with two keys, both JSON objects themselves: `{"input": {...}, "expected_output": {...}}` — the input the model sees and the gold answer the scorer grades against. Everything about scoring is derived from your words and your data; there is nothing to configure.

The shape is always the same:

1. Upload your rows + say what you want done (`evals.sets.create`).
2. Kick off an **eval run** with `"auto"` as the candidate and frontier baselines to beat (`evals.runs.create`), optionally waiting for it to finish.
3. Read `run.results` to compare quality and cost; read `run.cost` for the bill.

## Benchmark Pareta itself: `"auto"` as a contender

The candidate is the literal string `"auto"`, and the eval runs Pareta's
routing brain against every item — the same planning, routing, and
verification that serves your production traffic, scored by the same scorer
as the baselines. The per-contender result rows (quality mean + CI, mean cost
per item) are the product's core claim, measured on your data:

```python
run = client.evals.runs.create(
    eval_set=my_set,
    models=["auto"],          # the contender: Pareta's routing brain
    frontier=["gpt-5.5"],     # the frontier baseline to beat
)
```

A completed run's rows let you read the verdict directly: overlapping
quality CIs at lower cost = frontier-grade; higher mean without overlap =
ahead. Auto's failures count as errors (not skips) — availability is part of
what a benchmark should measure.


## A complete run, top to bottom

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()  # reads PARETA_API_KEY (and optional PARETA_BASE_URL)

run = pa.evals.runs.create(
    prompt="extract the effective and termination dates from each contract",
    items=[
        {"input": {"contract_text": "Effective as of January 1, 2026, ..."}, "expected_output": {"effective_date": "2026-01-01"}},
        {"input": {"contract_text": "This Agreement terminates on 2027-12-31 ..."}, "expected_output": {"termination_date": "2027-12-31"}},
    ],
    models=["auto"],                 # the contender
    frontier="benchmarked",          # baselines already benchmarked on this task
    wait=True,                       # block until the run is terminal
)

print(run.status)          # "completed"
print(f"billed ${run.cost}")  # Decimal dollars, floored to cents

for r in run.results:
    print(f"{r.model_id:16} {(r.kind or ''):8} q={r.quality_mean:.3f} "
          f"[{r.quality_ci_low:.3f}, {r.quality_ci_high:.3f}]  "
          f"~{r.mean_cost_micro_usd} uUSD/item  "
          f"({r.n_succeeded} ok, {r.error_count} err)")
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv(); // reads PARETA_API_KEY (and optional PARETA_BASE_URL)

const run = await pa.evals.runs.create({
  prompt: "extract the effective and termination dates from each contract",
  items: [
    { input: { contract_text: "Effective as of January 1, 2026, ..." }, expected_output: { effective_date: "2026-01-01" } },
    { input: { contract_text: "This Agreement terminates on 2027-12-31 ..." }, expected_output: { termination_date: "2027-12-31" } },
  ],
  models: ["auto"],               // the contender
  frontier: "benchmarked",        // baselines already benchmarked on this task
  wait: true,                     // block until the run is terminal
});

console.log(run.status);          // "completed"
console.log(`billed $${run.cost}`); // dollar string, floored to cents

for (const r of run.results) {
  console.log(
    `${r.modelId} ${r.kind ?? ""} q=${r.qualityMean} ` +
      `[${r.qualityCiLow}, ${r.qualityCiHigh}]  ` +
      `~${r.meanCostMicroUsd} uUSD/item  ` +
      `(${r.nSucceeded} ok, ${r.errorCount} err)`,
  );
}
```

That single call created the eval set inline, started the run, polled it to completion, and returned aggregates per contender. Everything below unpacks the pieces so you can vary them.

`models=` is always `["auto"]` — individual open-weights models are not part of the eval surface; they stay behind auto's routing. Frontier (vendor) ids are in the clear, and `frontier=` chooses which of them get scored alongside.

## Step 1: build an eval set

An eval set is your rows plus what you want done with them. Create one explicitly when you want to reuse it across several runs:

**Python**

```python
eval_set = pa.evals.sets.create(
    prompt="extract the effective and termination dates from each contract",
    items=[
        {"input": {"contract_text": "Effective as of January 1, 2026, ..."}, "expected_output": {"effective_date": "2026-01-01"}},
        {"input": {"contract_text": "This Agreement terminates on 2027-12-31 ..."}, "expected_output": {"termination_date": "2027-12-31"}},
    ],
    name="Q2 contracts sample",   # optional; defaults to "sdk eval set (N items)"
)

print(eval_set.id)               # pass this to runs.create(eval_set=...)
print(eval_set.scoring_strategy) # how it will be scored
print(eval_set.prompt)           # what you asked for, stored on the set
print(eval_set.item_count)       # 2
```

**TypeScript**

```typescript
const evalSet = await pa.evals.sets.create({
  prompt: "extract the effective and termination dates from each contract",
  items: [
    { input: { contract_text: "Effective as of January 1, 2026, ..." }, expected_output: { effective_date: "2026-01-01" } },
    { input: { contract_text: "This Agreement terminates on 2027-12-31 ..." }, expected_output: { termination_date: "2027-12-31" } },
  ],
  name: "Q2 contracts sample", // optional; defaults to "sdk eval set (N items)"
});

console.log(evalSet.id);              // pass this to runs.create({ evalSet: ... })
console.log(evalSet.scoringStrategy); // how it will be scored
console.log(evalSet.prompt);          // what you asked for, stored on the set
console.log(evalSet.itemCount);       // 2
```

`prompt` and `items` are both required (the SDK raises if either is missing or empty). If what you asked for doesn't line up with what's in the data — you asked for summaries but the rows look like classification labels — `create` refuses with suggestions instead of guessing. (`task=` exists to pin a specific scoring setup; most callers never need it.)

### Preview the scoring first: `propose_contract`

To see how a set will be scored before creating anything, call `propose_contract`. It's stateless (nothing is persisted):

**Python**

```python
proposal = pa.evals.propose_contract(
    prompt="extract the effective and termination dates from each contract",
    items=[{"input": {"contract_text": "..."}, "expected_output": {"effective_date": "2026-01-01"}}],
)
print(proposal.bound_task)   # how create would score this, or None if you must choose
for p in proposal.proposals:
    print(p.task_id, p.confidence, p.evidence.get("validated_n"), "/", p.evidence.get("total_n"))
```

**TypeScript**

```typescript
const proposal = await pa.evals.proposeContract({
  prompt: "extract the effective and termination dates from each contract",
  items: [{ input: { contract_text: "..." }, expected_output: { effective_date: "2026-01-01" } }],
});
console.log(proposal.boundTask); // how create would score this, or null if you must choose
```

If your data doesn't fit any of Pareta's built-in scorers, a judge panel grades each answer against what you asked for (reported as a win rate vs gpt-5.5) — so any dataset works. Pareta proposes this rather than assuming it; you confirm with `task="custom-eval"`.

The rows go up as JSONL on the wire — one `{"input": {...}, "expected_output": {...}}` object per line. To pull sample rows in a shape Pareta already knows how to score, use `tasks.retrieve(task_id, examples_n=...)` — see the [tasks reference](../reference/tasks.md).

Manage sets like any other resource:

**Python**

```python
pa.evals.sets.list()                  # -> list[EvalSet]
pa.evals.sets.retrieve(eval_set.id)   # -> EvalSet
pa.evals.sets.delete(eval_set.id)     # -> None
```

**TypeScript**

```typescript
await pa.evals.sets.list();             // -> EvalSet[]
await pa.evals.sets.retrieve(evalSet.id); // -> EvalSet
await pa.evals.sets.delete(evalSet.id);   // -> void
```

### Document and image tasks

Some tasks score over documents (PDFs, scanned invoices, images) rather than plain text. A task tells you this via `task.has_blob_input == True`. For those, each row references a binary that you attach after creating the set, one field at a time:

**Python**

```python
eval_set = pa.evals.sets.create(
    prompt="extract the total and vendor from each invoice",
    task="invoice-extraction",
    items=[
        {"expected_output": {"total": "1240.00", "vendor": "Katana ML"}},   # the doc is attached next
        {"expected_output": {"total": "89.50", "vendor": "Acme"}},
    ],
)

# Attach the PDF for row 0's `document` field.
pa.evals.sets.upload_document(
    eval_set.id,
    "invoices/katana-0001.pdf",   # path, raw bytes, or a binary file-like object
    idx=0,                        # 0-based row index
    field_name="document",        # the blob input field on this task
)

pa.evals.sets.upload_document(eval_set.id, "invoices/acme-0002.pdf", idx=1, field_name="document")
```

**TypeScript**

```typescript
const evalSet = await pa.evals.sets.create({
  prompt: "extract the total and vendor from each invoice",
  task: "invoice-extraction",
  items: [
    { expected_output: { total: "1240.00", vendor: "Katana ML" } }, // the doc is attached next
    { expected_output: { total: "89.50", vendor: "Acme" } },
  ],
});

// Attach the PDF for row 0's `document` field.
await pa.evals.sets.uploadDocument(
  evalSet.id,
  "invoices/katana-0001.pdf", // path, Blob, or bytes
  {
    idx: 0,                 // 0-based row index
    fieldName: "document",  // the blob input field on this task
  },
);

await pa.evals.sets.uploadDocument(evalSet.id, "invoices/acme-0002.pdf", { idx: 1, fieldName: "document" });
```

`upload_document` collapses the whole upload dance into one call. Files under 5 MiB go up inline; larger files get a signed URL and stream straight to storage. It accepts a path (`str`/`Path`), raw `bytes`, or any object with `.read()`; anything else raises `TypeError`. The MIME type is guessed from the filename and can be overridden with `mime=`:

**Python**

```python
with open("invoices/scan.tiff", "rb") as f:
    pa.evals.sets.upload_document(eval_set.id, f, idx=2, field_name="document", mime="image/tiff")
```

**TypeScript**

```typescript
import { readFile } from "node:fs/promises";

const bytes = await readFile("invoices/scan.tiff");
await pa.evals.sets.uploadDocument(evalSet.id, bytes, { idx: 2, fieldName: "document", mime: "image/tiff" });
```

Frontier baselines on document tasks are automatically vision-filtered — you never accidentally score a contract scan against a text-only model.

## Step 2: run the eval

`evals.runs.create` is the workhorse. You can drive an existing set, or create one inline in the same call.

**Python**

```python
# Against an existing set
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"], frontier="benchmarked", wait=True)

# Inline: create the set and run it in one shot
run = pa.evals.runs.create(
    prompt="extract the key fields from each contract",
    items=[{"input": {"contract_text": "..."}, "expected_output": {...}}],
    models=["auto"],
    frontier="benchmarked",
    wait=True,
)
```

**TypeScript**

```typescript
// Against an existing set
let run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["auto"], frontier: "benchmarked", wait: true });

// Inline: create the set and run it in one shot
run = await pa.evals.runs.create({
  prompt: "extract the key fields from each contract",
  items: [{ input: { contract_text: "..." }, expected_output: {} }],
  models: ["auto"],
  frontier: "benchmarked",
  wait: true,
});
```

You must pass **either** `eval_set=<id>` **or** `items=… + prompt=…` (with `task=` optional); the SDK raises `ValueError` if you give neither. `models` is required — pass `["auto"]`; `frontier=` names the baselines it is measured against. Each run is **metered**: the org balance is debited for the compute across auto and the frontier baselines. If the balance is empty, `create` raises `InsufficientCreditsError` (402). Top-up is browser-only — the SDK never exposes balance or payment methods. See [Errors and metering](errors-and-retries.md).

### Choosing frontier baselines

`frontier=` controls which vendor models get scored alongside `"auto"`, so the report shows you exactly how much quality (and cost) you're trading. It accepts a keyword or an explicit list, resolved SDK-side:

| `frontier=` | Baselines scored |
| --- | --- |
| `None` or `"none"` (default `None`) | none — `"auto"` alone |
| `"all"` | every frontier model available for the task |
| `"benchmarked"` | frontier models Pareta has already benchmarked on the task (vision-filtered for document tasks) |
| `["gpt-5.5", "claude-sonnet-4-6"]` | exactly these frontier model ids |

**Python**

```python
# Just auto, no baseline
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"], frontier="none", wait=True)

# Everything in the frontier pool for the task
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"], frontier="all", wait=True)

# A hand-picked baseline
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"], frontier=["gpt-5.5"], wait=True)
```

**TypeScript**

```typescript
// Just auto, no baseline
let run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["auto"], frontier: "none", wait: true });

// Everything in the frontier pool for the task
run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["auto"], frontier: "all", wait: true });

// A hand-picked baseline
run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["auto"], frontier: ["gpt-5.5"], wait: true });
```

The `"all"` and `"benchmarked"` keywords resolve against your eval set (or a pinned `task=`). If the SDK can't resolve them it raises `ValueError`, and an unrecognized keyword (anything other than `"all"`/`"benchmarked"`/`"none"`) raises `ValueError` too.

To see and pin the roster yourself, list it first:

**Python**

```python
roster = pa.evals.frontier_models(task="contract-key-fields")
for m in roster:
    print(m.id, m.vendor, "vision" if m.vision else "text", "benchmarked" if m.benchmarked else "-")

# Pin two of them explicitly
ids = [m.id for m in roster if m.benchmarked][:2]
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"], frontier=ids, wait=True)
```

**TypeScript**

```typescript
const roster = await pa.evals.frontierModels("contract-key-fields");
for (const m of roster) {
  console.log(m.id, m.vendor, m.vision ? "vision" : "text", m.benchmarked ? "benchmarked" : "-");
}

// Pin two of them explicitly
const ids = roster.filter((m) => m.benchmarked).map((m) => m.id).slice(0, 2);
const run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["auto"], frontier: ids, wait: true });
```

`frontier_models()` annotates `benchmarked` and applies the capability filter only when you pass `task=`. Without a task it returns the full roster, unannotated.

### Waiting, or not

By default `create` returns as soon as the run is queued, so you can poll on your own schedule:

**Python**

```python
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"])
print(run.status)   # "running" (or queued)

run = pa.evals.runs.retrieve(run.id)   # refetch full state
while not run.is_terminal:
    run = pa.evals.runs.retrieve(run.id)
```

**TypeScript**

```typescript
let run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["auto"] });
console.log(run.status); // "running" (or queued)

run = await pa.evals.runs.retrieve(run.id); // refetch full state
while (!run.isTerminal) {
  run = await pa.evals.runs.retrieve(run.id);
}
```

Or let the SDK block for you. `wait=True` polls `runs.retrieve` every `poll_interval` seconds (default 3.0) until the run is terminal, up to `timeout` seconds (default 900.0), then returns the final `EvalRun`. If the deadline passes first it raises `ParetaError`. You can also poll an already-started run with the same semantics:

**Python**

```python
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"])
run = pa.evals.runs.wait(run.id, poll_interval=5.0, timeout=1800.0)
```

**TypeScript**

```typescript
let run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["auto"] });
run = await pa.evals.runs.wait(run.id, { pollInterval: 5.0, timeout: 1800.0 });
```

`is_terminal` is true when `status` is `"completed"` or `"failed"`. On failure, read `run.error_detail` for the message.

## Step 3: read the results

A terminal `EvalRun` carries one `EvalResult` per contender in `run.results` — `"auto"` plus each frontier baseline — and the bill.

**Python**

```python
run = pa.evals.runs.retrieve(run_id)

if run.status == "failed":
    print("run failed:", run.error_detail)
else:
    auto = next(r for r in run.results if r.model_id == "auto")
    print(f"auto: q={auto.quality_mean:.3f} @ ~{auto.mean_cost_micro_usd} uUSD/item")

    for r in run.results:
        print(r.model_id, r.kind, r.quality_mean,
              r.quality_ci_low, r.quality_ci_high,
              r.mean_cost_micro_usd, r.n_succeeded, r.error_count)
```

**TypeScript**

```typescript
const run = await pa.evals.runs.retrieve(runId);

if (run.status === "failed") {
  console.log("run failed:", run.errorDetail);
} else {
  const auto = run.results.find((r) => r.modelId === "auto")!;
  console.log(`auto: q=${auto.qualityMean} @ ~${auto.meanCostMicroUsd} uUSD/item`);

  for (const r of run.results) {
    console.log(
      r.modelId, r.kind, r.qualityMean,
      r.qualityCiLow, r.qualityCiHigh,
      r.meanCostMicroUsd, r.nSucceeded, r.errorCount,
    );
  }
}
```

Each `EvalResult` has:

- `model_id` — `"auto"` for Pareta's row; the vendor id for each frontier baseline.
- `kind` — `"frontier"` on the baseline rows. Filter on it to separate the contender from what it is measured against.
- `quality_mean`, `quality_ci_low`, `quality_ci_high` — mean score in `[0, 1]` with a 95% confidence interval. Use the interval: two contenders whose CIs overlap are not meaningfully different on this sample, so add rows before declaring a winner.
- `mean_cost_micro_usd` — average cost per item in **micro-USD** (1,000,000 = $1.00). This stays in micro-USD on purpose: flooring sub-cent unit rates to whole cents would erase the auto-vs-frontier cost gap that the whole exercise is about.
- `n_succeeded`, `error_count` — how many items scored vs. errored for that contender.
- `per_item` — the per-item rows, each an `EvalItemResult` with `idx`, `score`, `error`, and `prediction` (the model's raw output, truncated). Reach for `prediction` when a `score` is surprisingly low — it's the actual answer, so you can see *why* it lost points without re-running the eval.

### What the run cost

The run total comes back two ways. `run.cost` is what you're billed — a `Decimal` in dollars, **floored to whole cents** (the SDK never rounds a charge up). `run.cost_micro_usd` is the raw integer for precise accounting.

**Python**

```python
print(run.cost)             # Decimal('0.07')  -> dollars, floored to cents
print(run.cost_micro_usd)   # 74211            -> raw micro-USD
```

**TypeScript**

```typescript
console.log(run.cost);         // "0.07"  -> dollar string, floored to cents
console.log(run.costMicroUsd); // 74211   -> raw micro-USD
```

A run that costs less than a cent reads `Decimal("0.00")` on `run.cost` while still carrying its true micro-USD value on `run.cost_micro_usd`. The same money convention applies everywhere in the SDK; see [Errors and metering](errors-and-retries.md) for the full picture.

Every response object also keeps the raw server JSON: `run.to_dict()`, `result.to_dict()`, and `eval_set.to_dict()` give you lossless access to anything not yet surfaced as a typed field.

## Async

Every method has an async twin on `AsyncPareta` with the same signatures. Run evals concurrently and await the results:

**Python**

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        run = await pa.evals.runs.create(
            prompt="extract the key fields from each contract",
            items=[{"input": {"contract_text": "..."}, "expected_output": {...}}],
            models=["auto"],
            frontier="benchmarked",
            wait=True,
        )
        for r in run.results:
            print(r.model_id, r.kind, r.quality_mean)
        print("billed", run.cost)

asyncio.run(main())
```

**TypeScript**

In TypeScript there is no separate async client — `Pareta` is already Promise-only, so every I/O method is just `await`ed. Concurrency is `Promise.all`:

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

const run = await pa.evals.runs.create({
  prompt: "extract the key fields from each contract",
  items: [{ input: { contract_text: "..." }, expected_output: {} }],
  models: ["auto"],
  frontier: "benchmarked",
  wait: true,
});

for (const r of run.results) {
  console.log(r.modelId, r.kind, r.qualityMean);
}
console.log("billed", run.cost);

// Fan several runs out concurrently with Promise.all:
const [a, b] = await Promise.all([
  pa.evals.runs.create({ evalSet: setA, models: ["auto"], frontier: "benchmarked", wait: true }),
  pa.evals.runs.create({ evalSet: setB, models: ["auto"], frontier: "benchmarked", wait: true }),
]);
```

`await pa.evals.runs.wait(runId)` and `await pa.evals.frontierModels(task)` work the same way. Document uploads are async too: `await pa.evals.sets.uploadDocument(...)`.

## From eval to production

There is no deploy step. The routing that just won your eval is the same routing that serves `model="auto"` in production — keep sending it your traffic:

**Python**

```python
resp = pa.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Extract the effective date from: ..."}],
)
print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
const resp = await pa.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "Extract the effective date from: ..." }],
});
console.log(resp.choices[0].message.content);
```

Inference is OpenAI-compatible and metered the same way evals are — one debit per request, no matter how many internal model calls auto's plan makes. To watch the production side of the story — requests, success rate, spend, and the projected savings vs frontier — poll `auto.metrics()`. See [Running inference](./inference.md) and [Cost & quality monitoring](../examples/cost-and-metrics.md).

## See also

- [The tasks reference](../reference/tasks.md) — find the right task id, inspect its schema, pull example rows.
- [Running inference](./inference.md) — the OpenAI-compatible `model="auto"` chat surface.
- [Cost & quality monitoring](../examples/cost-and-metrics.md) — read run costs and watch live auto traffic with `auto.metrics()`.
- [Errors and metering](errors-and-retries.md) — `InsufficientCreditsError`, the money convention, and the exception hierarchy.
