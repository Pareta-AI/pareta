"""Audio capabilities: transcribe speech, and synthesize speech from text.

Pareta's Speech lanes are the `asr` (speech-to-text) and `tts` (text-to-speech)
capabilities. Unlike chat-style capabilities they are NOT deployed as endpoints
and NOT called through chat.completions — they have a dedicated typed namespace,
`pa.audio`:

  pa.audio.transcriptions(audio, language=?)  -> Transcription(text, language, duration_s)
  pa.audio.speech(text, voice=?)              -> Speech(audio, sample_rate, duration_s, format)

`transcriptions` accepts a file path, raw bytes, or a base64 string and
base64-encodes it for you. `speech` returns a typed `Speech` whose `.audio` is
the decoded bytes; `.save(path)` writes a .wav.

Both are metered PER MINUTE of audio (input duration for ASR, output duration
for TTS) and debited against your org balance; a zero balance raises
InsufficientCreditsError (402).

These go through the client's transport, so auth, retries, and typed error
mapping all apply.

Run:
  export PARETA_API_KEY=pareta_sk_...
  python audio-transcribe-and-speak.py path/to/clip.wav
"""

from __future__ import annotations

import sys

from pareta import Pareta


def main() -> None:
    pa = Pareta.from_env()  # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)

    # --- Speech-to-text -------------------------------------------------------
    if len(sys.argv) > 1:
        audio_path = sys.argv[1]
        print(f"Transcribing {audio_path} ...")
        # Pass a path (read+encoded for you), bytes, or a base64 string. The
        # optional `language` is an ISO hint; omit to auto-detect across 50+
        # languages.
        result = pa.audio.transcriptions(audio_path)
        print(f"language  : {result.language}")
        print(f"duration  : {result.duration_s}s  (metered per minute)")
        print(f"transcript: {result.text}")
    else:
        print("(skipping transcription — pass an audio file path to transcribe)")

    # --- Text-to-speech -------------------------------------------------------
    print("\nSynthesizing speech ...")
    speech = pa.audio.speech(
        "Pareta makes it easy to deploy open models and pay only for what you use.",
        # voice="af_heart",   # optional; omit for the default (Kokoro) voice
    )
    speech.save("speech.wav")
    print(
        f"wrote speech.wav  "
        f"(format={speech.format}, sample_rate={speech.sample_rate}, "
        f"duration={speech.duration_s}s — metered per minute of output audio)"
    )


if __name__ == "__main__":
    main()
