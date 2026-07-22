# Quickstart

Pareta is one endpoint. Send any request with `model="auto"` and Pareta plans
it, routes each part to the cheapest model that holds frontier-grade quality,
verifies, and answers — billed as one request, with a frontier model as the
built-in quality floor. Inference is OpenAI-compatible and metered against
your org's balance.

## The 30-second version

```python
from pareta import Pareta

client = Pareta.from_env()          # reads PARETA_API_KEY
completion = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Summarize this contract: …"}],
)
print(completion.choices[0].message.content)
```

That is the product. Everything below — benchmarking auto against frontier
models on your own data and monitoring spend + projected savings — exists to
prove and operate that one call.

- **Prove it**: `client.evals` with `"auto"` among the candidates (see
  [Evaluation](evaluation.md)) — per-contender quality + cost on YOUR data.
- **Watch it**: `client.auto.metrics()` — requests, success rate, spend, and
  the projected savings vs frontier.
- **Compare it**: `client.auto.compare_frontier(...)` — one prompt against a
  frontier vendor, metered, for a side-by-side.

## Install

```bash
pip install pareta        # or: uv add pareta / poetry add pareta
```

## Authenticate

Mint a `pareta_sk_` key in the dashboard (key management is browser-only) and
export it. `Pareta.from_env()` reads `PARETA_API_KEY` (and an optional
`PARETA_BASE_URL`).

```bash
export PARETA_API_KEY="pareta_sk_..."
```

The SDK only ever consumes a key. It never creates, lists, or revokes them, and
it never exposes your balance or payment methods. Topping up credit is
browser-only.

## Find out how your data will be scored

There is no model to pick and nothing to deploy — send any generation job
straight to `model="auto"`. The one lookup you'll ever do is for
benchmarking: `tasks.match` maps a plain-English description of your dataset
to the task an eval scores it with:

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()                                  # reads PARETA_API_KEY

m = pa.tasks.match("extract key fields from contracts")
print(m.type)                    # "task" — a benchmarked task covers this
if m.chosen:
    print(m.chosen.task_id)      # e.g. "contract-key-fields"
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();                              // reads PARETA_API_KEY

const m = await pa.tasks.match("extract key fields from contracts");
console.log(m.matched);          // true — a benchmarked task covers this
console.log(m.chosen?.taskId);   // e.g. "contract-key-fields"
```

`m.type` is one of four verdicts: `"task"` (a benchmarked task fits),
`"capability"` (a general lane — chat, coding, vision, … — covers it),
`"unsupported"` (Pareta does not cover this; a correct answer, not an error),
or `"none"` (the router was unavailable and the lexical fallback found nothing
confident). Whatever the verdict names, running the job is always the same
call: `chat.completions.create(model="auto", ...)`.

Browse the whole catalog behind the router with `pa.tasks.list()` and
`pa.tasks.retrieve(task_id)` — see [tasks](../reference/tasks.md).

## Stream the response

Pass `stream=True` to get an iterator of `ChatCompletionChunk`. The incremental
text lives on `chunk.choices[0].delta.content` (it can be `None` on the first
and last chunks, so guard it).

**Python**

```python
for chunk in pa.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Write a haiku about invoices."}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="", flush=True)
print()
```

**TypeScript**

```typescript
for await (const chunk of pa.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "Write a haiku about invoices." }],
  stream: true,
})) {
  process.stdout.write(chunk.choices[0].delta.content || "");
}
console.log();
```

Extra OpenAI parameters (`temperature`, `max_tokens`, `top_p`, and so on) pass
straight through as keyword arguments.

## Cost and credit

Every successful completion debits your org's balance — one debit per request,
no matter how many internal model calls auto's plan makes. If the balance is
empty, the call raises `InsufficientCreditsError` (HTTP 402). Top-up is
browser-only.

**Python**

```python
from pareta import InsufficientCreditsError

try:
    resp = pa.chat.completions.create(model="auto", messages=[
        {"role": "user", "content": "ping"},
    ])
except InsufficientCreditsError:
    print("Out of credit — top up in the dashboard.")
```

**TypeScript**

```typescript
import { InsufficientCreditsError } from "pareta";

try {
  const resp = await pa.chat.completions.create({
    model: "auto",
    messages: [{ role: "user", content: "ping" }],
  });
} catch (e) {
  if (e instanceof InsufficientCreditsError) {
    console.log("Out of credit — top up in the dashboard.");
  } else {
    throw e;
  }
}
```

Evaluation runs are metered the same way (auto plus frontier compute). An
`EvalRun` reports its billed total on `run.cost`, a `Decimal` in dollars floored
to whole cents (so a sub-cent run reads `Decimal("0.00")`); the raw value is on
`run.cost_micro_usd`. See [Evals](evaluation.md).

## Clean up

There is nothing running on your account to stop — auto's serving fleet is
Pareta's to operate. Cleanup is just closing the client (or using it as a
context manager).

**Python**

```python
pa.close()
```

**TypeScript**

```typescript
// No close() in TS: the client owns no connection (it uses the native fetch),
// so there is nothing to release and no context-manager form to wrap it in.
```

**Python**

```python
# Context-manager form closes the HTTP client for you.
with Pareta.from_env() as pa:
    resp = pa.chat.completions.create(model="auto", messages=[
        {"role": "user", "content": "hi"},
    ])
```

**TypeScript**

```typescript
// No context manager in TS — just construct and use it; nothing to close.
const pa = Pareta.fromEnv();
const resp = await pa.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "hi" }],
});
```

## List what you can call

`models.list()` returns the OpenAI-compatible model list. It has exactly one
entry — `"auto"` — which is the point: the id you pass to
`chat.completions.create(model=...)` is never a decision.

**Python**

```python
for m in pa.models.list():
    print(m.id, m.owned_by)
```

**TypeScript**

```typescript
for (const m of await pa.models.list()) {
  console.log(m.id, m.ownedBy);
}
```

## Async

`AsyncPareta` mirrors the sync client; resource methods are `async def` and
streams are async iterators.

**Python**

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        resp = await pa.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": "Say hello."}],
        )
        print(resp.choices[0].message.content)

asyncio.run(main())
```

**TypeScript**

```typescript
// There is no AsyncPareta in TypeScript — the single `Pareta` client is already
// async. Every I/O method returns a Promise (await it), and streams are async
// iterables (`for await`).
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();
const resp = await pa.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "Say hello." }],
});
console.log(resp.choices[0].message.content);
```

## Already using the OpenAI SDK?

You do not need this SDK just to run inference. Point the `openai` client at
your `base_url` plus your `pareta_sk_` key:

**Python**

```python
from openai import OpenAI

client = OpenAI(api_key="pareta_sk_...", base_url="https://api.pareta.ai/v1")
resp = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "hi"}],
)
```

**TypeScript**

```typescript
import OpenAI from "openai";

const client = new OpenAI({ apiKey: "pareta_sk_...", baseURL: "https://api.pareta.ai/v1" });
const resp = await client.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "hi" }],
});
```

This SDK's unique value is everything around that call: benchmark `"auto"` on
your own data (`evals`), match intent to coverage (`tasks.match`), and watch
traffic + savings (`auto.metrics()`) — from code.

## Next steps

- [Core concepts](core-concepts.md) — tasks and capabilities, the routing
  brain, metering, and the match → eval → production funnel.
- [Evals](evaluation.md) — benchmark `"auto"` against frontier baselines on
  your own data.
- [Errors](errors-and-retries.md) — the `ParetaError` hierarchy and retry behavior.
