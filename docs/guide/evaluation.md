# Evaluating on your own data

Benchmarks tell you which model wins on someone else's data. This page is about the only number that matters: how the candidates score on *your* rows.

You give Pareta a list of items for a task, point it at a set of open models (and, optionally, frontier baselines to beat), and get back per-model quality with confidence intervals and cost. The platform scores everything with the task's scorer, runs the open candidates and the frontier baselines on the same items, and meters the compute against your org balance. No GPUs to size, no scorer to wire up, no judge to host.

The shape is always the same:

1. Turn your rows into an **eval set** (`evals.sets.create`), or pass them inline.
2. Kick off an **eval run** over a list of models (`evals.runs.create`), optionally waiting for it to finish.
3. Read `run.results` to compare quality and cost; read `run.cost` for the bill.

## A complete run, top to bottom

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()  # reads PARETA_API_KEY (and optional PARETA_BASE_URL)

run = pa.evals.runs.create(
    task="contract-key-fields",
    items=[
        {"input": "Effective as of January 1, 2026, ...", "expected": {"effective_date": "2026-01-01"}},
        {"input": "This Agreement terminates on 2027-12-31 ...", "expected": {"termination_date": "2027-12-31"}},
    ],
    models=["llama-1", "qwen-2"],   # per-task open aliases
    frontier="benchmarked",          # baselines already on this task's leaderboard
    wait=True,                       # block until the run is terminal
)

print(run.status)          # "completed"
print(f"billed ${run.cost}")  # Decimal dollars, floored to cents

for r in run.results:
    print(f"{r.model_id:16} {r.kind:8} q={r.quality_mean:.3f} "
          f"[{r.quality_ci_low:.3f}, {r.quality_ci_high:.3f}]  "
          f"~{r.mean_cost_micro_usd} uUSD/item  "
          f"({r.n_succeeded} ok, {r.error_count} err)")
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv(); // reads PARETA_API_KEY (and optional PARETA_BASE_URL)

const run = await pa.evals.runs.create({
  task: "contract-key-fields",
  items: [
    { input: "Effective as of January 1, 2026, ...", expected: { effective_date: "2026-01-01" } },
    { input: "This Agreement terminates on 2027-12-31 ...", expected: { termination_date: "2027-12-31" } },
  ],
  models: ["llama-1", "qwen-2"], // per-task open aliases
  frontier: "benchmarked",        // baselines already on this task's leaderboard
  wait: true,                     // block until the run is terminal
});

console.log(run.status);          // "completed"
console.log(`billed $${run.cost}`); // dollar string, floored to cents

for (const r of run.results) {
  console.log(
    `${r.modelId} ${r.kind} q=${r.qualityMean} ` +
      `[${r.qualityCiLow}, ${r.qualityCiHigh}]  ` +
      `~${r.meanCostMicroUsd} uUSD/item  ` +
      `(${r.nSucceeded} ok, ${r.errorCount} err)`,
  );
}
```

That single call created the eval set inline, started the run, polled it to completion, and returned aggregates per model. Everything below unpacks the pieces so you can vary them.

The model ids in `models=` are **per-task public aliases** (`{family}-{rank}`), not raw model names. They come from a task's leaderboard. Frontier (vendor) ids are in the clear. See [Models and aliases](inference.md) for why and how to discover them.

## Step 1: build an eval set

An eval set is your rows bound to a task. Create one explicitly when you want to reuse it across several runs.

**Python**

```python
eval_set = pa.evals.sets.create(
    task="contract-key-fields",
    items=[
        {"input": "Effective as of January 1, 2026, ...", "expected": {"effective_date": "2026-01-01"}},
        {"input": "This Agreement terminates on 2027-12-31 ...", "expected": {"termination_date": "2027-12-31"}},
    ],
    name="Q2 contracts sample",   # optional; defaults to "sdk eval set (N items)"
)

print(eval_set.id)               # pass this to runs.create(eval_set=...)
print(eval_set.task_id)          # "contract-key-fields"
print(eval_set.item_count)       # 2
print(eval_set.scoring_strategy) # e.g. "extraction" — how this task is scored
```

**TypeScript**

```typescript
const evalSet = await pa.evals.sets.create({
  task: "contract-key-fields",
  items: [
    { input: "Effective as of January 1, 2026, ...", expected: { effective_date: "2026-01-01" } },
    { input: "This Agreement terminates on 2027-12-31 ...", expected: { termination_date: "2027-12-31" } },
  ],
  name: "Q2 contracts sample", // optional; defaults to "sdk eval set (N items)"
});

