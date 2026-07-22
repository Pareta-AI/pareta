# Cost & quality monitoring

Every dollar you spend on Pareta runs through one org balance, and every `model="auto"` request your org sends gets rolled up for you. This page is about reading both: what a call or an eval run actually cost, how `"auto"` stacks up against the frontier baselines it replaces, and how to watch your live auto traffic — volume, success, spend, latency, and projected savings — so you catch a regression before your users do.

Two things to keep straight up front, because they shape every number below:

- **Money is metered against your org balance.** Inference (`chat.completions.create`) and evals (`evals.runs.create`) both debit the balance on success — one debit per request, no matter how many internal model calls auto's plan makes. An empty balance raises `InsufficientCreditsError` (402). The SDK never exposes balance or payment methods — top-up is browser-only, in the dashboard.
- **Models and GPUs are hidden behind `"auto"`.** You never priced a GPU-hour or picked a model; Pareta did, per request. So cost shows up as per-request debits, run totals, and an org-level rollup — and the only model ids in a cost report are `"auto"` and the frontier (vendor) ids in the clear.

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()  # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv(); // reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
```

## The money convention: dollars are floored to cents

You are billed in whole cents, and the SDK **floors** to cents so it never overstates a charge. That rule shows up in two complementary fields on anything that carries a total:

- `cost: Decimal` — the billed total in dollars, floored to whole cents. A run that truly cost a third of a cent reads `Decimal("0.00")`.
- `cost_micro_usd: int` — the raw integer in micro-USD, where `1_000_000` == `$1.00`. This is the precise number for your own accounting.

**Python**

```python
run = pa.evals.runs.retrieve(run_id)

print(run.cost)            # Decimal('0.07')  — billed dollars, floored to cents
print(run.cost_micro_usd)  # 74211            — raw micro-USD (74,211 uUSD)
```

**TypeScript**

```typescript
const run = await pa.evals.runs.retrieve(runId);

console.log(run.cost);          // "0.07"  — billed dollars (string), floored to cents
console.log(run.costMicroUsd);  // 74211   — raw micro-USD (74,211 uUSD)
```

The flooring is one-directional on purpose: a sub-cent total bills as `$0.00` but keeps its true value on `cost_micro_usd`, so nothing is lost. **Per-unit rates stay in micro-USD** and are never floored — flooring a sub-cent unit rate to whole cents would erase the auto-vs-frontier comparison that the whole exercise is about. You will see this on `result.mean_cost_micro_usd` below.

## What an eval run cost

An eval run is the densest cost signal you get, because it prices `"auto"` and several frontier baselines on the same rows in one shot. The run carries the bill; each `EvalResult` carries that contender's per-item rate.

**Python**

```python
run = pa.evals.runs.create(
    task="contract-key-fields",
    items=[
        {"input": "Effective as of January 1, 2026, ...", "expected": {"effective_date": "2026-01-01"}},
        {"input": "This Agreement terminates on 2027-12-31 ...", "expected": {"termination_date": "2027-12-31"}},
    ],
    intent="extract the key dates from each contract",
    models=["auto"],                 # the contender
    frontier="benchmarked",          # baselines already benchmarked on this task
    wait=True,                       # block until the run is terminal
)

print(f"run {run.id}: {run.status}")
print(f"billed ${run.cost} ({run.cost_micro_usd} uUSD)")  # auto + frontier compute

for r in run.results:
    print(f"{r.model_id:16} {(r.kind or ''):8} "
          f"q={r.quality_mean:.3f} [{r.quality_ci_low:.3f}, {r.quality_ci_high:.3f}]  "
          f"~{r.mean_cost_micro_usd} uUSD/item  "
          f"({r.n_succeeded} ok, {r.error_count} err)")
