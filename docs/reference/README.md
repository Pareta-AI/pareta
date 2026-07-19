# Reference

Field-by-field API docs for the Pareta SDK. Signatures are shown in Python; the **TypeScript** SDK mirrors them (a single Promise-only `Pareta` client, camelCase names, `await`ed calls). Everything hangs off one client object, `Pareta` (Python also ships an async mirror, `AsyncPareta`); the resource pages document the namespaces that live on it. Conventions that hold everywhere: the model id you pass for inference is `"auto"` (frontier vendor ids appear only in eval and comparison contexts), inference and evals are metered against your org balance, and money appears on `.cost` (a dollars `Decimal` in Python, a fixed-2dp string in TypeScript) with the raw integer on `.cost_micro_usd` / `.costMicroUsd`.

## Client

- [Client (`Pareta`, `AsyncPareta`)](./client.md) — the sync/async client: `from_env`, constructor params (`api_key`, `base_url`, `timeout`, `max_retries`, `http_client`), lifecycle, and the six resource namespaces.

## Resources

- [chat.completions](./chat.md) — `chat.completions.create`: params, `ChatCompletion`/chunk return types, streaming SSE behavior, metering, and the full error/retry surface, with sync, async, and OpenAI-SDK examples.
- [models](./models.md) — `client.models`: `list()` returns a `ModelList` with exactly one entry, `"auto"`; the three `Model` fields (`id`/`owned_by`/`created`) and sync+async usage.
- [tasks](./tasks.md) — `client.tasks`: `list`/`retrieve`/`match` with the `Task`/`TaskMatch` response models.
- [evals](./evals.md) — `client.evals`: `sets`, `runs`, and `frontier_models`, with `frontier=` resolution, metering, and response-object tables.
- [audio](./audio.md) — `client.audio`: `transcriptions` (speech-to-text) and `speech` (text-to-speech), the per-minute metering, and the `Transcription`/`Speech` response objects.
- [images](./images.md) — `client.images`: `generate` (text-to-image), the flat per-image metering, and the `ImageGeneration` response object.
- [rerank](./rerank.md) — `client.rerank`: rank documents by relevance to a query (per-document metering, calibrated scores, the `Rerank` response object).
- [embeddings](./embeddings.md) — `client.embeddings`: unit-normalized text vectors for search/RAG recall (per-token metering, query vs document embedding, the `Embeddings` response object).

## Types and errors

- [Exceptions](./exceptions.md) — the exception hierarchy: `ParetaError` base, status-to-class mapping, and the `status_code`/`detail`/`request_id` attributes.
- [Response types](./types.md) — every response object (chat, models, tasks, evals) plus the `.cost` vs `.cost_micro_usd` money convention.

## Transport

- [Underlying HTTP API](./http-api.md) — a per-method map of the `/v1` routes the SDK wraps (chat/completions, models, tasks+match, auto metrics + frontier compare, eval frontier-models, eval-sets, eval-runs) with method, path, Bearer auth, request/response shapes, and sync/async + curl examples.
- [Agent API (`/agent/v1`)](./agent-api.md) — the wire contract for agent runtimes (OpenClaw): request/response fields, session pinning, streaming, billing header, errors, and a working OpenClaw provider block.

## See also

- Concepts and step-by-step explanation: [Guide](../guide/README.md).
- Working end-to-end workflows: [Examples](../examples/README.md).
