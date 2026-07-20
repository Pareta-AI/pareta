"""`client.images` — the image-generation capability lanes (generate + edit).

Like the Speech lanes these are NOT called through `chat.completions`; they
have dedicated routes:

  POST /v1/images/generations  {prompt, size?, seed?}        -> {created, model,
                                                                 data: [{b64_json}], size}
  POST /v1/images/edits        {prompt, image (b64), seed?}  -> same shape

Both run on Pareta's open image model (`hidream-1`) and are metered at a
FLAT price per call — generation prices by image (every size costs the
same; the model renders at full 2K quality internally), editing prices by
edit (the output keeps the reference's aspect ratio). Debited against your
org balance; a zero balance returns 402. The response's `X-Pareta-Billed`
header carries the per-request receipt in micro-USD.

    pa.images.generate("a lighthouse at dusk").save("out.png")
    pa.images.edit("fox.png", "give the fox a red scarf").save("edited.png")

Calls go through the client's `request()` transport, so auth / retries / typed
error mapping apply — this resource never bypasses it.
"""

from __future__ import annotations

import base64
import os
from typing import Union

from .._models import ImageGeneration

_PATH = "/v1/images/generations"
_EDIT_PATH = "/v1/images/edits"

# Delivery sizes the generations route accepts today (server-authoritative —
# a bad size 400s with the full list; kept here for docstrings only):
# 1024x1024, 2048x2048, 2304x1728, 1728x2304, 2560x1440, 1440x2560.

# A path (str / os.PathLike), raw image bytes, or an already-base64 string —
# the same normalization convention as the audio lane's AudioInput.
ImageInput = Union[str, "os.PathLike[str]", bytes]


def _to_base64(image: ImageInput) -> str:
    """Normalize a file path / bytes / base64 string to a base64 ASCII string.

    - bytes              → base64-encoded.
    - str / PathLike that names an existing file → read + base64-encode.
    - any other str      → assumed to already be base64 (passed through).
    """
    if isinstance(image, bytes):
        return base64.b64encode(image).decode("ascii")
    if isinstance(image, os.PathLike) or (isinstance(image, str) and os.path.isfile(image)):
        with open(os.fspath(image), "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    if isinstance(image, str):
        if not image.strip():
            raise ValueError("image is empty")
        return image  # already base64
    raise TypeError(f"image must be a path, bytes, or base64 str (got {type(image).__name__})")


def _generate_body(prompt: str, size: str | None, seed: int | None) -> dict:
    if not prompt or not prompt.strip():
        raise ValueError("prompt is required")
    body: dict[str, object] = {"prompt": prompt}
    if size:
        body["size"] = size
    if seed is not None:
        body["seed"] = seed
    return body


def _edit_body(image: ImageInput, prompt: str, seed: int | None) -> dict:
    if not prompt or not prompt.strip():
        raise ValueError("prompt is required")
    body: dict[str, object] = {"prompt": prompt, "image": _to_base64(image)}
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

    def edit(self, image: ImageInput, prompt: str, *,
             seed: int | None = None) -> ImageGeneration:
        """Edit one reference image with a plain-language instruction
        (instruction-only — no mask). `image` is a file path, raw bytes, or a
        base64 string (≤25MB decoded). The output keeps the reference's
        aspect ratio; a ~1MP reference renders at ~4MP. Billed flat per
        edit. Returns an `ImageGeneration` (`.image` / `.save(path)`)."""
        return self._client.request(
            "POST", _EDIT_PATH, body=_edit_body(image, prompt, seed),
            cast=ImageGeneration)


class AsyncImages:
    def __init__(self, client):
        self._client = client

    async def generate(self, prompt: str, *, size: str | None = None,
                       seed: int | None = None) -> ImageGeneration:
        return await self._client.request(
            "POST", _PATH, body=_generate_body(prompt, size, seed),
            cast=ImageGeneration)

    async def edit(self, image: ImageInput, prompt: str, *,
                   seed: int | None = None) -> ImageGeneration:
        return await self._client.request(
            "POST", _EDIT_PATH, body=_edit_body(image, prompt, seed),
            cast=ImageGeneration)
