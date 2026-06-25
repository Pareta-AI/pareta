# Cost & quality monitoring

Every dollar you spend on Pareta runs through one org balance, and every model you serve gets watched for drift. This page is about reading both: what a call or an eval run actually cost, how the open model you deployed stacks up against the frontier baseline it replaced, and how to watch a live endpoint's spend and quality over time so you catch a regression before your users do.

Two things to keep straight up front, because they shape every number below:

- **Money is metered against your org balance.** Inference (`chat.completions.create`) and evals (`evals.runs.create`) both debit the balance on success. An empty balance raises `InsufficientCreditsError` (402). The SDK never exposes balance or payment methods — top-up is browser-only, in the dashboard.
- **GPUs are hidden and models are aliases.** You never priced a GPU-hour or picked a quantization; Pareta did. So cost shows up as a flat per-request rate for a numbered task (capability endpoints bill per token; speech bills per minute) or a run total, and the open models in every cost report are per-task public aliases, not raw model names. Frontier (vendor) ids are in the clear.

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

The flooring is one-directional on purpose: a sub-cent total bills as `$0.00` but keeps its true value on `cost_micro_usd`, so nothing is lost. **Per-unit rates stay in micro-USD** and are never floored — flooring a sub-cent unit rate to whole cents would erase the open-vs-frontier comparison that the whole exercise is about. You will see this on `result.mean_cost_micro_usd` below.

## What an eval run cost

An eval run is the densest cost signal you get, because it prices several models on the same rows in one shot. The run carries the bill; each `EvalResult` carries that model's per-item rate.

**Python**

```python
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

print(f"run {run.id}: {run.status}")
print(f"billed ${run.cost} ({run.cost_micro_usd} uUSD)")  # open + frontier compute

for r in run.results:
    print(f"{r.model_id:16} {r.kind:8} "
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
  models: ["llama-1", "qwen-2"],  // per-task open aliases
  frontier: "benchmarked",         // baselines already on this task's leaderboard
  wait: true,                      // block until the run is terminal
});

console.log(`run ${run.id}: ${run.status}`);
console.log(`billed $${run.cost} (${run.costMicroUsd} uUSD)`); // open + frontier compute

for (const r of run.results) {
  console.log(
    `${(r.modelId ?? "").padEnd(16)} ${(r.kind ?? "").padEnd(8)} ` +
      `q=${r.qualityMean?.toFixed(3)} [${r.qualityCiLow?.toFixed(3)}, ${r.qualityCiHigh?.toFixed(3)}]  ` +
      `~${r.meanCostMicroUsd} uUSD/item  ` +
      `(${r.nSucceeded} ok, ${r.errorCount} err)`,
  );
}
```

`run.cost` / `run.cost_micro_usd` is the **total** for the run, across both the open candidates and any frontier baselines — both are metered against your balance. Each `EvalResult` reports `mean_cost_micro_usd`, the average cost per item for that model in micro-USD. That field is the heart of a cost comparison, so it deliberately stays in raw micro-USD: a 700-uUSD frontier item and a 90-uUSD open item both floor to `$0.00`, and the gap between them is exactly the thing you came to measure.

If the balance is empty, `create` raises `InsufficientCreditsError` (402) before any compute runs. See [Errors, retries & timeouts](../guide/errors-and-retries.md).

### Quality vs. cost, the actual trade

The point of running open candidates next to a frontier baseline is to read both axes at once: how much quality you give up, and how much money you save. Split the results by `kind` and compare.

**Python**

```python
run = pa.evals.runs.retrieve(run_id)

frontier = next((r for r in run.results if r.kind == "frontier"), None)
open_models = [r for r in run.results if r.kind == "open"]

for r in sorted(open_models, key=lambda r: r.quality_mean or 0.0, reverse=True):
    line = f"{r.model_id:16} q={r.quality_mean:.3f}  {r.mean_cost_micro_usd} uUSD/item"
    if frontier and frontier.mean_cost_micro_usd and r.mean_cost_micro_usd:
        # micro-USD ratio — never compute savings off the floored dollar field
        cheaper = frontier.mean_cost_micro_usd / r.mean_cost_micro_usd
        dq = (r.quality_mean or 0.0) - (frontier.quality_mean or 0.0)
        line += f"  ({cheaper:.1f}x cheaper than {frontier.model_id}, dq={dq:+.3f})"
    print(line)
```

**TypeScript**

