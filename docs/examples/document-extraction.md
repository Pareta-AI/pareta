# Document extraction (PDF/image)

Pull structured fields out of PDFs and scanned images with `model="auto"` — and prove, on your own documents, that the routing holds frontier quality at a fraction of the cost.

`model="auto"` already routes document requests to Pareta's benchmark-proven extraction specialists — nothing to deploy, no model to pick. This page walks the loop that keeps you honest about it:

1. Find the blob task and check what it expects.
2. Build an eval set from your own documents (one JSONL row per document, with the PDF/image attached to each row).
3. Benchmark `"auto"` against frontier (vision) baselines on those documents.
4. Read the quality and cost verdict.
5. Send production documents to `model="auto"` with OpenAI-compatible inference.

Why do it this way: a document task is a *blob* task. The model reads pixels, not just text, so trusting any router — Pareta's included — on gut is a bad idea. Running an eval on your real documents tells you, in dollars and quality points, how `"auto"` compares to the frontier on exactly your paper. Both evals and inference are metered against your org balance, so the eval also tells you the bill before you commit.

Throughout, there is no model to name and no hardware to size: the only inference id is `"auto"`, and frontier (vendor) ids appear only as eval baselines.

## Setup

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()   # reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();   // reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

`from_env()` is the path you want in real code. See [Inference](../guide/inference.md) for the OpenAI-compatible alternative.

## 1. Find the document task

Document tasks carry binary inputs, surfaced as `task.has_blob_input == True`. If you know the task id (here, `invoice-extraction`), retrieve it directly. If you only know your intent in words, let the matcher rank candidates.

**Python**

```python
# By id
task = pa.tasks.retrieve("invoice-extraction")
print(task.id, task.default_scorer, task.has_blob_input)
# invoice-extraction  field_f1  True

# Or by intent
m = pa.tasks.match("extract totals and line items from vendor invoices")
if m.matched:
    print("chose:", m.chosen.task_id, m.chosen.confidence)   # 'high' | 'medium' | 'low'
for c in m.candidates:
    print(f"  {c.task_id}  score={c.score:.2f}  {c.confidence}")
```

**TypeScript**

```typescript
// By id
const task = await pa.tasks.retrieve("invoice-extraction");
console.log(task.id, task.defaultScorer, task.hasBlobInput);
// invoice-extraction  field_f1  true

// Or by intent
const m = await pa.tasks.match("extract totals and line items from vendor invoices");
if (m.matched) {
  console.log("chose:", m.chosen.taskId, m.chosen.confidence);   // 'high' | 'medium' | 'low'
}
for (const c of m.candidates) {
  console.log(`  ${c.taskId}  score=${c.score.toFixed(2)}  ${c.confidence}`);
}
```

`task.default_scorer` is the scorer the eval run applies (for a field-extraction task that is typically a field-level F1). You do not invoke it yourself; the run scores each contender against the expected output you provide in step 2.

See the [tasks reference](../reference/tasks.md) for the full catalog and matching surface.

## 2. Build an eval set from your documents

A document eval set is one JSONL row per document. Each row holds the *expected* extraction (what a correct answer looks like) plus a placeholder for the document blob. You attach the actual PDF/image to each row in a second step with `upload_document`.

Create the set first. `items` must be non-empty. The blob field (here `document`) is the input field the document attaches to; the rest of each row is the gold/expected output the scorer grades against.

**Python**

```python
items = [
    {
        "document": None,                       # filled by upload_document below
        "expected_output": {
            "invoice_number": "INV-4471",
            "invoice_date": "2026-03-14",
            "total": "1284.50",
            "currency": "USD",
            "vendor": "Katana ML",
        },
    },
    {
        "document": None,
        "expected_output": {
            "invoice_number": "INV-4472",
            "invoice_date": "2026-03-15",
            "total": "962.00",
            "currency": "USD",
            "vendor": "Katana ML",
        },
    },
]

eval_set = pa.evals.sets.create(
    task="invoice-extraction",
    items=items,
    prompt="extract invoice_number, invoice_date, total, currency, and vendor from each invoice",
    name="Q1 vendor invoices (10 docs)",   # optional; auto-named if omitted
)
print(eval_set.id, eval_set.item_count, eval_set.scoring_strategy)
# es_…  2  extraction
```

