# Streaming chat completions

Stream tokens as the model generates them instead of waiting for the whole
response. Pass `stream=True` to `chat.completions.create(...)` and you get an
iterator of `ChatCompletionChunk` objects, each carrying one incremental piece
of text on `chunk.choices[0].delta.content`. Use this for chat UIs, agent
loops, long generations, and anywhere a first-token-fast experience matters.

Inference on Pareta is OpenAI-compatible, so the streaming shape here is the
same vLLM-style data-only SSE the `openai` SDK consumes. Use `model="auto"` —
the routing brain streams progress while it plans and executes, then the
answer tokens. (A dedicated endpoint id from
[deploying an endpoint](../guide/deploying-endpoints.md) streams the same way.)
Streamed inference is metered against your org balance exactly like a
non-streaming call.

## Quickstart

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()  # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)

stream = pa.chat.completions.create(
    model="auto",             # the routing brain (or a dedicated endpoint id)
    messages=[{"role": "user", "content": "Write a haiku about throughput."}],
    stream=True,
)

for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
print()
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv(); // reads PARETA_API_KEY (+ optional PARETA_BASE_URL)

const stream = pa.chat.completions.create({
  model: "auto",            // the routing brain (or a dedicated endpoint id)
  messages: [{ role: "user", content: "Write a haiku about throughput." }],
  stream: true,
});

for await (const chunk of stream) {
  const delta = chunk.choices[0].delta.content;
  if (delta) {
    process.stdout.write(delta);
  }
}
console.log();
```

`stream=True` changes the return type: instead of a single `ChatCompletion`,
`create(...)` returns an `Iterator[ChatCompletionChunk]`. Nothing is sent until
you start iterating, and the connection stays open for the life of the loop.

## Reading a chunk

A streaming chunk has the same schema as a `ChatCompletion`, but each choice
carries a `delta` (the incremental token) instead of a full `message`:

**Python**

```python
chunk.choices[0].delta.content   # str | None — the new text in this chunk
chunk.choices[0].delta.role      # str | None — usually only set on the first chunk
chunk.choices[0].finish_reason   # str | None — "stop" / "length" on the last chunk
chunk.id                         # str | None
chunk.model                      # str | None
```

**TypeScript**

```typescript
chunk.choices[0].delta.content   // string | null — the new text in this chunk
chunk.choices[0].delta.role      // string | null — usually only set on the first chunk
chunk.choices[0].finishReason    // string | null — "stop" / "length" on the last chunk
chunk.id                         // string | null
chunk.model                      // string | null
```

`delta.content` is `None` on chunks that carry no text (for example the opening
role chunk, or a final chunk that only sets `finish_reason`), so always guard
the `if delta:` check before printing or appending. The stream ends when the
server sends `[DONE]`; the SDK consumes that sentinel and stops the iterator for
you, so a plain `for` loop terminates cleanly.

Need the raw server JSON for a field the typed layer does not surface? Every
response object keeps it: `chunk.to_dict()` returns the untouched payload.

## Accumulating the full text

Collect the deltas into a buffer to reconstruct the complete message:

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()

chunks = pa.chat.completions.create(
    model="auto",
    messages=[
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": "Summarize what an invoice number is."},
    ],
    stream=True,
    temperature=0.2,   # extra OpenAI params pass straight through
    max_tokens=256,
)

parts = []
finish_reason = None
for chunk in chunks:
    choice = chunk.choices[0]
    if choice.delta.content:
        parts.append(choice.delta.content)
    if choice.finish_reason:
        finish_reason = choice.finish_reason

full_text = "".join(parts)
print(full_text)
print("finish_reason:", finish_reason)  # e.g. "stop" or "length"
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

const chunks = pa.chat.completions.create({
  model: "auto",
  messages: [
    { role: "system", content: "You are concise." },
    { role: "user", content: "Summarize what an invoice number is." },
  ],
  stream: true,
  temperature: 0.2, // extra OpenAI params pass straight through
  max_tokens: 256,
});

const parts: string[] = [];
let finishReason: string | null = null;
for await (const chunk of chunks) {
  const choice = chunk.choices[0];
  if (choice.delta.content) {
    parts.push(choice.delta.content);
  }
  if (choice.finishReason) {
    finishReason = choice.finishReason;
  }
}

const fullText = parts.join("");
console.log(fullText);
console.log("finishReason:", finishReason); // e.g. "stop" or "length"
```

A `finish_reason` of `"length"` means the model hit `max_tokens` before it was
done; raise `max_tokens` if you need the full answer.

Note: token usage is not reliably populated on streamed chunks. If you need the
`usage` counts (`prompt_tokens` / `completion_tokens` / `total_tokens`), make
the same call with `stream=False` and read `completion.usage`.

