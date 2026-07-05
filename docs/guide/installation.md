# Installation & authentication

The `pareta` package is the official client for [Pareta](https://pareta.ai), available for **Python** (`pip install pareta`) and **TypeScript/JavaScript** (`npm install pareta`). It runs metered OpenAI-compatible inference against `model="auto"` (Pareta's routing brain — nothing to deploy), evaluates models on your own data, browses the benchmark catalog, and deploys dedicated open-weights endpoints — all from code. This page gets you installed, authenticated, and making a first call.

A few platform truths to know up front, because they shape the whole API:

- **GPUs are hidden.** You never pass a hardware knob. `endpoints.deploy()` takes a task and a model; Pareta resolves the serving class.
- **Models are per-task aliases.** Open-weights ids are masked to public aliases. Real ids never cross the SDK boundary.
- **Inference and evals are metered against your org balance.** A successful call debits credit; an empty balance raises `InsufficientCreditsError`. Top-up is browser-only — the SDK never touches billing.
- **Inference is OpenAI-compatible.** A deployed endpoint speaks the OpenAI chat-completions wire format, so you can use this SDK or the stock `openai` client interchangeably.

## Install

`pareta` requires Python 3.10+ and depends only on `httpx`. Install it with whichever tool you already use:

```bash
pip install pareta
```

```bash
uv add pareta
```

```bash
poetry add pareta
```

The package ships type hints (`py.typed`), so editors and `mypy` get full autocomplete on every method and response model.

### Optional extras: CLI and MCP server

Two more interfaces ship as optional extras on the same Python package:

```bash
pip install "pareta[cli]"     # the `pareta` shell command
pip install "pareta[mcp]"     # the `pareta-mcp` Model Context Protocol server
```

The [CLI](cli.md) gives you the whole control plane as shell commands (`pareta endpoints deploy …`); the [MCP server](mcp.md) exposes it to an AI agent (Claude Desktop, Cursor) as tools. Both authenticate from the same `PARETA_API_KEY`. Each installs a console script, so an isolated install with [`pipx`](https://pipx.pypa.io) (`pipx install "pareta[cli]"`) keeps it off your project's dependency tree while still putting the command on your PATH.

## Authenticate

Every request is authenticated with a `pareta_sk_` secret key sent as a Bearer token. You mint keys in the [dashboard](https://pareta.ai) — key management is browser-only, and the SDK only ever *consumes* a key. It never creates, lists, or revokes them.

### Recommended: `from_env()`

The cleanest path is to put your key in the environment and let the client read it. `from_env()` reads `PARETA_API_KEY` and the optional `PARETA_BASE_URL`:

```bash
export PARETA_API_KEY="pareta_sk_..."
```

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()                       # reads PARETA_API_KEY (+ PARETA_BASE_URL)

# List the deployed endpoints your org can call.
for model in pa.models.list():
    print(model.id, model.owned_by)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();                  // reads PARETA_API_KEY (+ PARETA_BASE_URL)

// List the deployed endpoints your org can call.
for (const model of await pa.models.list()) {
  console.log(model.id, model.ownedBy);
}
```

Keeping the key out of source is the point — `from_env()` means your code carries no secret.

### Explicit key

You can also pass the key directly. The constructor is keyword-only:

**Python**

```python
from pareta import Pareta

pa = Pareta(api_key="pareta_sk_...")
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = new Pareta({ apiKey: "pareta_sk_..." });
```

If `api_key` is falsy and `PARETA_API_KEY` is unset, the client raises `ParetaError` at construction time with a message pointing you to mint a key:

**Python**

```python
import pareta

try:
    pa = pareta.Pareta(api_key=None)         # and PARETA_API_KEY unset
except pareta.ParetaError as e:
    print(e)  # missing API key. Pass api_key=… or set PARETA_API_KEY (mint a pareta_sk_ key in the dashboard).
```

**TypeScript**

```typescript
import { Pareta, ParetaError } from "pareta";

try {
  const pa = new Pareta({ apiKey: undefined }); // and PARETA_API_KEY unset
} catch (e) {
  if (e instanceof ParetaError) {
    console.log(e.message); // missing API key. Pass apiKey: … or use Pareta.fromEnv() with PARETA_API_KEY (mint a pareta_sk_ key in the dashboard).
  }
}
```

## Constructor options

**Python**

```python
Pareta(
    api_key: str | None = None,              # pareta_sk_ key; falls back to nothing (from_env reads the env)
    base_url: str | None = None,             # defaults to "https://api.pareta.ai"
    timeout=None,                            # defaults to httpx.Timeout(60.0, connect=10.0)
    max_retries: int = 2,                    # retries on 408/409/429/500/502/503/504
    http_client: httpx.Client | None = None, # bring your own httpx.Client
)
```

**TypeScript**

```typescript
new Pareta({
  apiKey?: string,        // pareta_sk_ key; falls back to nothing (fromEnv reads the env)
  baseURL?: string,       // defaults to "https://api.pareta.ai"
  timeout?: number,       // milliseconds; defaults to 60_000
  maxRetries?: number,    // default 2; retries on 408/409/429/500/502/503/504
  fetch?: typeof fetch,   // inject your own fetch implementation
});
```

- **`base_url`** defaults to the production API, `https://api.pareta.ai`, and is normalized (trailing slash stripped). Override it only to point at a non-prod environment; set `PARETA_BASE_URL` to do the same via `from_env()`.
- **`max_retries`** (default 2) retries idempotent failures and rate limits with exponential backoff that honors a `Retry-After` header. See [Errors & retries](errors-and-retries.md).
- **`http_client`** lets you supply a pre-configured `httpx.Client` (custom proxies, connection limits, transport). When you pass one, the SDK does not own it and `close()` will not shut it down.

## Manage the connection

The client holds a pooled HTTP connection. Use it as a context manager so the pool is released cleanly:

**Python**

```python
from pareta import Pareta

with Pareta.from_env() as pa:
    resp = pa.chat.completions.create(
        model="ep_invoice_extract",          # an endpoint id from pa.models.list() or endpoints.deploy()
        messages=[{"role": "user", "content": "Extract the total from this invoice: ..."}],
    )
    print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();
const resp = await pa.chat.completions.create({
  model: "ep_invoice_extract",            // an endpoint id from pa.models.list() or endpoints.deploy()
  messages: [{ role: "user", content: "Extract the total from this invoice: ..." }],
});
console.log(resp.choices[0].message.content);
```

Outside a `with` block, call `pa.close()` when you are done. (`close()` is a no-op when you supplied your own `http_client`.) The TypeScript client holds no owned connection — it uses `fetch` per request, so there is nothing to close.

## Async client

`AsyncPareta` mirrors `Pareta` exactly — same constructor, same `from_env()`, same resource namespaces — with awaitable methods and `aclose()` / `async with`:

**Python**

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        resp = await pa.chat.completions.create(
            model="ep_invoice_extract",
            messages=[{"role": "user", "content": "Summarize this contract clause: ..."}],
        )
        print(resp.choices[0].message.content)

asyncio.run(main())
```

**TypeScript**

There is no `AsyncPareta` in TypeScript — there is one `Pareta` client and it is already async. Every I/O method returns a `Promise` you `await` (and streaming methods return an `AsyncIterable` you drive with `for await`). The same client works in sync-looking and concurrent code; there is no separate sync/async split to choose between.

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();
const resp = await pa.chat.completions.create({
  model: "ep_invoice_extract",
  messages: [{ role: "user", content: "Summarize this contract clause: ..." }],
});
console.log(resp.choices[0].message.content);
```

## Your first metered call

Inference debits your org balance on success. If the balance is empty, the call raises `InsufficientCreditsError` (402) — top up in the dashboard, which is the only place billing lives:

**Python**

```python
from pareta import Pareta, InsufficientCreditsError

pa = Pareta.from_env()

try:
    resp = pa.chat.completions.create(
        model="ep_invoice_extract",
        messages=[{"role": "user", "content": "What is the invoice number?"}],
        temperature=0,                       # extra OpenAI params pass straight through
    )
    print(resp.choices[0].message.content)
    print(resp.usage.total_tokens, "tokens")
except InsufficientCreditsError:
    print("Org out of credit — top up in the dashboard.")
```

**TypeScript**

```typescript
import { Pareta, InsufficientCreditsError } from "pareta";

const pa = Pareta.fromEnv();

try {
  const resp = await pa.chat.completions.create({
    model: "ep_invoice_extract",
    messages: [{ role: "user", content: "What is the invoice number?" }],
    temperature: 0,                        // extra OpenAI params pass straight through
  });
  console.log(resp.choices[0].message.content);
  console.log(resp.usage.totalTokens, "tokens");
} catch (e) {
  if (e instanceof InsufficientCreditsError) {
    console.log("Org out of credit — top up in the dashboard.");
  } else {
    throw e;
  }
}
```

The `model` is an endpoint id — anything from `pa.models.list()` or returned by `endpoints.deploy()`. See [Inference](./inference.md) for streaming and the full chat-completions surface.

## Zero-install alternative for inference

You do not need this SDK to *call* a deployed endpoint. Because inference is OpenAI-compatible, you can point the stock `openai` client at Pareta's `base_url` and use the same `pareta_sk_` key:

**Python**

```python
from openai import OpenAI

client = OpenAI(api_key="pareta_sk_...", base_url="https://api.pareta.ai/v1")

resp = client.chat.completions.create(
    model="ep_invoice_extract",
    messages=[{"role": "user", "content": "What is the invoice number?"}],
)
print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
import OpenAI from "openai";

const client = new OpenAI({ apiKey: "pareta_sk_...", baseURL: "https://api.pareta.ai/v1" });

const resp = await client.chat.completions.create({
  model: "ep_invoice_extract",
  messages: [{ role: "user", content: "What is the invoice number?" }],
});
console.log(resp.choices[0].message.content);
```

This is handy for inference-only workloads or dropping Pareta into an existing OpenAI codebase. The `pareta` SDK's distinct value is the **control plane** that the OpenAI client cannot reach: deploying and operating endpoints, browsing the benchmark catalog, and running evals against your own data.

## Next steps

- [Inference](./inference.md) — chat completions, streaming, and metering.
- [Deploying endpoints](deploying-endpoints.md) — `endpoints.deploy()`, lifecycle, and metrics (no GPU knob).
- [Tasks & the catalog](discovery.md) — discover benchmark tasks and the `recommended` model alias.
- [Evals](evaluation.md) — build eval sets and run open vs. frontier comparisons.
- [Errors & retries](errors-and-retries.md) — the typed exception hierarchy and retry policy.
- [The `pareta` CLI](cli.md) — the same control plane from your shell (`pip install "pareta[cli]"`).
- [MCP server](mcp.md) — drive Pareta from an AI agent (Claude Code, Codex, Claude Desktop, Cursor) over MCP (`pip install "pareta[mcp]"`).
- [The `/pareta` skill](skill.md) — a slash-command `SKILL.md` for Claude Code and Codex that drives the CLI.