**TypeScript**

```typescript
const items = [
  {
    document: null,                          // filled by uploadDocument below
    expected_output: {
      invoice_number: "INV-4471",
      invoice_date: "2026-03-14",
      total: "1284.50",
      currency: "USD",
      vendor: "Katana ML",
    },
  },
  {
    document: null,
    expected_output: {
      invoice_number: "INV-4472",
      invoice_date: "2026-03-15",
      total: "962.00",
      currency: "USD",
      vendor: "Katana ML",
    },
  },
];

const evalSet = await pa.evals.sets.create({
  task: "invoice-extraction",
  items,
  prompt: "extract invoice_number, invoice_date, total, currency, and vendor from each invoice",
  name: "Q1 vendor invoices (10 docs)",   // optional; auto-named if omitted
});
console.log(evalSet.id, evalSet.itemCount, evalSet.scoringStrategy);
// es_…  2  extraction
```

Now attach the document for each row. `idx` is the 0-based row index and `field_name` is the blob field you left as `None` above. `file` accepts a path (`str`/`Path`), raw `bytes`, or any binary file-like object; the MIME type is guessed from the filename and can be overridden with `mime=`.

**Python**

```python
from pathlib import Path

invoices = [Path("invoices/INV-4471.pdf"), Path("invoices/INV-4472.png")]

for idx, path in enumerate(invoices):
    pa.evals.sets.upload_document(
        eval_set.id,
        path,
        idx=idx,
        field_name="document",
    )
```

**TypeScript**

```typescript
const invoices = ["invoices/INV-4471.pdf", "invoices/INV-4472.png"];

for (let idx = 0; idx < invoices.length; idx++) {
  await pa.evals.sets.uploadDocument(
    evalSet.id,
    invoices[idx],
    { idx, fieldName: "document" },
  );
}
```

The upload is one call regardless of file size. Files under 5 MiB go up inline; larger files use a signed-URL direct-to-storage flow under the hood. You can also pass bytes or a handle:

**Python**

```python
with open("invoices/INV-4471.pdf", "rb") as fh:
    pa.evals.sets.upload_document(eval_set.id, fh, idx=0, field_name="document")

raw = Path("scan.tiff").read_bytes()
pa.evals.sets.upload_document(
    eval_set.id, raw, idx=1, field_name="document", mime="image/tiff",
)
```

**TypeScript**

```typescript
import { readFile } from "node:fs/promises";

// `file` accepts a path, a Blob, an ArrayBuffer, or a Uint8Array.
const pdf = await readFile("invoices/INV-4471.pdf");   // Buffer (a Uint8Array)
await pa.evals.sets.uploadDocument(evalSet.id, pdf, { idx: 0, fieldName: "document" });

const raw = await readFile("scan.tiff");
await pa.evals.sets.uploadDocument(
  evalSet.id, raw, { idx: 1, fieldName: "document", mime: "image/tiff" },
);
```

## 3. Run the eval

The contender is `"auto"` — the same routing that will serve your production documents — and `frontier=` chooses the baselines it is measured against. For a document task you want vision-capable baselines; `frontier="benchmarked"` resolves to the frontier models Pareta has already benchmarked on this task (vision-filtered for document tasks), so you compare against the right roster automatically.

**Python**

```python
run = pa.evals.runs.create(
    eval_set=eval_set.id,
    models=["auto"],                         # the contender: Pareta's routing brain
    frontier="benchmarked",                  # vision frontier baselines on this task
    wait=True,                               # block until the run is terminal
)
print(run.status, run.id)                    # 'completed'  run_…
```

**TypeScript**

