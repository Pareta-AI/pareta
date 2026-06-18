# chat.completions

Run inference against a deployed endpoint. `chat.completions.create(...)` is the one call you make to get tokens out of a model you deployed on Pareta. It has the same shape as the OpenAI chat completions API: pass a `model`, a list of `messages`, and you get a `ChatCompletion` back. Set `stream=True` and you get an iterator of token deltas instead.

Inference on Pareta is OpenAI-compatible on the wire (vLLM-style SSE), so this exact surface works whether you call it through this SDK, the `openai` package, or raw HTTP. This SDK's added value is the control plane around it (deploy, eval, discover); for plain inference the clients are interchangeable.

Two platform truths shape this page:

- **Models are per-task aliases, and GPUs are hidden.** The `model` you pass is an endpoint id from [`endpoints.deploy(...)`](./endpoints.md), or any callable model id your org can reach. Real open-weights model ids never cross to you, and you never pick a GPU, quantization, or tensor-parallel setting. The backend resolves all of that.
- **Inference is metered against your org balance.** A successful completion debits your balance in dollars. If the balance is empty, the call raises [`InsufficientCreditsError`](exceptions.md) (402). Top-up is browser-only; the SDK exposes no balance or payment surface.

**Route:** `POST /v1/chat/completions`

## Signature

```python
class Completions:
    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        stream: bool = False,
        **kwargs: Any,
    ) -> ChatCompletion | Iterator[ChatCompletionChunk]
```

All arguments are keyword-only.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `model` | `str` | required | An endpoint id from [`endpoints.deploy(...)`](./endpoints.md), an id from [`models.list()`](./models.md), or a per-task alias. Validated server-side at call time. |
| `messages` | `list[dict]` | required | Non-empty list of OpenAI-format message dicts (`{"role": ..., "content": ...}`). |
| `stream` | `bool` | `False` | `False` returns a `ChatCompletion`; `True` returns an iterator of `ChatCompletionChunk`. |
| `**kwargs` | `Any` | — | Any extra OpenAI body field (`temperature`, `max_tokens`, `top_p`, `stop`, `seed`, ...) passes through unchanged. |

`model` and `messages` are both required. The SDK raises `ValueError` before sending if `model` is falsy or `messages` is empty, so a malformed call fails fast without burning a request or a charge.

## Basic completion

```python
from pareta import Pareta

with Pareta.from_env() as pa:   # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
    resp = pa.chat.completions.create(
        model="ep_invoice_xtract",   # an endpoint id from endpoints.deploy()
        messages=[
            {"role": "system", "content": "You extract structured fields from documents."},
            {"role": "user", "content": "What is the invoice total?\n\nINVOICE\nTotal due: $4,210.00"},
        ],
    )

    print(resp.choices[0].message.content)
    print(resp.usage.total_tokens, "tokens")
```

`Pareta.from_env()` is the recommended constructor; it reads `PARETA_API_KEY` and the optional `PARETA_BASE_URL`. You can also pass the key explicitly with `Pareta(api_key="pareta_sk_...")`. The client is a context manager, so `with` releases the HTTP connection for you.

### Where `model` comes from

Three interchangeable sources:

- An endpoint id you deployed. See [`endpoints.deploy`](./endpoints.md).
- Any id returned by [`models.list()`](./models.md) (your deployed, callable endpoints).
- A per-task model alias. The deployable recommended pick for a task is `pa.tasks.recommended(task_id)`; see [`tasks`](./tasks.md).

## Return type: ChatCompletion

With `stream=False` (the default), `create(...)` returns a `ChatCompletion`. Fields mirror OpenAI:

```python
resp.id                            # str | None
resp.model                         # str | None — the alias that served the call
resp.created                       # int | None — Unix timestamp
resp.choices                       # list[Choice]
resp.choices[0].index              # int | None
resp.choices[0].finish_reason      # str | None — "stop", "length", ...
resp.choices[0].message.role       # str | None — "assistant"
resp.choices[0].message.content    # str | None — the generated text
resp.usage.prompt_tokens           # int | None
resp.usage.completion_tokens       # int | None
resp.usage.total_tokens            # int | None
```

