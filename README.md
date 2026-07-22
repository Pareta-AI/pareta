# pareta

[![PyPI](https://img.shields.io/pypi/v/pareta)](https://pypi.org/project/pareta/)
[![Python versions](https://img.shields.io/pypi/pyversions/pareta)](https://pypi.org/project/pareta/)
[![License](https://img.shields.io/pypi/l/pareta)](https://github.com/Pareta-AI/pareta/blob/main/LICENSE)

Python client for [Pareta](https://pareta.ai). One model id — `"auto"` — and
Pareta plans each request, routes it to benchmark-proven open specialists,
verifies the result, and falls back to a frontier model when that's the right
call. One request, one bill; you never pay for Pareta's orchestration or
cold starts.

```bash
pip install pareta        # or: uv add pareta / poetry add pareta
```

```python
from pareta import Pareta

pa = Pareta.from_env()                       # reads PARETA_API_KEY
# or: Pareta(api_key="pareta_sk_…", base_url="https://api.pareta.ai")

resp = pa.chat.completions.create(
    model="auto",                            # the routing brain — the product
    messages=[{"role": "user", "content": "Extract the total from this invoice: …"}],
)
print(resp.choices[0].message.content)

# Streaming (progress while Pareta plans + executes, then tokens)
for chunk in pa.chat.completions.create(model="auto", messages=[...], stream=True):
    print(chunk.choices[0].delta.content or "", end="")
```

Async mirrors the sync client:

```python
from pareta import AsyncPareta

async with AsyncPareta.from_env() as pa:
    resp = await pa.chat.completions.create(model="auto", messages=[...])
```

## Is it actually good? Measure it on YOUR data

Don't take the routing brain on faith — benchmark it. `pa.evals` runs `"auto"`
head-to-head against frontier models on your own ground truth and prices every
contender honestly:

```python
run = pa.evals.runs.create(eval_set=es.id, models=["auto"],
                           frontier=["claude-opus-4-7"], wait=True)
```

And watch what your live traffic is doing — spend, success rate, and the
projected savings vs calling a frontier directly:

```python
pa.auto.metrics()          # requests, success rate, spend, savings vs frontier
pa.auto.compare_frontier(  # one prompt, metered, side-by-side with auto
    model="gpt-5.5",
    messages=[{"role": "user", "content": "…"}],
)
```

## Inference is OpenAI-compatible

You don't even need this SDK to call Pareta — point the `openai` client at
`base_url` + your key and set `model="auto"`:

```python
from openai import OpenAI
client = OpenAI(api_key="pareta_sk_…", base_url="https://api.pareta.ai/v1")
resp = client.chat.completions.create(model="auto", messages=[...])
```

This SDK's unique value is everything AROUND that call — evals on your data,
auto metrics, and the benchmark catalog — as Python methods, a CLI, and an
MCP server.

## Discovery

`pa.tasks.match` resolves a plain-language intent to the benchmarked task (or
capability lane) Pareta covers it with — feed the matched task into `pa.evals`
to prove `"auto"` on your own data:

```python
m = pa.tasks.match("extract the key fields from these contracts")
m.type, m.chosen.task_id                     # "task", "contract-key-fields"

for model in pa.models.list():               # everything your org can call
    print(model.id)
```

## Auth

Mint a `pareta_sk_` key in the dashboard (key management is browser-only) and
pass it as `api_key=` or via `PARETA_API_KEY`. The SDK only ever *consumes* a
key; it never creates, lists, or revokes them.

## CLI

`pip install "pareta[cli]"` adds the `pareta` command (or `pipx install
"pareta[cli]"` for an isolated, always-on-PATH install):

```bash
export PARETA_API_KEY=pareta_sk_…

pareta chat "Summarize this contract: …"               # model:"auto" by default
pareta auto metrics                                     # your auto traffic, rolled up
pareta auto compare "…prompt…" --frontier gpt-5.5       # auto vs a frontier, metered

pareta tasks match "extract fields from invoices"       # intent → task
pareta evals run --prompt "extract the total from each invoice" \
  --file rows.jsonl --models auto --frontier --wait     # prove auto on your data
```

Add `--json` to any command for machine-readable output; `pareta --help` (or
`pareta <group> --help`) documents the full tree — `chat`, `auto`, `tasks`,
`models`, `evals`, `audio`.

## MCP server

`pareta-mcp` is a [Model Context Protocol](https://modelcontextprotocol.io)
server (stdio) that exposes Pareta to an AI agent (Claude Desktop, Cursor, …) as
tools — `chat` (defaults to `model="auto"`), `auto_metrics`, `compare_frontier`,
`run_eval` / `get_eval_run`, discovery (`match_task`, `list_tasks`, `get_task`,
`list_models`), and audio (`transcribe`, `speak`).

Run it in **its own isolated environment** — like any MCP server it has its own
dependency tree, so don't `pip install` it into an app/project venv. The simplest
is [`uvx`](https://docs.astral.sh/uv/) (no install, runs on demand). Register it
(Claude Desktop → Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "pareta": {
      "command": "uvx",
      "args": ["--from", "pareta[mcp]", "pareta-mcp"],
      "env": { "PARETA_API_KEY": "pareta_sk_…" }
    }
  }
}
```

Prefer a persistent install? `pipx install "pareta[mcp]"` puts `pareta-mcp` on
your PATH in a dedicated venv — then use `"command": "pareta-mcp"`. (Avoid a plain
`pip install "pareta[mcp]"` into a shared environment: its `mcp`/`starlette`
dependencies can clash with an app's FastAPI, and the console script may not land
on your PATH.) Inference, eval, and audio tools spend money; your MCP client's
per-tool-call approval is the guardrail.

## Errors

All errors subclass `pareta.ParetaError`:

| Exception | When |
|---|---|
| `AuthenticationError` (401) | bad/missing key |
| `InsufficientCreditsError` (402) | org out of credit — top up in the dashboard |
| `NotFoundError` (404) | unknown resource (task, eval set, run, …) |
| `EndpointNotReadyError` (503) | serving capacity cold / provider down (retryable) |
| `RateLimitError` (429) | throttled (auto-retried) |
| `BadRequestError` (400/422) | malformed request |
| `APIConnectionError` / `APITimeoutError` | transport failure (auto-retried) |

Idempotent GETs and 429/5xx/timeouts are retried with exponential backoff
(`max_retries`, default 2).

## Status

Live: `model="auto"` inference (buffered + streaming) with `pa.auto` metrics and
frontier comparison, plus `models`, `tasks` (browse + match), `evals`
(bring-your-own-data, with `"auto"` as a first-class contender), and `audio` —
and two interfaces over it: the **`pareta` CLI** (`pip install "pareta[cli]"`)
and the **`pareta-mcp` MCP server** (`pip install "pareta[mcp]"`). Sync + async
clients.