```

**TypeScript**

```typescript
const run = await pa.evals.runs.create({
  task: "contract-key-fields",
  items: [
    { input: "Effective as of January 1, 2026, ...", expected: { effective_date: "2026-01-01" } },
    { input: "This Agreement terminates on 2027-12-31 ...", expected: { termination_date: "2027-12-31" } },
  ],
  intent: "extract the key dates from each contract",
  models: ["auto"],               // the contender
  frontier: "benchmarked",        // baselines already benchmarked on this task
  wait: true,                     // block until the run is terminal
});

console.log(`run ${run.id}: ${run.status}`);
console.log(`billed $${run.cost} (${run.costMicroUsd} uUSD)`); // auto + frontier compute

for (const r of run.results) {
  console.log(
    `${(r.modelId ?? "").padEnd(16)} ${(r.kind ?? "").padEnd(8)} ` +
      `q=${r.qualityMean?.toFixed(3)} [${r.qualityCiLow?.toFixed(3)}, ${r.qualityCiHigh?.toFixed(3)}]  ` +
      `~${r.meanCostMicroUsd} uUSD/item  ` +
      `(${r.nSucceeded} ok, ${r.errorCount} err)`,
  );
}
```

`run.cost` / `run.cost_micro_usd` is the **total** for the run, across both auto and any frontier baselines — both are metered against your balance. Each `EvalResult` reports `mean_cost_micro_usd`, the average cost per item for that contender in micro-USD. That field is the heart of a cost comparison, so it deliberately stays in raw micro-USD: a 700-uUSD frontier item and a 90-uUSD auto item both floor to `$0.00`, and the gap between them is exactly the thing you came to measure.

If the balance is empty, `create` raises `InsufficientCreditsError` (402) before any compute runs. See [Errors, retries & timeouts](../guide/errors-and-retries.md).

### Quality vs. cost, the actual trade

The point of running `"auto"` next to frontier baselines is to read both axes at once: whether quality holds, and how much money you save. Pick auto's row out by `model_id` and compare it against each baseline (`kind == "frontier"`).

**Python**

```python
run = pa.evals.runs.retrieve(run_id)

auto = next(r for r in run.results if r.model_id == "auto")
baselines = [r for r in run.results if r.kind == "frontier"]

print(f"auto             q={auto.quality_mean:.3f}  {auto.mean_cost_micro_usd} uUSD/item")
for f in sorted(baselines, key=lambda r: r.quality_mean or 0.0, reverse=True):
    line = f"{f.model_id:16} q={f.quality_mean:.3f}  {f.mean_cost_micro_usd} uUSD/item"
    if f.mean_cost_micro_usd and auto.mean_cost_micro_usd:
        # micro-USD ratio — never compute savings off the floored dollar field
        cheaper = f.mean_cost_micro_usd / auto.mean_cost_micro_usd
        dq = (auto.quality_mean or 0.0) - (f.quality_mean or 0.0)
        line += f"  (auto is {cheaper:.1f}x cheaper, dq={dq:+.3f})"
    print(line)
```

**TypeScript**

```typescript
const run = await pa.evals.runs.retrieve(runId);

const auto = run.results.find((r) => r.modelId === "auto")!;
const baselines = run.results.filter((r) => r.kind === "frontier");

