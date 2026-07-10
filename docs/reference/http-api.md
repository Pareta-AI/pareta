# Underlying HTTP API

The Pareta SDKs (Python and TypeScript) are thin, typed wrappers over a plain JSON-over-HTTPS API
served at `https://api.pareta.ai` under the `/v1/` prefix. Every method you call
maps to exactly one route (a couple of ergonomic helpers fan out to two or
three). This page is the lookup table: for each SDK method, the HTTP method,
path, request shape, and response shape it wraps.

Reach for it when you are debugging a request in a proxy log, calling Pareta from
a language without an SDK, or you just want to know what goes over the wire.
Everywhere else, prefer the SDK: it handles auth, retries, SSE parsing, and the
cost flooring convention for you.

A few platform truths shape every route below:

- **One model id.** Inference takes `model: "auto"` — the only entry
  `GET /v1/models` returns. Every request is planned, routed to
  benchmark-proven open specialists, verified, and falls back to a frontier
  model when that's the right call. There is nothing to deploy, and no GPU,
  hardware, or model knob anywhere on the wire; Pareta resolves all of it
  server-side, per request.
- **The models behind `auto` stay behind `auto`.** Which model served a given
  request never crosses this boundary. Frontier (vendor) ids appear in the
  clear only where you pick them deliberately: eval baselines and the frontier
  compare.
- **Inference and evals are metered against your org balance.**
  `POST /v1/chat/completions` debits **once per request** — however many
  internal model calls auto's plan makes, orchestration overhead is Pareta's
  cost, not yours. `POST /v1/eval-runs` debits for the auto and frontier
  compute it runs; `POST /v1/playground/frontier` debits at the vendor's
  actual token cost. The speech routes (`/v1/audio/*`) bill **per minute** of
  audio. An empty balance returns `402`. Top-up is browser-only; there is no
  balance or payment route.
- **Inference is OpenAI-compatible.** `/v1/chat/completions` and `/v1/models`
  speak the OpenAI wire format, so existing OpenAI clients point at Pareta by
  swapping the base URL and key.

## Base URL and versioning

| | |
|---|---|
| Base URL | `https://api.pareta.ai` (override with `PARETA_BASE_URL`) |
| Prefix | `/v1/` |
| Content type | `application/json` (JSON bodies); `multipart/form-data` for uploads |
| Streaming | `text/event-stream` (chat streaming) |

The SDK normalizes the base URL with `rstrip("/")`, so a trailing slash is
harmless.

## Authentication

Every request carries a bearer token in the `Authorization` header. The token is
your `pareta_sk_…` secret key, minted in the dashboard.

```
Authorization: Bearer pareta_sk_…
User-Agent: pareta-python/<version>
Accept: application/json            # or text/event-stream for streaming routes
Content-Type: application/json      # JSON bodies only; multipart sets its own
```

The SDK reads the key from the `api_key=` argument or the `PARETA_API_KEY`
environment variable. Prefer `Pareta.from_env()`, which reads both
`PARETA_API_KEY` and the optional `PARETA_BASE_URL`:

```python
from pareta import Pareta

# Reads PARETA_API_KEY (+ optional PARETA_BASE_URL) from the environment.
with Pareta.from_env() as pa:
    print([m.id for m in pa.models.list()])
```

A raw `curl` against the same route:

```bash
curl https://api.pareta.ai/v1/models \
  -H "Authorization: Bearer $PARETA_API_KEY"
```

Constructing a client with no key raises `ParetaError` before any request goes
out. A key that reaches the server and is rejected returns `401`
(`AuthenticationError`). See [Errors, retries & timeouts](../guide/errors-and-retries.md).

## Route map at a glance

