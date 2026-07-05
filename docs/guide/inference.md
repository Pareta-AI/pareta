# Running inference

Once you have a live endpoint, you call it through `chat.completions.create`, which has the same shape as the OpenAI chat completions API. Pass the endpoint id as `model`, a list of messages, and you get a `ChatCompletion` back. Set `stream=True` and you get an iterator of token deltas instead.

Pareta is OpenAI-compatible on the wire, so you can run inference with this SDK, with the `openai` package, or with raw HTTP, whichever fits your stack. This SDK's extra value is the control plane (deploy, eval, discover); for plain inference the two are interchangeable.

A few platform truths that shape this page:

- **Models are per-task aliases.** The `model` you pass is an endpoint id from [deploy](deploying-endpoints.md), or a callable model alias. Real open-weights model ids never reach you; the backend resolves them. You never pick a GPU.
- **Inference is metered against your org balance.** A successful completion debits your balance. If the balance is empty, the call raises `InsufficientCreditsError` (402). Top-up is browser-only; the SDK has no balance or payment surface.

## `model="auto"` — the routing brain

The recommended model id for every request is the literal string `"auto"`.
Pareta decomposes the request, routes each part to the cheapest model that
holds frontier-grade quality, verifies checkable outputs (escalating to a
frontier model on a failed check), and synthesizes one answer. One request,
one debit; a request that errors out bills $0. Streaming works the same way —
the answer streams token by token, and the SSE stream carries
`: pareta-progress <stage>` comments (`planning` / `executing` / `answering`)
you can surface as status.

```python
completion = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "…"}],
)
```

Pass a specific endpoint id instead of `"auto"` only when you deliberately
want one pinned model — everything below applies to both.

## Setup

Mint a `pareta_sk_` key in the dashboard, export it, and build the client from the environment:

```bash
export PARETA_API_KEY=pareta_sk_...
```

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()   # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();   // reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
```

`from_env()` is the recommended path. You can also pass the key explicitly: `Pareta(api_key="pareta_sk_...")`. The client is a context manager, so `with Pareta.from_env() as pa:` cleans up the HTTP connection for you.

## A basic completion

Pass an endpoint id as `model` and a non-empty `messages` list in OpenAI format. You get back a `ChatCompletion`.

**Python**

```python
from pareta import Pareta

with Pareta.from_env() as pa:
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

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();
const resp = await pa.chat.completions.create({
  model: "ep_invoice_xtract",   // an endpoint id from endpoints.deploy()
  messages: [
    { role: "system", content: "You extract structured fields from documents." },
    { role: "user", content: "What is the invoice total?\n\nINVOICE\nTotal due: $4,210.00" },
  ],
});