console.log(evalSet.id);              // pass this to runs.create({ evalSet: ... })
console.log(evalSet.taskId);          // "contract-key-fields"
console.log(evalSet.itemCount);       // 2
console.log(evalSet.scoringStrategy); // e.g. "extraction" — how this task is scored
```

`items` is required and must be non-empty (the SDK raises `ValueError` otherwise). Each item is a row in the task's input schema; the rows go up as JSONL on the wire. The exact field names (`input`, `expected`, and any others) follow the task you chose. To inspect a task's schema and pull sample items before you format yours, use `tasks.retrieve(task_id, examples_n=...)` — see [Discovering tasks](discovery.md).

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
    task="invoice-extraction",
    items=[
        {"expected": {"total": "1240.00", "vendor": "Katana ML"}},   # the doc is attached next
        {"expected": {"total": "89.50", "vendor": "Acme"}},
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
  task: "invoice-extraction",
  items: [
    { expected: { total: "1240.00", vendor: "Katana ML" } }, // the doc is attached next
    { expected: { total: "89.50", vendor: "Acme" } },
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
run = pa.evals.runs.create(eval_set=eval_set.id, models=["llama-1", "qwen-2"], wait=True)

# Inline: create the set and run it in one shot
run = pa.evals.runs.create(
    task="contract-key-fields",
    items=[{"input": "...", "expected": {...}}],
    models=["llama-1", "qwen-2"],
    wait=True,
)
```

**TypeScript**

```typescript
// Against an existing set
let run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["llama-1", "qwen-2"], wait: true });

// Inline: create the set and run it in one shot
run = await pa.evals.runs.create({
  task: "contract-key-fields",
  items: [{ input: "...", expected: {} }],
  models: ["llama-1", "qwen-2"],
  wait: true,
});
```

You must pass **either** `eval_set=<id>` **or** `task=… + items=…`; the SDK raises `ValueError` if you give neither. `models` is required — it's the list of open candidate aliases to evaluate. Each run is **metered**: the org balance is debited for the compute across open and frontier models. If the balance is empty, `create` raises `InsufficientCreditsError` (402). Top-up is browser-only — the SDK never exposes balance or payment methods. See [Errors and metering](errors-and-retries.md).

### Choosing frontier baselines

`frontier=` controls which vendor models get scored alongside your open candidates, so the report shows you exactly how much quality (and cost) you're trading. It accepts a keyword or an explicit list, resolved SDK-side:

| `frontier=` | Baselines scored |
| --- | --- |
| `None` or `"none"` (default `None`) | none — open candidates only |
| `"all"` | every frontier model available for the task |
| `"benchmarked"` | frontier models already on the task's leaderboard (vision-filtered for document tasks) |
| `["gpt-4o", "claude-..."]` | exactly these frontier model ids |

**Python**

```python
# Just the open candidates, no baseline
run = pa.evals.runs.create(eval_set=eval_set.id, models=["llama-1"], frontier="none", wait=True)

# Everything in the frontier pool for the task
run = pa.evals.runs.create(eval_set=eval_set.id, models=["llama-1"], frontier="all", wait=True)

# A hand-picked baseline
run = pa.evals.runs.create(eval_set=eval_set.id, models=["llama-1"], frontier=["gpt-4o"], wait=True)
```

**TypeScript**

```typescript
// Just the open candidates, no baseline
let run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["llama-1"], frontier: "none", wait: true });

// Everything in the frontier pool for the task
run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["llama-1"], frontier: "all", wait: true });

// A hand-picked baseline
run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["llama-1"], frontier: ["gpt-4o"], wait: true });
```

The `"all"` and `"benchmarked"` keywords need to know the task. When you create inline (`task=…`) the SDK already has it; when you pass `eval_set=…` it looks the task up from the set. If it still can't resolve a task it raises `ValueError`, and an unrecognized keyword (anything other than `"all"`/`"benchmarked"`/`"none"`) raises `ValueError` too.

To see and pin the roster yourself, list it first:

**Python**

```python
roster = pa.evals.frontier_models(task="contract-key-fields")
for m in roster:
    print(m.id, m.vendor, "vision" if m.vision else "text", "benchmarked" if m.benchmarked else "-")

# Pin two of them explicitly
ids = [m.id for m in roster if m.benchmarked][:2]
run = pa.evals.runs.create(eval_set=eval_set.id, models=["llama-1"], frontier=ids, wait=True)
```

**TypeScript**

```typescript
const roster = await pa.evals.frontierModels("contract-key-fields");
for (const m of roster) {
  console.log(m.id, m.vendor, m.vision ? "vision" : "text", m.benchmarked ? "benchmarked" : "-");
}

// Pin two of them explicitly
const ids = roster.filter((m) => m.benchmarked).map((m) => m.id).slice(0, 2);
const run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["llama-1"], frontier: ids, wait: true });
```

`frontier_models()` annotates `benchmarked` and applies the capability filter only when you pass `task=`. Without a task it returns the full roster, unannotated.

### Waiting, or not

By default `create` returns as soon as the run is queued, so you can poll on your own schedule:

**Python**

```python
run = pa.evals.runs.create(eval_set=eval_set.id, models=["llama-1"])
print(run.status)   # "running" (or queued)

run = pa.evals.runs.retrieve(run.id)   # refetch full state
while not run.is_terminal:
    run = pa.evals.runs.retrieve(run.id)
```

**TypeScript**

```typescript
let run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["llama-1"] });
console.log(run.status); // "running" (or queued)

run = await pa.evals.runs.retrieve(run.id); // refetch full state
while (!run.isTerminal) {
  run = await pa.evals.runs.retrieve(run.id);
}
```

