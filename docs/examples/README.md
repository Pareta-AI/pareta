# Examples

Complete, runnable workflows for real jobs, in **Python and TypeScript**. Each page is self-contained and uses the real SDK surface end to end (`Pareta.from_env()` / `Pareta.fromEnv()`): call `model="auto"` with OpenAI-compatible inference, benchmark it on your data, read the metered cost in dollars off `run.cost` — and deploy a dedicated model when you want to pin one (no GPU knob). Grouped by what you are trying to do.

## Deploy and call a model

You know the task; you want a live endpoint and a response.

- [Deploy a model and call it](./deploy-and-infer.md) — the two-call workflow: `endpoints.deploy(task, model="recommended", wait=True)` then `chat.completions.create(model=endpoint.id, ...)`. Covers deploy events, streaming, metering and `InsufficientCreditsError`, errors, endpoint ops, and async.

## Pick the right model first

You have a job in plain English, or your own data, and want to deploy the model that actually wins on it.

- [From a sentence to a deployed winner](./find-and-deploy-best-model.md) — the full funnel: `tasks.match` to `leaderboard` to `evals.runs` on your own data, pick the best `kind == "open"` model, `endpoints.deploy` it, then run inference.
- [Benchmark models on your own data](./evaluate-on-your-data.md) — build an eval set from your rows, run open candidates against `frontier="benchmarked"`, and read ranked results plus `run.cost`.
- [Document extraction (PDF/image)](./document-extraction.md) — the blob-task loop: build an eval set from your PDFs/images, `upload_document` per row, run against open candidates plus vision frontier baselines, pick the winner by quality and cost, deploy, then run OpenAI-compatible inference.

## Inference patterns

Getting tokens out efficiently.

- [Streaming chat completions](./streaming-chat.md) — stream tokens with `chat.completions.create(stream=True)`: iterate `ChatCompletionChunk` objects, read `delta.content`, accumulate full text, plus async streaming and metering behavior.
- [Concurrent calls with AsyncPareta](./concurrent-async.md) — fire many inference and eval calls concurrently with `AsyncPareta` and `asyncio.gather`, with semaphore backpressure and per-task error handling.

## Operate and monitor

Watching what is deployed, and what it costs.

- [Cost & quality monitoring](./cost-and-metrics.md) — read what calls and eval runs cost, the open-vs-frontier savings framing, and watch a live endpoint's spend and quality via `endpoints.metrics()`.

## Migrating in

Already on the OpenAI SDK.

- [Migrating from the OpenAI SDK](./migrate-from-openai.md) — keep using the `openai` client against Pareta (`base_url` + `pareta_sk_` key), and when to switch to the `pareta` SDK for deploy, eval, and discovery.

## See also

- Concepts and step-by-step explanation: [Guide](../guide/README.md).
- Field-by-field API docs: [Reference](../reference/README.md).
