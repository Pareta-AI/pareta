# Benchmark `"auto"` on your own data

A public benchmark tells you how `model="auto"` performs on someone else's data. It does not tell you how it performs on *yours*. This page shows how to take your own labeled rows, score `"auto"` against the frontier baselines it replaces, and read back a cost-annotated verdict, all in one `evals.runs.create(...)` call.

The shape is always the same:

1. Say what you want done with each row — one sentence, like a prompt.
2. Build an eval set from your rows.
3. Run `"auto"` against `frontier="benchmarked"`.
4. Read the results and the dollar cost of the run.

Evals are metered: the org balance is debited for the compute you ran (`"auto"` **and** the frontier baselines). `run.cost` is the billed total in dollars; an empty balance raises `InsufficientCreditsError`. Top-up is browser-only.

## Setup

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()  # reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv(); // reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

`from_env()` is the path you want; it keeps the key out of your source. See [Authentication](../guide/installation.md) for the constructor form and key formats.

## 1. Your rows + what you want done

Each row of your data is an input and, when you have one, the answer you expect back. The only other thing Pareta needs is what you want done with each row — one sentence, written the way you'd prompt any model:

> "extract the effective date and parties from each contract"

That's the whole setup. Pareta works out how to score the results from your words and your data, and if they don't line up — you asked for a summary but the rows look like classification labels — `create` refuses with suggestions instead of guessing.

Want to see how a set will be scored before creating anything? `evals.propose_contract(items=..., prompt=...)` returns the scoring plan without persisting a thing — and `task=` lets you pin a specific one (see the [tasks reference](../reference/tasks.md)). Most of the time you need neither.

## 2. Build an eval set from your rows

An eval set is your labeled data, stored server-side and reusable across runs. Each row is a dict; Pareta checks every row's shape at create time. The shape is always `{"input": {...}, "expected_output": {...}}` — both values JSON objects: the **inputs the model sees** and the **gold answer** the scorer compares against. The inner field names are task-specific.

**Python**

```python
items = [
    {
        "input": {"contract_text": "This Agreement is made on 3 March 2026 between Acme Corp and Globex LLC..."},
        "expected_output": {"effective_date": "2026-03-03", "parties": ["Acme Corp", "Globex LLC"]},
    },
    {
        "input": {"contract_text": "Master Services Agreement, dated January 12, 2026, by and between Initech and Hooli..."},
        "expected_output": {"effective_date": "2026-01-12", "parties": ["Initech", "Hooli"]},
    },
    # ... more rows. A few dozen labeled rows already give you a usable signal.
]

eval_set = pa.evals.sets.create(
    items=items,
    prompt="extract the effective date and parties from each contract",
)   # refuses with suggestions if what you asked for doesn't match the data

print(eval_set.id)                # use this in runs.create(eval_set=...)
print(eval_set.item_count)        # 2
print(eval_set.scoring_strategy)  # e.g. "extraction"
```

**TypeScript**

```typescript
const items = [
  {
    input: { contract_text: "This Agreement is made on 3 March 2026 between Acme Corp and Globex LLC..." },
    expected_output: { effective_date: "2026-03-03", parties: ["Acme Corp", "Globex LLC"] },
  },
  {
    input: { contract_text: "Master Services Agreement, dated January 12, 2026, by and between Initech and Hooli..." },
    expected_output: { effective_date: "2026-01-12", parties: ["Initech", "Hooli"] },
  },
  // ... more rows. A few dozen labeled rows already give you a usable signal.
];

const evalSet = await pa.evals.sets.create({
  items,
  prompt: "extract the effective date and parties from each contract",
}); // refuses with suggestions if what you asked for doesn't match the data

console.log(evalSet.id);              // use this in runs.create({ evalSet: ... })
console.log(evalSet.itemCount);       // 2
console.log(evalSet.scoringStrategy); // e.g. "extraction"
```

`items` must be non-empty (an empty list raises `ValueError` before any request goes out). If you omit `name`, the set is labeled `"sdk eval set (N items)"`.

Reuse a set across many runs, or list and prune as you iterate:

