import httpx
import pytest

import pareta
from conftest import async_client, json_response, sse_response


async def test_async_models_list():
    pa = async_client(lambda r: json_response(200, {"data": [{"id": "ep_x", "object": "model"}]}))
    models = await pa.models.list()
    assert [m.id for m in models] == ["ep_x"]
    await pa.aclose()


async def test_async_chat_non_stream():
    def handler(request):
        return json_response(200, {
            "id": "c", "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi!"}}],
        })

    pa = async_client(handler)
    resp = await pa.chat.completions.create(model="ep", messages=[{"role": "user", "content": "hi"}])
    assert resp.choices[0].message.content == "hi!"
    await pa.aclose()


async def test_async_chat_stream():
    def handler(request):
        return sse_response([
            '{"choices":[{"index":0,"delta":{"content":"a"}}]}',
            '{"choices":[{"index":0,"delta":{"content":"b"}}]}',
        ])

    pa = async_client(handler)
    stream = await pa.chat.completions.create(
        model="ep", messages=[{"role": "user", "content": "hi"}], stream=True)
    text = ""
    async for chunk in stream:
        text += chunk.choices[0].delta.content or ""
    assert text == "ab"
    await pa.aclose()


async def test_async_402():
    pa = async_client(lambda r: json_response(402, {"detail": "out of credit"}), max_retries=0)
    with pytest.raises(pareta.InsufficientCreditsError):
        await pa.models.list()
    await pa.aclose()
