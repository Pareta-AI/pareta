import json

import pytest

from pareta import Rerank, RerankResult
from conftest import async_client, json_response, sync_client


def _payload():
    return {"results": [{"index": 2, "relevance_score": 0.93},
                        {"index": 0, "relevance_score": 0.41}],
            "model": "pareta-rerank-1", "pairs": 3}


# ── rerank (query + documents → ranked indices) ─────────────────────────
def test_rerank_posts_and_parses():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return json_response(200, _payload())

    pa = sync_client(handler)
    docs = ["irrelevant", "meh", "governing law of Delaware"]
    out = pa.rerank("governing law", docs, top_n=2)

    assert isinstance(out, Rerank)
    assert seen["path"] == "/v1/rerank"
    assert seen["body"] == {"query": "governing law", "documents": docs, "top_n": 2}
    assert out.model == "pareta-rerank-1"
    assert out.pairs == 3
    assert isinstance(out.results[0], RerankResult)
    assert out.results[0].index == 2
    assert out.results[0].relevance_score == 0.93
    # ranked indices map back onto the caller's documents, best first
    assert out.top_documents(docs) == ["governing law of Delaware", "irrelevant"]


def test_rerank_top_n_omitted_when_none():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return json_response(200, _payload())

    pa = sync_client(handler)
    pa.rerank("q", ["a"])
    assert "top_n" not in seen["body"]


def test_rerank_rejects_bad_input():
    pa = sync_client(lambda request: json_response(200, _payload()))
    with pytest.raises(ValueError):
        pa.rerank("", ["a"])
    with pytest.raises(ValueError):
        pa.rerank("q", [])


def test_rerank_top_documents_ignores_out_of_range():
    out = Rerank({"results": [{"index": 9, "relevance_score": 0.9},
                              {"index": 0, "relevance_score": 0.5}]})
    assert out.top_documents(["only"]) == ["only"]


async def test_async_rerank_roundtrip():
    def handler(request):
        assert request.url.path == "/v1/rerank"
        return json_response(200, _payload())

    pa = async_client(handler)
    out = await pa.rerank("q", ["a", "b", "c"])
    assert out.pairs == 3
    assert [r.index for r in out.results] == [2, 0]