**Python**

```python
for s in pa.evals.sets.list():
    print(s.id, s.task_id, s.item_count, s.name)

# pa.evals.sets.delete(eval_set.id)   # when you are done with it
```

**TypeScript**

```typescript
for (const s of await pa.evals.sets.list()) {
  console.log(s.id, s.taskId, s.itemCount, s.name);
}

// await pa.evals.sets.delete(evalSet.id);   // when you are done with it
```

### 2b. Document tasks: attach the file to each row

When `task.has_blob_input` is `True`, the row carries a binary document. Create the set with the row's text/label fields and a placeholder for the blob, then attach the file to that row by index:

**Python**

```python
doc_task = "invoice-extraction"   # a has_blob_input task

eval_set = pa.evals.sets.create(
    task=doc_task,
    items=[
        {"expected_output": {"invoice_number": "INV-7781", "total": "1240.00"}},
        {"expected_output": {"invoice_number": "INV-7782", "total": "98.50"}},
    ],
    prompt="extract the invoice number and total from each invoice",
)

# Attach one PDF per row. idx is the 0-based row; field_name is the blob input
# field from the task schema. MIME is auto-detected from the filename.
pa.evals.sets.upload_document(eval_set.id, "invoices/7781.pdf", idx=0, field_name="document")
pa.evals.sets.upload_document(eval_set.id, "invoices/7782.pdf", idx=1, field_name="document")
```

**TypeScript**

```typescript
const docTask = "invoice-extraction"; // a hasBlobInput task

const evalSet = await pa.evals.sets.create({
  task: docTask,
  items: [
    { expected_output: { invoice_number: "INV-7781", total: "1240.00" } },
    { expected_output: { invoice_number: "INV-7782", total: "98.50" } },
  ],
  prompt: "extract the invoice number and total from each invoice",
});

// Attach one PDF per row. idx is the 0-based row; fieldName is the blob input
// field from the task schema. MIME is auto-detected from the filename.
await pa.evals.sets.uploadDocument(evalSet.id, "invoices/7781.pdf", { idx: 0, fieldName: "document" });
await pa.evals.sets.uploadDocument(evalSet.id, "invoices/7782.pdf", { idx: 1, fieldName: "document" });
```

`upload_document` accepts a path (`str`/`Path`), raw `bytes`, or any binary file-like object; anything else raises `TypeError`. Files under 5 MiB upload inline; larger ones go through a signed-URL direct-to-storage flow. Either way the call returns the completion response dict. Pass `mime="application/pdf"` to override detection.

## 3. Run `"auto"` against the frontier baselines

This is the core call. The contender is `"auto"` — Pareta's routing brain, run against every row exactly as it runs in production — and `frontier="benchmarked"` pulls the vendor baselines Pareta has already benchmarked on this task. The run scores everything on the same rows with the same scorer, so the numbers are directly comparable.

**Python**

```python
run = pa.evals.runs.create(
    eval_set=eval_set.id,
    models=["auto"],          # the contender: Pareta's routing brain
    frontier="benchmarked",   # vendor baselines benchmarked on this task
    wait=True,                # block until the run is terminal
)

print(run.status)  # "completed"
```

**TypeScript**

```typescript
const run = await pa.evals.runs.create({
  evalSet: evalSet.id,
  models: ["auto"],         // the contender: Pareta's routing brain
  frontier: "benchmarked",  // vendor baselines benchmarked on this task
  wait: true,               // block until the run is terminal
});

console.log(run.status); // "completed"
```

`models` is required and is always `["auto"]` — individual open-weights models are not part of the eval surface; they stay behind auto's routing. `frontier` controls the baselines:

| `frontier=` | Evaluates against |
|---|---|
| `None` or `"none"` | nothing (`"auto"` alone) |
| `"benchmarked"` | frontier models Pareta has already benchmarked on this task (vision-filtered for document tasks) |
| `"all"` | every frontier model in the eval pool for the task |
| `["gpt-5.5", "claude-sonnet-4-6"]` | exactly these frontier ids |