```typescript
const run = await pa.evals.runs.create({
  evalSet: evalSet.id,
  models: ["auto"],                         // the contender: Pareta's routing brain
  frontier: "benchmarked",                  // vision frontier baselines on this task
  wait: true,                               // block until the run is terminal
});
console.log(run.status, run.id);            // 'completed'  run_…
```

`wait=True` polls until the run reaches `completed` or `failed` (default `poll_interval=3.0`s, `timeout=900.0`s), then returns the final run. To fire and poll yourself, leave `wait=False` and call `runs.wait(run.id)` or `runs.retrieve(run.id)` later:

**Python**

```python
run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"], frontier="benchmarked")
# ... do other work ...
run = pa.evals.runs.wait(run.id, poll_interval=5.0, timeout=1200.0)
```

**TypeScript**

```typescript
let run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["auto"], frontier: "benchmarked" });
// ... do other work ...
run = await pa.evals.runs.wait(run.id, { pollInterval: 5, timeout: 1200 });
```

If you would rather not pre-create the set, `runs.create` accepts `items=… + prompt=…` inline (`task=…` optional) and creates the set for you. You still attach blobs first, so for document tasks the explicit `sets.create` + `upload_document` path above is the one to use.

### What `frontier=` accepts

| Value | Resolves to |
|---|---|
| `None` or `"none"` | no baselines |
| `"all"` | every frontier model for the task (from `pa.evals.frontier_models(task=…)`) |
| `"benchmarked"` | frontier models Pareta has already benchmarked on this task (vision-filtered for document tasks) |
| `["gpt-5.5", "claude-sonnet-4-6"]` | exactly those frontier ids |

Frontier (vendor) ids are in the clear, so you can name them explicitly. To see the roster first:

**Python**

```python
for fm in pa.evals.frontier_models(task="invoice-extraction"):
    print(fm.id, fm.vendor, "vision" if fm.vision else "text", "benchmarked" if fm.benchmarked else "")
```

**TypeScript**

```typescript
for (const fm of await pa.evals.frontierModels("invoice-extraction")) {
  console.log(fm.id, fm.vendor, fm.vision ? "vision" : "text", fm.benchmarked ? "benchmarked" : "");
}
```

### Metering

The run debits your org balance for the compute it consumes, auto and frontier baselines alike. If the balance is empty, `runs.create` raises `InsufficientCreditsError` (402). Top-up is browser-only; the SDK never exposes balance or payment methods.

**Python**

```python
from pareta import InsufficientCreditsError

try:
    run = pa.evals.runs.create(eval_set=eval_set.id, models=["auto"], frontier="benchmarked", wait=True)
except InsufficientCreditsError:
    print("Org out of credit — top up in the dashboard, then re-run.")
```

**TypeScript**

```typescript
import { InsufficientCreditsError } from "pareta";

try {
  const run = await pa.evals.runs.create({ evalSet: evalSet.id, models: ["auto"], frontier: "benchmarked", wait: true });
} catch (e) {
  if (e instanceof InsufficientCreditsError) {
    console.log("Org out of credit — top up in the dashboard, then re-run.");
  } else {
    throw e;
  }
}
```

## 4. Read the verdict

`run.results` is one `EvalResult` per contender: `"auto"` plus each frontier baseline, each with mean quality, a 95% confidence interval, and the average cost per item. The baseline rows carry `kind == "frontier"`; auto's row is the one with `model_id == "auto"`. `run.cost` is the billed total for the whole run.

**Python**

```python
if run.status == "failed":
    raise RuntimeError(run.error_detail)

print(f"run cost: ${run.cost}")              # Decimal dollars, floored to cents

for r in sorted(run.results, key=lambda r: (r.quality_mean or 0), reverse=True):
    print(
        f"{r.model_id:18} {(r.kind or ''):8} "
        f"q={r.quality_mean:.3f} "
        f"[{r.quality_ci_low:.3f}, {r.quality_ci_high:.3f}]  "
        f"{r.mean_cost_micro_usd} uUSD/item  "
        f"ok={r.n_succeeded} err={r.error_count}"
    )
```

**TypeScript**

