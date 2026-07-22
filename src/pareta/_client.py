"""Sync (`Pareta`) and async (`AsyncPareta`) clients.

Both wrap httpx and share one base for URL/header construction, retry policy,
and error mapping. The resource namespaces (`chat`, `models`, …) hang off the
client and call back into `request()` / `stream()`.
"""

from __future__ import annotations

import json
import os
import random
import time
import uuid
from typing import Any, Iterator, AsyncIterator

import httpx

from ._exceptions import (
    APIConnectionError,
    APITimeoutError,
    ParetaError,
    error_from_response,
)
from ._version import __version__

DEFAULT_BASE_URL = "https://api.pareta.ai"
# #174: long-doc auto requests legitimately run 60-180s server-side. A 60s
# read-timeout made the SDK kill + retry them mid-flight; 600s matches the
# OpenAI SDK default and the proxy's own upstream client.
DEFAULT_TIMEOUT = httpx.Timeout(600.0, connect=10.0)
DEFAULT_MAX_RETRIES = 2
_RETRY_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})
# 409 here is the transient lock/contention class some backends emit; Pareta's
# 409 (seed/legacy endpoint) is not retried because it's a stable 4xx — but a
# stable 409 just exhausts retries and still raises ConflictError, so callers
# see the right error either way.


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


class _BaseClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str | None,
        timeout,
        max_retries: int,
    ):
        if not api_key:
            raise ParetaError(
                "missing API key. Pass api_key=… or set PARETA_API_KEY "
                "(mint a pareta_sk_ key in the dashboard)."
            )
        self.api_key = api_key
        self.base_url = _normalize_base_url(base_url or DEFAULT_BASE_URL)
        self.timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        self.max_retries = max(0, int(max_retries))

    # ── shared header / url / retry helpers ──────────────────────────
    def _headers(self, *, stream: bool = False, json_body: bool = False) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream" if stream else "application/json",
            "User-Agent": f"pareta-python/{__version__}",
        }
        if json_body:
            h["Content-Type"] = "application/json"
        # Multipart (files/data) sets its own Content-Type with a boundary —
        # httpx handles it; we must NOT set application/json there.
        return h

    def _should_retry(self, status_code: int) -> bool:
        return status_code in _RETRY_STATUSES

    def _backoff(self, attempt: int, retry_after: float | None) -> float:
        """Seconds to wait before retry `attempt` (0-indexed). Honors
        Retry-After when the server sends it; else exponential + jitter."""
        if retry_after is not None and retry_after >= 0:
            return min(retry_after, 30.0)
        return min(0.5 * (2 ** attempt), 8.0) + random.uniform(0, 0.25)

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float | None:
        val = response.headers.get("retry-after")
        if not val:
            return None
        try:
            return float(val)
        except ValueError:
            return None

    def _parse_error(self, response: httpx.Response):
        request_id = response.headers.get("x-request-id")
        detail: Any
        try:
            body = response.json()
            detail = body.get("detail") if isinstance(body, dict) else body
        except Exception:
            detail = (response.text or "").strip() or None
        return error_from_response(
            response.status_code, detail=detail, request_id=request_id, response=response
        )

    @staticmethod
    def _iter_sse_json(lines: Iterator[str]) -> Iterator[dict]:
        """Data-only SSE (vLLM chat stream): yield each `data:` JSON object."""
        for line in lines:
            line = line.strip()
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                line = line[len("data:"):].strip()
            if not line or line == "[DONE]":
                if line == "[DONE]":
                    return
                continue
            try:
                yield json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

