# Text to speech

Turn a line of text into spoken audio and write it to a `.wav` file — one call
in, one file out. You'll synthesize a short customer notification with
`pa.audio.speech(...)`, save the returned audio, and read back the format,
sample rate, and the duration that was metered.

Speech is text in, audio bytes out — a data shape the chat message contract
can't carry — so it has its own route, `POST /v1/audio/speech`, instead of
`chat.completions`. That is the only reason the route exists: there is no
voice model to name and nothing to deploy. You hand Pareta the text; everything
behind the call is resolved server-side, exactly as `model="auto"` does for chat.

## Setup

Install the SDK and set `PARETA_API_KEY` (see [installation](../guide/installation.md)).

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

## Synthesize a notification

`speech(text)` returns a typed `Speech` whose `.audio` is the synthesized audio
already base64-decoded to raw bytes; `.save(path)` writes them to disk. The
response also carries the container format, the sample rate, and `duration_s` —
the length of the *output* audio, which is the metered unit (billed per minute
of output, not per token).

**Python**

```python
speech = pa.audio.speech(
    "Your appointment is confirmed for Thursday at two PM. "
    "Reply R to reschedule, or call us any time."
)
speech.save("welcome.wav")

print(speech.format)        # container/codec, e.g. "wav"
print(speech.sample_rate)   # Hz
print(speech.duration_s)    # output length in seconds — the metered unit
```

**TypeScript**

```typescript
const speech = await pa.audio.speech(
  "Your appointment is confirmed for Thursday at two PM. " +
    "Reply R to reschedule, or call us any time.",
);
await speech.save("welcome.wav");   // Node only — lazy node:fs under the hood

console.log(speech.format);        // container/codec, e.g. "wav"
console.log(speech.sampleRate);    // Hz
console.log(speech.durationS);     // output length in seconds — the metered unit
```

Empty or whitespace-only text raises locally (`ValueError` in Python, a
`ParetaError` in TypeScript) before any request goes out.

Full runnable example: [python/tts/speak.py](https://github.com/Pareta-AI/examples/blob/main/python/tts/speak.py) · [typescript/tts/speak.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/tts/speak.ts)

## Bytes, voice, and metering

You don't have to touch the filesystem: `.audio` is the decoded bytes, ready
for a response body or an object store, and `.save()` returns the same `Speech`
so writing a file and keeping the bytes chains into one expression. `voice=` is
the one optional knob — a voice id; omit it for the default voice. The call
debits your org balance per minute of output audio; a zero balance raises
`InsufficientCreditsError` (402) and no audio is generated.

**Python**

```python
from pareta import InsufficientCreditsError

try:
    audio_bytes = pa.audio.speech(
        "Your order has shipped and is on its way.",
    ).save("shipped.wav").audio      # write the file and keep the bytes

    print(len(audio_bytes), "bytes")
except InsufficientCreditsError:
    print("Org out of credit — top up in the dashboard, then re-run.")
```

**TypeScript**

```typescript
import { InsufficientCreditsError } from "pareta";

try {
  const s = await pa.audio.speech("Your order has shipped and is on its way.");
  await s.save("shipped.wav");
  const audioBytes = s.audio;       // Uint8Array — the same decoded bytes

  console.log(audioBytes.length, "bytes");
} catch (e) {
  if (e instanceof InsufficientCreditsError) {
    console.log("Org out of credit — top up in the dashboard, then re-run.");
  } else {
    throw e;
  }
}
```

Full runnable example: [python/tts/speak.py](https://github.com/Pareta-AI/examples/blob/main/python/tts/speak.py) · [typescript/tts/speak.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/tts/speak.ts)

## See also

- [audio reference](../reference/audio.md) — the full `pa.audio` surface: `speech` (TTS) and `transcriptions` (ASR), response objects, async twins.
- [Errors and retries](../guide/errors-and-retries.md) — `InsufficientCreditsError` and the full exception hierarchy.
- [Core concepts](../guide/core-concepts.md) — why speech has its own route while everything chat-shaped goes through `model="auto"`.
- Prove it on your own data: [evaluate on your data](./evaluate-on-your-data.md) benchmarks Pareta against frontier baselines on your own examples, metered the same way.
