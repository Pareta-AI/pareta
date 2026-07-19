"""`client.images` — the image-generation capability lane.

Like the Speech lanes this is NOT called through `chat.completions`; it has a
dedicated route:

  POST /v1/images/generations  {prompt, size?, seed?} -> {created, model,
                                                          data: [{b64_json}], size}

Generation runs on Pareta's open image model (`hidream-1`) and is metered at a
FLAT price per image — every size costs the same (the model renders at full
2K quality internally regardless of the delivery size), debited against your
org balance; a zero balance returns 402. The response's `X-Pareta-Billed`
header carries the per-request receipt in micro-USD.

    pa.images.generate("a lighthouse at dusk").save("out.png")
    pa.images.generate("wide banner", size="2560x1440")

Calls go through the client's `request()` transport, so auth / retries / typed
error mapping apply — this resource never bypasses it.
"""

from __future__ import annotations

from .._models import ImageGeneration

_PATH = "/v1/images/generations"

# Delivery sizes the route accepts today (server-authoritative — a bad size
# 400s with the full list; kept here for docstrings only, not validation):
# 1024x1024, 2048x2048, 2304x1728, 1728x2304, 2560x1440, 1440x2560.


def _generate_body(prompt: str, size: str | None, seed: int | None) -> dict:
    if not prompt or not prompt.strip():
        raise ValueError("prompt is required")
    body: dict[str, object] = {"prompt": prompt}
    if size:
        body["size"] = size
    if seed is not None:
        body["seed"] = seed
    return body


class Images:
    def __init__(self, client):
        self._client = client

    def generate(self, prompt: str, *, size: str | None = None,
                 seed: int | None = None) -> ImageGeneration:
        """Generate one image from a text prompt. Returns an `ImageGeneration`
        whose `.image` is decoded PNG bytes (use `.save(path)` to write a
        file). `size` defaults to 1024x1024 server-side; every size bills the
        same flat per-image price. `seed` pins the noise for reproducibility."""
        return self._client.request(
            "POST", _PATH, body=_generate_body(prompt, size, seed),
            cast=ImageGeneration)


class AsyncImages:
    def __init__(self, client):
        self._client = client

    async def generate(self, prompt: str, *, size: str | None = None,
                       seed: int | None = None) -> ImageGeneration:
        return await self._client.request(
            "POST", _PATH, body=_generate_body(prompt, size, seed),
            cast=ImageGeneration)