```typescript
if (run.status === "failed") {
  throw new Error(run.errorDetail ?? "eval run failed");
}

console.log(`run cost: $${run.cost}`);       // dollar string, floored to cents

const sorted = [...run.results].sort((a, b) => (b.qualityMean ?? 0) - (a.qualityMean ?? 0));
for (const r of sorted) {
  console.log(
    `${r.modelId.padEnd(18)} ${(r.kind ?? "").padEnd(8)} ` +
    `q=${r.qualityMean.toFixed(3)} ` +
    `[${r.qualityCiLow.toFixed(3)}, ${r.qualityCiHigh.toFixed(3)}]  ` +
    `${r.meanCostMicroUsd} uUSD/item  ` +
    `ok=${r.nSucceeded} err=${r.errorCount}`,
  );
}
```

```
gpt-5.5            frontier q=0.946 [0.921, 0.968]  41200 uUSD/item  ok=10 err=0
auto                        q=0.938 [0.912, 0.961]   3400 uUSD/item  ok=10 err=0
gemini-3-1-pro     frontier q=0.925 [0.897, 0.950]  28900 uUSD/item  ok=10 err=0
```

Reading it: auto lands within a point of the strongest frontier baseline — the CIs overlap, so the two are not meaningfully different on this sample — at roughly a twelfth of the per-item cost. That is the verdict the eval exists to deliver, and there is nothing to pick or provision off the back of it: the routing that produced auto's row is the routing that serves production.

### A note on money

`run.cost` is a `Decimal` in dollars, floored to whole cents (the SDK never rounds a charge up). The raw integer is on `run.cost_micro_usd` (1,000,000 = $1.00) if you need sub-cent precision. Per-item rates like `result.mean_cost_micro_usd` stay in micro-USD on purpose; flooring them to cents would erase the auto-vs-frontier comparison that just earned its keep above.

**Python**

```python
print(run.cost)             # Decimal('0.07')
print(run.cost_micro_usd)   # 72500
```

**TypeScript**

```typescript
console.log(run.cost);          // "0.07"  (floored-to-cents dollar string)
console.log(run.costMicroUsd);  // 72500
```

## 5. Send documents to `model="auto"` in production

The routing your eval just measured is already live — it is the standard chat surface with `model="auto"`, OpenAI-compatible on the wire. For a vision document task, send the image in the standard OpenAI content-parts shape; PDFs are typically handed in as page images or a data URL, matching whatever the task expects.

**Python**

```python
import base64

img_b64 = base64.b64encode(open("invoices/new-INV.png", "rb").read()).decode()

resp = pa.chat.completions.create(
    model="auto",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Extract invoice_number, invoice_date, total, currency, vendor as JSON."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ],
        }
    ],
    temperature=0,
    max_tokens=512,
)
print(resp.choices[0].message.content)
print(resp.usage.total_tokens)
```

**TypeScript**

```typescript
import { readFile } from "node:fs/promises";

const imgB64 = (await readFile("invoices/new-INV.png")).toString("base64");

const resp = await pa.chat.completions.create({
  model: "auto",
  messages: [
    {
      role: "user",
      content: [
        { type: "text", text: "Extract invoice_number, invoice_date, total, currency, vendor as JSON." },
        { type: "image_url", image_url: { url: `data:image/png;base64,${imgB64}` } },
      ],
    },
  ],
  temperature: 0,
  max_tokens: 512,
});
console.log(resp.choices[0].message.content);
console.log(resp.usage.totalTokens);
```

Inference is metered the same way the eval was: a successful completion debits the org balance — one debit per request, no matter how many internal model calls auto's plan makes — and a zero balance raises `InsufficientCreditsError` (402). To stream tokens as they generate:

**Python**