## Extra parameters

Any OpenAI chat parameter you pass as a keyword argument is forwarded verbatim
in the request body: `temperature`, `max_tokens`, `top_p`, `stop`,
`frequency_penalty`, and so on. There is no hardware knob — GPUs, quantization,
and tensor-parallelism are resolved by Pareta when you deploy the endpoint, so
the only model selector here is the endpoint id you pass to `model`.

**Python**

```python
stream = pa.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "List three GPU-free wins."}],
    stream=True,
    top_p=0.9,
    stop=["\n\n"],
)
```

**TypeScript**

```typescript
const stream = pa.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "List three GPU-free wins." }],
  stream: true,
  top_p: 0.9,
  stop: ["\n\n"],
});
```

## Async streaming

`AsyncPareta` mirrors the sync client. `create(...)` is a coroutine, so
`await` it once to get the async iterator, then drive it with `async for`:

**Python**

```python
import asyncio
from pareta import AsyncPareta


async def main():
    async with AsyncPareta.from_env() as pa:
        stream = await pa.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": "Stream me a limerick."}],
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                print(delta, end="", flush=True)
        print()


asyncio.run(main())
```

**TypeScript**

```typescript
// There is no AsyncPareta in TypeScript: the single `Pareta` client is already
// async. `create({ stream: true })` returns an AsyncIterable<ChatCompletionChunk>
// directly — drive it with `for await`, no separate await for the stream handle.
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

const stream = pa.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "Stream me a limerick." }],
  stream: true,
});

for await (const chunk of stream) {
  const delta = chunk.choices[0].delta.content;
  if (delta) {
    process.stdout.write(delta);
  }
}
console.log();
```

The `async with` block calls `aclose()` for you when the block exits, releasing
the HTTP client. The chunk shape is identical to the sync path:
`chunk.choices[0].delta.content` is the incremental text.

## Metering and errors

Streamed inference debits your org balance on success, the same as a
non-streaming completion. Top-ups are browser-only; the SDK does not expose
balance or payment methods. If the balance is empty, the call raises
`InsufficientCreditsError` (HTTP 402) before any tokens flow:

**Python**

```python
from pareta import Pareta
from pareta import InsufficientCreditsError, EndpointNotReadyError

pa = Pareta.from_env()

try:
    stream = pa.chat.completions.create(
        model="auto",
        messages=[{"role": "user", "content": "Hello"}],
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            print(delta, end="", flush=True)
    print()
except InsufficientCreditsError:
    print("Out of credit — top up in the dashboard.")
except EndpointNotReadyError:
    print("Endpoint is cold or stopped — start it and retry.")
```

**TypeScript**

```typescript
import { Pareta, InsufficientCreditsError, EndpointNotReadyError } from "pareta";

const pa = Pareta.fromEnv();

try {
  const stream = pa.chat.completions.create({
    model: "auto",
    messages: [{ role: "user", content: "Hello" }],
    stream: true,
  });
  for await (const chunk of stream) {
    const delta = chunk.choices[0].delta.content;
    if (delta) {
      process.stdout.write(delta);
    }
  }
  console.log();
} catch (e) {
  if (e instanceof InsufficientCreditsError) {
    console.log("Out of credit — top up in the dashboard.");
  } else if (e instanceof EndpointNotReadyError) {
    console.log("Endpoint is cold or stopped — start it and retry.");
  } else {
    throw e;
  }
}
```

A few things to know about how the stream behaves under failure:

- **`model` / `messages` validation is local.** Passing an empty `model` or
  empty `messages` raises `ValueError` immediately, before any network call.
- **Errors surface before the first byte.** Non-2xx responses (402, 401, 404,
  503, and so on) are raised as the matching `ParetaError` subclass when the
  stream starts, not mid-loop. A stopped or cold endpoint raises
  `EndpointNotReadyError` (503).
- **Mid-stream drops are not retried.** Retries cover only the initial
  connect/handshake. Once SSE bytes are flowing, a dropped connection raises
  (`APIConnectionError` / `APITimeoutError`) rather than silently resuming,
  because a partial generation cannot be safely continued. Wrap the loop and
  re-issue the request if you need at-least-once delivery.

See [error handling](../guide/errors-and-retries.md) for the full exception hierarchy.

## Related

- [Deploying an endpoint](../guide/deploying-endpoints.md) — get the `model` id you
  pass here.
- [Listing models](../guide/inference.md) — `models.list()` returns your deployed,
  callable endpoints.
- [Non-streaming completions](../guide/inference.md) — `stream=False` returns a
  single `ChatCompletion` with `usage` populated.
- [Running evals](../guide/evaluation.md) — compare models on your own data, also metered
  against the org balance.
