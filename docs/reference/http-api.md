# Underlying HTTP API

The Pareta SDKs (Python and TypeScript) are thin, typed wrappers over a plain JSON-over-HTTPS API
served at `https://api.pareta.ai` under the `/v1/` prefix. Every method you call
maps to exactly one route (a couple of ergonomic helpers fan out to two or
three). This page is the lookup table: for each SDK method, the HTTP method,
path, request shape, and response shape it wraps.

Reach for it when you are debugging a request in a proxy log, calling Pareta from
a language without an SDK, or you just want to know what goes over the wire.
Everywhere else, prefer the SDK: it handles auth, retries, SSE parsing, the cost
flooring convention, and the per-task model aliasing for you.

A few platform truths shape every route below:

- **GPUs are hidden.** `POST /v1/endpoints` takes a `task` and a `model`; it
  never takes a GPU, tensor-parallel, or quantization knob. Pareta resolves the
  serving hardware server-side.
- **Models are per-task aliases.** Open-weights model ids are masked to
  per-task public aliases on the way out. Real ids never cross this boundary.
  Frontier (vendor) ids are in the clear.
- **Inference and evals are metered against your org balance.**
  `POST /v1/chat/completions` debits on success; `POST /v1/eval-runs` debits for
  the open and frontier compute it runs. An empty balance returns `402`. Top-up
  is browser-only; there is no balance or payment route.
- **Inference is OpenAI-compatible.** `/v1/chat/completions` and `/v1/models`
  speak the OpenAI wire format, so existing OpenAI clients point at Pareta by
  swapping the base URL and key.

## Base URL and versioning

| | |
|---|---|
| Base URL | `https://api.pareta.ai` (override with `PARETA_BASE_URL`) |
| Prefix | `/v1/` |
| Content type | `application/json` (JSON bodies); `multipart/form-data` for uploads |
| Streaming | `text/event-stream` (chat streaming, deploy progress) |

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
| `endpoints.deploy(...)` | `POST` | `/v1/endpoints` (SSE) |
| `endpoints.list()` | `GET` | `/v1/endpoints` |
| `endpoints.retrieve(id)` | `GET` | `/v1/endpoints/{id}` |
| `endpoints.start(id)` | `POST` | `/v1/endpoints/{id}/start` |
| `endpoints.stop(id)` | `POST` | `/v1/endpoints/{id}/stop` |
| `endpoints.delete(id)` | `DELETE` | `/v1/endpoints/{id}` |
| `endpoints.metrics(id).performance(...)` | `GET` | `/v1/endpoints/{id}/performance` |
| `endpoints.metrics(id).uptime(...)` | `GET` | `/v1/endpoints/{id}/uptime` |
| `endpoints.metrics(id).cost(...)` | `GET` | `/v1/endpoints/{id}/cost` |
| `endpoints.metrics(id).quality(...)` | `GET` | `/v1/endpoints/{id}/quality` |
| `endpoints.metrics(id).activity(...)` | `GET` | `/v1/endpoints/{id}/activity` |
| `tasks.list()` | `GET` | `/v1/tasks` |
| `tasks.retrieve(id)` | `GET` | `/v1/tasks/{id}` |
| `tasks.match(query)` | `POST` | `/v1/tasks/match` |
| `tasks.leaderboard(id)` / `tasks.recommended(id)` | `GET` | `/v1/tasks/{id}/leaderboard` |
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
completion debits the org balance, and an empty balance returns `402`
(`InsufficientCreditsError`).

`model` is an endpoint id from a deploy (or any model id your org can reach).
Extra OpenAI fields (`temperature`, `max_tokens`, `top_p`, ...) pass straight
through as body fields.

Request body:

