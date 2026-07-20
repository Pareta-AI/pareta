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
    Embeddings,
    ModelList,
    Rerank,
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


# ── dropped surfaces (1.0.0: auto-only) ──────────────────────────────────
def test_dropped_commands_are_gone(patch_client):
    """The endpoints group and tasks leaderboard/recommended were REMOVED in
    1.0.0 — invoking them must fail as unknown commands, not run."""
    patch_client(_fake_client())
    for args in (["endpoints", "list"],
                 ["endpoints", "deploy", "--task", "t"],
                 ["tasks", "leaderboard", "t"],
                 ["tasks", "recommended", "t"]):
        result = runner.invoke(cli.app, args)
        assert result.exit_code != 0, f"{args} unexpectedly succeeded"


# ── auto ─────────────────────────────────────────────────────────────────
def test_auto_metrics_renders(patch_client):
    metrics = {"requests_30d": 42, "success_rate_30d": 0.984,
               "billed_micro_usd_30d": 123456,
               "savings_vs_frontier_micro_usd_30d": 6543210,
               "savings_multiple_30d": 53}
    patch_client(_fake_client(auto=_ns(metrics=lambda: metrics)))
    result = runner.invoke(cli.app, ["auto", "metrics"])
    assert result.exit_code == 0
    assert "42" in result.output
    assert "98.4%" in result.output


