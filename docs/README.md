# Pareta

[Pareta](https://pareta.ai) is one OpenAI-compatible endpoint with one model id: **`"auto"`**. Each request is planned, routed to benchmark-proven open specialists, verified, and falls back to a frontier model when that's the right call — one request, one bill. Whichever interface you reach for, it does the same three things — behind one `pareta_sk_` key:

- **Serves `model="auto"` inference.** Metered, OpenAI-compatible (this SDK and the stock `openai` client are interchangeable), streaming included. Nothing to deploy.
- **Evaluates it on your own data.** Run `"auto"` head-to-head against frontier baselines on your rows, then read per-contender quality and cost.
- **Answers "can Pareta do X?".** Match a sentence to the benchmark catalog auto routes across (`tasks.match`), and browse the tasks behind it.

A few platform truths shape the whole API:

- **Models and GPUs are hidden.** You never pick either — "which model?" is the question `"auto"` answers for you, per request, and hardware is Pareta's problem.
- **Frontier (vendor) ids are in the clear.** They appear as eval baselines and in `auto.compare_frontier()`; everything open-weights stays behind `"auto"`.
- **Inference and evals are metered against your org balance.** A successful call debits credit — one debit per request, no matter how many internal model calls auto's plan makes. An empty balance raises `InsufficientCreditsError` (402). An eval run reports its billed total on `run.cost` (dollars). Top-up is browser-only; the SDK never touches billing.

## Ways to use Pareta

Several interfaces, one `pareta_sk_` key and one control plane behind them all — pick what fits how you work:

- **SDK** (Python + TypeScript) — `pip install pareta` / `npm install pareta`. Infer, evaluate, and monitor from code. The rest of these docs.
- **[CLI](./guide/cli.md)** — `pip install "pareta[cli]"`. The same control plane as the `pareta` shell command; tables, or `--json` for scripts.
- **[MCP server](./guide/mcp.md)** — `pip install "pareta[mcp]"`. `pareta-mcp` exposes the control plane to an AI agent (Claude Code, Codex, Claude Desktop, Cursor) as tools.
- **[`/pareta` skill](./guide/skill.md)** — a `SKILL.md` that drives the CLI as a slash command in Claude Code and Codex.

And because inference is OpenAI-compatible, you can skip the library entirely — point the stock `openai` client at `https://api.pareta.ai/v1` and you're done. If you already have an OpenAI codebase, this is the whole migration:

**Python**

```python
from openai import OpenAI

client = OpenAI(api_key="pareta_sk_...", base_url="https://api.pareta.ai/v1")

resp = client.chat.completions.create(
    model="auto",                                                       # the routing brain
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
)
print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
import OpenAI from "openai";

const client = new OpenAI({ apiKey: "pareta_sk_...", baseURL: "https://api.pareta.ai/v1" });

const resp = await client.chat.completions.create({
  model: "auto",                                                       // the routing brain
  messages: [{ role: "user", content: "Say hello in one sentence." }],
});
console.log(resp.choices[0].message.content);
```

Two changed strings — `api_key` and `base_url` — plus `model="auto"`. See [Migrating from the OpenAI SDK](./examples/migrate-from-openai.md) for the full walkthrough and when the `pareta` SDK's control plane (evals, catalog match, auto metrics) earns the install.

> **Python or TypeScript?** Both SDK clients are at full parity. The one design difference: Python ships sync (`Pareta`) **and** async (`AsyncPareta`) clients; TypeScript has a single Promise-only `Pareta` (every method is `async`). Code samples throughout these docs show **Python** and **TypeScript** side by side.

## Install

**Python**

```bash
pip install pareta        # or: uv add pareta / poetry add pareta
```

**TypeScript**

```bash
npm install pareta        # or: pnpm add pareta / yarn add pareta / bun add pareta
```

## Hello world

Mint a `pareta_sk_` key in the dashboard, export it as `PARETA_API_KEY`, and call `model="auto"` — nothing to deploy:

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()                                                  # reads PARETA_API_KEY
resp = pa.chat.completions.create(
    model="auto",                                                       # the routing brain
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
)
print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();                                            // reads PARETA_API_KEY
const resp = await pa.chat.completions.create({
  model: "auto",                                                       // the routing brain
  messages: [{ role: "user", content: "Say hello in one sentence." }],
});
console.log(resp.choices[0].message.content);
```

## Guide

Start-to-finish, in reading order — every page shows Python and TypeScript. See the [guide index](./guide/README.md).

- [Installation & authentication](./guide/installation.md) — install `pareta` (pip or npm), authenticate with a `pareta_sk_` key, make a first metered call.
- [Quickstart](./guide/quickstart.md) — `model="auto"` end to end in a dozen lines, then benchmarking it against frontier models on your data.
- [Core concepts](./guide/core-concepts.md) — tasks and capabilities, the routing brain, hidden models and hardware, metering, and the match → eval → production funnel.
- [Running inference](./guide/inference.md) — `chat.completions.create`, streaming, passthrough params, `models.list`, and metering errors.
- [Evaluating on your own data](./guide/evaluation.md) — benchmark `"auto"` against frontier baselines with `evals.sets` and `evals.runs`: quality/CIs/cost, and the metered run total.
- [Errors, retries & timeouts](./guide/errors-and-retries.md) — the `ParetaError` hierarchy, which errors to catch, and the retry policy.
- [Async & concurrency](./guide/async.md) — Python's `AsyncPareta` vs TypeScript's Promise-only client, and fanning out concurrent calls.
- [Configuration](./guide/configuration.md) — API key, base URL, timeouts, retries, and injecting a custom HTTP client.
- [The `pareta` CLI](./guide/cli.md) — the whole control plane as a shell command (`pip install "pareta[cli]"`), tables or `--json`.
- [MCP server](./guide/mcp.md) — expose the control plane to an AI agent (Claude Code, Codex, Claude Desktop, Cursor) as tools (`pip install "pareta[mcp]"`).
- [The `/pareta` skill](./guide/skill.md) — a `SKILL.md` that drives the CLI as a slash command in Claude Code and Codex.

## Examples

Copy-paste workflows for real jobs, in both languages. See the [examples index](./examples/README.md).

- [Benchmark auto on your own data](./examples/evaluate-on-your-data.md) — eval `"auto"` against frontier baselines and read `run.cost`.
- [Document extraction (PDF/image)](./examples/document-extraction.md) — the blob-task loop: upload documents, benchmark `"auto"` on them, send documents in production.
- [Streaming chat completions](./examples/streaming-chat.md) — iterate chat chunks and accumulate text.
- [Concurrent calls](./examples/concurrent-async.md) — fan out inference and eval calls (`asyncio.gather` / `Promise.all`).
- [Cost & quality monitoring](./examples/cost-and-metrics.md) — read what calls cost and watch your `"auto"` traffic with `auto.metrics()`.
- [Migrating from the OpenAI SDK](./examples/migrate-from-openai.md) — keep using `openai` against Pareta, and when to switch to `pareta`.

## Reference

Field-by-field API docs. Signatures are shown in Python; the TypeScript API mirrors them (camelCase names, options objects, `await`ed) — see any guide page for the TS form. See the [reference index](./reference/README.md).

- [Client](./reference/client.md) — `Pareta` (and Python's `AsyncPareta`): `from_env`/`fromEnv`, constructor params, lifecycle, and the resource namespaces.
- [chat.completions](./reference/chat.md) — `chat.completions.create`, return types, streaming, and the error surface.
- [models](./reference/models.md) — `models.list()` and the `Model` fields.
- [tasks](./reference/tasks.md) — `list`/`retrieve`/`match` and their response models.
- [evals](./reference/evals.md) — `evals.sets`, `evals.runs`, and `evals.frontierModels`.
- [audio](./reference/audio.md) — `audio.transcriptions` (speech-to-text) and `audio.speech` (text-to-speech), metered per minute.
- [Exceptions](./reference/exceptions.md) — the `ParetaError` hierarchy and status-to-class mapping.
- [Response types](./reference/types.md) — every response object plus the `.cost` vs `.costMicroUsd` money convention.
- [Underlying HTTP API](./reference/http-api.md) — the `/v1` routes the SDK wraps (language-neutral).
