"""`client.models` — list the models your org can call.

OpenAI-compatible. Each `Model.id` is usable as
`chat.completions.create(model=…)`, though `model="auto"` — the routing
brain — is the recommended surface.
"""

from __future__ import annotations

from .._models import ModelList

_PATH = "/v1/models"


class Models:
    def __init__(self, client):
        self._client = client

    def list(self) -> ModelList:
        return self._client.request("GET", _PATH, cast=ModelList)


class AsyncModels:
    def __init__(self, client):
        self._client = client

    async def list(self) -> ModelList:
        return await self._client.request("GET", _PATH, cast=ModelList)