Or let the SDK block for you. `wait=True` polls `runs.retrieve` every `poll_interval` seconds (default 3.0) until the run is terminal, up to `timeout` seconds (default 900.0), then returns the final `EvalRun`. If the deadline passes first it raises `ParetaError`. You can also poll an already-started run with the same semantics:

**Python**

```python
run = pa.evals.runs.create(eval_set=eval_set.id, models=["llama-1"])
run = pa.evals.runs.wait(run.id, poll_interval=5.0, timeout=1800.0)
```

**TypeScript**

```typescript
let run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["llama-1"] });
run = await pa.evals.runs.wait(run.id, { pollInterval: 5.0, timeout: 1800.0 });
```

`is_terminal` is true when `status` is `"completed"` or `"failed"`. On failure, read `run.error_detail` for the message.

## Step 3: read the results

A terminal `EvalRun` carries one `EvalResult` per model in `run.results`, plus the bill.

**Python**

```python
run = pa.evals.runs.retrieve(run_id)

if run.status == "failed":
    print("run failed:", run.error_detail)
else:
    # Best open model by mean quality
    open_models = [r for r in run.results if r.kind == "open"]
    best = max(open_models, key=lambda r: r.quality_mean or 0.0)
    print(f"best open: {best.model_id} @ {best.quality_mean:.3f}")

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
  // Best open model by mean quality
  const openModels = run.results.filter((r) => r.kind === "open");
  const best = openModels.reduce((a, b) => ((b.qualityMean ?? 0) > (a.qualityMean ?? 0) ? b : a));
  console.log(`best open: ${best.modelId} @ ${best.qualityMean}`);

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

- `model_id` — the per-task public alias (open) or vendor id (frontier).
- `kind` — `"open"` or `"frontier"`. Filter on this to separate candidates from baselines.
- `quality_mean`, `quality_ci_low`, `quality_ci_high` — mean score in `[0, 1]` with a 95% confidence interval. Use the interval: two models whose CIs overlap are not meaningfully different on this sample, so add rows before declaring a winner.
- `mean_cost_micro_usd` — average cost per item in **micro-USD** (1,000,000 = $1.00). This stays in micro-USD on purpose: flooring sub-cent unit rates to whole cents would erase the open-vs-frontier cost gap that the whole exercise is about.
- `n_succeeded`, `error_count` — how many items scored vs. errored for that model.

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

Every method has an async twin on `AsyncPareta` with the same signatures. Run candidates concurrently and await the results:

**Python**

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        run = await pa.evals.runs.create(
            task="contract-key-fields",
            items=[{"input": "...", "expected": {...}}],
            models=["llama-1", "qwen-2"],
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
  task: "contract-key-fields",
  items: [{ input: "...", expected: {} }],
  models: ["llama-1", "qwen-2"],
  frontier: "benchmarked",
  wait: true,
});

for (const r of run.results) {
  console.log(r.modelId, r.kind, r.qualityMean);
}
console.log("billed", run.cost);

// Fan several runs out concurrently with Promise.all:
const [a, b] = await Promise.all([
  pa.evals.runs.create({ evalSet: setA, models: ["llama-1"], wait: true }),
  pa.evals.runs.create({ evalSet: setB, models: ["qwen-2"], wait: true }),
]);
```

`await pa.evals.runs.wait(runId)` and `await pa.evals.frontierModels(task)` work the same way. Document uploads are async too: `await pa.evals.sets.uploadDocument(...)`.

## From eval to production

Once the results pick a winner, deploy it for that task and serve inference against it:

**Python**

```python
ep = pa.endpoints.deploy(task="contract-key-fields", model=best.model_id, wait=True)
print(ep.id, ep.is_live)

resp = pa.chat.completions.create(
    model=ep.id,
    messages=[{"role": "user", "content": "Extract the effective date from: ..."}],
)
print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
const ep = await pa.endpoints.deploy({ task: "contract-key-fields", model: best.modelId, wait: true });
console.log(ep.id, ep.isLive);

const resp = await pa.chat.completions.create({
  model: ep.id,
  messages: [{ role: "user", content: "Extract the effective date from: ..." }],
});
console.log(resp.choices[0].message.content);
```

Deploy takes only a task and a model — Pareta resolves the hardware, so there is no GPU or quantization knob. Inference is OpenAI-compatible and metered the same way evals are. See [Deploying endpoints](deploying-endpoints.md) and [Running inference](./inference.md) to go further.

## See also

- [Discovering tasks](discovery.md) — find the right task id, inspect its schema, pull example rows.
- [Models and aliases](inference.md) — where the per-task open aliases come from and why real ids are hidden.
- [Deploying endpoints](deploying-endpoints.md) — turn a winning model into a live endpoint.
- [Running inference](./inference.md) — the OpenAI-compatible chat surface.
- [Errors and metering](errors-and-retries.md) — `InsufficientCreditsError`, the money convention, and the exception hierarchy.