console.log(`auto             q=${auto.qualityMean?.toFixed(3)}  ${auto.meanCostMicroUsd} uUSD/item`);
for (const f of [...baselines].sort((a, b) => (b.qualityMean ?? 0) - (a.qualityMean ?? 0))) {
  let line = `${(f.modelId ?? "").padEnd(16)} q=${f.qualityMean?.toFixed(3)}  ${f.meanCostMicroUsd} uUSD/item`;
  if (f.meanCostMicroUsd && auto.meanCostMicroUsd) {
    // micro-USD ratio — never compute savings off the floored dollar field
    const cheaper = f.meanCostMicroUsd / auto.meanCostMicroUsd;
    const dq = (auto.qualityMean ?? 0) - (f.qualityMean ?? 0);
    line += `  (auto is ${cheaper.toFixed(1)}x cheaper, dq=${dq >= 0 ? "+" : ""}${dq.toFixed(3)})`;
  }
  console.log(line);
}
```

Two rules when you read this:

- **Compute savings from `mean_cost_micro_usd`, never from `cost`.** The dollar field is floored to cents and a per-item rate is almost always sub-cent, so a ratio built on it would divide by zero or lie. Stay in micro-USD for any per-unit math.
- **Respect the confidence interval.** `quality_mean` comes with `quality_ci_low` / `quality_ci_high` (a 95% CI). Two contenders whose intervals overlap are not meaningfully different on this sample — add rows before you call the verdict on a hair's-width quality edge.

Full eval mechanics (building sets, frontier roster selection, document tasks, async) live in [Benchmark `"auto"` on your own data](./evaluate-on-your-data.md) and the [Evaluation guide](../guide/evaluation.md).

## What an inference call cost

Inference is OpenAI-compatible, so `chat.completions.create` returns a `ChatCompletion` with a `usage` block. Use it for token accounting; the dollar cost of that traffic lands in your org's auto rollup (next section) rather than inline on each response.

**Python**

```python
resp = pa.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Extract the effective date from: ..."}],
)

u = resp.usage
print(u.prompt_tokens, u.completion_tokens, u.total_tokens)
print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
const resp = await pa.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "Extract the effective date from: ..." }],
});

const u = resp.usage;
console.log(u.promptTokens, u.completionTokens, u.totalTokens);
console.log(resp.choices[0].message.content);
```

Each successful call debits your org balance — one debit per request, no matter how many internal model calls auto's plan makes. An empty balance raises `InsufficientCreditsError` (402) here too. The inference surface — streaming, kwargs pass-through, the OpenAI compatibility contract — is covered in [Running inference](../guide/inference.md).

## Monitoring your live auto traffic

Once production traffic is flowing, `auto.metrics()` is your window into it: one org-level rollup of every `model="auto"` request, covering volume, success, spend, latency, and the savings story. One call, no parameters — Python returns the raw rollup dict; TypeScript types it as `AutoMetrics`:

**Python**

```python
m = pa.auto.metrics()   # dict — the org's auto rollup

print(m["requests_30d"], "requests (30d),", m["requests_today"], "today")
print("success rate (30d):", m["success_rate_30d"])
print("billed (30d):", m["billed_micro_usd_30d"], "uUSD")
print("projected savings vs frontier (30d):", m["savings_vs_frontier_micro_usd_30d"], "uUSD")
```

**TypeScript**

```typescript
const m = await pa.auto.metrics(); // typed AutoMetrics

console.log(m.requests_30d, "requests (30d),", m.requests_today, "today");
console.log("success rate (30d):", m.success_rate_30d);
console.log("billed (30d):", m.billed_micro_usd_30d, "uUSD");
console.log("projected savings vs frontier (30d):", m.savings_vs_frontier_micro_usd_30d, "uUSD");
```

What comes back, dimension by dimension:

- **Volume + success** — `requests_30d`, `requests_today`, `success_rate_30d` (`None` with no traffic), and `days_30d`: one cell per day (`{day, n, ok, success_rate}`) over the last 30 days.
- **Spend** — `billed_micro_usd_30d` and `billed_micro_usd_today`, in raw micro-USD. The money convention holds: floor to cents yourself only when you want a billed-dollar figure.
- **Latency + errors** — `performance_hourly_7d`: hourly buckets (`{hour, requests, error_rate, p50_ms, p95_ms}`) over the last 7 days.
- **Projected savings vs frontier** — `savings_vs_frontier_micro_usd_30d` and `savings_multiple_30d`: what the same traffic would have cost at frontier list prices vs what you were billed. It is **projected** — a frontier list-priced counterfactual — and `None` when there is no traffic to project from.
- **`last_request`** — the most recent request's `created_at`, `status_code`, `duration_ms`, and billed cost; a quick liveness check.

### Watching for drift

The rollup is cheap to poll, so put it on a schedule and alert off the health fields: a `days_30d` cell whose `success_rate` dips below your bar, or a `performance_hourly_7d` bucket whose `error_rate` or `p95_ms` creeps up, is your cue to investigate before users notice.

**Python**

```python
m = pa.auto.metrics()