```typescript
const run = await pa.evals.runs.retrieve(runId);

const frontier = run.results.find((r) => r.kind === "frontier") ?? null;
const openModels = run.results.filter((r) => r.kind === "open");

for (const r of [...openModels].sort((a, b) => (b.qualityMean ?? 0) - (a.qualityMean ?? 0))) {
  let line = `${(r.modelId ?? "").padEnd(16)} q=${r.qualityMean?.toFixed(3)}  ${r.meanCostMicroUsd} uUSD/item`;
  if (frontier && frontier.meanCostMicroUsd && r.meanCostMicroUsd) {
    // micro-USD ratio — never compute savings off the floored dollar field
    const cheaper = frontier.meanCostMicroUsd / r.meanCostMicroUsd;
    const dq = (r.qualityMean ?? 0) - (frontier.qualityMean ?? 0);
    line += `  (${cheaper.toFixed(1)}x cheaper than ${frontier.modelId}, dq=${dq >= 0 ? "+" : ""}${dq.toFixed(3)})`;
  }
  console.log(line);
}
```

Two rules when you read this:

- **Compute savings from `mean_cost_micro_usd`, never from `cost`.** The dollar field is floored to cents and a per-item rate is almost always sub-cent, so a ratio built on it would divide by zero or lie. Stay in micro-USD for any per-unit math.
- **Respect the confidence interval.** `quality_mean` comes with `quality_ci_low` / `quality_ci_high` (a 95% CI). Two models whose intervals overlap are not meaningfully different on this sample — add rows before you call one the winner on a hair's-width quality edge.

Full eval mechanics (building sets, frontier roster selection, document tasks, async) live in [Evaluating on your own data](./evaluate-on-your-data.md) and the [Evaluation guide](../guide/evaluation.md).

## What an inference call cost

Inference is OpenAI-compatible, so `chat.completions.create` returns a `ChatCompletion` with a `usage` block. Use it for token accounting; the dollar cost of that traffic lands on the endpoint's cost metric (next section), since pricing is per-request at the endpoint, not returned inline per call.

**Python**

```python
resp = pa.chat.completions.create(
    model="ep-contract-key-fields",   # an endpoint id from endpoints.deploy()
    messages=[{"role": "user", "content": "Extract the effective date from: ..."}],
)

u = resp.usage
print(u.prompt_tokens, u.completion_tokens, u.total_tokens)
print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
const resp = await pa.chat.completions.create({
  model: "ep-contract-key-fields", // an endpoint id from endpoints.deploy()
  messages: [{ role: "user", content: "Extract the effective date from: ..." }],
});

const u = resp.usage;
console.log(u.promptTokens, u.completionTokens, u.totalTokens);
console.log(resp.choices[0].message.content);
```

Each successful call debits your org balance. An empty balance raises `InsufficientCreditsError` (402) here too. The inference surface — streaming, kwargs pass-through, the OpenAI compatibility contract — is covered in [Running inference](../guide/inference.md).

## Monitoring a live endpoint

Once a model is serving, `endpoints.metrics(endpoint_id)` is your window into its spend, quality, latency, and uptime over time. It returns a `Metrics` handle with one method per dimension. Each method takes free-form `**params` that become the query string (e.g. a time window or a grouping), and each returns the raw metric JSON for that dimension — shapes vary by dimension, and typed models arrive with the OpenAPI generation later.

**Python**

```python
m = pa.endpoints.metrics("ep-contract-key-fields")

cost      = m.cost()           # per-endpoint spend + vs-frontier savings
quality   = m.quality()        # judge windows over time
perf      = m.performance()    # p50/p95/p99 latency
uptime    = m.uptime()         # availability
activity  = m.activity()       # usage stats

# Narrow with params — they pass straight through as the query string.
last_day  = m.cost(window="24h")
by_day    = m.cost(group_by="day")
```

**TypeScript**

```typescript
const m = pa.endpoints.metrics("ep-contract-key-fields"); // sync handle, no await

const cost     = await m.cost();          // per-endpoint spend + vs-frontier savings
const quality  = await m.quality();       // judge windows over time
const perf     = await m.performance();   // p50/p95/p99 latency
const uptime   = await m.uptime();        // availability
const activity = await m.activity();      // usage stats

// Narrow with params — they pass straight through as the query string.
const lastDay = await m.cost({ window: "24h" });
const byDay   = await m.cost({ group_by: "day" });
```

`endpoints.metrics(id)` is a cheap local handle — it does no I/O until you call a dimension. So you can hold one handle and query several dimensions off it.

### Cost and the vs-frontier savings framing

