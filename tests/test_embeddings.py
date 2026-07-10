import json

import pytest

from pareta import Embeddings
from conftest import async_client, json_response, sync_client


def _payload(n=2):
    return {"object": "list",
            "data": [{"object": "embedding", "index": i,
                      "embedding": [1.0, 0.0]} for i in range(n)],
            "model": "bge-1",
            "usage": {"prompt_tokens": 42, "total_tokens": 42}}


def test_embeddings_posts_and_parses():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return json_response(200, _payload())

    pa = sync_client(handler)
    out = pa.embeddings(["a", "b"])
    assert isinstance(out, Embeddings)
    assert seen["path"] == "/v1/embeddings"
    assert seen["body"] == {"input": ["a", "b"]}
    assert out.vectors == [[1.0, 0.0], [1.0, 0.0]]
    assert out.model == "bge-1"
    assert out.prompt_tokens == 42
    assert len(out) == 2


def test_embeddings_single_string_and_query_type():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return json_response(200, _payload(1))

    pa = sync_client(handler)
    pa.embeddings("what governs", input_type="query")
    assert seen["body"] == {"input": ["what governs"], "input_type": "query"}


def test_embeddings_rejects_bad_input():
    pa = sync_client(lambda request: json_response(200, _payload()))
    with pytest.raises(ValueError):
        pa.embeddings([])
    with pytest.raises(ValueError):
        pa.embeddings("  ")
    with pytest.raises(ValueError):
        pa.embeddings("x", input_type="banana")


def test_embeddings_vectors_sorted_by_index():
    out = Embeddings({"data": [
        {"index": 1, "embedding": [2.0]},
        {"index": 0, "embedding": [1.0]}]})
    assert out.vectors == [[1.0], [2.0]]


async def test_async_embeddings_roundtrip():
    def handler(request):
        assert request.url.path == "/v1/embeddings"
        return json_response(200, _payload(3))

    pa = async_client(handler)
    out = await pa.embeddings(["a", "b", "c"])
    assert len(out) == 3
