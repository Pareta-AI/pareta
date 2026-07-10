# Retrieval: reranking and embeddings

Build search over a small support knowledge base three ways: rerank a
candidate list with `pa.rerank(...)`, semantic-search it with
`pa.embeddings(...)`, and compose the two into the classic two-stage RAG
stack — embeddings for recall, reranking for precision.

These are the Retrieval interfaces: `query + documents → ranked list` goes to
`rerank`, `text → vectors` goes to `embeddings`. They are dedicated routes
because ranked lists and vectors don't fit the chat message contract — not
because there is anything to navigate. You never name a serving model on
either; Pareta resolves the lane server-side, the same way `model="auto"`
does for chat. Rerank is metered per document scored, embeddings per input
token, both against your org balance.

## Setup

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()   # reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();   // reads PARETA_API_KEY (and optional PARETA_BASE_URL)
```

See [installation](../guide/installation.md) if the package isn't set up yet.

## Reranking

`rerank(query, documents)` scores every document against the query and returns
`(index, relevance_score)` rows, most relevant first. The scores are
**calibrated** — each is an independent P(relevant) in (0, 1), not a softmax
over the batch — so a fixed cutoff like `>= 0.5` is a real keep/drop filter
that means the same thing across calls and corpora. `top_n` truncates the
response to the best N, but all documents are still scored (and metered).

**Python**

```python
KB = [
    "Refunds: annual plans are refundable in full within 30 days of purchase...",
    "Failed payments: a declined charge is retried after 24 hours...",
    "Seat changes: adding a seat mid-cycle bills the prorated difference...",
    # ...8 help-center passages in the full example
]

ranked = pa.rerank("Can I get my money back if I cancel my annual plan?", KB)
print(ranked.pairs)                        # documents scored — the metered unit
for r in ranked.results:                   # most relevant first
    print(f"{r.relevance_score:.3f}  {KB[r.index][:60]}")

# calibrated scores: threshold to filter, not just sort
keep = [KB[r.index] for r in ranked.results if r.relevance_score >= 0.5]

# top_n truncates the response; top_documents maps indices back to your texts
top3 = pa.rerank("Can I get my money back if I cancel my annual plan?", KB, top_n=3)
print(top3.top_documents(KB))              # the winning texts, best first
```

**TypeScript**

```typescript
const ranked = await pa.rerank("Can I get my money back if I cancel my annual plan?", KB);
console.log(ranked.pairs);                 // documents scored — the metered unit
for (const r of ranked.results) {          // most relevant first
  console.log(`${r.relevanceScore.toFixed(3)}  ${KB[r.index].slice(0, 60)}`);
}

// calibrated scores: threshold to filter, not just sort
const keep = ranked.results.filter((r) => r.relevanceScore >= 0.5).map((r) => KB[r.index]);

// topN truncates the response; topDocuments maps indices back to your texts
const top3 = await pa.rerank("Can I get my money back if I cancel my annual plan?", KB, { topN: 3 });
console.log(top3.topDocuments(KB));        // the winning texts, best first
```

Full runnable example: [python/retrieval/rerank.py](https://github.com/Pareta-AI/examples/blob/main/python/retrieval/rerank.py) · [typescript/retrieval/rerank.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/retrieval/rerank.ts)

## Embeddings (semantic search)

Embedding is asymmetric: index your passages raw (the default), and embed the
incoming question with `input_type="query"` so it gets the retrieval-query
treatment. The vectors come back unit-normalized, so cosine similarity is a
plain dot product — a one-line function, no vector library needed for a corpus
this size.

**Python**

```python
def dot(a, b):                             # unit vectors: this IS cosine
    return sum(x * y for x, y in zip(a, b))

# index side: embed all passages in one order-preserving call, raw
index = pa.embeddings(KB)
doc_vecs = index.vectors
print(index.prompt_tokens)                 # tokens embedded — the metered unit

# search side: the query embeds asymmetrically from the passages
q = pa.embeddings("can I get a refund on my yearly subscription?",
                  input_type="query").vectors[0]

