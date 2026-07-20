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
    def __init__(self, text: str):
        self.choices = [_Choice(text)]
        self.model = "ep_fake"
        self.usage = _Obj({"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8})


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
    def create(self, *, model, messages, **kwargs):
        return _Completion("hello from " + model)


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self, *, tasks=None):
        self.tasks = tasks or _FakeTasks()
        self.chat = _FakeChat()


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
        "run_eval", "get_eval_run",
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
