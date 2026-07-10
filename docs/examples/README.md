# Examples

Complete, runnable workflows for real jobs, in **Python and TypeScript**. Each page is self-contained and uses the real SDK surface end to end (`Pareta.from_env()` / `Pareta.fromEnv()`): call `model="auto"` with OpenAI-compatible inference, benchmark it on your data, and read the metered cost in dollars off `run.cost`. Grouped by what you are trying to do.

## Prove it on your own data

You have a job in plain English, or your own data, and want proof that `"auto"` wins on it.

- [Benchmark models on your own data](./evaluate-on-your-data.md) — build an eval set from your rows, run `"auto"` against `frontier="benchmarked"` baselines, and read ranked results plus `run.cost`.
- [Document extraction (PDF/image)](./document-extraction.md) — the blob-task loop: build an eval set from your PDFs/images, `upload_document` per row, benchmark `"auto"` against vision frontier baselines, then run OpenAI-compatible inference with `model="auto"`.

## Inference patterns

Getting tokens out efficiently.

- [Streaming chat completions](./streaming-chat.md) — stream tokens with `chat.completions.create(stream=True)`: iterate `ChatCompletionChunk` objects, read `delta.content`, accumulate full text, plus async streaming and metering behavior.
- [Concurrent calls with AsyncPareta](./concurrent-async.md) — fire many inference and eval calls concurrently with `AsyncPareta` and `asyncio.gather`, with semaphore backpressure and per-task error handling.

## Operate and monitor

Watching what auto is doing, and what it costs.

- [Cost & quality monitoring](./cost-and-metrics.md) — read what calls and eval runs cost, the projected savings vs frontier, and watch requests, success rate, and spend via `auto.metrics()`.

## Migrating in

Already on the OpenAI SDK.

- [Migrating from the OpenAI SDK](./migrate-from-openai.md) — keep using the `openai` client against Pareta (`base_url` + `pareta_sk_` key), and when to switch to the `pareta` SDK for tasks, evals, and auto's metrics.

## See also

- Concepts and step-by-step explanation: [Guide](../guide/README.md).
- Field-by-field API docs: [Reference](../reference/README.md).
