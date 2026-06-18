# Exceptions

Every error the Pareta SDK raises is a subclass of `ParetaError`. That single
base class is the contract: one `except ParetaError` catches anything the SDK
can throw, and a narrower `except InsufficientCreditsError` catches exactly the
case you care about. Server errors carry the HTTP `status_code`, the server's
`detail` message, and a `request_id` you can quote in a support ticket.

This page is the class-by-class reference: the full hierarchy, the
status-code-to-class mapping, and the attributes on each error. For the
narrative version (what gets retried automatically, how to tune timeouts and
the retry budget), see [Errors, retries & timeouts](../guide/errors-and-retries.md).

## Import

All exception classes are exported from the top-level package. Import the ones
you handle directly.

```python
from pareta import (
    ParetaError,                # base class for everything below
    APIConnectionError,         # never reached the server (DNS/TCP/TLS)
    APITimeoutError,            # subclass of APIConnectionError
    APIStatusError,             # any non-2xx from the server
    BadRequestError,            # 400, 422
    AuthenticationError,        # 401
    InsufficientCreditsError,   # 402 — org out of balance
    PermissionDeniedError,      # 403
    NotFoundError,              # 404
    ConflictError,              # 409
    RateLimitError,             # 429
    EndpointNotReadyError,      # 503 — endpoint stopped/cold/provider down
)
```

## The hierarchy

```
Exception
└── ParetaError                      base class for every SDK error
    ├── APIConnectionError           request never reached the server
    │   └── APITimeoutError          timed out before any response
    └── APIStatusError               server returned a non-2xx status
        ├── BadRequestError          400, 422
        ├── AuthenticationError      401
        ├── InsufficientCreditsError 402
        ├── PermissionDeniedError    403
        ├── NotFoundError            404
        ├── ConflictError            409
        ├── RateLimitError           429
        └── EndpointNotReadyError    503
```

Two facts that fall out of this tree and are worth holding onto:

- `APITimeoutError` is a subclass of `APIConnectionError`, so catching
  `APIConnectionError` also catches timeouts.
- Every status-mapped class (`BadRequestError`, `InsufficientCreditsError`, and
  the rest) is a subclass of `APIStatusError`, so catching `APIStatusError`
  catches all of them and gives you `.status_code`, `.detail`, and `.request_id`.

## Status code mapping

When the server returns a non-2xx response, the SDK builds the most specific
`APIStatusError` subclass for that status. Anything not in the table below
(other 5xx, unexpected codes) surfaces as a plain `APIStatusError` carrying the
raw `status_code`.

| Status | Exception | When |
| --- | --- | --- |
| 400 | `BadRequestError` | Request rejected by the server |
| 401 | `AuthenticationError` | Missing or invalid `pareta_sk_` API key |
| 402 | `InsufficientCreditsError` | Org balance is empty — top up in the dashboard |
| 403 | `PermissionDeniedError` | Authenticated, but not allowed |
| 404 | `NotFoundError` | Endpoint, task, eval set, or run id does not exist |
| 409 | `ConflictError` | Conflict (e.g. seed endpoint, transient lock/contention) |
| 422 | `BadRequestError` | FastAPI request validation failed |
| 429 | `RateLimitError` | Rate limited; honors `Retry-After` |
| 503 | `EndpointNotReadyError` | Endpoint stopped, cold-starting, or provider down |
| other 5xx | `APIStatusError` | Generic server error |

Note that `400` and `422` both map to `BadRequestError`, so a single clause
covers both client-side and FastAPI-validation rejections.

## Class reference

### `ParetaError`

The base class for every error the SDK raises. Catch this to handle any SDK
failure with one clause. It is also raised directly in one non-HTTP case:
constructing a client with no API key.

```python
from pareta import Pareta, ParetaError

try:
    pa = Pareta()            # no api_key arg, PARETA_API_KEY unset
except ParetaError as e:
    print(e)                 # "missing API key. Pass api_key=… or set PARETA_API_KEY …"
```

