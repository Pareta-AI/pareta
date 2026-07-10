# embeddings

`client.embeddings` is the Retrieval surface's recall lane: turn text into
vectors for semantic search and RAG. It exposes the `embed` **capability
lane** as a single callable:

- [`embeddings(input, input_type=None)`](#embeddings-1): embed one string or
  a list, order-preserving.

Two facts set this namespace apart from the rest of the SDK:

- **Its own route, not `chat.completions`.** `embeddings(...)` hits
  `POST /v1/embeddings` directly (OpenAI-shaped request and response). You
  never pick a serving model or GPU; Pareta resolves the model behind the
  lane (`bge-1` — BGE-large-en-v1.5, the same embedder the platform's own
  retrieval pipelines run on).
- **Metered per input token.** Each call debits your org balance by the
  tokens embedded — $0.01 per 1M tokens, 2× under OpenAI
  `text-embedding-3-small` and 13× under `3-large`. An empty balance raises
  [`InsufficientCreditsError`](exceptions.md) (402).

```python
from pareta import Pareta

pa = Pareta()  # PARETA_API_KEY from the environment

# Index side: embed documents raw.
docs = ["Delaware law governs.", "30-day termination notice.", "Notices in writing."]
doc_vecs = pa.embeddings(docs).vectors

# Search side: embed the QUERY with input_type="query" — retrieval queries
# embed differently from passages (BGE's query instruction).
q = pa.embeddings("which state's law applies?", input_type="query").vectors[0]

# Vectors are unit-normalized: cosine similarity is a plain dot product.
best = max(range(len(docs)), key=lambda i: sum(a * b for a, b in zip(q, doc_vecs[i])))
```

## embeddings()

```python
pa.embeddings(input, *, input_type=None) -> Embeddings
```

| Parameter | Type | Notes |
|---|---|---|
| `input` | `str \| Sequence[str]` | Text(s) to embed. Up to 512 per call; each is truncated at 512 tokens. |
| `input_type` | `"query" \| "document" \| None` | `"query"` applies the retrieval-query embedding; default (`None`/`"document"`) embeds raw. |

Returns an [`Embeddings`](#the-embeddings-object). Raises `ValueError`
locally on empty input (before any network call).

## The `Embeddings` object

| Accessor | Type | Meaning |
|---|---|---|
| `.vectors` | `list[list[float]]` | Unit-normalized 1024-dim vectors, in your input order. |
| `.model` | `str` | The lane's serving model (`bge-1`). |
| `.prompt_tokens` | `int` | Tokens embedded — the metered unit. |
| `len(result)` | `int` | Number of vectors. |

## The RAG stack on Pareta

Embeddings are the recall stage; pair them with [`rerank`](rerank.md) for
precision — retrieve a wide candidate set by cosine, then let
`pareta-rerank-1` re-score the top 50–100. Both stages are benchmarkable on
your own data (the `text-embedding` and `document-reranking` catalog tasks
score nDCG@10 against your graded relevance), and both are measured on the
same public pools, so the leaderboard shows exactly what each stage buys.