top_k = sorted(range(len(KB)), key=lambda i: dot(q, doc_vecs[i]), reverse=True)[:3]
for i in top_k:
    print(f"{dot(q, doc_vecs[i]):.3f}  {KB[i][:60]}")
```

**TypeScript**

```typescript
const dot = (a: number[], b: number[]) => a.reduce((s, v, i) => s + v * b[i], 0);

// index side: embed all passages in one order-preserving call, raw
const index = await pa.embeddings(KB);
const docVecs = index.vectors;
console.log(index.promptTokens);           // tokens embedded — the metered unit

// search side: the query embeds asymmetrically from the passages
const q = (await pa.embeddings("can I get a refund on my yearly subscription?",
                               { inputType: "query" })).vectors[0];

const topK = KB.map((_, i) => i)
  .sort((a, b) => dot(q, docVecs[b]) - dot(q, docVecs[a]))
  .slice(0, 3);
for (const i of topK) {
  console.log(`${dot(q, docVecs[i]).toFixed(3)}  ${KB[i].slice(0, 60)}`);
}
```

Full runnable example: [python/retrieval/semantic_search.py](https://github.com/Pareta-AI/examples/blob/main/python/retrieval/semantic_search.py) · [typescript/retrieval/semantic-search.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/retrieval/semantic-search.ts)

## The two-stage RAG stack

The two lanes have complementary jobs. Embeddings are the **recall** stage: a
cheap, per-token wide net that scans the whole corpus and won't miss a
relevant passage phrased nothing like the question. The reranker is the
**precision** stage: a per-document scorer that reads each (query, candidate)
pair closely and is far better at deciding what actually answers the question
— too expensive for the whole corpus, exactly right for the shortlist. So:
embed-retrieve a wide top-K, rerank only those, keep the calibrated winners.

**Python**

```python
# stage 1 — recall: cosine top-5 over the whole corpus
doc_vecs = pa.embeddings(KB).vectors
q = pa.embeddings(QUERY, input_type="query").vectors[0]
candidates = sorted(range(len(KB)), key=lambda i: dot(q, doc_vecs[i]),
                    reverse=True)[:5]

# stage 2 — precision: rerank only the 5 candidates (5 metered, not 8)
pool = [KB[i] for i in candidates]
ranked = pa.rerank(QUERY, pool, top_n=2)

for r in ranked.results:                   # r.index points into pool;
    print(f"{r.relevance_score:.3f}  {pool[r.index]}")  # candidates[r.index] recovers the KB index
```

**TypeScript**

```typescript
// stage 1 — recall: cosine top-5 over the whole corpus
const docVecs = (await pa.embeddings(KB)).vectors;
const q = (await pa.embeddings(QUERY, { inputType: "query" })).vectors[0];
const candidates = KB.map((_, i) => i)
  .sort((a, b) => dot(q, docVecs[b]) - dot(q, docVecs[a]))
  .slice(0, 5);

// stage 2 — precision: rerank only the 5 candidates (5 metered, not 8)
const pool = candidates.map((i) => KB[i]);
const ranked = await pa.rerank(QUERY, pool, { topN: 2 });

for (const r of ranked.results) {          // r.index points into pool;
  console.log(`${r.relevanceScore.toFixed(3)}  ${pool[r.index]}`);  // candidates[r.index] recovers the KB index
}
```

Full runnable example: [python/retrieval/rag_search.py](https://github.com/Pareta-AI/examples/blob/main/python/retrieval/rag_search.py) · [typescript/retrieval/rag-search.ts](https://github.com/Pareta-AI/examples/blob/main/typescript/retrieval/rag-search.ts)

## See also

- [rerank reference](../reference/rerank.md) — the full `Rerank` object, limits, and calibration notes.
- [embeddings reference](../reference/embeddings.md) — the `Embeddings` object and input limits.
- [Inference](../guide/inference.md) — `model="auto"` chat, the lane the retrieved context usually feeds.
- Prove it on your own data: [evaluate on your data](./evaluate-on-your-data.md) benchmarks both retrieval stages against your own graded relevance.
