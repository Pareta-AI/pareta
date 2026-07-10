# Summarization

Turn a raw meeting transcript into a three-sentence executive summary plus an owner — item — due action-items list, with one call to `model="auto"`. The output format lives entirely in the prompt, so the same call summarizes support threads, incident timelines, or research notes by swapping the instructions.

Summarization is a chat/text job, so it goes to the one chat interface — `pa.chat.completions.create(model="auto", ...)`, OpenAI-compatible on the wire. There is no model to pick and nothing to deploy: `"auto"` routes every request server-side, and a successful completion is one debit against your org balance regardless of how it routes internally.

## Setup

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()   # reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();   // reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

See [installation](../guide/installation.md) for getting the SDK and key in place.

## Executive summary + action items

Everything that shapes the output is prompt: a system message that pins the summarizer to the facts, and an instruction block that spells out the exact format — three sentences, then `- owner — item — due date` bullets, with a final bullet for anything explicitly deferred. `temperature=0.2` keeps repeated runs of the same transcript close to each other, and `max_tokens=512` is generous headroom for a one-page meeting.

**Python**

```python
from pathlib import Path

transcript = Path("data/meeting-notes.txt").read_text(encoding="utf-8")

completion = pa.chat.completions.create(
    model="auto",
    messages=[
        {"role": "system", "content": "You summarize meeting transcripts for executives. "
                                      "Be factual; never invent owners, dates, or decisions."},
        {"role": "user", "content": INSTRUCTIONS + "\n" + transcript},
    ],
    temperature=0.2,
    max_tokens=512,
)
print(completion.choices[0].message.content)
print(completion.usage.total_tokens)
```

**TypeScript**

```typescript
import { readFile } from "node:fs/promises";

const transcript = await readFile("data/meeting-notes.txt", "utf8");

const completion = await pa.chat.completions.create({
  model: "auto",
  messages: [
    { role: "system", content: "You summarize meeting transcripts for executives. " +
                               "Be factual; never invent owners, dates, or decisions." },
    { role: "user", content: INSTRUCTIONS + "\n" + transcript },
  ],
  temperature: 0.2,
  max_tokens: 512,
});
console.log(completion.choices[0].message.content);
console.log(completion.usage.totalTokens);
```

A `finish_reason` of `"length"` on the choice means the summary hit `max_tokens` before it finished — raise the cap rather than trusting a truncated action-items list.

Full runnable example: [python/summarization/summarize.py](https://github.com/Pareta-AI/examples/blob/main/python/summarization/summarize.py) · [typescript/summarization/summarize.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/summarization/summarize.ts)

## Stream the summary

For anything a person reads as it generates — a summary panel in your app, a CLI — pass `stream=True` and the same call returns an iterator of chunks instead of one completion. Print `chunk.choices[0].delta.content` as it arrives; the delta is `None` on bookkeeping chunks, so keep the guard. Everything else about the request, including the single debit, is unchanged.

**Python**

```python
stream = pa.chat.completions.create(
    model="auto",
    messages=messages,        # same system + transcript messages as above
    stream=True,
    temperature=0.2,
    max_tokens=512,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
print()
```

**TypeScript**

```typescript
const stream = pa.chat.completions.create({
  model: "auto",
  messages,                   // same system + transcript messages as above
  stream: true,
  temperature: 0.2,
  max_tokens: 512,
});
for await (const chunk of stream) {
  const delta = chunk.choices[0].delta.content;
  if (delta) {
    process.stdout.write(delta);
  }
}
console.log();
```

Chunk anatomy, accumulation, async streaming, and failure behavior are covered in [streaming chat completions](./streaming-chat.md).

Full runnable example: [python/summarization/summarize.py](https://github.com/Pareta-AI/examples/blob/main/python/summarization/summarize.py) · [typescript/summarization/summarize.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/summarization/summarize.ts)

## See also

- [Inference](../guide/inference.md) — the full chat surface: parameters, errors, and the OpenAI-compatible wire format.
- [Streaming chat completions](./streaming-chat.md) — chunks, accumulation, and async streaming in depth.
- [Error handling](../guide/errors-and-retries.md) — `InsufficientCreditsError` (402) and the rest of the exception hierarchy.
- Prove it on your own data: [evaluate summaries from your real transcripts](./evaluate-on-your-data.md), metered against the same org balance.