console.log(resp.choices[0].message.content);
console.log(resp.usage.totalTokens, "tokens");
```

Where does the `model` value come from? Three sources, all interchangeable here:

- An endpoint id you deployed. See [Deploying endpoints](deploying-endpoints.md).
- Any id returned by `pa.models.list()` (see [Listing models](#listing-callable-models) below).
- A per-task model alias. The recommended pick for a task is `pa.tasks.recommended(task_id)`; see [Discovering tasks](discovery.md).

`model` and `messages` are both required. The SDK raises `ValueError` before sending if `model` is falsy or `messages` is empty, so a malformed call fails fast without burning a request.

## The ChatCompletion shape

`create()` returns a `ChatCompletion`. The fields mirror OpenAI:

**Python**

```python
resp.id                              # str | None
resp.model                           # str | None: the alias that served the call
resp.created                         # int | None: Unix timestamp
resp.choices                         # list[Choice]
resp.choices[0].index                # int | None
resp.choices[0].finish_reason        # "stop", "length", ...
resp.choices[0].message.role         # "assistant"
resp.choices[0].message.content      # str | None: the generated text
resp.usage.prompt_tokens             # int | None
resp.usage.completion_tokens         # int | None
resp.usage.total_tokens              # int | None
```

**TypeScript**

```typescript
resp.id                              // string | null
resp.model                           // string | null: the alias that served the call
resp.created                         // number | null: Unix timestamp
resp.choices                         // Choice[]
resp.choices[0].index                // number | null
resp.choices[0].finishReason         // "stop", "length", ...
resp.choices[0].message.role         // "assistant"
resp.choices[0].message.content      // string | null: the generated text
resp.usage.promptTokens              // number | null
resp.usage.completionTokens          // number | null
resp.usage.totalTokens               // number | null
```

Every response object keeps the raw server JSON. If a field isn't surfaced as a typed property, reach it with `resp.to_dict()` or `resp["..."]`. Nothing the API returns is lost behind the typed layer.

## Passthrough parameters

Any extra keyword you pass goes straight into the request body, so the full OpenAI parameter set is available without the SDK enumerating it:

**Python**

```python
resp = pa.chat.completions.create(
    model="ep_invoice_xtract",
    messages=[{"role": "user", "content": "Summarize this contract clause: ..."}],
    temperature=0.2,
    max_tokens=512,
    top_p=0.9,
)
```

**TypeScript**

```typescript
const resp = await pa.chat.completions.create({
  model: "ep_invoice_xtract",
  messages: [{ role: "user", content: "Summarize this contract clause: ..." }],
  temperature: 0.2,
  max_tokens: 512,
  top_p: 0.9,
});
```

`temperature`, `max_tokens`, `top_p`, `stop`, `seed`, and friends all pass through unchanged.

## Streaming

Set `stream=True` and `create()` returns an iterator of `ChatCompletionChunk` objects instead of a single `ChatCompletion`. Each chunk carries a `delta` (not a `message`); the incremental text is at `chunk.choices[0].delta.content`.

**Python**

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

**TypeScript**

```typescript
const pa = Pareta.fromEnv();
const stream = pa.chat.completions.create({
  model: "ep_invoice_xtract",
  messages: [{ role: "user", content: "Draft a one-paragraph status update." }],
  stream: true,
});
for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0].delta.content || "");
}
console.log();
```

`ChatCompletionChunk` has the same schema as `ChatCompletion`; it exists as a distinct type only for hinting. Guard `delta.content` with `or ""`: the first and last chunks of a stream often carry role or finish metadata with no text.

The stream is data-only SSE and always terminates on a `[DONE]` sentinel, which the SDK consumes for you, so the iterator simply ends. Note that retries only cover the initial handshake. Once tokens are flowing, a mid-stream drop raises immediately rather than silently resuming.

## Listing callable models

`models.list()` returns the OpenAI-compatible model list: only your deployed, url-bearing endpoints. Use it to discover ids you can pass to `create(model=...)`.

**Python**

```python
with Pareta.from_env() as pa:
    models = pa.models.list()         # ModelList
    print(len(models))                # number of callable endpoints
    for m in models:                  # iterates Model objects
        print(m.id, m.owned_by)       # m.id is usable as chat.completions.create(model=...)
```

**TypeScript**

```typescript
const pa = Pareta.fromEnv();
const models = await pa.models.list();   // ModelList
console.log(models.length);              // number of callable endpoints
for (const m of models) {                // iterates Model objects
  console.log(m.id, m.ownedBy);          // m.id is usable as chat.completions.create({ model })
}
```

`ModelList` is iterable and has a length. Each `Model` exposes `.id` (the callable endpoint id), `.owned_by` (`"pareta"` or a vendor name), and `.created`. This is the inference-time view; to manage endpoint lifecycle (start, stop, metrics) use the [endpoints](deploying-endpoints.md) namespace.

## Async

`AsyncPareta` mirrors the sync client. Methods are `async def`; for streaming you `await` the call once, then `async for` over the chunks.

**Python**

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        # Non-streaming
        resp = await pa.chat.completions.create(
            model="ep_invoice_xtract",
            messages=[{"role": "user", "content": "What is the invoice total?"}],
        )
        print(resp.choices[0].message.content)

        # Streaming
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

**TypeScript**

```typescript
// There is no AsyncPareta in TypeScript — the one Pareta client is already
// Promise-only. Every I/O method returns a Promise you `await`; streaming
// returns an AsyncIterable you drive with `for await`.
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

