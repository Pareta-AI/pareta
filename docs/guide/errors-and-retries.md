# Errors, retries & timeouts

Every failure the SDK can raise is a subclass of `ParetaError`, so one `except`
clause catches everything, and a more specific clause catches exactly the case
you care about. The client also retries transient failures for you (network
blips, 429s, 5xx) with exponential backoff before giving up. This page is the
map: which exception means what, what is retried automatically, and how to tune
the timeout and retry budget.

Import the exceptions straight from the package:

**Python**

```python
from pareta import (
    Pareta,
    ParetaError,                # base class for everything below
    APIConnectionError,         # never reached the server (DNS/TCP/TLS)
    APITimeoutError,            # subclass of APIConnectionError
    APIStatusError,             # any non-2xx from the server
    BadRequestError,            # 400, 422
    AuthenticationError,        # 401
    PermissionDeniedError,      # 403
    InsufficientCreditsError,   # 402 — org out of balance
    NotFoundError,              # 404
    ConflictError,              # 409
    RateLimitError,             # 429
    EndpointNotReadyError,      # 503 — a backend behind auto warming/briefly down
)
```

**TypeScript**

```typescript
import {
  Pareta,
  ParetaError,                // base class for everything below
  APIConnectionError,         // never reached the server (DNS/TCP/TLS)
  APITimeoutError,            // subclass of APIConnectionError
  APIStatusError,             // any non-2xx from the server
  BadRequestError,            // 400, 422
  AuthenticationError,        // 401
  PermissionDeniedError,      // 403
  InsufficientCreditsError,   // 402 — org out of balance
  NotFoundError,              // 404
  ConflictError,              // 409
  RateLimitError,             // 429
  EndpointNotReadyError,      // 503 — a backend behind auto warming/briefly down
} from "pareta";
```

## The hierarchy

```
ParetaError
├── APIConnectionError          request never reached the server
│   └── APITimeoutError         timed out before any response
└── APIStatusError              server returned a non-2xx status
    ├── BadRequestError         400, 422
    ├── AuthenticationError     401
    ├── InsufficientCreditsError 402
    ├── PermissionDeniedError   403
    ├── NotFoundError           404
    ├── ConflictError           409
    ├── RateLimitError          429
    └── EndpointNotReadyError   503
```

