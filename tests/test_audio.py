import base64
import json

import pytest

from pareta import Speech, Transcription
from conftest import async_client, json_response, sync_client


# ── transcriptions (speech → text) ──────────────────────────────────────
def test_transcriptions_from_bytes_base64_encodes_and_posts():
    seen = {}
    raw_audio = b"RIFF....fake wav bytes...."

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return json_response(200, {"text": "hello world", "language": "en", "duration_s": 1.5})

    pa = sync_client(handler)
    out = pa.audio.transcriptions(raw_audio, language="en")

    assert isinstance(out, Transcription)
    assert out.text == "hello world"
    assert out.language == "en"
    assert out.duration_s == 1.5
    assert str(out) == "hello world"
    # right route + body shape (bytes were base64-encoded under audio_base64)
    assert seen["path"] == "/v1/audio/transcriptions"
    assert seen["body"]["language"] == "en"
    assert base64.b64decode(seen["body"]["audio_base64"]) == raw_audio


def test_transcriptions_from_file_path(tmp_path):
    seen = {}
    audio = b"\x00\x01\x02 some bytes"
    clip = tmp_path / "clip.wav"
    clip.write_bytes(audio)

    def handler(request):
        seen["body"] = json.loads(request.content)
        return json_response(200, {"text": "from file", "language": "en", "duration_s": 0.4})

    pa = sync_client(handler)
    out = pa.audio.transcriptions(str(clip))
    assert out.text == "from file"
    # file was read + base64-encoded; no language key when omitted
    assert base64.b64decode(seen["body"]["audio_base64"]) == audio
    assert "language" not in seen["body"]


def test_transcriptions_passes_through_base64_string():
    seen = {}
    b64 = base64.b64encode(b"already encoded").decode("ascii")

    def handler(request):
        seen["body"] = json.loads(request.content)
        return json_response(200, {"text": "ok", "language": "en", "duration_s": 0.2})

    pa = sync_client(handler)
    pa.audio.transcriptions(b64)
    # a non-path string is treated as already-base64 and sent verbatim
    assert seen["body"]["audio_base64"] == b64


def test_transcriptions_rejects_bad_input():
    pa = sync_client(lambda r: json_response(200, {}))
    with pytest.raises(ValueError):
        pa.audio.transcriptions("")
    with pytest.raises(TypeError):
        pa.audio.transcriptions(123)  # type: ignore[arg-type]


# ── speech (text → speech) ──────────────────────────────────────────────
def test_speech_decodes_audio_and_reports_metadata():
    seen = {}
    audio_bytes = b"\x52\x49\x46\x46 fake wav payload"
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return json_response(200, {
            "audio_base64": audio_b64, "sample_rate": 24000,
            "duration_s": 2.0, "format": "wav",
        })

    pa = sync_client(handler)
    out = pa.audio.speech("hello there", voice="af_heart")

    assert isinstance(out, Speech)
    assert out.audio == audio_bytes          # decoded from base64
    assert out.audio_base64 == audio_b64
    assert out.sample_rate == 24000
    assert out.duration_s == 2.0
    assert out.format == "wav"
    # right route + body
    assert seen["path"] == "/v1/audio/speech"
    assert seen["body"] == {"text": "hello there", "voice": "af_heart"}


def test_speech_save_writes_decoded_bytes(tmp_path):
    audio_bytes = b"some synthesized audio"
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

    def handler(request):
        # voice omitted → not in body
        assert json.loads(request.content) == {"text": "hi"}
        return json_response(200, {
            "audio_base64": audio_b64, "sample_rate": 24000,
            "duration_s": 0.5, "format": "wav",
        })

    pa = sync_client(handler)
    out = pa.audio.speech("hi")
    dest = tmp_path / "out.wav"
    ret = out.save(dest)
    assert ret is out                        # chainable
    assert dest.read_bytes() == audio_bytes


def test_speech_requires_text():
    pa = sync_client(lambda r: json_response(200, {}))
    with pytest.raises(ValueError):
        pa.audio.speech("   ")


# ── async parity ────────────────────────────────────────────────────────
async def test_async_audio_roundtrip():
    audio_bytes = b"async audio"
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

    def handler(request):
        if request.url.path.endswith("/transcriptions"):
            return json_response(200, {"text": "async text", "language": "en", "duration_s": 1.0})
        return json_response(200, {
            "audio_base64": audio_b64, "sample_rate": 24000,
            "duration_s": 1.0, "format": "wav",
        })

    pa = async_client(handler)
    t = await pa.audio.transcriptions(b"bytes")
    assert t.text == "async text"
    s = await pa.audio.speech("hello")
    assert s.audio == audio_bytes
    await pa.aclose()