| SDK call | Method | Path |
|---|---|---|
| `chat.completions.create(...)` | `POST` | `/v1/chat/completions` |
| `models.list()` | `GET` | `/v1/models` |
| `tasks.list()` | `GET` | `/v1/tasks` |
| `tasks.retrieve(id)` | `GET` | `/v1/tasks/{id}` |
| `tasks.match(query)` | `POST` | `/v1/tasks/match` |
| `auto.metrics()` | `GET` | `/v1/auto/metrics` |
| `auto.compare_frontier(...)` | `POST` | `/v1/playground/frontier` |
| `audio.transcriptions(audio)` | `POST` | `/v1/audio/transcriptions` |
| `audio.speech(text)` | `POST` | `/v1/audio/speech` |
| `evals.frontier_models(task)` | `GET` | `/v1/eval/frontier-models` |
| `evals.sets.create(...)` | `POST` | `/v1/eval-sets` |
| `evals.sets.list()` | `GET` | `/v1/eval-sets` |
| `evals.sets.retrieve(id)` | `GET` | `/v1/eval-sets/{id}` |
| `evals.sets.delete(id)` | `DELETE` | `/v1/eval-sets/{id}` |
| `evals.sets.upload_document(...)` | `POST` | `/v1/eval-sets/{id}/attach-blob` (small) or `/blob-upload-url` + `PUT` + `/blob-upload-complete` (large) |
| `evals.runs.create(...)` | `POST` | `/v1/eval-runs` |
| `evals.runs.retrieve(id)` / `evals.runs.wait(id)` | `GET` | `/v1/eval-runs/{id}` |

## Inference: chat completions

### `POST /v1/chat/completions`

OpenAI-compatible chat completions. Wrapped by
[`chat.completions.create()`](../guide/inference.md). Metered: a successful
completion debits the org balance **once per request** — however many internal
model calls auto's plan makes, orchestration overhead is Pareta's cost, not
yours — and an empty balance returns `402` (`InsufficientCreditsError`).

`model` is `"auto"`. Extra OpenAI fields (`temperature`, `max_tokens`,
`top_p`, ...) pass straight through as body fields.

Request body:

```json
{
  "model": "auto",
  "messages": [{"role": "user", "content": "Extract the parties."}],
  "temperature": 0.0
}
```

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    resp = pa.chat.completions.create(
        model="auto",
        messages=[{"role": "user", "content": "Extract the parties."}],
        temperature=0.0,
    )
    print(resp.choices[0].message.content)   # ChatCompletion -> Choice -> Message
    print(resp.usage.total_tokens)           # Usage
```

The same request as `curl`:

```bash
curl https://api.pareta.ai/v1/chat/completions \
  -H "Authorization: Bearer $PARETA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Extract the parties."}]
  }'
```

#### Streaming

Set `"stream": true`. The response is a data-only SSE stream in vLLM format:
each `data:` line is one JSON chunk, and the stream ends with `data: [DONE]`.

```
data: {"choices": [{"delta": {"content": "The"}}]}
data: {"choices": [{"delta": {"content": " parties"}}]}
data: [DONE]
```

The SDK yields `ChatCompletionChunk` objects;
`chunk.choices[0].delta.content` is the incremental text.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    for chunk in pa.chat.completions.create(
        model="auto",
        messages=[{"role": "user", "content": "Summarize the contract."}],
        stream=True,
    ):
        piece = chunk.choices[0].delta.content
        if piece:
            print(piece, end="", flush=True)
```

Retries cover only the initial handshake. Once SSE bytes are flowing a
mid-stream drop raises immediately (`APIConnectionError`) and cannot be resumed.

### `GET /v1/models`

OpenAI-compatible model listing. Wrapped by `models.list()`. Returns exactly
one entry — `"auto"` — shaped as
`{"data": [{"id", "owned_by", "created"}, ...]}`. The `id` is what you pass to
`chat.completions.create(model=...)`.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    models = pa.models.list()          # ModelList (iterable, has len)
    for m in models:
        print(m.id, m.owned_by)        # Model
```

## Tasks (benchmark catalog)

### `GET /v1/tasks`

List the benchmark catalog. Wrapped by `tasks.list()`. The server returns
`{"tasks": [...]}`; the SDK maps each to a `Task` (`id`, `default_scorer`,
`has_blob_input`).

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    for t in pa.tasks.list():
        print(t.id, t.default_scorer, t.has_blob_input)
```

### `GET /v1/tasks/{task_id}`

Retrieve one task's schema and default scorer. Wrapped by
`tasks.retrieve(task_id, examples_n=None)`. The optional `examples_n` query param
requests N example items when available.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    task = pa.tasks.retrieve("contract-key-fields", examples_n=3)
    print(task.id, task.has_blob_input)
