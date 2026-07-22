import os

import httpx
import pytest

import pareta
from pareta import Pareta
from conftest import sync_client, json_response, TEST_KEY


def test_missing_api_key_raises():
    with pytest.raises(pareta.ParetaError):
        Pareta(api_key=None)


def test_from_env_reads_key_and_base_url(monkeypatch):
    monkeypatch.setenv("PARETA_API_KEY", "pareta_sk_fromenv")
    monkeypatch.setenv("PARETA_BASE_URL", "https://api-staging.pareta.ai/")
    pa = Pareta.from_env()
    assert pa.api_key == "pareta_sk_fromenv"
    assert pa.base_url == "https://api-staging.pareta.ai"   # trailing slash stripped


def test_default_base_url_is_prod(monkeypatch):
    monkeypatch.delenv("PARETA_BASE_URL", raising=False)
    pa = Pareta(api_key="pareta_sk_x")
    assert pa.base_url == "https://api.pareta.ai"


def test_auth_header_and_path():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["ua"] = request.headers.get("user-agent")
        seen["path"] = request.url.path
        return json_response(200, {"object": "list", "data": []})

    pa = sync_client(handler)
    pa.models.list()
    assert seen["auth"] == f"Bearer {TEST_KEY}"
    assert seen["ua"].startswith("pareta-python/")
    assert seen["path"] == "/v1/models"


def test_chat_completion_exposes_cost_receipt():
    # #164: the chat proxy returns X-Pareta-Billed + the frontier counterfactual
    # as headers; the SDK surfaces them on the completion.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "c1", "model": "auto",
                  "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                  "usage": {"total_tokens": 10}},
            headers={"X-Pareta-Billed": "700",
                     "X-Pareta-Frontier-Would-Have-Cost": "12000"})

    pa = sync_client(handler)
    c = pa.chat.completions.create(model="auto", messages=[{"role": "user", "content": "hi"}])
    assert c.billed_micro_usd == 700
    assert c.frontier_would_have_cost_micro_usd == 12000
    assert c.savings_factor == round(12000 / 700, 1)


def test_chat_completion_cost_none_when_headers_absent():
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(200, {"choices": [{"message": {"content": "hi"}}]})

    pa = sync_client(handler)
    c = pa.chat.completions.create(model="auto", messages=[{"role": "user", "content": "x"}])
    assert c.billed_micro_usd is None
    assert c.frontier_would_have_cost_micro_usd is None
    assert c.savings_factor is None


def test_context_manager_closes():
    with sync_client(lambda r: json_response(200, {"data": []})) as pa:
        assert pa.models.list() is not None


def test_auto_only_surface_no_endpoints_or_leaderboard():
    """1.0.0 surface lock: the endpoints namespace and the leaderboard/
    recommended discovery methods are REMOVED (not hidden) from both clients,
    and the dropped types are gone from the package exports."""
    pa = Pareta(api_key="pareta_sk_x")
    assert not hasattr(pa, "endpoints")
    assert not hasattr(pa.tasks, "leaderboard")
    assert not hasattr(pa.tasks, "recommended")

    apa = pareta.AsyncPareta(api_key="pareta_sk_x")
    assert not hasattr(apa, "endpoints")
    assert not hasattr(apa.tasks, "leaderboard")
    assert not hasattr(apa.tasks, "recommended")

    for name in ("Endpoint", "Leaderboard", "LeaderboardEntry"):
        assert not hasattr(pareta, name)
        assert name not in pareta.__all__
    assert hasattr(pareta, "FrontierModel")   # evals still returns these