// Non-streaming
const resp = await pa.chat.completions.create({
  model: "ep_invoice_xtract",
  messages: [{ role: "user", content: "What is the invoice total?" }],
});
console.log(resp.choices[0].message.content);

// Streaming
const stream = pa.chat.completions.create({
  model: "ep_invoice_xtract",
  messages: [{ role: "user", content: "Stream me a haiku about ledgers." }],
  stream: true,
});
for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0].delta.content || "");
}
console.log();
```

## Handling metering and not-ready errors

Two error cases are specific to running inference. Both subclass `ParetaError`, so a single `except ParetaError` is a fine catch-all; the specific classes let you branch.

**Python**

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
        # Balance hit zero. Top up in the dashboard (billing is browser-only);
        # the SDK exposes no balance or payment surface.
        print("Out of credit. Top up in the dashboard, then retry.")
    except EndpointNotReadyError:
        # The endpoint is stopped or cold-starting. Start it and wait for live.
        pa.endpoints.start("ep_invoice_xtract")
        print("Endpoint was not ready; started it, retry shortly.")
```

**TypeScript**

```typescript
import {
  Pareta,
  InsufficientCreditsError,   // 402: org balance empty
  EndpointNotReadyError,      // 503: endpoint stopped / cold / provider down
} from "pareta";

const pa = Pareta.fromEnv();
try {
  const resp = await pa.chat.completions.create({
    model: "ep_invoice_xtract",
    messages: [{ role: "user", content: "Hello" }],
  });
  console.log(resp.choices[0].message.content);
} catch (e) {
  if (e instanceof InsufficientCreditsError) {
    // Balance hit zero. Top up in the dashboard (billing is browser-only);
    // the SDK exposes no balance or payment surface.
    console.log("Out of credit. Top up in the dashboard, then retry.");
  } else if (e instanceof EndpointNotReadyError) {
    // The endpoint is stopped or cold-starting. Start it and wait for live.
    await pa.endpoints.start("ep_invoice_xtract");
    console.log("Endpoint was not ready; started it, retry shortly.");
  } else {
    throw e;
  }
}
```

Transient failures (429 rate limits, 5xx, connection timeouts) are retried automatically with exponential backoff, `max_retries` times (default 2). You only see `RateLimitError` or `APITimeoutError` after retries are exhausted. See [Errors](errors-and-retries.md) for the full hierarchy.

## Using the OpenAI SDK instead

Because the endpoint is OpenAI-compatible, you don't need this SDK to *call* it. Point the `openai` client at Pareta's base URL with your `pareta_sk_` key. Note the `/v1` suffix the OpenAI client expects:

**Python**

```python
from openai import OpenAI

client = OpenAI(api_key="pareta_sk_...", base_url="https://api.pareta.ai/v1")

resp = client.chat.completions.create(
    model="ep_invoice_xtract",
    messages=[{"role": "user", "content": "What is the invoice total?"}],
)
print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
import OpenAI from "openai";

const client = new OpenAI({ apiKey: "pareta_sk_...", baseURL: "https://api.pareta.ai/v1" });

const resp = await client.chat.completions.create({
  model: "ep_invoice_xtract",
  messages: [{ role: "user", content: "What is the invoice total?" }],
});
console.log(resp.choices[0].message.content);
```

Streaming, `temperature`, `max_tokens`, and the rest work exactly as they do against OpenAI. Metering still applies: a zero balance returns a 402, which the `openai` client surfaces as its own status error. Reach for the Pareta SDK when you want the control plane: [deploying endpoints](deploying-endpoints.md), [discovering tasks](discovery.md), and [running evals](evaluation.md).
