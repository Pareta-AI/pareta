"""Hermetic CLI tests.

We never touch the network: `pareta.cli._client` is monkeypatched to return a
fake client whose resource namespaces yield canned SDK model objects. The one
exception is the missing-key path, which exercises the real `_client()` with
PARETA_API_KEY unset so we prove the clean (no-traceback) exit.
"""

import json
import types

import pytest
from typer.testing import CliRunner

import pareta
from pareta import (
    ChatCompletion,
    Endpoint,
    ModelList,
    Task,
    TaskMatch,
    Transcription,
    Speech,
)
from pareta import cli

runner = CliRunner()


# ── fake client plumbing ─────────────────────────────────────────────────
def _ns(**attrs):
    """A simple attribute bag standing in for a resource namespace."""
    return types.SimpleNamespace(**attrs)


def _fake_client(**namespaces):
    """Build a fake `Pareta` with the given resource namespaces, then patch
    `cli._client` to return it. Returns the fake so a test can assert on it."""
    return types.SimpleNamespace(**namespaces)


@pytest.fixture
def patch_client(monkeypatch):
    """Yields a setter that installs a fake client for the duration of a test."""
    def _install(fake):
        monkeypatch.setattr(cli, "_client", lambda: fake)
        return fake
    return _install


# ── version + missing key ────────────────────────────────────────────────
def test_version_prints_sdk_version():
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0
    assert pareta.__version__ in result.stdout


def test_missing_api_key_exits_nonzero_with_message(monkeypatch):
    monkeypatch.delenv("PARETA_API_KEY", raising=False)
    monkeypatch.delenv("PARETA_BASE_URL", raising=False)
    result = runner.invoke(cli.app, ["tasks", "list"])
    assert result.exit_code != 0
    # A clean message, not a traceback.
    assert "error:" in result.output
    assert "API key" in result.output
    assert "Traceback" not in result.output


# ── tasks ────────────────────────────────────────────────────────────────
def test_tasks_list_renders(patch_client):
    tasks = [
        Task({"id": "contract-kie", "default_scorer": "macro_joint_f1", "has_blob_input": True}),
        Task({"id": "text-to-sql", "default_scorer": "execution_accuracy"}),
    ]
    patch_client(_fake_client(tasks=_ns(list=lambda: tasks)))
    result = runner.invoke(cli.app, ["tasks", "list"])
    assert result.exit_code == 0
    assert "contract-kie" in result.output
    assert "text-to-sql" in result.output


def test_tasks_match_renders(patch_client):
    match = TaskMatch({
        "query": "pull fields from contracts",
        "type": "task",
        "confidence": "high",
        "chosen": {"task_id": "contract-kie", "score": 0.92},
        "reasoning": "intent is contract field extraction",
    })
    captured = {}

    def _match(query, *, top_k=5):
        captured["query"] = query
        captured["top_k"] = top_k
        return match

    patch_client(_fake_client(tasks=_ns(match=_match)))
    result = runner.invoke(cli.app, ["tasks", "match", "pull fields from contracts", "--top-k", "3"])
    assert result.exit_code == 0
    assert "contract-kie" in result.output
    assert captured["query"] == "pull fields from contracts"
    assert captured["top_k"] == 3


# ── models ───────────────────────────────────────────────────────────────
def test_models_list_renders(patch_client):
    models = ModelList({"object": "list", "data": [
        {"id": "ep_abc", "owned_by": "pareta", "created": 1},
    ]})
    patch_client(_fake_client(models=_ns(list=lambda: models)))
    result = runner.invoke(cli.app, ["models", "list"])
    assert result.exit_code == 0
    assert "ep_abc" in result.output


# ── endpoints ────────────────────────────────────────────────────────────
def test_endpoints_list_renders(patch_client):
    endpoints = [
        Endpoint({"id": "ep_abc", "status": "live", "taskName": "contract-kie", "model": "contract-1"}),
        Endpoint({"id": "ep_def", "status": "stopped", "taskName": "text-to-sql", "model": "sql-1"}),
    ]
    patch_client(_fake_client(endpoints=_ns(list=lambda: endpoints)))
    result = runner.invoke(cli.app, ["endpoints", "list"])
    assert result.exit_code == 0
    assert "ep_abc" in result.output
    assert "live" in result.output


