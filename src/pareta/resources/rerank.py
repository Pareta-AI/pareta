"""`client.rerank` — the Retrieval capability (document reranking).

Like the Speech lanes this is NOT called through `chat.completions`; it has a
dedicated route:

  POST /v1/rerank  {query, documents[], top_n?} -> {results: [{index,
                    relevance_score}, ...desc], model, pairs}

Scores are calibrated P(relevant) in (0, 1) — usable as a threshold, not just
an ordering. Metered PER DOCUMENT scored and debited against your org
balance; a zero balance returns 402. Send an `Idempotency-Key` header (via
`extra_headers` on the client if supported) to make retries bill once.

    ranked = pa.rerank("governing law", docs, top_n=3)
    ranked.results[0].index            # position in YOUR docs list
    ranked.top_documents(docs)         # the winning texts, best first

Calls go through the client's `request()` transport, so auth / retries /
typed error mapping apply — this resource never bypasses it.
"""

from __future__ import annotations

from typing import Sequence

from .._models import Rerank

_PATH = "/v1/rerank"


def _rerank_body(query: str, documents: Sequence[str],
                 top_n: int | None) -> dict:
    if not query or not query.strip():
        raise ValueError("query is required")
    docs = list(documents)
    if not docs:
        raise ValueError("documents must be a non-empty list of strings")
    body: dict[str, object] = {"query": query, "documents": docs}
    if top_n is not None:
        body["top_n"] = top_n
    return body


class RerankResource:
    def __init__(self, client):
        self._client = client

    def __call__(self, query: str, documents: Sequence[str], *,
                 top_n: int | None = None) -> Rerank:
        """Rank `documents` by relevance to `query`. Returns a `Rerank` whose
        `.results` are (index, relevance_score) rows, most relevant first;
        `top_n` truncates the response (all documents are still scored and
        metered). Metered per document."""
        return self._client.request(
            "POST", _PATH, body=_rerank_body(query, documents, top_n),
            cast=Rerank)


class AsyncRerankResource:
    def __init__(self, client):
        self._client = client

    async def __call__(self, query: str, documents: Sequence[str], *,
                       top_n: int | None = None) -> Rerank:
        return await self._client.request(
            "POST", _PATH, body=_rerank_body(query, documents, top_n),
            cast=Rerank)
