# Reference

Field-by-field API docs for the Pareta SDK. Signatures are shown in Python; the **TypeScript** SDK mirrors them (a single Promise-only `Pareta` client, camelCase names, `await`ed calls). Everything hangs off one client object, `Pareta` (Python also ships an async mirror, `AsyncPareta`); the resource pages document the five namespaces that live on it. Conventions that hold everywhere: model ids you pass and read are per-task aliases, inference and evals are metered against your org balance, and money appears on `.cost` (a dollars `Decimal` in Python, a fixed-2dp string in TypeScript) with the raw integer on `.cost_micro_usd` / `.costMicroUsd`.

## Client

- [Client (`Pareta`, `AsyncPareta`)](./client.md) — the sync/async client: `from_env`, constructor params (`api_key`, `base_url`, `timeout`, `max_retries`, `http_client`), lifecycle, and the five resource namespaces.

## Resources

- [chat.completions](./chat.md) — `chat.completions.create`: params, `ChatCompletion`/chunk return types, streaming SSE behavior, metering, and the full error/retry surface, with sync, async, and OpenAI-SDK examples.
- [models](./models.md) — `client.models`: `list()` returns a `ModelList` of callable deployed endpoints; the three `Model` fields (`id`/`owned_by`/`created`), sync+async usage, and how it differs from `endpoints.list()`.
- [endpoints](./endpoints.md) — `client.endpoints`: `deploy` (wait semantics + progress-event SSE), `list`/`retrieve`/`start`/`stop`/`delete`, the `Endpoint` object, and `metrics(id)` observability dimensions.
- [tasks](./tasks.md) — `client.tasks`: `list`/`retrieve`/`match`/`leaderboard`/`recommended` with the `Task`/`TaskMatch`/`Leaderboard` response models.
- [evals](./evals.md) — `client.evals`: `sets`, `runs`, and `frontier_models`, with `frontier=` resolution, metering, and response-object tables.

## Types and errors

- [Exceptions](./exceptions.md) — the exception hierarchy: `ParetaError` base, status-to-class mapping, and the `status_code`/`detail`/`request_id` attributes.
- [Response types](./types.md) — every response object (chat, models, endpoints, tasks, evals) plus the `.cost` vs `.cost_micro_usd` money convention.

## Transport

- [Underlying HTTP API](./http-api.md) — a per-method map of the `/v1` routes the SDK wraps (chat/completions, models, endpoints+metrics, tasks+match/leaderboard, eval frontier-models, eval-sets, eval-runs) with method, path, Bearer auth, request/response shapes, and sync/async + curl examples.

## See also

- Concepts and step-by-step explanation: [Guide](../guide/README.md).
- Working end-to-end workflows: [Examples](../examples/README.md).
