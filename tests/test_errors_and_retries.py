import httpx
import pytest

import pareta
from conftest import sync_client, json_response


def test_402_maps_to_insufficient_credits():
    def handler(request):
        return json_response(402, {"detail": "organization is out of credit. Top up…"})

    pa = sync_client(handler, max_retries=0)
    with pytest.raises(pareta.InsufficientCreditsError) as ei:
        pa.chat.completions.create(model="ep", messages=[{"role": "user", "content": "x"}])
    assert ei.value.status_code == 402
    assert "out of credit" in str(ei.value)
    assert ei.value.request_id == "req_test"


def test_401_maps_to_authentication_error():
    pa = sync_client(lambda r: json_response(401, {"detail": "invalid API key"}), max_retries=0)
    with pytest.raises(pareta.AuthenticationError):
        pa.models.list()


def test_404_maps_to_not_found():
    pa = sync_client(lambda r: json_response(404, {"detail": "endpoint 'ep' not found"}), max_retries=0)
    with pytest.raises(pareta.NotFoundError):
        pa.chat.completions.create(model="ep", messages=[{"role": "user", "content": "x"}])


def test_503_maps_to_endpoint_not_ready():
    pa = sync_client(lambda r: json_response(503, {"detail": "endpoint 'ep' is stopped."}), max_retries=0)
    with pytest.raises(pareta.EndpointNotReadyError):
        pa.chat.completions.create(model="ep", messages=[{"role": "user", "content": "x"}])


def test_retries_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return json_response(500, {"detail": "boom"})
        return json_response(200, {"object": "list", "data": []})

    pa = sync_client(handler, max_retries=2)
    pa.models.list()
    assert calls["n"] == 3   # 2 failures + 1 success


def test_400_is_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return json_response(400, {"detail": "bad"})

    pa = sync_client(handler, max_retries=3)
    with pytest.raises(pareta.BadRequestError):
        pa.models.list()
    assert calls["n"] == 1   # 4xx (non-429) is terminal


def test_429_is_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"detail": "slow down"}, headers={"retry-after": "0"})
        return json_response(200, {"data": []})

    pa = sync_client(handler, max_retries=2)
    pa.models.list()
    assert calls["n"] == 2


def test_connection_error_wrapped():
    def handler(request):
        raise httpx.ConnectError("no route")

    pa = sync_client(handler, max_retries=1)
    with pytest.raises(pareta.APIConnectionError):
        pa.models.list()


def test_stream_midstream_drop_raises_and_is_not_retried():
    """A drop AFTER the 2xx body starts flowing must raise (not re-issue the
    request — that would re-run a generation / re-trigger a deploy). The first
    event is delivered, then APIConnectionError; the handler is called once."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1

        def body():
            yield b'event: progress\ndata: {"stage": "provisioning-gpu"}\n\n'
            raise httpx.ReadError("mid-stream drop")
        return httpx.Response(200, content=body(),
                              headers={"content-type": "text/event-stream"})

    pa = sync_client(handler, max_retries=2)
    stream = pa.endpoints.deploy(task="invoice-extraction", wait=False)
    seen = []
    with pytest.raises(pareta.APIConnectionError):
        for ev in stream:
            seen.append(ev["event"])
    assert seen == ["progress"]      # the pre-drop event was delivered
    assert calls["n"] == 1           # NOT retried mid-stream


def test_stream_connect_failure_is_retried():
    """A failure BEFORE any 2xx body (connect/handshake) still retries up to
    max_retries, then raises."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectError("no route")

    pa = sync_client(handler, max_retries=2)
    with pytest.raises(pareta.APIConnectionError):
        list(pa.chat.completions.create(
            model="ep", messages=[{"role": "user", "content": "hi"}], stream=True))
    assert calls["n"] == 3           # initial + 2 retries
