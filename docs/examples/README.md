# Examples

Complete, runnable workflows for real jobs, in **Python and TypeScript**. Each page is self-contained and uses the real SDK surface end to end (`Pareta.from_env()` / `Pareta.fromEnv()`): call `model="auto"` with OpenAI-compatible inference, benchmark it on your data, and read the metered cost in dollars off `run.cost`. Grouped by what you are trying to do.

## Use-case recipes

Straight-up inference, one page per workload. Every recipe is the same shape — send your data to the interface that matches it (`model="auto"` for messages, dedicated routes for ranked lists, vectors, and audio) — and each section links to a full runnable program in [Pareta-AI/examples](https://github.com/Pareta-AI/examples).

- [Medical coding (ICD-10)](./icd-coding.md) — a clinical discharge summary in, ICD-10-CM codes as strict JSON out.
- [Retrieval: reranking and embeddings](./retrieval.md) — the RAG stack: calibrated reranking, embedding-based semantic search, and the two-stage recall→precision pipeline.
- [Extraction: documents and contracts](./extraction.md) — pull JSON fields out of invoice images and PDFs (how to attach them to the prompt) and out of contract text.
- [Text classification](./text-classification.md) — intent classification with a closed label set + few-shot, and hate-speech content moderation.
- [Summarization](./summarization.md) — meeting notes to an executive summary and action items, with a streaming variant.
- [Text to speech](./text-to-speech.md) — synthesize spoken audio and save it to a file.
- [Speech to text](./speech-to-text.md) — transcribe an audio clip from a path, raw bytes, or base64.

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
- Full runnable programs for every recipe: [Pareta-AI/examples](https://github.com/Pareta-AI/examples).