def test_endpoints_delete_aborts_without_confirmation(patch_client):
    deleted = {"called": False}

    def _delete(endpoint_id):
        deleted["called"] = True

    patch_client(_fake_client(endpoints=_ns(delete=_delete)))
    # Answer the confirm prompt with "n" → abort, nothing deleted.
    result = runner.invoke(cli.app, ["endpoints", "delete", "ep_abc"], input="n\n")
    assert result.exit_code != 0
    assert deleted["called"] is False


def test_endpoints_delete_with_yes(patch_client):
    deleted = {"id": None}

    def _delete(endpoint_id):
        deleted["id"] = endpoint_id

    patch_client(_fake_client(endpoints=_ns(delete=_delete)))
    result = runner.invoke(cli.app, ["endpoints", "delete", "ep_abc", "--yes"])
    assert result.exit_code == 0
    assert deleted["id"] == "ep_abc"


# ── chat ─────────────────────────────────────────────────────────────────
def test_chat_non_stream_prints_message(patch_client):
    resp = ChatCompletion({
        "id": "cmpl_1", "model": "ep_abc",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": "hello there"}}],
    })
    captured = {}

    def _create(*, model, messages, stream=False, **kw):
        captured["model"] = model
        captured["messages"] = messages
        captured["stream"] = stream
        return resp

    completions = _ns(create=_create)
    patch_client(_fake_client(chat=_ns(completions=completions)))
    result = runner.invoke(cli.app, ["chat", "hi", "--model", "ep_abc"])
    assert result.exit_code == 0
    assert "hello there" in result.output
    assert captured["model"] == "ep_abc"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["stream"] is False


def test_chat_reads_prompt_from_stdin(patch_client):
    resp = ChatCompletion({
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
    })

    def _create(*, model, messages, stream=False, **kw):
        # the stdin text must reach the user message
        assert messages[0]["content"].strip() == "from stdin"
        return resp

    patch_client(_fake_client(chat=_ns(completions=_ns(create=_create))))
    result = runner.invoke(cli.app, ["chat", "--model", "ep_abc"], input="from stdin")
    assert result.exit_code == 0
    assert "ok" in result.output


# ── json mode ────────────────────────────────────────────────────────────
def test_json_flag_produces_valid_json(patch_client):
    models = ModelList({"object": "list", "data": [{"id": "ep_abc", "owned_by": "pareta"}]})
    patch_client(_fake_client(models=_ns(list=lambda: models)))
    result = runner.invoke(cli.app, ["--json", "models", "list"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["data"][0]["id"] == "ep_abc"


def test_json_flag_on_tasks_list_is_array(patch_client):
    tasks = [Task({"id": "contract-kie", "default_scorer": "macro_joint_f1"})]
    patch_client(_fake_client(tasks=_ns(list=lambda: tasks)))
    result = runner.invoke(cli.app, ["--json", "tasks", "list"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert isinstance(parsed, list)
    assert parsed[0]["id"] == "contract-kie"


# ── api error → clean non-zero exit ──────────────────────────────────────
def test_api_error_exits_clean(patch_client):
    def _boom():
        raise pareta.NotFoundError("no such task", status_code=404)

    patch_client(_fake_client(tasks=_ns(list=_boom)))
    result = runner.invoke(cli.app, ["tasks", "list"])
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "no such task" in result.output
    assert "Traceback" not in result.output


def test_auth_error_exits_code_2(patch_client):
    def _boom():
        raise pareta.AuthenticationError("invalid API key", status_code=401)

    patch_client(_fake_client(models=_ns(list=_boom)))
    result = runner.invoke(cli.app, ["models", "list"])
    assert result.exit_code == 2


# ── audio ────────────────────────────────────────────────────────────────
def test_audio_transcribe_prints_text(patch_client):
    tr = Transcription({"text": "the transcript", "language": "en", "duration_s": 1.2})
    patch_client(_fake_client(audio=_ns(transcriptions=lambda f, **kw: tr)))
    result = runner.invoke(cli.app, ["audio", "transcribe", "clip.wav"])
    assert result.exit_code == 0
    assert "the transcript" in result.output


def test_audio_speak_writes_file(patch_client, tmp_path):
    import base64

    speech = Speech({"audio_base64": base64.b64encode(b"RIFFwav").decode(), "format": "wav", "duration_s": 0.5})
    patch_client(_fake_client(audio=_ns(speech=lambda text, **kw: speech)))
    out = tmp_path / "out.wav"
    result = runner.invoke(cli.app, ["audio", "speak", "hello", "--out", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    assert out.read_bytes() == b"RIFFwav"
