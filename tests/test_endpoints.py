import httpx

from pareta import Endpoint
from conftest import sync_client, json_response


def test_endpoints_list_returns_typed_objects():
    def handler(request):
        assert request.url.path == "/v1/endpoints"
        return json_response(200, [
            {"id": "ep1", "name": "ep1", "model": "qwen-vl-2", "status": "live",
             "taskName": "invoice-extraction", "url": "https://u"},
            {"id": "ep2", "name": "ep2", "model": "qwen-1", "status": "stopped"},
        ])

    pa = sync_client(handler)
    eps = pa.endpoints.list()
    assert [e.id for e in eps] == ["ep1", "ep2"]
    assert isinstance(eps[0], Endpoint)
    assert eps[0].is_live is True
    assert eps[0].task == "invoice-extraction"
    assert eps[1].is_live is False


def test_endpoints_retrieve():
    def handler(request):
        assert request.url.path == "/v1/endpoints/ep1"
        return json_response(200, {"id": "ep1", "name": "ep1", "model": "qwen-1", "status": "live"})

    pa = sync_client(handler)
    ep = pa.endpoints.retrieve("ep1")
    assert ep.model == "qwen-1" and ep.is_live


def test_endpoint_surfaces_prompt_fields():
    # Extraction endpoint exposes the benchmark system prompt (auto-applied by the
    # proxy); a classifier exposes a copy-and-customize scaffold; a plain endpoint
    # omits both, and the accessors return None rather than KeyError.
    rows = {
        "ep-x": {"id": "ep-x", "status": "live", "taskName": "icd-coding",
                 "recommendedSystemPrompt": "You are an expert inpatient medical coder.",
                 "promptScaffold": None},
        "ep-c": {"id": "ep-c", "status": "live", "taskName": "intent-classification",
                 "recommendedSystemPrompt": None,
                 "promptScaffold": "This endpoint classifies text, but the categories are YOURS"},
        "ep-p": {"id": "ep-p", "status": "live", "taskName": "chat"},
    }

    def handler(request):
        return json_response(200, rows[request.url.path.rsplit("/", 1)[-1]])

    pa = sync_client(handler)
    x = pa.endpoints.retrieve("ep-x")
    assert x.recommended_system_prompt.startswith("You are an expert")
    assert x.prompt_scaffold is None
    c = pa.endpoints.retrieve("ep-c")
    assert c.prompt_scaffold.startswith("This endpoint classifies")
    assert c.recommended_system_prompt is None
    p = pa.endpoints.retrieve("ep-p")
    assert p.recommended_system_prompt is None and p.prompt_scaffold is None


def test_endpoints_lifecycle_calls_right_routes():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        return json_response(200, {"ok": True}) if request.method != "DELETE" else httpx.Response(204)

    pa = sync_client(handler)
    pa.endpoints.start("ep1")
    pa.endpoints.stop("ep1")
    pa.endpoints.delete("ep1")
    assert seen == [
        ("POST", "/v1/endpoints/ep1/start"),
        ("POST", "/v1/endpoints/ep1/stop"),
        ("DELETE", "/v1/endpoints/ep1"),
    ]


def test_endpoint_metrics_dimensions():
    def handler(request):
        # echo which dimension was hit
        dim = request.url.path.rsplit("/", 1)[-1]
        return json_response(200, {"dimension": dim, "p50": 12})

    pa = sync_client(handler)
    m = pa.endpoints.metrics("ep1")
    assert m.performance()["dimension"] == "performance"
    assert m.uptime()["dimension"] == "uptime"
    assert m.cost()["dimension"] == "cost"
    assert m.quality()["dimension"] == "quality"
    assert m.activity()["dimension"] == "activity"


def test_metrics_params_forwarded():
    seen = {}

    def handler(request):
        seen["query"] = dict(request.url.params)
        return json_response(200, {})

    pa = sync_client(handler)
    pa.endpoints.metrics("ep1").cost(since="30d")
    assert seen["query"].get("since") == "30d"
