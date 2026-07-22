"""Hermetic tests for the Pareta MCP server.

No network and no real `mcp` round-trip: we monkeypatch
`pareta.mcp_server._client` to hand each tool a fake client, then call the tool
functions directly (FastMCP's `@tool()` returns the function unchanged, so the
module-level names stay callable). We also assert the server registers the
expected tool surface via `await mcp.list_tools()`.
"""

from __future__ import annotations

import pytest

mcp_server = pytest.importorskip(
    "pareta.mcp_server",
    reason="the `mcp` package (pareta[mcp]) is not installed",
)

import pareta


# ── fakes ───────────────────────────────────────────────────────────────────
class _Obj:
    """Stand-in for an SDK response object: carries a dict and a `.to_dict()`."""

    def __init__(self, raw: dict):
        self._raw = raw

    def to_dict(self) -> dict:
        return self._raw


class _Choice:
    def __init__(self, content: str):
        self.message = _Obj({"role": "assistant", "content": content})
        self.message.content = content  # mirror the SDK's attribute access


class _Completion:
    def __init__(self, text: str, *, billed=None, frontier=None, savings=None):
        self.choices = [_Choice(text)]
        self.model = "ep_fake"
        self.usage = _Obj({"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8})
        # #164 receipt fields the SDK's ChatCompletion exposes.
        self.billed_micro_usd = billed
        self.frontier_would_have_cost_micro_usd = frontier
        self.savings_factor = savings


class _FakeTasks:
    def __init__(self, *, match=None, raise_exc=None):
        self._match = match or {"type": "task", "chosen": {"task_id": "invoice-extraction"}}
        self._raise = raise_exc

    def match(self, query, *, top_k=5):
        if self._raise:
            raise self._raise
        return _Obj({**self._match, "query": query, "top_k": top_k})

    def list(self):
        return [_Obj({"id": "invoice-extraction"}), _Obj({"id": "text-to-sql"})]


class _FakeCompletions:
    def __init__(self, *, billed=None, frontier=None, savings=None):
        self._cost = dict(billed=billed, frontier=frontier, savings=savings)
        self.last_messages = None

    def create(self, *, model, messages, **kwargs):
        self.last_messages = messages
        return _Completion("hello from " + model, **self._cost)


class _FakeChat:
    def __init__(self, completions=None):
        self.completions = completions or _FakeCompletions()


class _FakeClient:
    def __init__(self, *, tasks=None, chat=None):
        self.tasks = tasks or _FakeTasks()
        self.chat = chat or _FakeChat()


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(mcp_server, "_client", lambda: client)


# ── server / registration ───────────────────────────────────────────────────
def test_server_object_exists():
    from mcp.server.fastmcp import FastMCP

    assert isinstance(mcp_server.mcp, FastMCP)
    assert callable(mcp_server.main)


@pytest.mark.asyncio
async def test_registers_expected_tools():
    tools = await mcp_server.mcp.list_tools()
    names = {t.name for t in tools}
    # RULE: register an MCP tool in mcp_server.py and add it to THIS set in the
    # SAME commit. The SDK CI job runs on every push (no path filter), so a tool
    # that lands ahead of its pin reds main for anyone — see sdk/CLAUDE.md.
    expected = {
        # discovery
        "match_task", "list_tasks", "get_task", "list_models",
        # eval
        "propose_contract", "run_eval", "get_eval_run",
        # inference + auto
        "chat", "auto_metrics", "compare_frontier",
        # audio
        "transcribe", "speak",
        # retrieval
        "rerank", "embed",
        # images
        "generate_image", "edit_image",
    }
    assert names == expected, (
        f"missing: {expected - names}; unexpected: {names - expected}")
    # every registered tool carries a non-empty description (the agent reads it)
    assert all(t.description for t in tools)


@pytest.mark.asyncio
async def test_dropped_tools_are_gone():
    """1.0.0 removed the leaderboard/recommended discovery tools and the whole
    endpoint provisioning surface — none may register."""
    tools = await mcp_server.mcp.list_tools()
    names = {t.name for t in tools}
    dropped = {
        "get_leaderboard", "recommended_model",
        "deploy_endpoint", "list_endpoints", "get_endpoint", "start_endpoint",
        "stop_endpoint", "delete_endpoint", "endpoint_metrics", "endpoint_cost",
    }
    assert not (dropped & names), f"dropped tools still registered: {dropped & names}"


# ── representative tool bodies ───────────────────────────────────────────────
def test_match_task_returns_dict(monkeypatch):
    _patch_client(monkeypatch, _FakeClient())
    out = mcp_server.match_task("extract invoice fields", top_k=3)
    assert out["type"] == "task"
    assert out["chosen"]["task_id"] == "invoice-extraction"
    assert out["query"] == "extract invoice fields"
    assert out["top_k"] == 3


def test_chat_returns_assistant_text(monkeypatch):
    _patch_client(monkeypatch, _FakeClient())
    out = mcp_server.chat(model="ep_1", prompt="hi")
    assert out["text"] == "hello from ep_1"
    assert out["model"] == "ep_fake"
    assert out["usage"]["total_tokens"] == 8
    # no cost keys when the completion carries no receipt — and no crash
    assert "billed_micro_usd" not in out


def test_chat_returns_cost_receipt_and_savings(monkeypatch):
    comp = _FakeCompletions(billed=700, frontier=12000, savings=17.1)
    _patch_client(monkeypatch, _FakeClient(chat=_FakeChat(comp)))
    out = mcp_server.chat(prompt="hi")
    assert out["billed_micro_usd"] == 700
    assert out["billed_usd"] == round(700 / 1_000_000, 6)
    assert out["frontier_would_have_cost_micro_usd"] == 12000
    assert out["savings_vs_frontier_x"] == 17.1


def test_chat_with_images_builds_multimodal_message(monkeypatch, tmp_path):
    comp = _FakeCompletions()
    _patch_client(monkeypatch, _FakeClient(chat=_FakeChat(comp)))
    img = tmp_path / "receipt.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfakebytes")
    mcp_server.chat(prompt="extract the total", image_paths=[str(img)])
    content = comp.last_messages[0]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "extract the total"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_chat_bad_image_path_returns_clean_error(monkeypatch):
    _patch_client(monkeypatch, _FakeClient())
    out = mcp_server.chat(prompt="x", image_paths=["/nope/does-not-exist.png"])
    assert "error" in out and "could not read image" in out["error"]


def test_chat_text_only_content_stays_a_string(monkeypatch):
    comp = _FakeCompletions()
    _patch_client(monkeypatch, _FakeClient(chat=_FakeChat(comp)))
    mcp_server.chat(prompt="just text")
    assert comp.last_messages[0]["content"] == "just text"


# ── error handling: ParetaError is surfaced, never raised ────────────────────
def test_pareta_error_is_caught_as_error_dict(monkeypatch):
    boom = pareta.NotFoundError("no such task", status_code=404)
    _patch_client(monkeypatch, _FakeClient(tasks=_FakeTasks(raise_exc=boom)))
    out = mcp_server.match_task("nonsense")
    assert out["error"] == "no such task"
    assert out["type"] == "NotFoundError"


def test_missing_api_key_surfaces_as_error_not_crash(monkeypatch):
    # _client() raises ParetaError when PARETA_API_KEY is absent; the guard must
    # turn that into an error dict rather than letting the tool raise.
    monkeypatch.setattr(mcp_server, "_cached_client", None)

    def _boom():
        raise pareta.ParetaError("missing API key")

    monkeypatch.setattr(mcp_server, "_client", _boom)
    out = mcp_server.list_tasks()
    assert out["error"] == "missing API key"
    assert out["type"] == "ParetaError"
