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
    request — that would re-run a generation). The first chunk is delivered,
    then APIConnectionError; the handler is called once."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1

        def body():
            yield b'data: {"choices": [{"delta": {"content": "hel"}}]}\n\n'
            raise httpx.ReadError("mid-stream drop")
        return httpx.Response(200, content=body(),
                              headers={"content-type": "text/event-stream"})

    pa = sync_client(handler, max_retries=2)
    stream = pa.chat.completions.create(
        model="auto", messages=[{"role": "user", "content": "hi"}], stream=True)
    seen = []
    with pytest.raises(pareta.APIConnectionError):
        for chunk in stream:
            seen.append(chunk.choices[0].delta.content)
    assert seen == ["hel"]           # the pre-drop chunk was delivered
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


# ─── #174: Idempotency-Key — one logical request, one server-side debit ─

def test_post_carries_stable_idempotency_key_across_retries():
    """Every POST carries an Idempotency-Key, generated ONCE per logical call
    and re-sent VERBATIM on each auto-retry — the server collapses all
    attempts onto one ledger debit (the long-doc over-bill fix)."""
    seen = []

    def handler(request):
        seen.append(request.headers.get("Idempotency-Key"))
        if len(seen) < 3:
            return json_response(500, {"detail": "boom"})
        return json_response(200, {"id": "c", "object": "chat.completion",
                                   "choices": [{"index": 0, "message":
                                                {"role": "assistant", "content": "x"},
                                                "finish_reason": "stop"}]})

    pa = sync_client(handler, max_retries=3)
    pa.chat.completions.create(model="auto", messages=[{"role": "user", "content": "x"}])
    assert len(seen) == 3
    assert all(k and k.startswith("pareta-py-") for k in seen)
    assert len(set(seen)) == 1                       # SAME key on every attempt


def test_separate_calls_get_separate_idempotency_keys():
    seen = []

    def handler(request):
        seen.append(request.headers.get("Idempotency-Key"))
        return json_response(200, {"id": "c", "object": "chat.completion",
                                   "choices": [{"index": 0, "message":
                                                {"role": "assistant", "content": "x"},
                                                "finish_reason": "stop"}]})

    pa = sync_client(handler, max_retries=0)
    for _ in range(2):
        pa.chat.completions.create(model="auto", messages=[{"role": "user", "content": "x"}])
    assert len(set(seen)) == 2                       # fresh key per logical call


def test_get_requests_carry_no_idempotency_key():
    def handler(request):
        assert request.headers.get("Idempotency-Key") is None
        return json_response(200, {"object": "list", "data": []})

    sync_client(handler, max_retries=0).models.list()


def test_default_timeout_is_600s():
    """#174: the 60s default read-timeout killed + retried legitimate long-doc
    requests mid-flight; 600s matches the OpenAI SDK default."""
    from pareta._client import DEFAULT_TIMEOUT
    assert DEFAULT_TIMEOUT.read == 600.0