Every response object keeps the untouched server JSON. If a field is not surfaced as a typed property, reach it with `resp.to_dict()` or `resp["..."]`. Nothing the API returns is lost behind the typed layer.

## Passthrough parameters

Any extra keyword goes straight into the request body, so the full OpenAI parameter set is available without the SDK enumerating it:

```python
resp = pa.chat.completions.create(
    model="ep_invoice_xtract",
    messages=[{"role": "user", "content": "Summarize this contract clause: ..."}],
    temperature=0.2,
    max_tokens=512,
    top_p=0.9,
    stop=["\n\n"],
    seed=7,
)
```

These fields are not validated SDK-side; they are forwarded as-is and validated by the serving model. An unsupported field comes back as a `BadRequestError` (400/422).

## Streaming

Set `stream=True` and `create(...)` returns an `Iterator[ChatCompletionChunk]` instead of a single `ChatCompletion`. Each chunk carries a `delta` (not a `message`); the incremental text is at `chunk.choices[0].delta.content`.

```python
with Pareta.from_env() as pa:
    stream = pa.chat.completions.create(
        model="ep_invoice_xtract",
        messages=[{"role": "user", "content": "Draft a one-paragraph status update."}],
        stream=True,
    )
    for chunk in stream:
        print(chunk.choices[0].delta.content or "", end="", flush=True)
    print()
```

A chunk has the same schema as a `ChatCompletion`. `ChatCompletionChunk` exists as a distinct type only for hinting:

```python
chunk.choices[0].delta.content    # str | None — the new text in this chunk
chunk.choices[0].delta.role       # str | None — usually only set on the first chunk
chunk.choices[0].finish_reason    # str | None — "stop" / "length" on the last chunk
chunk.id                          # str | None
chunk.model                       # str | None
```

Guard `delta.content` with `or ""` (or an `if delta:` check): the opening role chunk and the final `finish_reason` chunk carry no text, so `delta.content` is `None` there. To accumulate the full text:

```python
text = "".join(c.choices[0].delta.content or "" for c in stream)
```

The stream is data-only SSE and always terminates on a `[DONE]` sentinel, which the SDK consumes for you, so the iterator simply ends and a plain `for` loop exits cleanly.

**Mid-stream behavior:** retries (see below) cover only the initial connect and status-line handshake. Once tokens are flowing, a mid-stream connection drop raises immediately rather than silently resuming. Nothing is sent until you start iterating, and the connection stays open for the life of the loop.

## Async

`AsyncPareta` mirrors the sync client. `create(...)` is `async def`. For streaming you `await` the call once, then `async for` over the chunks.

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        # Non-streaming: await returns a ChatCompletion
        resp = await pa.chat.completions.create(
            model="ep_invoice_xtract",
            messages=[{"role": "user", "content": "What is the invoice total?"}],
        )
        print(resp.choices[0].message.content)

        # Streaming: await once, then async-for the chunks
        stream = await pa.chat.completions.create(
            model="ep_invoice_xtract",
            messages=[{"role": "user", "content": "Stream me a haiku about ledgers."}],
            stream=True,
        )
        async for chunk in stream:
            print(chunk.choices[0].delta.content or "", end="", flush=True)
        print()