`m.cost()` is the per-endpoint counterpart to a run's total: it reports what the endpoint has spent and frames it against the frontier baseline the open model stands in for. That "vs-frontier savings" framing is the whole pitch of serving an open model — the metric tells you, in production, how much cheaper this endpoint is than calling the vendor model would have been. Because the dimension returns raw JSON, read it with the dict accessors:

**Python**

```python
cost = pa.endpoints.metrics("ep-contract-key-fields").cost(window="7d")

# raw JSON dict — use the keys the dimension returns
print(cost.get("total_micro_usd"))
print(cost.get("frontier_baseline_micro_usd"))
print(cost.get("savings_micro_usd"))
```

**TypeScript**

```typescript
// dimensions return raw JSON (untyped) — read the keys the backend sends
const cost = (await pa.endpoints
  .metrics("ep-contract-key-fields")
  .cost({ window: "7d" })) as Record<string, unknown>;

console.log(cost.total_micro_usd);
console.log(cost.frontier_baseline_micro_usd);
console.log(cost.savings_micro_usd);
```

The exact keys are owned by the backend and may grow; treat the dict as the source of truth and pull what you need. The money convention still holds — anything labeled `micro_usd` is raw micro-USD (`1_000_000` == `$1.00`), and you floor to cents yourself only when you want a billed-dollar figure.

### Quality monitoring (judge windows)

`m.quality()` reports the endpoint's quality over rolling windows, scored by the platform's judge — the same scoring machinery evals use, run continuously against live traffic so you catch drift without launching a run. Poll it on a schedule and alert when a window dips below your bar.

**Python**

```python
q = pa.endpoints.metrics("ep-contract-key-fields").quality(window="24h")

score = q.get("quality_mean")
if score is not None and score < 0.90:
    print(f"quality slipped to {score:.3f} on the last window — investigate")
```

**TypeScript**

```typescript
const q = (await pa.endpoints
  .metrics("ep-contract-key-fields")
  .quality({ window: "24h" })) as Record<string, unknown>;

const score = q.quality_mean as number | undefined;
if (score != null && score < 0.9) {
  console.log(`quality slipped to ${score.toFixed(3)} on the last window — investigate`);
}
```

Latency (`performance`) and `uptime` round out the operational picture; `activity` reports usage volume. They are all the same call shape: pass a window or grouping, read the returned dict.

## Async

Every method here has an async twin on `AsyncPareta` with the same signatures. Note one shape detail: `endpoints.metrics(id)` itself is **not** a coroutine even on the async client — it returns an `AsyncMetrics` handle synchronously — but the dimension methods on that handle are `async def`.

**Python**

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        run = await pa.evals.runs.retrieve(run_id)
        print("billed", run.cost, "/", run.cost_micro_usd, "uUSD")

        m = pa.endpoints.metrics("ep-contract-key-fields")  # sync handle, no await
        cost, quality = await asyncio.gather(
            m.cost(window="7d"),
            m.quality(window="24h"),
        )
        print(cost.get("savings_micro_usd"), quality.get("quality_mean"))

asyncio.run(main())
```

**TypeScript**

```typescript
// No AsyncPareta in TS — there's one Promise-only client, so every method is
// already async. Concurrency is just Promise.all over the awaitables.
const run = await pa.evals.runs.retrieve(runId);
console.log("billed", run.cost, "/", run.costMicroUsd, "uUSD");

const m = pa.endpoints.metrics("ep-contract-key-fields"); // sync handle, no await
const [cost, quality] = (await Promise.all([
  m.cost({ window: "7d" }),
  m.quality({ window: "24h" }),
])) as Array<Record<string, unknown>>;
console.log(cost.savings_micro_usd, quality.quality_mean);
```

## Lossless access

Every response object keeps the raw server JSON. `run.to_dict()`, `result.to_dict()`, and the dicts returned by the metric dimensions give you everything the API sent, including fields not yet surfaced as typed properties. When a metric grows a new key before the SDK grows a property for it, `to_dict()` (or plain `.get()`) is your escape hatch.

## See also

- [Evaluating on your own data](./evaluate-on-your-data.md) — build eval sets, pick frontier baselines, read per-model results.
- [Deploy a model and call it](./deploy-and-infer.md) — task to live endpoint in two calls.
- [Concurrent & async](./concurrent-async.md) — fan-out inference and parallel eval runs.
- [Deploying endpoints](../guide/deploying-endpoints.md) — the full `endpoints` surface, including the `metrics` dimension table.
- [Running inference](../guide/inference.md) — the OpenAI-compatible chat surface and streaming.
- [Errors, retries & timeouts](../guide/errors-and-retries.md) — `InsufficientCreditsError`, the money convention, and the exception hierarchy.