def test_auto_metrics_json(patch_client):
    metrics = {"requests_30d": 7, "success_rate_30d": 1.0}
    patch_client(_fake_client(auto=_ns(metrics=lambda: metrics)))
    result = runner.invoke(cli.app, ["--json", "auto", "metrics"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["requests_30d"] == 7


def _compare_fakes(captured):
    """Fake client for `auto compare`: one chat call (model:auto) plus one
    frontier comparison call."""
    resp = ChatCompletion({
        "choices": [{"message": {"role": "assistant", "content": "auto answer"}}],
    })
    frontier = {"model": "gpt-5.5", "content": "frontier answer",
                "cost_micro_usd": 1234, "latency_ms": 2100}

    def _create(*, model, messages, **kw):
        captured["chat_model"] = model
        captured["prompt"] = messages[0]["content"]
        return resp

    def _compare_frontier(*, model, messages):
        captured["frontier_model"] = model
        return frontier

    return _fake_client(chat=_ns(completions=_ns(create=_create)),
                        auto=_ns(compare_frontier=_compare_frontier))


def test_auto_compare_renders(patch_client):
    captured = {}
    patch_client(_compare_fakes(captured))
    result = runner.invoke(cli.app, ["auto", "compare", "which is best?",
                                     "--frontier", "gpt-5.5"])
    assert result.exit_code == 0
    assert "auto answer" in result.output
    assert "frontier answer" in result.output
    assert captured["chat_model"] == "auto"
    assert captured["prompt"] == "which is best?"
    assert captured["frontier_model"] == "gpt-5.5"


def test_auto_compare_json(patch_client):
    """Regression: pre-1.0.0 the --json branch referenced a nonexistent
    `state.json_output` / `_print_json` and crashed."""
    captured = {}
    patch_client(_compare_fakes(captured))
    result = runner.invoke(cli.app, ["--json", "auto", "compare", "which is best?"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["auto"]["content"] == "auto answer"
    assert parsed["frontier"]["model"] == "gpt-5.5"


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


# ── rerank ───────────────────────────────────────────────────────────────
def _rerank_fake(captured):
    """Fake for the callable `client.rerank` resource; records its args."""
    ranked = Rerank({"results": [{"index": 2, "relevance_score": 0.931},
                                 {"index": 0, "relevance_score": 0.412}],
                     "pairs": 3})

    def _rerank(query, documents, *, top_n=None):
        captured.update(query=query, documents=list(documents), top_n=top_n)
        return ranked

    return _fake_client(rerank=_rerank)


def test_rerank_renders_table_and_metering(patch_client):
    captured = {}
    patch_client(_rerank_fake(captured))
    result = runner.invoke(cli.app, ["rerank", "governing law",
                                     "doc alpha", "doc beta", "doc gamma",
                                     "--top-n", "2"])
    assert result.exit_code == 0
    assert "0.931" in result.output
    assert "doc gamma" in result.output  # index 2, ranked first
    assert "3 documents scored (metered per document)" in result.output
    assert captured["query"] == "governing law"
    assert captured["documents"] == ["doc alpha", "doc beta", "doc gamma"]
    assert captured["top_n"] == 2


def test_rerank_json(patch_client):
    captured = {}
    patch_client(_rerank_fake(captured))
    result = runner.invoke(cli.app, ["--json", "rerank", "q", "a", "b", "c"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["results"][0]["index"] == 2
    assert parsed["pairs"] == 3
    assert captured["top_n"] is None


def test_rerank_no_documents_errors_clean(patch_client):
    patch_client(_rerank_fake({}))
    result = runner.invoke(cli.app, ["rerank", "just a query"])
    assert result.exit_code != 0
    assert "error:" in result.output
    assert "Traceback" not in result.output


def test_rerank_reads_documents_from_file(patch_client, tmp_path):
    captured = {}
    patch_client(_rerank_fake(captured))
    docs = tmp_path / "docs.txt"
    docs.write_text("first doc\nsecond doc\n\nthird doc\n", encoding="utf-8")
    result = runner.invoke(cli.app, ["rerank", "q", "--file", str(docs)])
    assert result.exit_code == 0
    assert captured["documents"] == ["first doc", "second doc", "third doc"]


def test_rerank_docs_and_file_both_given_errors_clean(patch_client, tmp_path):
    captured = {}
    patch_client(_rerank_fake(captured))
    docs = tmp_path / "docs.txt"
    docs.write_text("from file\n", encoding="utf-8")
    result = runner.invoke(cli.app, ["rerank", "q", "positional doc", "--file", str(docs)])
    assert result.exit_code == 2
    assert "error:" in result.output
    assert "Traceback" not in result.output
    assert "query" not in captured  # no metered call was made


def test_rerank_missing_file_errors_clean(patch_client, tmp_path):
    patch_client(_rerank_fake({}))
    result = runner.invoke(cli.app, ["rerank", "q", "--file", str(tmp_path / "nope.txt")])
    assert result.exit_code == 2
    assert "error:" in result.output
    assert "Traceback" not in result.output


# ── embed ────────────────────────────────────────────────────────────────
def _embed_fake(captured, n=2, dim=4):
    """Fake for the callable `client.embeddings` resource; records its args."""
    emb = Embeddings({"object": "list",
                      "data": [{"object": "embedding", "index": i,
                                "embedding": [0.5] * dim} for i in range(n)],
                      "usage": {"prompt_tokens": 42, "total_tokens": 42}})

    def _embeddings(input, *, input_type=None):
        captured.update(input=list(input), input_type=input_type)
        return emb

    return _fake_client(embeddings=_embeddings)


def test_embed_renders_table_and_metering(patch_client):
    captured = {}
    patch_client(_embed_fake(captured))
    result = runner.invoke(cli.app, ["embed", "alpha text", "beta", "--type", "query"])
    assert result.exit_code == 0
    assert "4" in result.output  # vector dim
    assert "2 texts, 42 prompt tokens (metered per input token)" in result.output
    # Vectors never reach the table.
    assert "0.5" not in result.output
    assert captured["input"] == ["alpha text", "beta"]
    assert captured["input_type"] == "query"


def test_embed_file_and_out_writes_jsonl(patch_client, tmp_path):
    captured = {}
    patch_client(_embed_fake(captured))
    src = tmp_path / "texts.txt"
    src.write_text("line one\nline two\n", encoding="utf-8")
    dest = tmp_path / "vecs.jsonl"
    result = runner.invoke(cli.app, ["embed", "--file", str(src), "--out", str(dest)])
    assert result.exit_code == 0
    assert captured["input"] == ["line one", "line two"]
    assert captured["input_type"] == "document"  # the default side
    rows = [json.loads(ln) for ln in dest.read_text(encoding="utf-8").splitlines()]
    assert [r["index"] for r in rows] == [0, 1]
    assert rows[0]["vector"] == [0.5] * 4


def test_embed_json(patch_client):
    captured = {}
    patch_client(_embed_fake(captured))
    result = runner.invoke(cli.app, ["--json", "embed", "some text"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["usage"]["prompt_tokens"] == 42
    assert len(parsed["data"]) == 2


def test_embed_no_texts_errors_clean(patch_client):
    patch_client(_embed_fake({}))
    result = runner.invoke(cli.app, ["embed"])
    assert result.exit_code != 0
    assert "error:" in result.output
    assert "Traceback" not in result.output


def test_embed_texts_and_file_both_given_errors_clean(patch_client, tmp_path):
    captured = {}
    patch_client(_embed_fake(captured))
    src = tmp_path / "texts.txt"
    src.write_text("from file\n", encoding="utf-8")
    result = runner.invoke(cli.app, ["embed", "positional", "--file", str(src)])
    assert result.exit_code == 2
    assert "error:" in result.output
    assert "Traceback" not in result.output
    assert "input" not in captured  # no metered call was made


def test_embed_bad_type_errors_clean(patch_client):
    captured = {}
    patch_client(_embed_fake(captured))
    result = runner.invoke(cli.app, ["embed", "text", "--type", "passage"])
    assert result.exit_code == 2
    assert "error:" in result.output
    assert "Traceback" not in result.output
    assert "input" not in captured  # rejected before the metered call


def test_embed_unwritable_out_errors_clean(patch_client, tmp_path):
    patch_client(_embed_fake({}))
    dest = tmp_path / "no-such-dir" / "vecs.jsonl"
    result = runner.invoke(cli.app, ["embed", "text", "--out", str(dest)])
    assert result.exit_code == 2
    assert "error:" in result.output
    assert "Traceback" not in result.output


def test_image_edit_missing_file_fails_locally():
    """A typo'd reference path must fail with a clear LOCAL error (exit 2),
    never fall through the SDK's path-or-base64 handling into a network
    round-trip that ends in an opaque server 400."""
    result = runner.invoke(cli.app, ["image-edit", "/no/such/ref.png", "make it blue"])
    assert result.exit_code == 2
    assert "no such image file" in result.output