The `"benchmarked"` and `"all"` keywords need to know the task. With `eval_set=...` the SDK looks it up from the set; if you pass an explicit list of ids it skips the lookup entirely.

GPUs and serving hardware never enter this call. There is no GPU, quantization, or run-mode knob — and no model to pick. You name a task and the baselines; Pareta resolves the rest. Frontier ids are the vendor names in the clear.

### Inline create (skip step 2)

If you do not need a reusable set, hand the rows straight to the run. Pass `items=` and `prompt=` instead of `eval_set=`, and the SDK creates the set for you:

**Python**

```python
run = pa.evals.runs.create(
    items=items,
    prompt="extract the effective date and parties from each contract",
    models=["auto"],
    frontier="benchmarked",
    wait=True,
)   # one call: builds the set and runs it
```

**TypeScript**

```typescript
const run = await pa.evals.runs.create({
  items,
  prompt: "extract the effective date and parties from each contract",
  models: ["auto"],
  frontier: "benchmarked",
  wait: true,
}); // one call: builds the set and runs it
```

You must pass either `eval_set=<id>` or `items=` plus `prompt=` (`task=` is optional); anything else raises `ValueError`.

### Pinning the frontier roster

To see exactly which baselines a keyword resolves to — or to build an explicit `frontier=[...]` list — enumerate the roster first with `evals.frontier_models`; each entry exposes `.id`, `.vendor`, `.vision`, and `.benchmarked`:

**Python**

```python
roster = pa.evals.frontier_models(task=eval_set.task_id)   # resolved from your eval set
for m in roster:
    print(m.id, m.vendor, "vision" if m.vision else "text", "benchmarked" if m.benchmarked else "-")

# Pin two of them explicitly
ids = [m.id for m in roster if m.benchmarked][:2]
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"], frontier=ids, wait=True)
```

**TypeScript**

```typescript
const roster = await pa.evals.frontierModels(evalSet.taskId!); // resolved from your eval set
for (const m of roster) {
  console.log(m.id, m.vendor, m.vision ? "vision" : "text", m.benchmarked ? "benchmarked" : "-");
}

// Pin two of them explicitly
const ids = roster.filter((m) => m.benchmarked).map((m) => m.id).slice(0, 2);
const run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["auto"], frontier: ids, wait: true });
```

`frontier_models()` annotates `benchmarked` and applies the vision filter only when you pass `task=`. Without a task it returns the full roster, unannotated.

## 4. Read the ranked results

A terminal run carries one `EvalResult` per contender — `"auto"` plus each baseline. Sort by `quality_mean` to see where auto lands, and read `run.cost` to see what the run cost you:

**Python**

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

**TypeScript**

```typescript
const ranked = [...run.results].sort((a, b) => (b.qualityMean ?? 0) - (a.qualityMean ?? 0));

for (const r of ranked) {
  const costPerItem = (r.meanCostMicroUsd ?? 0) / 1_000_000; // micro-USD → dollars
  console.log(
    `${(r.modelId ?? "").padEnd(24)}  ` +
      `quality=${r.qualityMean!.toFixed(3)}  ` +
      `[${r.qualityCiLow!.toFixed(3)}, ${r.qualityCiHigh!.toFixed(3)}]  ` +
      `$${costPerItem.toFixed(6)}/item  ` +
      `ok=${r.nSucceeded} err=${r.errorCount}`,
  );
}

console.log(`\nrun cost: $${run.cost}`);     // dollar string, floored to cents
console.log(`raw micro-USD: ${run.costMicroUsd}`);
```

What the fields mean:

- **`quality_mean`**: the contender's mean score on the task's scorer, in `[0, 1]`.
- **`quality_ci_low` / `quality_ci_high`**: the 95% confidence interval. If two contenders' intervals overlap heavily, your eval set is too small to separate them, so add rows.
- **`mean_cost_micro_usd`**: average cost per item, kept in micro-USD (not floored). This is where the auto-vs-frontier comparison lives, so sub-cent precision is preserved: auto matching frontier quality at a fraction of the cost is the whole point.
- **`n_succeeded` / `error_count`**: how many rows scored cleanly. Auto's failures count as errors, not skips — availability is part of what a benchmark should measure.
- **`model_id`**: `"auto"` for Pareta's row; the vendor id for each baseline. `kind` is `"frontier"` on the baseline rows, so you can filter the contender from what it is measured against.