```

### `POST /v1/tasks/match`

Map free-text intent to one match. Wrapped by `tasks.match(query, top_k=5)`. The
matcher is an LLM reasoning router that maps intent to a benchmarked task, a
general capability lane (`"capability:<id>"`), or `"unsupported"`, degrading to a
keyword scorer if the router is unavailable. An empty `query` raises `ValueError`
client-side. The response keeps the legacy keys (`matched`/`chosen`/`candidates`/
`ambiguous`/`matcher`) and adds `type` (`"task"`/`"capability"`/`"unsupported"`/
`"none"`), `reasoning`, and `capability` (when `type == "capability"`).

Request body:

```json
{"query": "pull key fields out of vendor contracts", "top_k": 5}
```

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    match = pa.tasks.match("pull key fields out of vendor contracts")
    if match.matched and match.chosen:
        print(match.chosen.task_id, match.chosen.confidence)
    for c in match.candidates:        # ranked alternates
        print(c.task_id, c.score)
```

## Auto (metrics and frontier compare)

The routes around the `model: "auto"` call itself: an org-level rollup of your
auto traffic, and a metered one-prompt comparison against a frontier vendor.
The SDK wraps both in the `pa.auto` namespace.

### `GET /v1/auto/metrics`

Your org's `model: "auto"` traffic, rolled up. Wrapped by `auto.metrics()`,
which returns the raw JSON dict: requests + success rate (30d), billed spend,
hourly p50/p95/error buckets (7d), daily success cells (30d), and the
**projected** savings vs frontier (a frontier list-priced counterfactual,
labeled as projected in the dashboard too).

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    m = pa.auto.metrics()
    print(m["requests_30d"], m["success_rate_30d"])
    print(m["savings_vs_frontier_micro_usd_30d"])   # projected, micro-USD
```

### `POST /v1/playground/frontier`

Run one prompt against a frontier vendor for a side-by-side with
`model: "auto"`. Wrapped by `auto.compare_frontier(model=..., messages=...)`.
Allowed `model` values: `gpt-5.5`, `gemini-3-5-flash`, `gemini-3-1-pro`,
`claude-sonnet-4-6` (anything else returns `400`); `messages` takes 1–40
entries. Metered at the vendor's **actual token cost** — one debit per call; a
failed vendor call returns `502` and bills $0. An empty balance returns `402`.

Request body:

```json
{
  "model": "gpt-5.5",
  "messages": [{"role": "user", "content": "Extract the parties."}]
}
```

Returns `{"model": ..., "content": ..., "cost_micro_usd": ..., "latency_ms": ...}`.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    side = pa.auto.compare_frontier(
        model="gpt-5.5",
        messages=[{"role": "user", "content": "Extract the parties."}],
    )
    print(side["content"], side["cost_micro_usd"], side["latency_ms"])
```

## Speech (audio)

The Speech capability lanes (`asr`, `tts`) run on dedicated services, not the
chat-completions path, so they have their own routes. The SDK wraps them in the
`pa.audio` namespace (`pa.audio.transcriptions(...)` / `pa.audio.speech(...)`);
the routes below are what those methods call. Both are metered **per minute** of
audio and return `402` (`InsufficientCreditsError`) on an empty balance.

### `POST /v1/audio/transcriptions`

Speech-to-text (the `asr` lane). Body is JSON with base64 audio:

```json
{"audio_base64": "<base64 wav/mp3/m4a/webm>", "language": "en"}
```

`language` is optional. Returns `{"text": ..., "language": ..., "duration_s": ...}`;
debits per minute of **input** audio.

```bash
curl https://api.pareta.ai/v1/audio/transcriptions \
  -H "Authorization: Bearer $PARETA_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"audio_base64\": \"$(base64 -i call.wav)\"}"
```

### `POST /v1/audio/speech`

Text-to-speech (the `tts` lane). Body is JSON:

```json
{"text": "Hello from Pareta.", "voice": "<optional kokoro voice id>"}
```

`text` is required (max 5000 chars); `voice` is optional (omit for the default
Kokoro voice). Returns
`{"audio_base64": ..., "sample_rate": ..., "duration_s": ..., "format": ...}`;
debits per minute of **output** audio.

```bash
curl https://api.pareta.ai/v1/audio/speech \
  -H "Authorization: Bearer $PARETA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from Pareta."}'
```

## Evals

### `GET /v1/eval/frontier-models`

