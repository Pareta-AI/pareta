"""client.auto — the routing brain's surrounding surfaces (metrics + the
metered frontier comparison). Calling the brain itself is plain chat with
model="auto" (covered by the chat tests' passthrough)."""

import json

import pytest

from conftest import sync_client, async_client, json_response

METRICS = {
    "requests_30d": 42, "requests_today": 3, "success_rate_30d": 0.99,
    "billed_micro_usd_30d": 12_500, "billed_micro_usd_today": 900,
    "savings_vs_frontier_micro_usd_30d": 88_000, "savings_multiple_30d": 5.5,
    "performance_hourly_7d": [], "days_30d": [], "last_request": None,
    "cost_to_serve_micro_usd_30d": 15_000,
}


def test_auto_metrics():
    def handler(request):
        assert request.url.path == "/v1/auto/metrics"
        assert request.method == "GET"
        return json_response(200, METRICS)

    pa = sync_client(handler)
    m = pa.auto.metrics()
    assert m["requests_30d"] == 42
    assert m["savings_multiple_30d"] == 5.5


def test_compare_frontier_posts_model_and_messages():
    def handler(request):
        assert request.url.path == "/v1/playground/frontier"
        body = json.loads(request.content)
        assert body["model"] == "gpt-5.5"
        assert body["messages"][0]["content"] == "hello"
        return json_response(200, {"model": "gpt-5.5", "content": "hi",
                                   "cost_micro_usd": 450, "latency_ms": 900})

    pa = sync_client(handler)
    out = pa.auto.compare_frontier(
        model="gpt-5.5", messages=[{"role": "user", "content": "hello"}])
    assert out["content"] == "hi"
    assert out["cost_micro_usd"] == 450


@pytest.mark.anyio
async def test_auto_metrics_async():
    def handler(request):
        return json_response(200, METRICS)

    pa = async_client(handler)
    m = await pa.auto.metrics()
    assert m["requests_30d"] == 42


@pytest.fixture
def anyio_backend():
    return "asyncio"
