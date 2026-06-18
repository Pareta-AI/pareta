"""Shared test helpers: build clients backed by an httpx MockTransport so
every test is hermetic (no network, no real keys)."""

import httpx

from pareta import Pareta, AsyncPareta

TEST_KEY = "pareta_sk_testid000000000000000000.testverifier000000000000"


def sync_client(handler, *, max_retries: int = 2) -> Pareta:
    pa = Pareta(
        api_key=TEST_KEY,
        base_url="https://api.test",
        max_retries=max_retries,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    pa._backoff = lambda *a, **k: 0  # no real sleeping in tests
    return pa


def async_client(handler, *, max_retries: int = 2) -> AsyncPareta:
    pa = AsyncPareta(
        api_key=TEST_KEY,
        base_url="https://api.test",
        max_retries=max_retries,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    pa._backoff = lambda *a, **k: 0
    return pa


def json_response(status: int, body) -> httpx.Response:
    return httpx.Response(status, json=body, headers={"x-request-id": "req_test"})


def sse_response(chunks: list[str]) -> httpx.Response:
    payload = "".join(f"data: {c}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(
        200, content=payload.encode("utf-8"),
        headers={"content-type": "text/event-stream"},
    )
