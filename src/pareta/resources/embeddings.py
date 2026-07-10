"""`client.embeddings` — the Retrieval capability's recall lane.

OpenAI-shaped: POST /v1/embeddings {input, input_type?} → unit-normalized
1024-dim vectors. `input_type="query"` embeds a retrieval QUERY (BGE's query
instruction); the default embeds documents/passages raw — use both sides for
a RAG stack and cosine (a plain dot product on unit vectors) just works.

Metered PER INPUT TOKEN and debited against your org balance; a zero balance
returns 402.

    vecs = pa.embeddings(["passage one", "passage two"]).vectors
    q = pa.embeddings("what governs this contract?", input_type="query")

Calls go through the client's `request()` transport, so auth / retries /
typed error mapping apply — this resource never bypasses it.
"""

from __future__ import annotations

from typing import Sequence, Union

from .._models import Embeddings

_PATH = "/v1/embeddings"

TextInput = Union[str, Sequence[str]]


def _embeddings_body(input: TextInput, input_type: str | None) -> dict:
    texts = [input] if isinstance(input, str) else list(input)
    if not texts or any(not isinstance(t, str) or not t.strip() for t in texts):
        raise ValueError("input must be a non-empty string or list of non-empty strings")
    body: dict[str, object] = {"input": texts}
    if input_type is not None:
        if input_type not in ("query", "document"):
            raise ValueError('input_type must be "query" or "document"')
        body["input_type"] = input_type
    return body


class EmbeddingsResource:
    def __init__(self, client):
        self._client = client

    def __call__(self, input: TextInput, *,
                 input_type: str | None = None) -> Embeddings:
        """Embed one string or a list of strings (order-preserving). Returns
        an `Embeddings` whose `.vectors` are unit-normalized lists of floats.
        Metered per input token."""
        return self._client.request(
            "POST", _PATH, body=_embeddings_body(input, input_type),
            cast=Embeddings)


class AsyncEmbeddingsResource:
    def __init__(self, client):
        self._client = client

    async def __call__(self, input: TextInput, *,
                       input_type: str | None = None) -> Embeddings:
        return await self._client.request(
            "POST", _PATH, body=_embeddings_body(input, input_type),
            cast=Embeddings)