asyncio.run(main())
```

The async return type is `ChatCompletion | AsyncIterator[ChatCompletionChunk]`. The async client also exposes `aclose()` and works as an `async with` context manager.

## Metering

Every successful completion (streaming or not) debits your org balance. The `chat.completions` surface does not return a per-call cost field; spend is summarized per endpoint via [`endpoints.metrics(...).cost(...)`](./endpoints.md). If the org balance is empty, the call raises `InsufficientCreditsError` (402, a subclass of `ParetaError`). Top up in the dashboard; billing is browser-only and the SDK has no balance or payment surface.

## Errors

`create(...)` raises specific subclasses of `ParetaError`. A single `except ParetaError` is a fine catch-all; the named classes let you branch. The two cases specific to running inference are an empty balance and a not-ready endpoint:

```python
from pareta import (
    Pareta,
    InsufficientCreditsError,   # 402: org balance empty
    EndpointNotReadyError,      # 503: endpoint stopped / cold / provider down
)

with Pareta.from_env() as pa:
    try:
        resp = pa.chat.completions.create(
            model="ep_invoice_xtract",
            messages=[{"role": "user", "content": "Hello"}],
        )
        print(resp.choices[0].message.content)
    except InsufficientCreditsError:
        # Balance hit zero. Top up in the dashboard (billing is browser-only).
        print("Out of credit — top up in the dashboard, then retry.")
    except EndpointNotReadyError:
        # The endpoint is stopped or cold-starting. Start it, wait for live, retry.
        pa.endpoints.start("ep_invoice_xtract")
        print("Endpoint was not ready — started it; retry shortly.")
```

| Raised | Status | When |
|--------|--------|------|
| `ValueError` | — | `model` falsy or `messages` empty (SDK-side, before sending) |
| `BadRequestError` | 400 / 422 | Malformed request or unsupported passthrough field |
| `AuthenticationError` | 401 | Invalid or missing API key |
| `InsufficientCreditsError` | 402 | Org balance empty |
| `PermissionDeniedError` | 403 | Caller lacks permission for the endpoint |
| `NotFoundError` | 404 | `model` is not a callable endpoint or model id |
| `RateLimitError` | 429 | Rate limited (after retries) |
| `EndpointNotReadyError` | 503 | Endpoint stopped, cold-starting, or provider down |
| `APITimeoutError` | — | No response within the client timeout (after retries) |
| `APIConnectionError` | — | DNS, TCP, or TLS failure |

`APIStatusError` subclasses expose `status_code`, `detail`, `request_id` (the `x-request-id` header), and the raw `response` for debugging. See [Errors](exceptions.md) for the full hierarchy.

### Retries

Transient failures (408, 409, 429, 500, 502, 503, 504) are retried automatically with exponential backoff and jitter, up to `max_retries` times (default 2), honoring a `Retry-After` header when present. You only see `RateLimitError`, `EndpointNotReadyError`, or `APITimeoutError` after retries are exhausted. For streaming, retries cover only the initial handshake, never a mid-stream drop.

## Using the OpenAI SDK instead

Because the endpoint is OpenAI-compatible, you do not need this SDK to call it. Point the `openai` client at Pareta's base URL with your `pareta_sk_` key. Note the `/v1` suffix the OpenAI client expects:

```python
from openai import OpenAI

client = OpenAI(api_key="pareta_sk_...", base_url="https://api.pareta.ai/v1")

resp = client.chat.completions.create(
    model="ep_invoice_xtract",
    messages=[{"role": "user", "content": "What is the invoice total?"}],
)
print(resp.choices[0].message.content)
```

Streaming, `temperature`, `max_tokens`, and the rest work exactly as they do against OpenAI. Metering still applies; a zero balance returns a 402, which the `openai` client surfaces as its own status error. Reach for the Pareta SDK when you want the control plane: [deploying endpoints](./endpoints.md), [discovering tasks](./tasks.md), and [running evals](./evals.md).

## See also

- [`models`](./models.md) — list the callable endpoint ids you can pass as `model`.
- [`endpoints`](./endpoints.md) — deploy, start, stop, and read cost metrics for the endpoint you infer against.
- [`tasks`](./tasks.md) — discover tasks and the recommended deployable model for each.
- [`evals`](./evals.md) — evaluate candidate models on your own data before deploying.
- [Errors](exceptions.md) — the full exception hierarchy and retry policy.
