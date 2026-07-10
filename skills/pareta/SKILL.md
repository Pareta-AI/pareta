---
name: pareta
description: >-
  Call Pareta's model:"auto" routing brain (one endpoint that routes every
  request to the best model at frontier-grade quality for a fraction of the
  cost), benchmark it against frontier models on the user's own data, run
  retrieval (rerank + embeddings), and monitor spend/quality/savings. Drives
  the `pareta` shell command; auth is the `PARETA_API_KEY` env var.
---

# Pareta

[Pareta](https://pareta.ai) is ONE endpoint: send any request with
`model: "auto"` and Pareta plans it, routes each part to the cheapest model
that holds frontier-grade quality, verifies, and answers — billed as one
request, with the frontier as the built-in quality floor (a request that
can't complete degrades to a frontier model; a failed request bills $0).

The whole workflow is three verbs:

1. **Call it** — `pareta chat "…"` (model `"auto"` is the default; or any
   OpenAI-compatible client pointed at api.pareta.ai with `model: "auto"`).
2. **Prove it** — benchmark auto against frontier models on the USER'S data:
   `pareta evals run` with `"auto"` among the candidates. The report gives
   per-contender quality + cost — the product's core claim, measured.
3. **Watch it** — `pareta --json auto metrics` (requests, success rate,
   spend, PROJECTED savings vs frontier).

There is nothing to deploy or operate: no endpoints, no GPUs, no model picking.

## Before you start

1. **CLI present?** Check with `pareta --version`. If missing, install it:
   `pipx install "pareta[cli]"` (isolated, recommended) or `pip install "pareta[cli]"`.
2. **Authenticated?** The CLI reads `PARETA_API_KEY` (a `pareta_sk_` key from the
   dashboard) and optional `PARETA_BASE_URL`. If `PARETA_API_KEY` is unset, stop
   and ask the user to export it — do not guess a key.
3. **Parsing output?** Add the global `--json` flag *before* the subcommand
   (`pareta --json <group> <cmd>`) to get machine-readable JSON instead of a table.

## Money + safety (read before calling)

Several actions **spend the user's org balance** — confirm with the user before
running them, and report what each will cost where you can:

- `chat`, `auto compare`, `evals run`, `audio transcribe`, `audio speak`,
  `rerank` (per document scored), `embed` (per input token) —
  **metered** per call/token/minute (`auto compare` makes TWO real calls: auto
  plus a frontier vendor at its actual token cost).
- `evals sets delete` — **destructive** (prompts unless `--yes`).

A failed request bills $0. Never run a spending or destructive command
speculatively.

## The core workflow

### 1. Call it (metered)

```bash
pareta chat "What is the contract's effective date? <contract text>"
echo "Summarize this clause: ..." | pareta chat        # or pipe stdin
pareta chat --stream "…"                               # stream tokens
```

`model: "auto"` is the default — Pareta picks the best model per request.

### 2. Find the grading contract for an eval (free)

A task names how a dataset is scored — a grading contract. This step exists
only to get a `task` id for an eval; describe the user's dataset in plain
language:

```bash
pareta --json tasks match "extract the key fields from these contracts"
```

Read the `type` (`task` | `capability` | `unsupported` | `none`), the chosen
`task_id`, and the reasoning. If a task matched, feed its `task_id` into an
eval (below) to prove auto on their data. `unsupported`/`none` mean no
benchmarked scorer grades this dataset shape — that says nothing about
serving: the generation work itself still goes straight to `pareta chat`
(model `"auto"`).

### 3. Benchmark on the user's own data (metered)

When the user has labeled rows (a JSONL file, one object per line), prove what
auto does on *their* data — head-to-head with frontier baselines:

```bash
pareta evals run --task contract-key-fields --file rows.jsonl \
  --models auto --frontier --wait
```

`--models` is repeatable and required — include `auto` to benchmark the routing
brain itself. `--frontier` adds the task's benchmarked vendor models as
baselines. Read the per-contender quality + mean cost from the results: that
cost-quality gap is the product's core claim, measured on the user's data.

### 4. Watch live traffic (free)

```bash
pareta --json auto metrics     # requests, success rate, spend, projected savings
```

### 5. Side-by-side spot check (metered — two real calls)

```bash
pareta auto compare "…prompt…" --frontier gpt-5.5
```

Runs one prompt against auto AND a frontier vendor and prints both answers
with the frontier's real bill and latency.

## Other surfaces

- `pareta models list` — the models the org can call (auto is the default and
  the recommended surface).
- `pareta tasks list` / `pareta tasks show <task>` — browse the benchmark catalog.
- `pareta audio transcribe <file>` / `pareta audio speak "<text>" --out out.wav` — speech in/out (metered per minute).
- `pareta rerank "query" doc1 doc2 …  # or --file docs.txt` — rank documents by relevance (RAG precision; metered per document).
- `pareta embed "text" --type query` — unit vectors for semantic search (RAG recall; metered per input token).
- `pareta evals sets create|list|show|delete` — manage reusable eval sets.

`pareta --help` (or `pareta <group> --help`) documents the full tree. Full docs:
https://docs.pareta.ai.