Reading the verdict: auto's quality CI overlapping the frontier's at a lower per-item cost = frontier-grade on your data; a higher mean without overlap = ahead.

### A note on money

`run.cost` is a `Decimal` of dollars, floored to whole cents, so the SDK never overstates a charge and a sub-cent run reads `Decimal("0.00")`. For the exact figure use `run.cost_micro_usd` (an integer, where `1_000_000` micro-USD is `$1.00`). The same convention is why per-item rates like `mean_cost_micro_usd` stay in micro-USD: flooring them to cents would erase the auto-vs-frontier difference you ran the eval to find.

## Not blocking on the run

`wait=True` polls until the run reaches `"completed"` or `"failed"`, then returns. For long sets, tune the cadence and ceiling:

**Python**

```python
run = pa.evals.runs.create(
    eval_set=eval_set.id,
    models=["auto"],
    frontier="benchmarked",
    wait=True,
    poll_interval=5.0,   # seconds between polls (default 3.0)
    timeout=1800.0,      # give up after 30 min (default 900.0); raises ParetaError on timeout
)
```

**TypeScript**

```typescript
const run = await pa.evals.runs.create({
  evalSet: evalSet.id,
  models: ["auto"],
  frontier: "benchmarked",
  wait: true,
  pollInterval: 5,   // seconds between polls (default 3)
  timeout: 1800,     // give up after 30 min (default 900); throws ParetaError on timeout
});
```

Or fire and poll yourself. `wait=False` returns immediately with a run you can retrieve later:

**Python**

```python
run = pa.evals.runs.create(eval_set=eval_set.id,
                           models=["auto"], frontier="benchmarked")
run_id = run.id
# ... later, from anywhere ...
run = pa.evals.runs.retrieve(run_id)
if run.is_terminal:
    print(run.status, run.results)

# equivalently, block on an already-started run:
run = pa.evals.runs.wait(run_id, timeout=1800.0)
```

**TypeScript**

```typescript
let run = await pa.evals.runs.create({
  evalSet: evalSet.id,
  models: ["auto"],
  frontier: "benchmarked",
});
const runId = run.id!;
// ... later, from anywhere ...
run = await pa.evals.runs.retrieve(runId);
if (run.isTerminal) {
  console.log(run.status, run.results);
}

// equivalently, block on an already-started run:
run = await pa.evals.runs.wait(runId, { timeout: 1800 });
```

## Handling an empty balance

Both auto's compute and the frontier baselines are metered. If the org balance cannot cover the run, `create` raises before any work is billed:

**Python**

```python
from pareta import InsufficientCreditsError

try:
    run = pa.evals.runs.create(eval_set=eval_set.id,
                               models=["auto"], frontier="benchmarked", wait=True)
except InsufficientCreditsError:
    print("Out of credit. Top up in the dashboard (billing is browser-only).")
```

**TypeScript**

```typescript
import { InsufficientCreditsError } from "pareta";

try {
  const run = await pa.evals.runs.create({
    evalSet: evalSet.id,
    models: ["auto"],
    frontier: "benchmarked",
    wait: true,
  });
} catch (e) {
  if (e instanceof InsufficientCreditsError) {
    console.log("Out of credit. Top up in the dashboard (billing is browser-only).");
  } else {
    throw e;
  }
}
```

`InsufficientCreditsError` is a subclass of `APIStatusError` (status 402), so you can also catch the broader `ParetaError` if you want one handler for every SDK failure.

## Full example

**Python**

