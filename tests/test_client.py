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