today = m["days_30d"][-1] if m["days_30d"] else None
if today and today["success_rate"] < 0.99:
    print(f"success slipped to {today['success_rate']:.4f} today — investigate")
```

**TypeScript**

```typescript
const m = await pa.auto.metrics();

const today = m.days_30d.at(-1);
if (today && today.success_rate < 0.99) {
  console.log(`success slipped to ${today.success_rate.toFixed(4)} today — investigate`);
}
```

### Spot-check a prompt against a frontier vendor

The rollup's savings number is a projection. For a concrete single-prompt data point, run the same messages against a frontier vendor and compare with what `"auto"` gave you:

**Python**

```python
side = pa.auto.compare_frontier(
    model="gpt-5.5",   # or gemini-3-5-flash, gemini-3-1-pro, claude-sonnet-4-6
    messages=[{"role": "user", "content": "Extract the effective date from: ..."}],
)
print(side["model"], side["cost_micro_usd"], "uUSD,", side["latency_ms"], "ms")
print(side["content"])
```

**TypeScript**

```typescript
const side = await pa.auto.compareFrontier({
  model: "gpt-5.5",   // or gemini-3-5-flash, gemini-3-1-pro, claude-sonnet-4-6
  messages: [{ role: "user", content: "Extract the effective date from: ..." }],
});
console.log(side.model, side.cost_micro_usd, "uUSD,", side.latency_ms, "ms");
console.log(side.content);
```

`compare_frontier` is **metered at the vendor's actual token cost** — one debit per call, and a failed vendor call bills $0. The allowed models are gpt-5.5, gemini-3-5-flash, gemini-3-1-pro, and claude-sonnet-4-6.

## Async

Every method here has an async twin on `AsyncPareta` with the same signatures — `auto.metrics()` and `auto.compare_frontier()` included. Pull the run and the rollup concurrently:

**Python**

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        run, m = await asyncio.gather(
            pa.evals.runs.retrieve(run_id),
            pa.auto.metrics(),
        )
        print("billed", run.cost, "/", run.cost_micro_usd, "uUSD")
        print("30d spend:", m["billed_micro_usd_30d"], "uUSD")
        print("projected savings:", m["savings_vs_frontier_micro_usd_30d"], "uUSD")

asyncio.run(main())
```

**TypeScript**

```typescript
// No AsyncPareta in TS — there's one Promise-only client, so every method is
// already async. Concurrency is just Promise.all over the awaitables.
const [run, m] = await Promise.all([
  pa.evals.runs.retrieve(runId),
  pa.auto.metrics(),
]);
console.log("billed", run.cost, "/", run.costMicroUsd, "uUSD");
console.log("30d spend:", m.billed_micro_usd_30d, "uUSD");
console.log("projected savings:", m.savings_vs_frontier_micro_usd_30d, "uUSD");
```

## Lossless access

Every response object keeps the raw server JSON. `run.to_dict()` and `result.to_dict()` give you everything the API sent, including fields not yet surfaced as typed properties. `auto.metrics()` already hands you the raw rollup (a dict in Python, `AutoMetrics` in TypeScript), so when the backend grows a new key it shows up without an SDK upgrade.

## See also

- [Benchmark `"auto"` on your own data](./evaluate-on-your-data.md) — build eval sets, pick frontier baselines, read per-contender results.
- [Concurrent & async](./concurrent-async.md) — fan-out inference and parallel eval runs.
- [Running inference](../guide/inference.md) — the OpenAI-compatible chat surface and streaming.
- [Errors, retries & timeouts](../guide/errors-and-retries.md) — `InsufficientCreditsError`, the money convention, and the exception hierarchy.
