# audio

`client.audio` is the Speech surface: turn recorded audio into text, and turn
text into spoken audio. It exposes the two general **capability lanes** that are
not chat — `asr` (speech-to-text) and `tts` (text-to-speech) — as two methods:

- [`audio.transcriptions`](#audiotranscriptions): transcribe an audio clip to text (ASR).
- [`audio.speech`](#audiospeech): synthesize speech from text and save it to a file (TTS).

Two facts set this namespace apart from the rest of the SDK:

- **No endpoint, no `chat.completions`.** Unlike the chat-style capabilities,
  Speech is not something you deploy. There is no endpoint id to manage and no
  `chat.completions.create` call — `audio.transcriptions(...)` and
  `audio.speech(...)` hit their own dedicated routes directly. You never pick a
  voice model, a GPU, or a quantization; Pareta resolves the serving model behind
  the lane.
- **Metered per minute of audio.** Both lanes are metered against your org
  balance by **audio duration** — input length for transcription, output length
  for synthesis — not by tokens. An empty balance raises
  [`InsufficientCreditsError`](exceptions.md) (402). Top-up is browser-only; the
  SDK exposes neither balance nor payment methods.

Both calls go through the client's transport, so auth, retries, and typed error
mapping apply exactly as they do everywhere else.

All examples use the synchronous `Pareta` client. Every method has an `async`
twin with the same signature on `AsyncPareta`; see [Async](#async).

```python
from pareta import Pareta

pa = Pareta.from_env()   # reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

---

## audio.transcriptions

```python
def transcriptions(self, audio, *, language: str | None = None) -> Transcription
```

**Route:** `POST /v1/audio/transcriptions`

Speech-to-text (the `asr` lane). Hands your audio to Pareta, returns the
transcript plus the detected language and the metered duration.

- `audio` (required): the clip to transcribe, in any of three forms — a **path**
  (`str` / `os.PathLike`) to an audio file, raw audio **bytes**, or an already
  **base64**-encoded string. A path or bytes are read and base64-encoded for you;
  a string that does not name a file is assumed to be base64 and passed through.
  An empty base64 string raises `ValueError`; anything that is not a path, bytes,
  or string raises `TypeError`.
- `language` (optional): an ISO language hint (e.g. `"en"`, `"es"`). Omit it to
  auto-detect across the supported languages.

Metered per minute of **input** audio.

```python
result = pa.audio.transcriptions("meeting-clip.wav")

print(result.text)          # the transcript
print(result.language)      # detected (or the hint you passed)
print(result.duration_s)    # input length that was metered (per minute)
```

`audio=` is flexible about where the bytes come from — a path, an in-memory
buffer, or a pre-encoded string all work — and `language` is a hint, not a
requirement:

```python
# Raw bytes (e.g. from a recorder or an upload), with a language hint.
with open("call.ogg", "rb") as f:
    result = pa.audio.transcriptions(f.read(), language="en")

# A Transcription stringifies to its transcript.
print(str(result))          # same as result.text (empty string if None)
```

Returns a [`Transcription`](#transcription).

---

## audio.speech

```python
def speech(self, text: str, *, voice: str | None = None) -> Speech
```

**Route:** `POST /v1/audio/speech`

Text-to-speech (the `tts` lane). Synthesizes spoken audio from text and returns a
[`Speech`](#speech) whose `.audio` is the decoded bytes — call `.save(path)` to
write a file.

- `text` (required): the text to speak. Empty or whitespace-only text raises
  `ValueError` before any request goes out.
- `voice` (optional): a voice id. Omit it for the default (Kokoro) voice.

Metered per minute of **output** audio.

```python
speech = pa.audio.speech("Pareta makes open models easy to deploy.")
speech.save("out.wav")

print(speech.format)        # container/codec, e.g. "wav"
print(speech.sample_rate)   # Hz
print(speech.duration_s)    # output length that was metered (per minute)
```

`.save()` returns the same `Speech`, so you can chain it; pick a voice with
`voice=`:

```python
audio_bytes = pa.audio.speech(
    "Your contract has been processed.",
    voice="af_heart",
).save("notice.wav").audio       # write the file and keep the bytes
```

Returns a [`Speech`](#speech).

---

## Async

Every method above has an `async` twin on `AsyncPareta` with an identical
signature; the methods are coroutines. `Speech.save(...)` is a local file write,
not a network call, so it is the same on both clients.

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        result = await pa.audio.transcriptions("clip.wav", language="en")
        print(result.text, result.duration_s)

        speech = await pa.audio.speech("Hello from Pareta.")
        speech.save("hello.wav")
        print(speech.format, speech.sample_rate)

asyncio.run(main())
```

---

## Response objects

Every object keeps the raw server JSON: call `.to_dict()` for lossless access to
anything not yet surfaced as a typed field, and index it dict-style
(`result["..."]`) as an escape hatch.

### Transcription

From `audio.transcriptions`. Stringifies to `.text` (or `""` when absent).

| Field | Type | Notes |
| --- | --- | --- |
| `text` | `str \| None` | The transcript |
| `language` | `str \| None` | Detected language, or the hint you passed |
| `duration_s` | `float \| None` | Input audio length that was metered (per minute) |

### Speech

From `audio.speech`.

| Field | Type | Notes |
| --- | --- | --- |
| `audio` | `bytes` | The synthesized audio, base64-decoded to raw bytes (`b""` if empty) |
| `audio_base64` | `str \| None` | The raw base64 payload as returned by the server |
| `sample_rate` | `int \| None` | Sample rate in Hz |
| `duration_s` | `float \| None` | Output audio length that was metered (per minute) |
| `format` | `str \| None` | Container/codec of the returned audio, e.g. `"wav"` |

`Speech` also has one method:

| Method | Returns | Notes |
| --- | --- | --- |
| `save(path)` | `Speech` | Write the decoded `.audio` bytes to `path` (`str` / `os.PathLike`); returns `self` for chaining |

## See also

- [`tasks`](./tasks.md): `tasks.match(...)` routes a free-text job to a
  capability lane (including `speech-to-text` / `text-to-speech`) when no
  benchmarked task fits.
- [`chat`](./chat.md): the OpenAI-compatible inference surface for the chat-style
  capabilities, metered the same way.
- [`endpoints`](./endpoints.md): deploy and operate the chat-style models — Speech
  needs none of this.
- [Errors and metering](exceptions.md): `InsufficientCreditsError`, the per-minute
  metering, and the full exception hierarchy.
