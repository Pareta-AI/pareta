import httpx

from pareta import ChatCompletion, Model
from conftest import sync_client, json_response, sse_response


def test_models_list_returns_typed_objects():
    def handler(request):
        assert request.url.path == "/v1/models"
        return json_response(200, {
            "object": "list",
            "data": [{"id": "ep_abc", "object": "model", "owned_by": "pareto", "created": 1}],
        })

    pa = sync_client(handler)
    models = pa.models.list()
    assert len(models) == 1
    first = list(models)[0]
    assert isinstance(first, Model)
    assert first.id == "ep_abc"
    assert first.owned_by == "pareto"


def test_chat_completion_non_stream():
    def handler(request):
        body = httpx.Request("POST", request.url, content=request.content).read()
        assert request.url.path == "/v1/chat/completions"
        return json_response(200, {
            "id": "cmpl_1",
            "model": "ep_abc",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "hello there"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        })

    pa = sync_client(handler)
    resp = pa.chat.completions.create(
        model="ep_abc", messages=[{"role": "user", "content": "hi"}])
    assert isinstance(resp, ChatCompletion)
    assert resp.choices[0].message.content == "hello there"
    assert resp.choices[0].finish_reason == "stop"
    assert resp.usage.total_tokens == 5


def test_chat_completion_stream_yields_deltas():
    def handler(request):
        # the SDK must set stream:true in the body
        import json
        sent = json.loads(request.content)
        assert sent["stream"] is True
        return sse_response([
            '{"id":"c","choices":[{"index":0,"delta":{"role":"assistant","content":"Hel"}}]}',
            '{"id":"c","choices":[{"index":0,"delta":{"content":"lo"}}]}',
        ])

    pa = sync_client(handler)
    stream = pa.chat.completions.create(
        model="ep_abc", messages=[{"role": "user", "content": "hi"}], stream=True)
    text = "".join(chunk.choices[0].delta.content or "" for chunk in stream)
    assert text == "Hello"


def test_chat_requires_model_and_messages():
    pa = sync_client(lambda r: json_response(200, {}))
    import pytest
    with pytest.raises(ValueError):
        pa.chat.completions.create(model="", messages=[{"role": "user", "content": "x"}])
    with pytest.raises(ValueError):
        pa.chat.completions.create(model="ep", messages=[])