class Pareta(_BaseClient):
    """Synchronous Pareta client.

    >>> pa = Pareta(api_key="pareta_sk_…")          # or Pareta.from_env()
    >>> pa.chat.completions.create(model="auto", messages=[...])
    >>> pa.evals.runs.create(...)                   # prove auto on your data
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout=None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.Client | None = None,
    ):
        super().__init__(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries)
        self._http = http_client or httpx.Client(timeout=self.timeout)
        self._owns_http = http_client is None
        # Resource namespaces (imported here to avoid a circular import).
        from .resources.chat import Chat
        from .resources.models import Models
        from .resources.tasks import Tasks
        from .resources.evals import Evals
        from .resources.audio import Audio
        from .resources.auto import Auto
        from .resources.rerank import RerankResource
        from .resources.embeddings import EmbeddingsResource
        from .resources.images import Images

        self.chat = Chat(self)
        self.models = Models(self)
        self.tasks = Tasks(self)
        self.evals = Evals(self)
        self.audio = Audio(self)
        self.auto = Auto(self)
        self.rerank = RerankResource(self)
        self.embeddings = EmbeddingsResource(self)
        self.images = Images(self)

    # ── lifecycle ─────────────────────────────────────────────────────
    @classmethod
    def from_env(cls, **kwargs) -> "Pareta":
        """Build from PARETA_API_KEY (+ optional PARETA_BASE_URL)."""
        return cls(
            api_key=kwargs.pop("api_key", None) or os.environ.get("PARETA_API_KEY"),
            base_url=kwargs.pop("base_url", None) or os.environ.get("PARETA_BASE_URL"),
            **kwargs,
        )

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> "Pareta":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ── transport ─────────────────────────────────────────────────────
    def request(self, method: str, path: str, *, body=None, params=None, files=None, data=None, cast=None, with_headers=False):
        url = f"{self.base_url}{path}"
        is_multipart = files is not None or data is not None
        headers = self._headers(json_body=(body is not None and not is_multipart))
        # #174: ONE idempotency key per logical call, resent verbatim on every
        # auto-retry — the server collapses all attempts onto a single ledger
        # debit (a long-doc request can outlive a client timeout yet complete).
        if method.upper() == "POST":
            headers.setdefault("Idempotency-Key", f"pareta-py-{uuid.uuid4().hex}")
        kwargs = {"params": params, "headers": headers}
        if is_multipart:
            kwargs["files"] = files
            if data is not None:
                kwargs["data"] = data
        elif body is not None:
            kwargs["json"] = body
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._http.request(method, url, **kwargs)
            except httpx.TimeoutException as e:
                last_exc = APITimeoutError(cause=e)
            except httpx.HTTPError as e:
                last_exc = APIConnectionError(str(e) or "connection error", cause=e)
            else:
                if resp.is_success:
                    raw = resp.json() if resp.content else {}
                    obj = cast(raw) if cast else raw
                    # #164: the chat path attaches the per-call receipt headers
                    # (X-Pareta-Billed + the frontier counterfactual) — return
                    # the response headers so the caller can read them.
                    return (obj, resp.headers) if with_headers else obj
                if attempt < self.max_retries and self._should_retry(resp.status_code):
                    time.sleep(self._backoff(attempt, self._retry_after_seconds(resp)))
                    continue
                raise self._parse_error(resp)
            if attempt < self.max_retries:
                time.sleep(self._backoff(attempt, None))
        raise last_exc  # type: ignore[misc]

    def stream(self, method: str, path: str, *, body=None, params=None, cast=None) -> Iterator:
        """Yield parsed SSE objects. Retries only the initial connect/handshake;
        once bytes are flowing a mid-stream drop raises (can't safely resume)."""
        url = f"{self.base_url}{path}"
        headers = self._headers(stream=True, json_body=body is not None)
        # #174: stable key across handshake retries (see request()).
        if method.upper() == "POST":
            headers.setdefault("Idempotency-Key", f"pareta-py-{uuid.uuid4().hex}")
        for attempt in range(self.max_retries + 1):
            started = False   # set once a 2xx body is flowing — no safe retry past here
            try:
                with self._http.stream(method, url, json=body, params=params, headers=headers) as resp:
                    if not resp.is_success:
                        resp.read()
                        if attempt < self.max_retries and self._should_retry(resp.status_code):
                            time.sleep(self._backoff(attempt, self._retry_after_seconds(resp)))
                            continue
                        raise self._parse_error(resp)
                    started = True
                    for obj in self._iter_sse_json(resp.iter_lines()):
                        yield cast(obj) if cast else obj
                    return
            except httpx.TimeoutException as e:
                # A mid-stream drop must NOT re-issue the request (would re-run a
                # generation). Only the connect/handshake retries.
                if started or attempt >= self.max_retries:
                    raise APITimeoutError(cause=e)
                time.sleep(self._backoff(attempt, None))
            except httpx.HTTPError as e:
                if started or attempt >= self.max_retries:
                    raise APIConnectionError(str(e) or "connection error", cause=e)
                time.sleep(self._backoff(attempt, None))


class AsyncPareta(_BaseClient):
    """Asynchronous Pareta client. Mirrors `Pareta` with awaitable methods."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout=None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.AsyncClient | None = None,
    ):
        super().__init__(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries)
        self._http = http_client or httpx.AsyncClient(timeout=self.timeout)
        self._owns_http = http_client is None
        from .resources.chat import AsyncChat
        from .resources.models import AsyncModels
        from .resources.tasks import AsyncTasks
        from .resources.evals import AsyncEvals
        from .resources.audio import AsyncAudio
        from .resources.auto import AsyncAuto
        from .resources.rerank import AsyncRerankResource
        from .resources.embeddings import AsyncEmbeddingsResource
        from .resources.images import AsyncImages

        self.chat = AsyncChat(self)
        self.models = AsyncModels(self)
        self.tasks = AsyncTasks(self)
        self.evals = AsyncEvals(self)
        self.audio = AsyncAudio(self)
        self.auto = AsyncAuto(self)
        self.rerank = AsyncRerankResource(self)
        self.embeddings = AsyncEmbeddingsResource(self)
        self.images = AsyncImages(self)

    @classmethod
    def from_env(cls, **kwargs) -> "AsyncPareta":
        return cls(
            api_key=kwargs.pop("api_key", None) or os.environ.get("PARETA_API_KEY"),
            base_url=kwargs.pop("base_url", None) or os.environ.get("PARETA_BASE_URL"),
            **kwargs,
        )

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> "AsyncPareta":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def request(self, method: str, path: str, *, body=None, params=None, files=None, data=None, cast=None, with_headers=False):
        import asyncio

        url = f"{self.base_url}{path}"
        is_multipart = files is not None or data is not None
        headers = self._headers(json_body=(body is not None and not is_multipart))
        # #174: ONE idempotency key per logical call, resent verbatim on every
        # auto-retry — the server collapses all attempts onto a single ledger
        # debit (a long-doc request can outlive a client timeout yet complete).
        if method.upper() == "POST":
            headers.setdefault("Idempotency-Key", f"pareta-py-{uuid.uuid4().hex}")
        kwargs = {"params": params, "headers": headers}
        if is_multipart:
            kwargs["files"] = files
            if data is not None:
                kwargs["data"] = data
        elif body is not None:
            kwargs["json"] = body
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._http.request(method, url, **kwargs)
            except httpx.TimeoutException as e:
                last_exc = APITimeoutError(cause=e)
            except httpx.HTTPError as e:
                last_exc = APIConnectionError(str(e) or "connection error", cause=e)
            else:
                if resp.is_success:
                    raw = resp.json() if resp.content else {}
                    obj = cast(raw) if cast else raw
                    return (obj, resp.headers) if with_headers else obj
                if attempt < self.max_retries and self._should_retry(resp.status_code):
                    await asyncio.sleep(self._backoff(attempt, self._retry_after_seconds(resp)))
                    continue
                raise self._parse_error(resp)
            if attempt < self.max_retries:
                await asyncio.sleep(self._backoff(attempt, None))
        raise last_exc  # type: ignore[misc]

    async def stream(self, method: str, path: str, *, body=None, params=None, cast=None) -> AsyncIterator:
        import asyncio

        url = f"{self.base_url}{path}"
        headers = self._headers(stream=True, json_body=body is not None)
        # #174: stable key across handshake retries (see request()).
        if method.upper() == "POST":
            headers.setdefault("Idempotency-Key", f"pareta-py-{uuid.uuid4().hex}")
        for attempt in range(self.max_retries + 1):
            started = False   # set once a 2xx body is flowing — no safe retry past here
            try:
                async with self._http.stream(method, url, json=body, params=params, headers=headers) as resp:
                    if not resp.is_success:
                        await resp.aread()
                        if attempt < self.max_retries and self._should_retry(resp.status_code):
                            await asyncio.sleep(self._backoff(attempt, self._retry_after_seconds(resp)))
                            continue
                        raise self._parse_error(resp)
                    started = True
                    lines = [line async for line in resp.aiter_lines()]
                    for obj in self._iter_sse_json(iter(lines)):
                        yield cast(obj) if cast else obj
                    return
            except httpx.TimeoutException as e:
                if started or attempt >= self.max_retries:
                    raise APITimeoutError(cause=e)
                await asyncio.sleep(self._backoff(attempt, None))
            except httpx.HTTPError as e:
                if started or attempt >= self.max_retries:
                    raise APIConnectionError(str(e) or "connection error", cause=e)
                await asyncio.sleep(self._backoff(attempt, None))