```json
{
  "model": "ep_contract_kie",
  "messages": [{"role": "user", "content": "Extract the parties."}],
  "temperature": 0.0
}
```

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    resp = pa.chat.completions.create(
        model="ep_contract_kie",
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
    "model": "ep_contract_kie",
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
        model="ep_contract_kie",
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

OpenAI-compatible model listing. Wrapped by `models.list()`. Returns only
deployed, url-bearing endpoints (the OpenAI-compatible subset), shaped as
`{"data": [{"id", "owned_by", "created"}, ...]}`. Each `id` is usable as
`chat.completions.create(model=...)`.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    models = pa.models.list()          # ModelList (iterable, has len)
    for m in models:
        print(m.id, m.owned_by)        # Model
```

## Endpoints

### `POST /v1/endpoints` (SSE)

Deploy a model for a task. Wrapped by
[`endpoints.deploy()`](../guide/deploying-endpoints.md). No hardware knob:
the body is `{task, model, ...}` and Pareta resolves the serving class. `model`
defaults to `"recommended"` (the task's curated or leaderboard-top open pick);
you may also pass a per-task alias or a real id.

Request body:

```json
{"task": "contract-key-fields", "model": "recommended"}
```

The response is a **named-event** SSE stream (distinct from the chat stream's
data-only format):

```
event: progress
data: {"stage": "pulling weights", "pct": 45}

event: complete
data: {"endpoint": {"id": "ep_...", "status": "live", "url": "https://..."}}

event: error
data: {"message": "out of memory"}
```

With `wait=False` (default) the SDK yields `{"event": str, "data": dict}` tuples
so you can drive a progress bar. With `wait=True` it consumes the stream
internally and returns the live `Endpoint` on the `complete` event, raising
`ParetaError` on `error`.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    # Stream progress yourself:
    for ev in pa.endpoints.deploy(task="contract-key-fields"):
        if ev["event"] == "progress":
            print(ev["data"])

    # Or block until live:
    ep = pa.endpoints.deploy(task="contract-key-fields", model="recommended", wait=True)
    print(ep.id, ep.is_live, ep.url)   # Endpoint
```

Extra deploy parameters (`cost_per_request_micro_usd`,
`frontier_cost_per_request_micro_usd`, `region`, `provider`, `quality`,
`run_mode`, `taskDisplay`) pass through as body fields when present.

### `GET /v1/endpoints`

List every endpoint your org can access. Wrapped by `endpoints.list()`. Returns
a bare JSON array of endpoint records; the SDK maps each to an `Endpoint`. The
`model` field on each is the per-task public alias.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    for ep in pa.endpoints.list():
        print(ep.id, ep.status, ep.model)   # Endpoint
```

### `GET /v1/endpoints/{endpoint_id}`

Retrieve one endpoint. Wrapped by `endpoints.retrieve(endpoint_id)`. Returns the
endpoint record as an `Endpoint`. A wrong id returns `404` (`NotFoundError`).

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    ep = pa.endpoints.retrieve("ep_contract_kie")
    print(ep.is_live)   # status == "live"
```

### `POST /v1/endpoints/{endpoint_id}/start` and `/stop`

Start a stopped endpoint, or stop a live one. Wrapped by
`endpoints.start(endpoint_id)` and `endpoints.stop(endpoint_id)`. Both take only
the endpoint id (no GPU knob) and return the raw JSON status body.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    pa.endpoints.start("ep_contract_kie")   # warm a cold endpoint
    pa.endpoints.stop("ep_contract_kie")    # scale to zero
```

### `DELETE /v1/endpoints/{endpoint_id}`

Remove an endpoint. Wrapped by `endpoints.delete(endpoint_id)`, which returns
`None`.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    pa.endpoints.delete("ep_contract_kie")
```

### Endpoint metrics

Five read-only dimensions hang off `endpoints.metrics(endpoint_id)`. Each method
issues a `GET` and returns the raw metric JSON (typed models are forthcoming).
All accept arbitrary query params via `**params`, which become the query string.

| SDK call | Method | Path | What it returns |
|---|---|---|---|
| `.performance(**params)` | `GET` | `/v1/endpoints/{id}/performance` | p50/p95/p99 latency |
| `.uptime(**params)` | `GET` | `/v1/endpoints/{id}/uptime` | availability metrics |
| `.cost(**params)` | `GET` | `/v1/endpoints/{id}/cost` | per-endpoint spend + vs-frontier savings |
| `.quality(**params)` | `GET` | `/v1/endpoints/{id}/quality` | judge windows |
| `.activity(**params)` | `GET` | `/v1/endpoints/{id}/activity` | usage stats |

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    m = pa.endpoints.metrics("ep_contract_kie")
    print(m.performance())          # GET /v1/endpoints/ep_contract_kie/performance
    print(m.cost(window="7d"))      # ?window=7d
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

Map free-text intent to ranked candidate tasks. Wrapped by
`tasks.match(query, top_k=5)`. The matcher is a deterministic keyword scorer with
an optional semantic backstop. An empty `query` raises `ValueError` client-side.

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

### `GET /v1/tasks/{task_id}/leaderboard`

Models ranked by quality and cost for a task, plus the `recommended` alias and a
`frontier` baseline entry. Wrapped by two sync methods:

- `tasks.leaderboard(task_id)` returns the full `Leaderboard`.
- `tasks.recommended(task_id)` is a convenience that returns
  `leaderboard(task_id).recommended` (the deployable model id to pass to
  `endpoints.deploy(model=...)`).

Leaderboard rows carry `cost_per_request_micro_usd` as raw micro-USD (not floored
to cents). Open-model rows are aliases; the `frontier` baseline is a vendor id.

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    lb = pa.tasks.leaderboard("contract-key-fields")
    print(lb.recommended, lb.metric, lb.cost_unit)
    for entry in lb.models:           # LeaderboardEntry
        print(entry.name, entry.kind, entry.quality, entry.cost_per_request_micro_usd)

    best = pa.tasks.recommended("contract-key-fields")
    ep = pa.endpoints.deploy(task="contract-key-fields", model=best, wait=True)
```

> `tasks.leaderboard()` and `tasks.recommended()` exist on the sync client only;
> the async `AsyncTasks` has `list`, `retrieve`, and `match`.

## Evals

### `GET /v1/eval/frontier-models`

The vendor frontier roster you can evaluate against. Wrapped by
`evals.frontier_models(task=None)`. The server returns
`{"frontier_models": [...]}`; the SDK maps each to a `FrontierModel`
(`id`, `vendor`, `vision`, `benchmarked`). Pass `task` to annotate `benchmarked`
(on that task's leaderboard) and vision-filter for document tasks. Feed the ids
into `evals.runs.create(frontier=[...])`.

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
eval set first). `models` is the list of open-candidate aliases to evaluate;
`frontier` adds vendor baselines.

The SDK resolves `frontier` to a list of ids before sending, then posts
`{"eval_set_id": ..., "candidate_model_ids": [...open..., ...frontier...]}`:

| `frontier=` value | Resolves to |
|---|---|
| `None` or `"none"` | `[]` (no baselines) |
| list of ids | the list, as-is |
| `"all"` | every id from `GET /v1/eval/frontier-models?task=...` |
| `"benchmarked"` | frontier models on the task's leaderboard |

A keyword (`"all"` / `"benchmarked"`) needs the task; if you passed `eval_set=`
only, the SDK looks up its `task_id` to resolve the roster, and raises
`ValueError` if the task is unknown. Metered: the org balance is debited for open
and frontier compute, and an empty balance returns `402`.

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
        models=["contract-1", "contract-2"],   # open-model aliases
        frontier="benchmarked",                 # vendor baselines on the leaderboard
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
such as `EvalResult.mean_cost_micro_usd` stay in micro-USD so the open-vs-frontier
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
| 404 | `NotFoundError` | endpoint / eval set / run / task id not found |
| 409 | `ConflictError` | seed endpoint, transient lock/contention |
| 429 | `RateLimitError` | rate limited |
| 503 | `EndpointNotReadyError` | endpoint stopped, cold, or provider down |
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
            model="ep_contract_kie",
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
- [Deploying endpoints](../guide/deploying-endpoints.md) — `deploy`, `start`/`stop`, and `is_live`
- [Evaluation](../guide/evaluation.md) — eval sets, runs, `wait`, and `run.cost`
- [Discovery](../guide/discovery.md) — the benchmark catalog, `match()`, and leaderboards
- [Errors, retries & timeouts](../guide/errors-and-retries.md) — the full exception hierarchy
- [Async](../guide/async.md) — the `AsyncPareta` client end to end
- [Configuration](../guide/configuration.md) — base URL, keys, timeout, and retry budget