The vendor frontier roster you can evaluate against. Wrapped by
`evals.frontier_models(task=None)`. The server returns
`{"frontier_models": [...]}`; the SDK maps each to a `FrontierModel`
(`id`, `vendor`, `vision`, `benchmarked`). Pass `task` to annotate `benchmarked`
(already benchmarked on that task) and vision-filter for document tasks. Feed
the ids into `evals.runs.create(frontier=[...])`.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    roster = pa.evals.frontier_models(task="contract-key-fields")
    for fm in roster:
        print(fm.id, fm.vendor, fm.vision, fm.benchmarked)
```

### `POST /v1/eval-sets`

Create an eval set from your rows. Wrapped by
[`evals.sets.create(task=..., items=...)`](../guide/evaluation.md). The rows go
over the wire as **JSONL** inside a `multipart/form-data` body (`items` file part
plus `task_id` and `name` form fields), not as a JSON array. An empty `items`
raises `ValueError`. The server returns `{"eval_set": {...}}`; the SDK maps it to
an `EvalSet` (`id`, `task_id`, `name`, `item_count`, `scoring_strategy`).

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    eval_set = pa.evals.sets.create(
        task="contract-key-fields",
        items=[
            {"input": "Agreement between A and B...", "expected": {"parties": ["A", "B"]}},
            {"input": "This SOW is by C for D...",     "expected": {"parties": ["C", "D"]}},
        ],
    )
    print(eval_set.id, eval_set.item_count, eval_set.scoring_strategy)
```

### `GET /v1/eval-sets` and `GET /v1/eval-sets/{eval_set_id}`

List your eval sets, or retrieve one. Wrapped by `evals.sets.list()` (server
returns `{"eval_sets": [...]}`) and `evals.sets.retrieve(eval_set_id)` (server
returns `{"eval_set": {...}}`). Both map to `EvalSet`.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    for es in pa.evals.sets.list():
        print(es.id, es.name, es.item_count)
    one = pa.evals.sets.retrieve("evset_123")
```

### `DELETE /v1/eval-sets/{eval_set_id}`

Delete an eval set. Wrapped by `evals.sets.delete(eval_set_id)`, which returns
`None`.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    pa.evals.sets.delete("evset_123")
```

### Uploading documents to a row (3 routes)

For document/image tasks, attach a binary blob to one row's input field. The SDK
collapses two upload paths into a single
`evals.sets.upload_document(eval_set_id, file, *, idx, field_name, mime=None)`
call. `file` may be a path, raw `bytes`, or a binary file-like; anything else
raises `TypeError`. `idx` is the 0-based row, `field_name` the blob input field.

The SDK picks the path by size:

- **Files under 5 MiB** go inline through
  `POST /v1/eval-sets/{id}/attach-blob` (`multipart/form-data`: the `file` part
  plus `idx`, `field_name`, `mime` form fields).
- **Larger files** use the signed-URL flow: mint a URL with
  `POST /v1/eval-sets/{id}/blob-upload-url`, `PUT` the bytes directly to storage
  (GCS), then confirm with `POST /v1/eval-sets/{id}/blob-upload-complete`.

Either way the method returns the response dict from the terminal call.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    eval_set = pa.evals.sets.create(
        task="document-extraction",
        items=[{"expected": {"invoice_total": "1240.00"}}],
    )
    # Attach the PDF that row 0's blob field expects.
    pa.evals.sets.upload_document(
        eval_set.id, "invoice.pdf", idx=0, field_name="document"
    )
```

### `POST /v1/eval-runs`

Start an eval run. Wrapped by
[`evals.runs.create(...)`](../guide/evaluation.md). Pass either an existing
`eval_set=<id>` or an inline `task=...` + `items=...` (which the SDK turns into an
eval set first). `models` is the list of candidate ids to evaluate — pass
`["auto"]`; `frontier` adds vendor baselines.

The SDK resolves `frontier` to a list of ids before sending, then posts
`{"eval_set_id": ..., "candidate_model_ids": ["auto", ...frontier...]}`:

| `frontier=` value | Resolves to |
|---|---|
| `None` or `"none"` | `[]` (no baselines) |
| list of ids | the list, as-is |
| `"all"` | every id from `GET /v1/eval/frontier-models?task=...` |
| `"benchmarked"` | frontier models already benchmarked on the task |

A keyword (`"all"` / `"benchmarked"`) needs the task; if you passed `eval_set=`
only, the SDK looks up its `task_id` to resolve the roster, and raises
`ValueError` if the task is unknown. Metered: the org balance is debited for
auto and frontier compute, and an empty balance returns `402`.

The server responds with `{"run_id": ..., "status": ...}`. With `wait=False`
the SDK returns an `EvalRun` in its initial (running/queued) state. With
`wait=True` it polls `GET /v1/eval-runs/{run_id}` every `poll_interval` seconds
(default 3.0) until terminal, up to `timeout` seconds (default 900.0), then
returns the final `EvalRun`; exceeding the deadline raises `ParetaError` while the
run keeps going server-side.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    run = pa.evals.runs.create(
        task="contract-key-fields",
        items=[{"input": "Agreement between A and B...", "expected": {"parties": ["A", "B"]}}],
        models=["auto"],                        # the candidate under test
        frontier="benchmarked",                 # vendor baselines benchmarked on the task
        wait=True,
    )
    print(run.status, run.cost)                 # "completed" Decimal("0.42")
    for r in run.results:                       # EvalResult per model
        print(r.model_id, r.kind, r.quality_mean, r.mean_cost_micro_usd)
```