`ParetaError` is also raised directly (not as an `APIStatusError`) in two
non-HTTP cases: constructing a client with no API key, and an `evals.runs.wait()`
poll loop that exceeds its `timeout`. See [Timeouts](#timeouts) below.

## Status code to exception

The server is FastAPI, so error bodies are `{"detail": "<message>"}` with an HTTP
status. The SDK maps the status to the most specific subclass so you catch by
meaning, not by sniffing integers.

| Status | Exception | What it means |
|--------|-----------|---------------|
| 400, 422 | `BadRequestError` | Request validation failed (bad params, malformed body) |
| 401 | `AuthenticationError` | API key missing or invalid |
| 402 | `InsufficientCreditsError` | Org is out of balance; top up in the dashboard |
| 403 | `PermissionDeniedError` | Authenticated, but not allowed to do this |
| 404 | `NotFoundError` | Task / eval set / run id does not exist |
| 409 | `ConflictError` | Conflict (transient lock/contention) |
| 429 | `RateLimitError` | Rate limited; honor `Retry-After` |
| 503 | `EndpointNotReadyError` | A serving backend behind `auto` is warming or briefly unavailable |
| other 5xx | `APIStatusError` | Generic server error |

## Reading an `APIStatusError`

Every `APIStatusError` carries the fields you need to log and debug. `request_id`
comes from the `x-request-id` response header and is the fastest thing to quote
in a support thread.

**Python**

```python
from pareta import Pareta, APIStatusError

with Pareta.from_env() as pa:
    try:
        pa.tasks.retrieve("nonexistent-task")
    except APIStatusError as e:
        print(e.status_code)   # 404
        print(e.detail)        # server's `detail` string (or raw body)
        print(e.request_id)    # "req_…" — quote this in bug reports
        print(e.response)      # the underlying httpx.Response, for advanced use
```

**TypeScript**

```typescript
import { Pareta, APIStatusError } from "pareta";

const pa = Pareta.fromEnv();
try {
  await pa.tasks.retrieve("nonexistent-task");
} catch (e) {
  if (e instanceof APIStatusError) {
    console.log(e.status);     // 404
    console.log(e.detail);     // server's `detail` string (or raw body)
    console.log(e.requestId);  // "req_…" — quote this in bug reports
    console.log(e.response);   // the underlying fetch Response, for advanced use
  }
}
```

`str(e)` is the server's `detail` message when present, otherwise `HTTP <code>`.

## The errors worth catching

Most code only needs to handle a handful of these explicitly. The rest are fine
to let bubble up to a top-level `except ParetaError`.

### `InsufficientCreditsError` (402) — out of balance

Both inference and evals are metered against your org's balance. A successful
[`chat.completions.create()`](./inference.md) debits the balance; an
[`evals.runs.create()`](evaluation.md) debits for the auto and frontier compute it
runs. When the balance can't cover the call, you get a 402. Top-up is
browser-only — the SDK exposes no balance or payment surface — so the right move
is to surface a clear message pointing at the dashboard.

**Python**

```python
from pareta import Pareta, InsufficientCreditsError

with Pareta.from_env() as pa:
    try:
        resp = pa.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": "Extract the parties."}],
        )
    except InsufficientCreditsError:
        raise SystemExit("Org balance is empty. Top up at https://pareta.ai dashboard.")
```

**TypeScript**

```typescript
import { Pareta, InsufficientCreditsError } from "pareta";

const pa = Pareta.fromEnv();
try {
  const resp = await pa.chat.completions.create({
    model: "auto",
    messages: [{ role: "user", content: "Extract the parties." }],
  });
} catch (e) {
  if (e instanceof InsufficientCreditsError) {
    throw new Error("Org balance is empty. Top up at https://pareta.ai dashboard.");
  }
  throw e;
}
```

### `NotFoundError` (404) — wrong id

A stale or mistyped task id, eval set id, or run id.

**Python**

```python
from pareta import Pareta, NotFoundError

with Pareta.from_env() as pa:
    try:
        task = pa.tasks.retrieve("nonexistent-task")
    except NotFoundError:
        match = pa.tasks.match("extract key fields from contracts")  # recover the real id
        if match.chosen:
            task = pa.tasks.retrieve(match.chosen.task_id)
```

**TypeScript**

```typescript
import { Pareta, NotFoundError } from "pareta";

const pa = Pareta.fromEnv();
let task;
try {
  task = await pa.tasks.retrieve("nonexistent-task");
} catch (e) {
  if (e instanceof NotFoundError) {
    const match = await pa.tasks.match("extract key fields from contracts");  // recover the real id
    if (match.chosen?.taskId) task = await pa.tasks.retrieve(match.chosen.taskId);
  } else {
    throw e;
  }
}
```

### `EndpointNotReadyError` (503) — a backend is still warming

`auto` routes each request across serving backends that Pareta manages.
Occasionally the one your request needs is warming up (a cold start) or briefly
unavailable, and the request surfaces a 503. The SDK already retries 503 a
couple of times (see [Automatic retries](#automatic-retries)), which absorbs
most warm-ups; if it still surfaces, there is nothing to start or fix on your
side — wait briefly and re-issue the request.

**Python**

```python
import time

from pareta import Pareta, EndpointNotReadyError

with Pareta.from_env() as pa:
    try:
        resp = pa.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": "ping"}],
        )
    except EndpointNotReadyError:
        time.sleep(10)                       # still warming after the SDK's own retries
        resp = pa.chat.completions.create(   # same request, second pass
            model="auto",
            messages=[{"role": "user", "content": "ping"}],
        )
```

**TypeScript**

```typescript
import { Pareta, EndpointNotReadyError } from "pareta";

const pa = Pareta.fromEnv();
const request = () =>
  pa.chat.completions.create({
    model: "auto",
    messages: [{ role: "user", content: "ping" }],
  });
let resp;
try {
  resp = await request();
} catch (e) {
  if (e instanceof EndpointNotReadyError) {
    await new Promise((r) => setTimeout(r, 10_000));  // still warming after the SDK's own retries
    resp = await request();                           // same request, second pass
  } else {
    throw e;
  }
}
```

### `RateLimitError` (429) — slow down

Already retried automatically, honoring the server's `Retry-After`. You only see
it after the retry budget is exhausted. Back off and try again later.

**Python**

```python
from pareta import Pareta, RateLimitError

with Pareta.from_env() as pa:
    try:
        pa.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": "hi"}],
        )
    except RateLimitError as e:
        print(f"Still rate limited after retries (request {e.request_id}); back off.")
```

**TypeScript**

```typescript
import { Pareta, RateLimitError } from "pareta";

const pa = Pareta.fromEnv();
try {
  await pa.chat.completions.create({
    model: "auto",
    messages: [{ role: "user", content: "hi" }],
  });
} catch (e) {
  if (e instanceof RateLimitError) {
    console.log(`Still rate limited after retries (request ${e.requestId}); back off.`);
  } else {
    throw e;
  }
}
```

### `AuthenticationError` (401) vs missing key

A 401 means the key reached the server and was rejected (wrong or revoked). That
is distinct from constructing a client with *no* key at all, which fails fast
client-side with a plain `ParetaError` before any request goes out:

**Python**

```python
import pareta

try:
    pa = pareta.Pareta(api_key="")   # or PARETA_API_KEY unset with from_env()
except pareta.ParetaError as e:
    print(e)  # "missing API key. Pass api_key=… or set PARETA_API_KEY …"
```

**TypeScript**

```typescript
import { Pareta, ParetaError } from "pareta";

try {
  const pa = new Pareta({ apiKey: "" });   // or PARETA_API_KEY unset with Pareta.fromEnv()
} catch (e) {
  if (e instanceof ParetaError) {
    console.log(e.message);  // "missing API key. Pass apiKey: … or use Pareta.fromEnv() …"
  }
}
```

## Pre-flight `ValueError` / `TypeError`

Some mistakes never become an HTTP call. The SDK validates the obvious ones up
front and raises the standard Python exception — not a `ParetaError` — because
they are programming errors, not server responses:

- [`chat.completions.create()`](./inference.md) raises `ValueError` if `model`
  or `messages` is empty.
- [`tasks.match()`](../reference/tasks.md) raises `ValueError` if `query` is empty.
- [`evals.sets.create()`](evaluation.md) raises `ValueError` if `items` or
  `prompt` is empty.
- [`evals.runs.create()`](evaluation.md) raises `ValueError` if neither
  `eval_set=` nor `items=` (with `prompt=`) is supplied, and
  `ValueError`/`TypeError` if `frontier=` is an unparseable keyword or a
  frontier keyword can't be resolved to a task.
- [`evals.sets.upload_document()`](evaluation.md) raises `TypeError` if `file` is
  not a path, bytes, or a binary file-like object.

These are fine to let crash in development; they signal a bug in the call, not a
runtime condition to recover from.

## Automatic retries

The client retries transient failures for you before raising. You usually do not
need a retry loop of your own.

**What is retried:** status codes `408, 409, 429, 500, 502, 503, 504`, plus
connection-level errors that happen *between* attempts. The default budget is
`max_retries=2` (so up to three attempts total).

**Backoff:** if the server sent a `Retry-After` header, the SDK waits that many
seconds (capped at 30s). Otherwise it uses exponential backoff with jitter:
`min(0.5 * 2**attempt, 8.0) + random(0, 0.25)` seconds, so roughly 0.5s, then
1s, capped at 8s.

**What is not retried:** stable 4xx (400, 401, 402, 403, 404, 422) raise
immediately — retrying a bad request or an empty balance won't help. Connection
errors on the very first attempt are surfaced as `APIConnectionError` /
`APITimeoutError` once the budget is exhausted.

Tune the budget per client. Set `max_retries=0` to disable retries entirely:

**Python**

```python
from pareta import Pareta

# More aggressive: up to 6 attempts on transient failures.
pa = Pareta.from_env(max_retries=5)

# No retries — fail fast and handle it yourself.
strict = Pareta.from_env(max_retries=0)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

// More aggressive: up to 6 attempts on transient failures.
const pa = Pareta.fromEnv({ maxRetries: 5 });

// No retries — fail fast and handle it yourself.
const strict = Pareta.fromEnv({ maxRetries: 0 });
```

### Streaming and retries

Retries apply only to the initial handshake (connect and status line). Once SSE
bytes are flowing — token chunks from a streamed
[chat completion](./inference.md) — a mid-stream drop raises immediately, because
the stream cannot be safely resumed. Catch it and restart the request from the
top if you need to.

**Python**

```python
from pareta import Pareta, APIConnectionError

with Pareta.from_env() as pa:
    try:
        for chunk in pa.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": "Summarize the contract."}],
            stream=True,
        ):
            piece = chunk.choices[0].delta.content
            if piece:
                print(piece, end="", flush=True)
    except APIConnectionError:
        print("\n[stream dropped — re-issue the request to retry]")
```

**TypeScript**

```typescript
import { Pareta, APIConnectionError } from "pareta";

const pa = Pareta.fromEnv();
try {
  const stream = pa.chat.completions.create({
    model: "auto",
    messages: [{ role: "user", content: "Summarize the contract." }],
    stream: true,
  });
  for await (const chunk of stream) {
    const piece = chunk.choices[0].delta.content;
    if (piece) process.stdout.write(piece);
  }
} catch (e) {
  if (e instanceof APIConnectionError) {
    console.log("\n[stream dropped — re-issue the request to retry]");
  } else {
    throw e;
  }
}
```

## Timeouts

The default per-request timeout is `httpx.Timeout(60.0, connect=10.0)`: 60s
overall, 10s to establish the connection. A request that exceeds it raises
`APITimeoutError` (a subclass of `APIConnectionError`) after the retry budget is
spent. Override it with any `httpx.Timeout` (or a bare float):

**Python**

```python
import httpx
from pareta import Pareta, APITimeoutError

# 120s overall, 5s to connect — handy for long generations.
pa = Pareta.from_env(timeout=httpx.Timeout(120.0, connect=5.0))

with pa:
    try:
        pa.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": "Write a long summary."}],
            max_tokens=4096,
        )
    except APITimeoutError:
        print("Request timed out; consider streaming or a larger timeout.")
```

**TypeScript**

```typescript
import { Pareta, APITimeoutError } from "pareta";

// 120s overall (one budget — there's no separate connect timeout in TS).
const pa = Pareta.fromEnv({ timeout: 120_000 });

try {
  await pa.chat.completions.create({
    model: "auto",
    messages: [{ role: "user", content: "Write a long summary." }],
    max_tokens: 4096,
  });
} catch (e) {
  if (e instanceof APITimeoutError) {
    console.log("Request timed out; consider streaming or a larger timeout.");
  } else {
    throw e;
  }
}
```

### Eval-run wait timeout

[`evals.runs.create(wait=True)`](evaluation.md) and `evals.runs.wait()` are
different: they poll the run to completion. The `timeout` parameter there bounds
the *whole poll loop* (default 900s), not a single HTTP request. If the run
hasn't reached a terminal status (`completed` or `failed`) by the deadline, the
poll helper raises a plain `ParetaError` — the run keeps going server-side, so
you can re-`retrieve()` it later by id.

**Python**

```python
from pareta import Pareta, ParetaError

with Pareta.from_env() as pa:
    try:
        run = pa.evals.runs.create(
            prompt="extract the key fields from each contract",
            items=[{"input": {"contract_text": "..."}, "expected_output": {...}}],
            models=["auto"],
            frontier="benchmarked",
            wait=True,
            timeout=600.0,      # give up waiting after 10 minutes
            poll_interval=5.0,
        )
        print(run.status, run.cost)        # e.g. "completed" Decimal("0.42")
    except ParetaError as e:
        print(e)  # "eval run … did not finish within 600s" — poll later with runs.retrieve(id)
```

**TypeScript**

```typescript
import { Pareta, ParetaError } from "pareta";

const pa = Pareta.fromEnv();
try {
  const run = await pa.evals.runs.create({
    prompt: "extract the key fields from each contract",
    items: [{ input: { contract_text: "..." }, expected_output: {} }],
    models: ["auto"],
    frontier: "benchmarked",
    wait: true,
    timeout: 600,        // give up waiting after 10 minutes
    pollInterval: 5,
  });
  console.log(run.status, run.cost);   // e.g. "completed" "0.42"
} catch (e) {
  if (e instanceof ParetaError) {
    console.log(e.message);  // "eval run … did not finish within 600s" — poll later with runs.retrieve(id)
  } else {
    throw e;
  }
}
```

Note that a run finishing with `status == "failed"` is *not* an exception — it's
a terminal state you read off the returned `EvalRun` (`run.is_terminal` is True,
`run.error_detail` carries the message). Only the wait *timeout* raises.

## Async

`AsyncPareta` raises the exact same exception classes; wrap `await` calls in the
same `try`/`except`. Retries, backoff, and timeouts behave identically — backoff
just uses `asyncio.sleep` under the hood.

**Python**

```python
import asyncio
from pareta import AsyncPareta, InsufficientCreditsError, EndpointNotReadyError

async def main():
    async with AsyncPareta.from_env() as pa:
        try:
            resp = await pa.chat.completions.create(
                model="auto",
                messages=[{"role": "user", "content": "Extract the parties."}],
            )
            print(resp.choices[0].message.content)
        except InsufficientCreditsError:
            print("Top up your org balance in the dashboard.")
        except EndpointNotReadyError:
            print("A backend behind auto is still warming — retry shortly.")

asyncio.run(main())
```

**TypeScript**

```typescript
// There is no AsyncPareta in TypeScript — the single `Pareta` client is already
// async: every I/O method returns a Promise, so you just `await` it. The same
// exception classes, retries, backoff, and timeouts apply unchanged.
import { Pareta, InsufficientCreditsError, EndpointNotReadyError } from "pareta";

async function main() {
  const pa = Pareta.fromEnv();
  try {
    const resp = await pa.chat.completions.create({
      model: "auto",
      messages: [{ role: "user", content: "Extract the parties." }],
    });
    console.log(resp.choices[0].message.content);
  } catch (e) {
    if (e instanceof InsufficientCreditsError) {
      console.log("Top up your org balance in the dashboard.");
    } else if (e instanceof EndpointNotReadyError) {
      console.log("A backend behind auto is still warming — retry shortly.");
    } else {
      throw e;
    }
  }
}

main();
```

## A layered handler

A practical pattern: catch the few cases you can act on, then fall back to the
base class so nothing escapes unhandled.

**Python**

```python
from pareta import (
    Pareta,
    InsufficientCreditsError,
    EndpointNotReadyError,
    RateLimitError,
    APITimeoutError,
    ParetaError,
)

with Pareta.from_env() as pa:
    try:
        resp = pa.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": "Extract the parties."}],
        )
        print(resp.choices[0].message.content)
    except InsufficientCreditsError:
        print("Out of balance — top up in the dashboard.")
    except EndpointNotReadyError:
        print("A backend is still warming — wait briefly, then retry.")
    except RateLimitError:
        print("Rate limited after retries — back off and try again.")
    except APITimeoutError:
        print("Timed out — raise the timeout or stream the response.")
    except ParetaError as e:
        print(f"Unexpected SDK error: {e}")  # request_id is on APIStatusError subclasses
```

**TypeScript**

```typescript
import {
  Pareta,
  InsufficientCreditsError,
  EndpointNotReadyError,
  RateLimitError,
  APITimeoutError,
  ParetaError,
} from "pareta";

const pa = Pareta.fromEnv();
try {
  const resp = await pa.chat.completions.create({
    model: "auto",
    messages: [{ role: "user", content: "Extract the parties." }],
  });
  console.log(resp.choices[0].message.content);
} catch (e) {
  if (e instanceof InsufficientCreditsError) {
    console.log("Out of balance — top up in the dashboard.");
  } else if (e instanceof EndpointNotReadyError) {
    console.log("A backend is still warming — wait briefly, then retry.");
  } else if (e instanceof RateLimitError) {
    console.log("Rate limited after retries — back off and try again.");
  } else if (e instanceof APITimeoutError) {
    console.log("Timed out — raise the timeout or stream the response.");
  } else if (e instanceof ParetaError) {
    console.log(`Unexpected SDK error: ${e.message}`);  // requestId is on APIStatusError subclasses
  } else {
    throw e;
  }
}
```

## See also

- [Inference](./inference.md) — OpenAI-compatible chat completions and streaming
- [Evals](evaluation.md) — eval sets, runs, `wait`, and `run.cost`
- [Tasks](../reference/tasks.md) — the benchmark catalog and `match()`