### `APIConnectionError(ParetaError)`

The request never reached the server: DNS failure, TCP refusal, TLS error, or a
dropped connection. Connection failures on the initial handshake are retried up
to `max_retries` times; this is raised only after the retry budget is spent.

```python
APIConnectionError(message: str = "connection error", *, cause: BaseException | None = None)
```

The underlying `httpx` exception is attached as `.__cause__`, so a traceback
shows the original network error.

### `APITimeoutError(APIConnectionError)`

The request did not complete within the client `timeout` (default
`httpx.Timeout(60.0, connect=10.0)`). Because it subclasses
`APIConnectionError`, an `except APIConnectionError` clause also catches it.

```python
APITimeoutError(message: str = "request timed out", *, cause: BaseException | None = None)
```

### `APIStatusError(ParetaError)`

The server returned a non-2xx status. This is the parent of every
status-mapped class below, and is also raised directly for any status not in
the [mapping table](#status-code-mapping).

**Attributes**

```python
status_code: int                  # the HTTP status
detail: Any                       # server's `detail` message, or the raw body
request_id: str | None            # value of the x-request-id response header
response: httpx.Response | None   # the full response, for advanced use
```

`detail` is the FastAPI `{"detail": "..."}` message when the body is JSON;
otherwise it falls back to the raw response text. `request_id` comes from the
`x-request-id` header and is the value to quote when reporting a problem.

```python
from pareta import Pareta, APIStatusError

pa = Pareta.from_env()
try:
    pa.endpoints.retrieve("ep_does_not_exist")
except APIStatusError as e:
    print(e.status_code)     # 404
    print(e.detail)          # server's explanation
    print(e.request_id)      # quote this in a support ticket
```

### `BadRequestError(APIStatusError)` — 400, 422

The request was rejected by the server, either as a bad request (400) or a
FastAPI validation failure (422). Inspect `.detail` for the specific field or
reason.

### `AuthenticationError(APIStatusError)` — 401

The `pareta_sk_` API key is missing or invalid. Mint a fresh key in the
dashboard and pass it via `Pareta.from_env()` (reads `PARETA_API_KEY`) or
`Pareta(api_key="pareta_sk_…")`.

### `InsufficientCreditsError(APIStatusError)` — 402

The org balance is empty. Both metered paths raise this: inference
(`chat.completions.create()`) and eval runs (`evals.runs.create()`, billed for
open and frontier compute combined). Top-up is browser-only — the SDK never
exposes balance or payment methods, so the fix is to add credit in the
dashboard and retry.

```python
from pareta import Pareta, InsufficientCreditsError

pa = Pareta.from_env()
try:
    pa.chat.completions.create(
        model="ep_contract_kie",
        messages=[{"role": "user", "content": "Extract the parties."}],
    )
except InsufficientCreditsError:
    print("Org is out of credit — top up at https://pareta.ai in the dashboard, then retry.")
```

### `PermissionDeniedError(APIStatusError)` — 403

The key is valid but the org or user lacks permission for the requested
resource or action.

### `NotFoundError(APIStatusError)` — 404

The referenced resource does not exist: an unknown endpoint id, task id, eval
set id, or run id.

### `ConflictError(APIStatusError)` — 409

A conflict on the server — for example a seed/legacy endpoint that is not
deployable, or a transient lock or contention. A 409 is retried automatically
(see [the retry list below](#what-gets-retried)); a stable 409 surfaces here
after the retry budget is spent.

### `RateLimitError(APIStatusError)` — 429

Too many requests. The client retries 429s automatically, honoring the server's
`Retry-After` header when present; this is raised only after retries are
exhausted.

### `EndpointNotReadyError(APIStatusError)` — 503

The target endpoint is not serving yet: stopped, cold-starting, or its provider
is temporarily unavailable. Start it with `endpoints.start(endpoint_id)`, wait
for `endpoint.is_live`, then retry. 503 is in the automatic retry set, so a
brief cold start often resolves before this is raised.

```python
from pareta import Pareta, EndpointNotReadyError

pa = Pareta.from_env()
try:
    pa.chat.completions.create(
        model="ep_contract_kie",
        messages=[{"role": "user", "content": "ping"}],
    )
except EndpointNotReadyError:
    pa.endpoints.start("ep_contract_kie")   # wake it, then retry
```

## What gets retried

The client retries transient failures before raising, so most of the errors
above only surface after the retry budget (`max_retries`, default `2`) is spent.

- **Retried automatically:** connection and timeout errors on the initial
  handshake, and HTTP statuses **408, 409, 429, 500, 502, 503, 504**. Backoff is
  exponential with jitter — `min(0.5 * 2**attempt, 8.0)` seconds — and honors a
  `Retry-After` header when the server sends one.
- **Never retried:** `400`, `401`, `402`, `403`, `404`, `422`, and any other
  status not in the list. These are deterministic — retrying would not change the
  outcome — so they raise immediately.
- **Mid-stream drops are not retried.** Retries apply only to the initial
  handshake; once SSE bytes are flowing (a streaming chat completion or a deploy
  progress stream) a dropped connection raises immediately, since the stream
  cannot be safely resumed.

Tune the budget per client:

```python
from pareta import Pareta

pa = Pareta.from_env(max_retries=5)   # default is 2; set 0 to disable retries
```

## Handling errors

Order `except` clauses from most specific to least specific. The base
`ParetaError` is the safety net at the bottom.

```python
from pareta import (
    Pareta,
    InsufficientCreditsError,
    EndpointNotReadyError,
    RateLimitError,
    APIStatusError,
    APIConnectionError,
    ParetaError,
)

pa = Pareta.from_env()

try:
    completion = pa.chat.completions.create(
        model="ep_contract_kie",
        messages=[{"role": "user", "content": "Summarize this contract."}],
    )
    print(completion.choices[0].message.content)
except InsufficientCreditsError:
    print("Out of credit — top up in the dashboard, then retry.")
except EndpointNotReadyError:
    pa.endpoints.start("ep_contract_kie")          # wake a cold/stopped endpoint
except RateLimitError as e:
    print(f"Rate limited; the client already retried. request_id={e.request_id}")
except APIStatusError as e:
    print(f"Server returned {e.status_code}: {e.detail} (request_id={e.request_id})")
except APIConnectionError:
    print("Could not reach the API after retries — check the network.")
except ParetaError as e:
    print(f"Unexpected SDK error: {e}")
```

The same classes and hierarchy apply to the async client — `await`ed
`AsyncPareta` calls raise the exact same exception types, so error handling code
is identical across sync and async.

```python
import asyncio
from pareta import AsyncPareta, APIStatusError

async def main():
    async with AsyncPareta.from_env() as pa:
        try:
            await pa.endpoints.retrieve("ep_does_not_exist")
        except APIStatusError as e:
            print(e.status_code, e.detail)

asyncio.run(main())
```

## Pre-flight `ValueError`

A few methods validate arguments before any network call and raise the
standard-library `ValueError` (not a `ParetaError`) when an argument is plainly
unusable. These are programming errors caught early, not server responses:

- `chat.completions.create()` — empty `model` or `messages`
- `tasks.match()` — empty `query`
- `evals.sets.create()` — empty `items`
- `evals.runs.create(frontier=…)` — a `frontier` value that cannot be resolved

## See also

- [Errors, retries & timeouts](../guide/errors-and-retries.md) — the narrative
  guide: retry behavior, backoff, and tuning the timeout and retry budget.
- [Configuration](../guide/configuration.md) — setting `api_key`, `base_url`,
  `timeout`, and `max_retries`.
- [Inference](../guide/inference.md) — the metered chat path that raises
  `InsufficientCreditsError`.
- [Deploying endpoints](../guide/deploying-endpoints.md) — starting and stopping
  endpoints behind `EndpointNotReadyError`.
- [Evaluation](../guide/evaluation.md) — eval runs, also metered against the org
  balance.