### `GET /v1/eval-runs/{run_id}`

Retrieve full run state, including per-model results once terminal. Wrapped by
`evals.runs.retrieve(run_id)` and the `evals.runs.wait(run_id, ...)` poll helper
(same semantics as `create(..., wait=True)`). The server returns an envelope
`{"run": {...}, "results": [...]}` that the SDK maps to an `EvalRun`.

`EvalRun.cost` is the billed total as `Decimal` dollars **floored to cents**
(never rounded up), while `EvalRun.cost_micro_usd` keeps the raw integer
micro-USD value. A 5 micro-USD run reads `Decimal("0.00")`. Per-item unit rates
such as `EvalResult.mean_cost_micro_usd` stay in micro-USD so the auto-vs-frontier
comparison is not erased by flooring.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    run = pa.evals.runs.retrieve("run_456")
    if run.is_terminal:                         # status in ("completed", "failed")
        print(run.cost, run.cost_micro_usd)
        if run.status == "failed":
            print(run.error_detail)
    else:
        run = pa.evals.runs.wait("run_456", poll_interval=5.0, timeout=600.0)
```

## Status codes

The server is FastAPI, so error bodies are `{"detail": "<message>"}` with a
standard HTTP status. The SDK maps each status to a specific
`ParetaError` subclass so you catch by meaning.

| Status | Exception | When |
|---|---|---|
| 400, 422 | `BadRequestError` | request validation failed |
| 401 | `AuthenticationError` | invalid or missing API key |
| 402 | `InsufficientCreditsError` | org out of balance (top up in the dashboard) |
| 403 | `PermissionDeniedError` | authenticated, not allowed |
| 404 | `NotFoundError` | eval set / run / task id not found |
| 409 | `ConflictError` | transient lock/contention |
| 429 | `RateLimitError` | rate limited |
| 503 | `EndpointNotReadyError` | a serving backend behind `auto` is warming or briefly unavailable (retried automatically) |
| other 5xx | `APIStatusError` | generic server error |

Each `APIStatusError` exposes `status_code`, `detail`, `request_id` (from the
`x-request-id` response header), and the underlying `response`. The SDK
automatically retries `408, 409, 429, 500, 502, 503, 504` with exponential
backoff that honors `Retry-After`. Full treatment in
[Errors, retries & timeouts](../guide/errors-and-retries.md).

## Async over the same routes

`AsyncPareta` hits the identical routes with awaitable methods. Streaming routes
return async iterators; `evals.runs.wait()` is a coroutine. The wire format,
auth, status mapping, and retry policy are the same.

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        models = await pa.models.list()                 # GET /v1/models
        async for chunk in await pa.chat.completions.create(  # POST /v1/chat/completions
            model="auto",
            messages=[{"role": "user", "content": "Extract the parties."}],
            stream=True,
        ):
            piece = chunk.choices[0].delta.content
            if piece:
                print(piece, end="", flush=True)

asyncio.run(main())
```

## See also

- [Inference](../guide/inference.md) — OpenAI-compatible chat completions and streaming
- [Evaluation](../guide/evaluation.md) — eval sets, runs, `wait`, and `run.cost`
- [Tasks](tasks.md) — the benchmark catalog and `match()`
- [Errors, retries & timeouts](../guide/errors-and-retries.md) — the full exception hierarchy
- [Async](../guide/async.md) — the `AsyncPareta` client end to end
- [Configuration](../guide/configuration.md) — base URL, keys, timeout, and retry budget
