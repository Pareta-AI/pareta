"""`client.audio` — the Speech capability lanes (ASR + TTS).

Unlike chat-style capabilities these are NOT called through
`chat.completions`; they have dedicated routes:

  POST /v1/audio/transcriptions  {audio_base64, language?} -> {text, language, duration_s}
  POST /v1/audio/speech          {text, voice?}            -> {audio_base64, sample_rate, duration_s, format}

Both are metered PER MINUTE of audio (input duration for ASR, output duration
for TTS) and debited against your org balance; a zero balance returns 402.

    pa.audio.transcriptions("clip.wav").text          # speech → text
    pa.audio.speech("hello there").save("out.wav")    # text → speech file

Calls go through the client's `request()` transport, so auth / retries / typed
error mapping apply — these resources never bypass it.
"""

from __future__ import annotations

import base64
import os
from typing import Union

from .._models import Speech, Transcription

_BASE = "/v1/audio"

# A path (str / os.PathLike), raw audio bytes, or an already-base64 string.
AudioInput = Union[str, "os.PathLike[str]", bytes]


def _to_base64(audio: AudioInput) -> str:
    """Normalize a file path / bytes / base64 string to a base64 ASCII string.

    - bytes              → base64-encoded.
    - str / PathLike that names an existing file → read + base64-encode.
    - any other str      → assumed to already be base64 (passed through).
    """
    if isinstance(audio, bytes):
        return base64.b64encode(audio).decode("ascii")
    if isinstance(audio, os.PathLike) or (isinstance(audio, str) and os.path.isfile(audio)):
        with open(os.fspath(audio), "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    if isinstance(audio, str):
        if not audio.strip():
            raise ValueError("audio is empty")
        return audio  # already base64
    raise TypeError(f"audio must be a path, bytes, or base64 str (got {type(audio).__name__})")


def _transcribe_body(audio: AudioInput, language: str | None) -> dict:
    body: dict[str, object] = {"audio_base64": _to_base64(audio)}
    if language:
        body["language"] = language
    return body


def _speech_body(text: str, voice: str | None) -> dict:
    if not text or not text.strip():
        raise ValueError("text is required")
    body: dict[str, object] = {"text": text}
    if voice:
        body["voice"] = voice
    return body


class Audio:
    def __init__(self, client):
        self._client = client

    def transcriptions(self, audio: AudioInput, *, language: str | None = None) -> Transcription:
        """Speech-to-text (the `asr` lane). `audio` is a file path, raw bytes, or
        a base64 string; `language` is an optional ISO hint (omit to auto-detect).
        Metered per minute of input audio."""
        return self._client.request(
            "POST", f"{_BASE}/transcriptions",
            body=_transcribe_body(audio, language), cast=Transcription)

    def speech(self, text: str, *, voice: str | None = None) -> Speech:
        """Text-to-speech (the `tts` lane). Returns a `Speech` whose `.audio` is
        decoded bytes (use `.save(path)` to write a .wav). `voice` is optional
        (omit for the default Kokoro voice). Metered per minute of output audio."""
        return self._client.request(
            "POST", f"{_BASE}/speech", body=_speech_body(text, voice), cast=Speech)


class AsyncAudio:
    def __init__(self, client):
        self._client = client

    async def transcriptions(self, audio: AudioInput, *, language: str | None = None) -> Transcription:
        return await self._client.request(
            "POST", f"{_BASE}/transcriptions",
            body=_transcribe_body(audio, language), cast=Transcription)

    async def speech(self, text: str, *, voice: str | None = None) -> Speech:
        return await self._client.request(
            "POST", f"{_BASE}/speech", body=_speech_body(text, voice), cast=Speech)
