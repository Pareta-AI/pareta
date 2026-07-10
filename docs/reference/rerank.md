# rerank

`client.rerank` is the Retrieval surface: rank a list of candidate documents
by relevance to a query. It exposes the `rerank` **capability lane** — the
Cohere-shaped workload behind search, RAG context selection, and citation
finding — as a single callable:

- [`rerank(query, documents, top_n=None)`](#rerank-1): score and order the
  documents, most relevant first.

Two facts set this namespace apart from the rest of the SDK:

- **Its own route, not `chat.completions`.** Reranking does not go through
  `chat.completions.create` — `rerank(...)` hits `POST /v1/rerank` directly.
  You never pick a serving model, a GPU, or a quantization; Pareta resolves
  the model behind the lane (`pareta-rerank-1`, a purpose-trained pointwise
  reranker), exactly as `model="auto"` does for chat.
- **Metered per document scored.** Each call is metered against your org
  balance by the number of documents it scores — not by tokens, and not by
  how many results `top_n` keeps. An empty balance raises
  [`InsufficientCreditsError`](exceptions.md) (402). Top-up is browser-only;
  the SDK exposes neither balance nor payment methods.

The call goes through the client's transport, so auth, retries, and typed
error mapping apply exactly as they do everywhere else.

All examples use the synchronous `Pareta` client. The `async` twin has the
same signature on `AsyncPareta` (`await pa.rerank(...)`).

```python
from pareta import Pareta

pa = Pareta()  # PARETA_API_KEY from the environment

docs = [
    "This Agreement shall be governed by the laws of the State of Delaware.",
    "Either party may terminate upon thirty (30) days written notice.",
    "All notices shall be delivered to the addresses set forth above.",
]

ranked = pa.rerank("Which state's law governs this contract?", docs)

ranked.results[0].index            # 0 — position in YOUR docs list
ranked.results[0].relevance_score  # calibrated P(relevant), e.g. 0.97
ranked.top_documents(docs)[0]      # the winning text itself
```

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();
const ranked = await pa.rerank("Which state's law governs this contract?", docs);
ranked.results[0].index;           // position in YOUR docs array
ranked.results[0].relevanceScore;  // calibrated P(relevant)
ranked.topDocuments(docs)[0];      // the winning text itself
```

## rerank()

```python
pa.rerank(query, documents, *, top_n=None) -> Rerank
```

| Parameter | Type | Notes |
|---|---|---|
| `query` | `str` | What to rank against. Required, non-empty. |
| `documents` | `Sequence[str]` | The candidate texts. Required, non-empty; up to 1,000 per call. Only the first ~512 tokens of each document are scored. |
| `top_n` | `int \| None` | Truncate the response to the best N. All documents are still scored (and metered). |

Returns a [`Rerank`](#the-rerank-object). Raises `ValueError` locally on an
empty query/documents (before any network call); server-side validation
errors surface as typed API errors like everywhere else.

## The `Rerank` object

| Accessor | Type | Meaning |
|---|---|---|
| `.results` | `list[RerankResult]` | Ordered most-relevant-first. Each row has `.index` (position in your `documents`) and `.relevance_score` (calibrated P(relevant) ∈ (0, 1) — thresholdable, not just ordinal). |
| `.model` | `str` | The lane's serving model (`pareta-rerank-1`). |
| `.pairs` | `int` | Documents scored — the metered unit. |
| `.top_documents(documents)` | `list[str]` | Convenience: map the ranked indices back onto the list you sent, best first. |

## Scores are calibrated

The reranker is a pointwise yes/no scorer: each `relevance_score` is an
independent probability, not a softmax over the batch. That means a fixed
threshold (say, `>= 0.5`) means the same thing across calls — use it to
*filter* ("keep only actually-relevant passages"), not just to sort:

```python
relevant = [docs[r.index] for r in ranked.results if r.relevance_score >= 0.5]
```

## Benchmark it on your data

`document-reranking` is a catalog task: upload your own (query, documents,
graded relevance) items as an eval set and the benchmark scores nDCG@10 per
candidate — the same metric, math, and serving path this route uses. See
[Evaluation](../guide/evaluation.md).
