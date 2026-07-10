"""`client.chat.completions` — OpenAI-compatible chat completions.

`model` is `"auto"` — Pareta's routing brain plans the request, routes it to
the best model, verifies, and answers (`models.list()` shows anything else
your org can reach). The call is metered: a successful completion debits the
org's balance; a zero balance raises `InsufficientCreditsError` (402).
"""

from __future__ import annotations

from typing import Any, Iterator, AsyncIterator

from .._models import ChatCompletion, ChatCompletionChunk

_PATH = "/v1/chat/completions"


def _build_body(model: str, messages: list[dict[str, Any]], stream: bool, extra: dict) -> dict:
    if not model:
        raise ValueError('model is required (use "auto")')
    if not messages:
        raise ValueError("messages is required and must be non-empty")
    body: dict[str, Any] = {"model": model, "messages": messages, **extra}
    if stream:
        body["stream"] = True
    return body


class Completions:
    def __init__(self, client):
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        stream: bool = False,
        **kwargs: Any,
    ):
        """Create a chat completion.

        stream=False → returns a `ChatCompletion`.
        stream=True  → returns an iterator of `ChatCompletionChunk`
                       (`chunk.choices[0].delta.content` is the incremental text).
        Extra OpenAI params (temperature, max_tokens, …) pass through as kwargs.
        """
        body = _build_body(model, messages, stream, kwargs)
        if stream:
            return self._client.stream("POST", _PATH, body=body, cast=ChatCompletionChunk)
        return self._client.request("POST", _PATH, body=body, cast=ChatCompletion)


class Chat:
    def __init__(self, client):
        self.completions = Completions(client)


class AsyncCompletions:
    def __init__(self, client):
        self._client = client

    async def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        stream: bool = False,
        **kwargs: Any,
    ):
        """Async chat completion. stream=True returns an async iterator of chunks."""
        body = _build_body(model, messages, stream, kwargs)
        if stream:
            # Return the async generator directly (caller does `async for`).
            return self._client.stream("POST", _PATH, body=body, cast=ChatCompletionChunk)
        return await self._client.request("POST", _PATH, body=body, cast=ChatCompletion)


class AsyncChat:
    def __init__(self, client):
        self.completions = AsyncCompletions(client)
