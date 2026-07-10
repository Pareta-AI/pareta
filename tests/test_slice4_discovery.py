import json

from pareta import FrontierModel
from conftest import sync_client, json_response


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
