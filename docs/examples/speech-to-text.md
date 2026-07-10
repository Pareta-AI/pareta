# Speech to text

Turn a recorded audio clip into text with `pa.audio.transcriptions(...)`. One
call sends the clip to `POST /v1/audio/transcriptions` and returns the
transcript, the detected language, and the audio duration that was metered.

Speech has its own route because audio bytes do not fit the chat message
contract — that is the only reason it is not `chat.completions`. Everything
else works the same way `model="auto"` does for chat: you never pick a serving
model or a GPU; Pareta resolves the ASR lane server-side. Transcription is
metered **per minute of input audio** against your org balance, and an empty
balance raises `InsufficientCreditsError` (402).

## Setup

Install the SDK ([installation guide](../guide/installation.md)), export
`PARETA_API_KEY`, and build the client from the environment:

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

## Transcribe a file

The common case is a file on disk: pass the path and the SDK reads and encodes
it for you. The `Transcription` you get back carries the transcript on
`.text`, the detected language on `.language`, and the input duration on
`.duration_s` (`.durationS` in TypeScript) — that duration is what the
per-minute meter charged.

**Python**

```python
t = pa.audio.transcriptions("meeting-clip.wav")

print(t.text)         # the transcript
print(t.language)     # detected language, e.g. "en"
print(t.duration_s)   # metered input length in seconds
```

**TypeScript**

```typescript
const t = await pa.audio.transcriptions("meeting-clip.wav");

console.log(t.text);        // the transcript
console.log(t.language);    // detected language, e.g. "en"
console.log(t.durationS);   // metered input length in seconds
```

Full runnable example: [python/asr/transcribe.py](https://github.com/Pareta-AI/examples/blob/main/python/asr/transcribe.py) · [typescript/asr/transcribe.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/asr/transcribe.ts)

## Bytes and base64 input

`audio` accepts three forms, so the clip does not have to touch disk first.
Raw bytes fit audio you already hold in memory — an upload body, a microphone
buffer — and a base64 string passes pre-encoded audio (say, off a webhook or a
queue message) through untouched. One casing trap in TypeScript: a plain
string is always treated as a **file path**, so pre-encoded audio must be
wrapped as `{ base64: ... }`; in Python a non-path string is assumed to
already be base64.

**Python**

```python
# 1. path (str or os.PathLike) — read + encoded for you
t = pa.audio.transcriptions("meeting-clip.wav")

# 2. raw bytes — e.g. an upload body already in memory
raw = open("meeting-clip.wav", "rb").read()
t = pa.audio.transcriptions(raw)

# 3. base64 string — passed through untouched
import base64
b64 = base64.b64encode(raw).decode("ascii")
t = pa.audio.transcriptions(b64)
```

**TypeScript**

```typescript
import { readFile } from "node:fs/promises";

// 1. string = FILE PATH — read + encoded for you (Node)
let t = await pa.audio.transcriptions("meeting-clip.wav");

// 2. raw bytes — Uint8Array, ArrayBuffer, or Blob
const raw = await readFile("meeting-clip.wav");   // Buffer (a Uint8Array)
t = await pa.audio.transcriptions(raw);

// 3. pre-encoded base64 — must be wrapped, a bare string means a path
t = await pa.audio.transcriptions({ base64: raw.toString("base64") });
```

Full runnable example: [python/asr/transcribe.py](https://github.com/Pareta-AI/examples/blob/main/python/asr/transcribe.py) · [typescript/asr/transcribe.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/asr/transcribe.ts)

## The language hint

`language` is an optional ISO hint. Omit it and the lane detects the language
from the audio itself — the right default for mixed or unknown sources. Pass
it when you already know the language: on short or noisy clips the hint
removes the one thing detection can get wrong.

**Python**

```python
t = pa.audio.transcriptions("support-call.wav", language="en")
print(t.language)   # "en" — the hint you gave, confirmed back
```

**TypeScript**

```typescript
const t = await pa.audio.transcriptions("support-call.wav", { language: "en" });
console.log(t.language);   // "en" — the hint you gave, confirmed back
```

Full runnable example: [python/asr/transcribe.py](https://github.com/Pareta-AI/examples/blob/main/python/asr/transcribe.py) · [typescript/asr/transcribe.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/asr/transcribe.ts)

## See also

- [The audio reference](../reference/audio.md) — full `transcriptions` / `speech` signatures, response models, and metering details.
- [Text to speech](./text-to-speech.md) — the companion lane; the runnable example's sample clip was synthesized with it.
- [Error handling](../guide/errors-and-retries.md) — the exception hierarchy, including `InsufficientCreditsError` (402).
- Prove it on your own data: [evaluate on your data](./evaluate-on-your-data.md) benchmarks the same lanes on your own recordings, metered against the same org balance.