```python
for chunk in pa.chat.completions.create(model="auto", messages=[...], stream=True):
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

**TypeScript**

```typescript
for await (const chunk of pa.chat.completions.create({ model: "auto", messages: [...], stream: true })) {
  process.stdout.write(chunk.choices[0].delta.content ?? "");
}
```

## Async

Every step mirrors on `AsyncPareta`. `runs.wait` is awaitable; chat streams are `async for`.

**Python**

```python
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        es = await pa.evals.sets.create(
            task="invoice-extraction", items=items,
            prompt="extract invoice_number, invoice_date, total, currency, and vendor from each invoice")
        await pa.evals.sets.upload_document(es.id, "invoices/INV-4471.pdf", idx=0, field_name="document")

        run = await pa.evals.runs.create(
            eval_set=es.id, models=["auto"], frontier="benchmarked", wait=True,
        )
        for r in run.results:
            print(r.model_id, r.quality_mean, r.mean_cost_micro_usd)

        resp = await pa.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": "Extract the total as JSON."}],
        )
        print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
// There is no AsyncPareta in TypeScript — the one `Pareta` client is already
// async. Every I/O method returns a Promise you `await`; streams are `for await`.
// No context manager, no `.close()`: there is no owned connection to release.
import { Pareta } from "pareta";

async function main() {
  const pa = Pareta.fromEnv();

  const es = await pa.evals.sets.create({
    task: "invoice-extraction", items,
    prompt: "extract invoice_number, invoice_date, total, currency, and vendor from each invoice",
  });
  await pa.evals.sets.uploadDocument(es.id, "invoices/INV-4471.pdf", { idx: 0, fieldName: "document" });

  const run = await pa.evals.runs.create({
    evalSet: es.id, models: ["auto"], frontier: "benchmarked", wait: true,
  });
  for (const r of run.results) {
    console.log(r.modelId, r.qualityMean, r.meanCostMicroUsd);
  }

  const resp = await pa.chat.completions.create({
    model: "auto",
    messages: [{ role: "user", content: "Extract the total as JSON." }],
  });
  console.log(resp.choices[0].message.content);
}
```

## The whole loop

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()
TASK = "invoice-extraction"

# 1. eval set from your documents
es = pa.evals.sets.create(
    task=TASK, items=items,
    prompt="extract invoice_number, invoice_date, total, currency, and vendor from each invoice",
    name="vendor invoices")
for idx, path in enumerate(invoices):
    pa.evals.sets.upload_document(es.id, path, idx=idx, field_name="document")

# 2. benchmark auto against vision frontier baselines
run = pa.evals.runs.create(
    eval_set=es.id,
    models=["auto"],
    frontier="benchmarked",
    wait=True,
)
print(f"eval cost ${run.cost}")
for r in run.results:
    print(r.model_id, r.quality_mean, r.mean_cost_micro_usd)

# 3. production is the same id the eval just measured
resp = pa.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Extract the invoice fields as JSON."}],
)
print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();
const TASK = "invoice-extraction";

// 1. eval set from your documents
const es = await pa.evals.sets.create({
  task: TASK, items,
  prompt: "extract invoice_number, invoice_date, total, currency, and vendor from each invoice",
  name: "vendor invoices",
});
for (let idx = 0; idx < invoices.length; idx++) {
  await pa.evals.sets.uploadDocument(es.id, invoices[idx], { idx, fieldName: "document" });
}

// 2. benchmark auto against vision frontier baselines
const run = await pa.evals.runs.create({
  evalSet: es.id,
  models: ["auto"],
  frontier: "benchmarked",
  wait: true,
});
console.log(`eval cost $${run.cost}`);
for (const r of run.results) {
  console.log(r.modelId, r.qualityMean, r.meanCostMicroUsd);
}

// 3. production is the same id the eval just measured
const resp = await pa.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "Extract the invoice fields as JSON." }],
});
console.log(resp.choices[0].message.content);
```

## See also

- [Inference (OpenAI-compatible)](../guide/inference.md) — `model="auto"`, streaming, using the `openai` client.
- [The tasks reference](../reference/tasks.md) — the catalog, `match`, and task schemas.
- [Evaluating models on your data](../guide/evaluation.md) — eval sets, runs, frontier baselines, and metering in depth.
- [Cost & quality monitoring](./cost-and-metrics.md) — read run costs and watch live auto traffic with `auto.metrics()`.
