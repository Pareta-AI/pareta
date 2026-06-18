import json

import httpx
import pytest

from pareta import Leaderboard, FrontierModel, Endpoint
from conftest import sync_client, json_response


# ── tasks.leaderboard / recommended ─────────────────────────────────────
def _leaderboard_handler(request):
    assert request.url.path == "/v1/tasks/invoice-extraction/leaderboard"
    return json_response(200, {
        "task_id": "invoice-extraction", "metric": "F1", "cost_unit": "$/1k invoices",
        "recommended": "qwen-vl-1",
        "frontier": {"name": "claude-opus-4-7", "quality": 0.919, "cost_per_request_micro_usd": 28800},
        "models": [
            {"name": "claude-opus-4-7", "kind": "frontier", "quality": 0.919, "cost_per_request_micro_usd": 28800},
            {"name": "qwen-vl-1", "kind": "open", "quality": 0.926, "cost_per_request_micro_usd": 3800},
        ],
    })


def test_tasks_leaderboard():
    pa = sync_client(_leaderboard_handler)
    lb = pa.tasks.leaderboard("invoice-extraction")
    assert isinstance(lb, Leaderboard)
    assert lb.recommended == "qwen-vl-1"
    assert lb.metric == "F1"
    assert lb.frontier.name == "claude-opus-4-7"
    assert {m.name for m in lb.models} == {"claude-opus-4-7", "qwen-vl-1"}


def test_tasks_recommended():
    pa = sync_client(_leaderboard_handler)
    assert pa.tasks.recommended("invoice-extraction") == "qwen-vl-1"


# ── evals.frontier_models ────────────────────────────────────────────────
def test_frontier_models_roster_and_filter():
    def handler(request):
        assert request.url.path == "/v1/eval/frontier-models"
        task = dict(request.url.params).get("task")
        roster = [
            {"id": "gpt-5.5", "vendor": "openai", "vision": True, "benchmarked": task == "contract-key-fields"},
            {"id": "claude-opus-4-7", "vendor": "anthropic", "vision": True, "benchmarked": False},
        ]
        return json_response(200, {"frontier_models": roster, "task": task})

    pa = sync_client(handler)
    roster = pa.evals.frontier_models()
    assert all(isinstance(m, FrontierModel) for m in roster)
    assert {m.id for m in roster} == {"gpt-5.5", "claude-opus-4-7"}
    benched = pa.evals.frontier_models(task="contract-key-fields")
    assert any(m.id == "gpt-5.5" and m.benchmarked for m in benched)


def test_runs_create_resolves_frontier_benchmarked_keyword():
    seen = {}

    def handler(request):
        p = request.url.path
        if p == "/v1/eval/frontier-models":
            return json_response(200, {"frontier_models": [
                {"id": "gpt-5.5", "vendor": "openai", "vision": True, "benchmarked": True},
                {"id": "gemini-x", "vendor": "google", "vision": True, "benchmarked": False},
            ]})
        if p == "/v1/eval-runs":
            seen["cands"] = json.loads(request.content)["candidate_model_ids"]
            return json_response(202, {"run_id": "r1", "status": "queued"})
        return json_response(200, {})

    pa = sync_client(handler)
    pa.evals.runs.create(eval_set="es_1", task="contract-key-fields",
                         models=["pareta-distilled-kie-1"], frontier="benchmarked")
    # only the benchmarked frontier id is merged
    assert seen["cands"] == ["pareta-distilled-kie-1", "gpt-5.5"]


def test_runs_create_frontier_none_and_list():
    seen = []

    def handler(request):
        if request.url.path == "/v1/eval-runs":
            seen.append(json.loads(request.content)["candidate_model_ids"])
        return json_response(202, {"run_id": "r", "status": "queued"})

    pa = sync_client(handler)
    pa.evals.runs.create(eval_set="es", models=["qwen-1"], frontier="none")
    pa.evals.runs.create(eval_set="es", models=["qwen-1"], frontier=["gpt-5.5"])
    assert seen == [["qwen-1"], ["qwen-1", "gpt-5.5"]]


# ── endpoints.deploy (SSE consume) ───────────────────────────────────────
def _deploy_sse(extra_complete=None):
    ep = extra_complete or {"id": "pareta-prod-9", "name": "pareta-prod-9", "model": "qwen-vl-1", "status": "live"}
    payload = (
        "event: progress\ndata: {\"stage\": \"provisioning-gpu\", \"label\": \"Provisioning GPU\"}\n\n"
        "event: progress\ndata: {\"stage\": \"warming-up\", \"label\": \"Warming up\"}\n\n"
        "event: complete\ndata: " + json.dumps({"endpoint": ep}) + "\n\n"
    )
    return httpx.Response(200, content=payload.encode(), headers={"content-type": "text/event-stream"})


def test_deploy_wait_returns_live_endpoint():
    def handler(request):
        assert request.url.path == "/v1/endpoints"
        body = json.loads(request.content)
        assert body["task"] == "invoice-extraction"
        assert body["model"] == "recommended"   # default, resolved server-side
        return _deploy_sse()

    pa = sync_client(handler)
    ep = pa.endpoints.deploy(task="invoice-extraction", wait=True)
    assert isinstance(ep, Endpoint)
    assert ep.id == "pareta-prod-9" and ep.is_live


def test_deploy_error_event_raises():
    def handler(request):
        payload = ("event: progress\ndata: {\"stage\": \"provisioning-gpu\"}\n\n"
                   "event: error\ndata: {\"message\": \"GPU pool exhausted\"}\n\n")
        return httpx.Response(200, content=payload.encode(), headers={"content-type": "text/event-stream"})

    pa = sync_client(handler)
    import pareta
    with pytest.raises(pareta.ParetaError) as ei:
        pa.endpoints.deploy(task="invoice-extraction", model="qwen-vl-1", wait=True)
    assert "GPU pool exhausted" in str(ei.value)


def test_deploy_no_wait_returns_progress_stream():
    def handler(request):
        return _deploy_sse()

    pa = sync_client(handler)
    events = list(pa.endpoints.deploy(task="invoice-extraction", wait=False))
    kinds = [e["event"] for e in events]
    assert kinds == ["progress", "progress", "complete"]
    assert events[0]["data"]["stage"] == "provisioning-gpu"
