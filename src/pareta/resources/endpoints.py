"""`client.endpoints` — operate deployed endpoints + read their metrics.

list / retrieve / start / stop / delete, and `metrics(id).<dimension>()`.

`deploy()` is intentionally NOT here yet: POST /v1/endpoints currently expects
the frontend-computed deploy params (taskDisplay, region, quality, cost rates).
The ergonomic `deploy(task, model="recommended")` from SDK_PLAN §5/§8 needs a
backend resolver ({task, model} → full deploy spec + the recommended-model
pick), which lands with the discovery work (Slice 4). Operating + measuring
existing endpoints works today.
"""

from __future__ import annotations

from .._exceptions import ParetaError
from .._models import Endpoint, _endpoint_list

_BASE = "/v1/endpoints"
_DIMENSIONS = ("performance", "uptime", "cost", "quality", "activity")


def _deploy_body(task: str, model: str, name: str | None, extra: dict) -> dict:
    if not task:
        raise ValueError("task is required")
    body = {"task": task, "model": model or "recommended", **extra}
    if name is not None:
        body["name"] = name
    return body


def _endpoint_from_complete(data) -> Endpoint:
    ep = data.get("endpoint") if isinstance(data, dict) else None
    return Endpoint(ep or {})


def _deploy_error(data) -> ParetaError:
    msg = data.get("message") if isinstance(data, dict) else str(data)
    return ParetaError(f"deploy failed: {msg or 'unknown error'}")


class Metrics:
    """`endpoints.metrics(id).performance()` etc. Each returns the raw metric
    JSON (shapes vary by dimension; typed models arrive with the OpenAPI
    generation — SDK_PLAN §10)."""

    def __init__(self, client, endpoint_id: str):
        self._client = client
        self._id = endpoint_id

    def performance(self, **params):
        return self._client.request("GET", f"{_BASE}/{self._id}/performance", params=params or None)

    def uptime(self, **params):
        return self._client.request("GET", f"{_BASE}/{self._id}/uptime", params=params or None)

    def cost(self, **params):
        return self._client.request("GET", f"{_BASE}/{self._id}/cost", params=params or None)

    def quality(self, **params):
        return self._client.request("GET", f"{_BASE}/{self._id}/quality", params=params or None)

    def activity(self, **params):
        return self._client.request("GET", f"{_BASE}/{self._id}/activity", params=params or None)


class Endpoints:
    def __init__(self, client):
        self._client = client

    def deploy(self, *, task: str, model: str = "recommended", name: str | None = None,
               wait: bool = False, **extra):
        """Deploy a model for a task. Pareta picks the GPU/serving config; you
        never pass hardware. model defaults to the task's recommended pick.

        wait=False (default) → returns an iterator of progress events
        ({"event","data"}); the terminal event is 'complete' (data.endpoint) or
        'error'. wait=True → blocks through the deploy and returns the live
        Endpoint (raises ParetaError on a deploy 'error' event)."""
        body = _deploy_body(task, model, name, extra)
        stream = self._client.stream("POST", _BASE, body=body, events=True)
        if not wait:
            return stream
        for ev in stream:
            if ev.get("event") == "complete":
                return _endpoint_from_complete(ev.get("data"))
            if ev.get("event") == "error":
                raise _deploy_error(ev.get("data"))
        raise ParetaError("deploy stream ended without a 'complete' event")

    def list(self) -> list[Endpoint]:
        return self._client.request("GET", _BASE, cast=_endpoint_list)

    def retrieve(self, endpoint_id: str) -> Endpoint:
        return self._client.request("GET", f"{_BASE}/{endpoint_id}", cast=Endpoint)

    def start(self, endpoint_id: str):
        return self._client.request("POST", f"{_BASE}/{endpoint_id}/start")

    def stop(self, endpoint_id: str):
        return self._client.request("POST", f"{_BASE}/{endpoint_id}/stop")

    def delete(self, endpoint_id: str) -> None:
        self._client.request("DELETE", f"{_BASE}/{endpoint_id}")

    def metrics(self, endpoint_id: str) -> Metrics:
        return Metrics(self._client, endpoint_id)


class AsyncMetrics:
    def __init__(self, client, endpoint_id: str):
        self._client = client
        self._id = endpoint_id

    async def performance(self, **params):
        return await self._client.request("GET", f"{_BASE}/{self._id}/performance", params=params or None)

    async def uptime(self, **params):
        return await self._client.request("GET", f"{_BASE}/{self._id}/uptime", params=params or None)

    async def cost(self, **params):
        return await self._client.request("GET", f"{_BASE}/{self._id}/cost", params=params or None)

    async def quality(self, **params):
        return await self._client.request("GET", f"{_BASE}/{self._id}/quality", params=params or None)

    async def activity(self, **params):
        return await self._client.request("GET", f"{_BASE}/{self._id}/activity", params=params or None)


class AsyncEndpoints:
    def __init__(self, client):
        self._client = client

    async def deploy(self, *, task: str, model: str = "recommended", name: str | None = None,
                     wait: bool = False, **extra):
        """Async deploy. wait=False returns the async progress-event iterator;
        wait=True awaits the deploy and returns the live Endpoint."""
        body = _deploy_body(task, model, name, extra)
        stream = self._client.stream("POST", _BASE, body=body, events=True)
        if not wait:
            return stream
        async for ev in stream:
            if ev.get("event") == "complete":
                return _endpoint_from_complete(ev.get("data"))
            if ev.get("event") == "error":
                raise _deploy_error(ev.get("data"))
        raise ParetaError("deploy stream ended without a 'complete' event")

    async def list(self) -> list[Endpoint]:
        return await self._client.request("GET", _BASE, cast=_endpoint_list)

    async def retrieve(self, endpoint_id: str) -> Endpoint:
        return await self._client.request("GET", f"{_BASE}/{endpoint_id}", cast=Endpoint)

    async def start(self, endpoint_id: str):
        return await self._client.request("POST", f"{_BASE}/{endpoint_id}/start")

    async def stop(self, endpoint_id: str):
        return await self._client.request("POST", f"{_BASE}/{endpoint_id}/stop")

    async def delete(self, endpoint_id: str) -> None:
        await self._client.request("DELETE", f"{_BASE}/{endpoint_id}")

    def metrics(self, endpoint_id: str) -> AsyncMetrics:
        return AsyncMetrics(self._client, endpoint_id)