```python
from pareta import Pareta, InsufficientCreditsError

pa = Pareta.from_env()

# 1. Your rows + one sentence saying what you want done with each row.
prompt = "extract the effective date and parties from each contract"

# 2. Build the eval set from your rows.
items = [
    {"input": {"contract_text": "This Agreement is made on 3 March 2026 between Acme Corp and Globex LLC..."},
     "expected_output": {"effective_date": "2026-03-03", "parties": ["Acme Corp", "Globex LLC"]}},
    {"input": {"contract_text": "Master Services Agreement, dated January 12, 2026, by and between Initech and Hooli..."},
     "expected_output": {"effective_date": "2026-01-12", "parties": ["Initech", "Hooli"]}},
]
eval_set = pa.evals.sets.create(items=items, prompt=prompt,
                                name="contract fields v1")
print("scored as:", eval_set.scoring_strategy)

# 3. Run auto against the benchmarked frontier baselines.
try:
    run = pa.evals.runs.create(
        eval_set=eval_set.id,
        models=["auto"],
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

**TypeScript**

```typescript
import { Pareta, InsufficientCreditsError } from "pareta";

const pa = Pareta.fromEnv();

// 1. Your rows + one sentence saying what you want done with each row.
const prompt = "extract the effective date and parties from each contract";

// 2. Build the eval set from your rows.
const items = [
  { input: { contract_text: "This Agreement is made on 3 March 2026 between Acme Corp and Globex LLC..." },
    expected_output: { effective_date: "2026-03-03", parties: ["Acme Corp", "Globex LLC"] } },
  { input: { contract_text: "Master Services Agreement, dated January 12, 2026, by and between Initech and Hooli..." },
    expected_output: { effective_date: "2026-01-12", parties: ["Initech", "Hooli"] } },
];
const evalSet = await pa.evals.sets.create({ items, prompt, name: "contract fields v1" });
console.log("scored as:", evalSet.scoringStrategy);

// 3. Run auto against the benchmarked frontier baselines.
let run;
try {
  run = await pa.evals.runs.create({
    evalSet: evalSet.id,
    models: ["auto"],
    frontier: "benchmarked",
    wait: true,
  });
} catch (e) {
  if (e instanceof InsufficientCreditsError) {
    throw new Error("Out of credit. Top up in the dashboard.");
  }
  throw e;
}

// 4. Read the ranked results.
for (const r of [...run.results].sort((a, b) => (b.qualityMean ?? 0) - (a.qualityMean ?? 0))) {
  console.log(`${(r.modelId ?? "").padEnd(24)} ${r.qualityMean!.toFixed(3)}  $${((r.meanCostMicroUsd ?? 0) / 1e6).toFixed(6)}/item`);
}

console.log("run cost:", run.cost); // dollar string, floored to cents
```

## Async

Every call here has an `async` twin on `AsyncPareta`. The signatures match; the methods are coroutines (`wait` included).

**Python**

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        eval_set = await pa.evals.sets.create(
            task="contract-key-fields", items=items,
            prompt="extract the effective date and parties from each contract")
        run = await pa.evals.runs.create(
            eval_set=eval_set.id,
            models=["auto"],
            frontier="benchmarked",
            wait=True,
        )
        for r in run.results:
            print(r.model_id, r.quality_mean)
        print("run cost:", run.cost)

asyncio.run(main())
```

**TypeScript**

In TypeScript there is no separate `AsyncPareta` — the one `Pareta` client is already
async. Every I/O method returns a `Promise`, so you just `await` it; there is no sync/async
split to mirror and no context manager to close.

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

const evalSet = await pa.evals.sets.create({
  task: "contract-key-fields", items,
  prompt: "extract the effective date and parties from each contract",
});
const run = await pa.evals.runs.create({
  evalSet: evalSet.id,
  models: ["auto"],
  frontier: "benchmarked",
  wait: true,
});
for (const r of run.results) {
  console.log(r.modelId, r.qualityMean);
}
console.log("run cost:", run.cost);
```

## Next steps

- [Run inference](../guide/inference.md): send production traffic to the same `model="auto"` your eval just measured; inference is metered the same way evals are.
- [Cost & quality monitoring](./cost-and-metrics.md): watch spend, success, and projected savings with `auto.metrics()`.
- [Errors and retries](../guide/errors-and-retries.md): the full exception hierarchy behind `InsufficientCreditsError` and friends.
