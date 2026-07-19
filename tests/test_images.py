import base64
import json

import pytest

from pareta import ImageGeneration
from conftest import async_client, json_response, sync_client

_PNG = base64.b64encode(b"\x89PNG fake bytes").decode()


def _payload():
    return {"created": 1789000000, "model": "hidream-1",
            "data": [{"b64_json": _PNG}], "size": "1024x1024"}


def test_images_generate_posts_and_parses():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return json_response(200, _payload())

    pa = sync_client(handler)
    out = pa.images.generate("a red fox in the snow")
    assert isinstance(out, ImageGeneration)
    assert seen["path"] == "/v1/images/generations"
    assert seen["body"] == {"prompt": "a red fox in the snow"}
    assert out.image == b"\x89PNG fake bytes"
    assert out.b64_json == _PNG
    assert out.size == "1024x1024"
    assert out.model == "hidream-1"
    assert out.created == 1789000000


def test_images_generate_size_and_seed_forwarded():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return json_response(200, _payload())

    pa = sync_client(handler)
    pa.images.generate("x", size="2560x1440", seed=7)
    assert seen["body"] == {"prompt": "x", "size": "2560x1440", "seed": 7}


def test_images_generate_rejects_empty_prompt():
    pa = sync_client(lambda request: json_response(200, _payload()))
    with pytest.raises(ValueError):
        pa.images.generate("")
    with pytest.raises(ValueError):
        pa.images.generate("   ")


def test_images_generate_save(tmp_path):
    pa = sync_client(lambda request: json_response(200, _payload()))
    out_file = tmp_path / "img.png"
    pa.images.generate("x").save(out_file)
    assert out_file.read_bytes() == b"\x89PNG fake bytes"


async def test_images_generate_async_roundtrip():
    pa = async_client(lambda request: json_response(200, _payload()))
    out = await pa.images.generate("async fox")
    assert out.image.startswith(b"\x89PNG")
    await pa.aclose()
