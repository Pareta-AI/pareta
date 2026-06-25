# pareta

[![PyPI](https://img.shields.io/pypi/v/pareta)](https://pypi.org/project/pareta/)
[![Python versions](https://img.shields.io/pypi/pyversions/pareta)](https://pypi.org/project/pareta/)
[![License](https://img.shields.io/pypi/l/pareta)](https://github.com/Pareta-AI/pareta/blob/main/LICENSE)

Python client for [Pareta](https://pareta.ai) — deploy open-weights endpoints,
run metered inference, browse the benchmark catalog, and eval models on your own
data.

```bash
pip install pareta        # or: uv add pareta / poetry add pareta
```

```python
from pareta import Pareta

pa = Pareta.from_env()                       # reads PARETA_API_KEY
# or: Pareta(api_key="pareta_sk_…", base_url="https://api.pareta.ai")

# OpenAI-compatible inference against a deployed endpoint
resp = pa.chat.completions.create(
    model="ep_…",                            # an endpoint id (see pa.models.list())
    messages=[{"role": "user", "content": "Extract the total from this invoice: …"}],
)
print(resp.choices[0].message.content)

# Streaming
for chunk in pa.chat.completions.create(model="ep_…", messages=[...], stream=True):
    print(chunk.choices[0].delta.content or "", end="")

# List the models (endpoints) your org can call
for m in pa.models.list():
    print(m.id)
```

Async mirrors the sync client:

```python
from pareta import AsyncPareta

async with AsyncPareta.from_env() as pa:
    resp = await pa.chat.completions.create(model="ep_…", messages=[...])
```

## Auth

Mint a `pareta_sk_` key in the dashboard (key management is browser-only) and
pass it as `api_key=` or via `PARETA_API_KEY`. The SDK only ever *consumes* a
key; it never creates, lists, or revokes them.

## Inference is OpenAI-compatible

You don't even need this SDK to *call* a deployed endpoint — point the `openai`
client at `base_url` + your key:

```python
from openai import OpenAI
client = OpenAI(api_key="pareta_sk_…", base_url="https://api.pareta.ai/v1")
```

This SDK's unique value is the **control plane**: deploy, operate, and eval
models from code — available both as Python methods and via the two interfaces
below.

## CLI

`pip install "pareta[cli]"` adds the `pareta` command — the same control plane
from your shell (or `pipx install "pareta[cli]"` for an isolated, always-on-PATH
install):

```bash
export PARETA_API_KEY=pareta_sk_…

pareta tasks match "extract fields from invoices"     # intent → task
pareta tasks leaderboard invoice-extraction           # ranked open models + savings
pareta endpoints deploy --task invoice-extraction --wait
pareta endpoints list
pareta chat ep_… "Summarize this contract: …"          # prompt arg or piped stdin
pareta endpoints cost ep_…
```

Add `--json` to any command for machine-readable output; `pareta --help` (or
`pareta <group> --help`) documents the full tree — `tasks`, `models`,
`endpoints`, `evals`, `chat`, `audio`.

## MCP server

`pareta-mcp` is a [Model Context Protocol](https://modelcontextprotocol.io)
server (stdio) that exposes Pareta to an AI agent (Claude Desktop, Cursor, …) as
tools — so the agent can *find the best open model for a task, benchmark it on
your data, and deploy it*.

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
on your PATH.)

It exposes the full surface — discovery (`match_task`, `get_leaderboard`, …),
provisioning (`deploy_endpoint`, `start` / `stop` / `delete`), eval (`run_eval`),
and metered `chat` / `transcribe` / `speak`. Provisioning and inference tools
spend money; your MCP client's per-tool-call approval is the guardrail.

## Errors

All errors subclass `pareta.ParetaError`:

| Exception | When |
|---|---|
| `AuthenticationError` (401) | bad/missing key |
| `InsufficientCreditsError` (402) | org out of credit — top up in the dashboard |
| `NotFoundError` (404) | unknown endpoint |
| `EndpointNotReadyError` (503) | endpoint stopped / cold / provider down |
| `RateLimitError` (429) | throttled (auto-retried) |
| `BadRequestError` (400/422) | malformed request |
| `APIConnectionError` / `APITimeoutError` | transport failure (auto-retried) |

Idempotent GETs and 429/5xx/timeouts are retried with exponential backoff
(`max_retries`, default 2).

## Status

Live: the full control plane — `chat`, `models`, `tasks` (browse + match),
`endpoints` (deploy / operate / metrics), `evals` (bring-your-own-data), and
`audio` — plus two interfaces over it: the **`pareta` CLI** (`pip install
"pareta[cli]"`) and the **`pareta-mcp` MCP server** (`pip install "pareta[mcp]"`).
Sync + async clients.
