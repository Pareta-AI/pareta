# Quickstart

Deploy the recommended open-weights model for a task and run inference against
it, end to end, in about a dozen lines. Pareta picks the GPU and serving config
for you, so there is no hardware to choose. Inference is OpenAI-compatible and
metered against your org's balance.

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

## Deploy and run inference

This is the whole loop: name a task, let Pareta pick the recommended model,
deploy it, and send a request. The `wait=True` flag blocks through the deploy
SSE stream and hands you back a live `Endpoint`.

```python
from pareta import Pareta

pa = Pareta.from_env()                                  # reads PARETA_API_KEY

task = "contract-key-fields"                             # a subtask id from the catalog

# Inspect the model deploy(model="recommended") will pick (a per-task alias).
print("recommended:", pa.tasks.recommended(task))       # e.g. "qwen-vl-2"

# Deploy it. No GPU, quantization, or parallelism knob — Pareta resolves all of it.
ep = pa.endpoints.deploy(task=task, model="recommended", wait=True)
print("live endpoint:", ep.id, ep.status)               # e.g. "ep_a1b2c3" "live"

# Run OpenAI-compatible inference against the endpoint id.
resp = pa.chat.completions.create(
    model=ep.id,                                         # the endpoint id, not the alias
    messages=[{"role": "user", "content": "Say hello in one short sentence."}],
)
print(resp.choices[0].message.content)
print("tokens:", resp.usage.total_tokens)
```

Output:

```
recommended: qwen-vl-2
live endpoint: ep_a1b2c3 live
Hello, it is good to meet you.
tokens: 27
```

A few things worth pinning down:

- **`task`** is a subtask id (for example `"contract-key-fields"`). Discover
  ids with `pa.tasks.list()`, or turn a sentence into a task with
  `pa.tasks.match("extract fields from contracts")`. See
  [Tasks](discovery.md).
- **`model="recommended"`** (the default) resolves server-side to the task's
  curated pick, falling back to the top open model on the leaderboard. You can
  also pass a specific per-task alias. Real model ids never reach the client.
- **`ep.id`** is what you pass to `chat.completions.create(model=...)`. That is
  the deployed endpoint id, distinct from `ep.model`, which is the per-task
  public alias the endpoint serves.
- **No hardware knob.** `deploy()` takes only `task`, `model`, and an optional
  `name`. Pareta selects the GPU and serving class from its registry.

## Stream the response

Pass `stream=True` to get an iterator of `ChatCompletionChunk`. The incremental
text lives on `chunk.choices[0].delta.content` (it can be `None` on the first
and last chunks, so guard it).

```python
for chunk in pa.chat.completions.create(
    model=ep.id,
    messages=[{"role": "user", "content": "Write a haiku about invoices."}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="", flush=True)
print()
```

Extra OpenAI parameters (`temperature`, `max_tokens`, `top_p`, and so on) pass
straight through as keyword arguments.

## Cost and credit

Every successful completion debits your org's balance. If the balance is empty,
the call raises `InsufficientCreditsError` (HTTP 402). Top-up is browser-only.

```python
from pareta import InsufficientCreditsError

try:
    resp = pa.chat.completions.create(model=ep.id, messages=[
        {"role": "user", "content": "ping"},
    ])
except InsufficientCreditsError:
    print("Out of credit — top up in the dashboard.")
```

Evaluation runs are metered the same way (open plus frontier compute). An
`EvalRun` reports its billed total on `run.cost`, a `Decimal` in dollars floored
to whole cents (so a sub-cent run reads `Decimal("0.00")`); the raw value is on
`run.cost_micro_usd`. See [Evals](evaluation.md).

## Clean up

Stop the endpoint when you are done so it stops accruing cost, and close the
client (or use it as a context manager).

```python
pa.endpoints.stop(ep.id)        # later: pa.endpoints.start(ep.id) / pa.endpoints.delete(ep.id)
pa.close()
```

```python
# Context-manager form closes the HTTP client for you.
with Pareta.from_env() as pa:
    resp = pa.chat.completions.create(model=ep.id, messages=[
        {"role": "user", "content": "hi"},
    ])
```

## List what you can call

`models.list()` returns the OpenAI-compatible subset: deployed endpoints with a
live URL. Each `id` is usable directly in `chat.completions.create(model=...)`.

```python
for m in pa.models.list():
    print(m.id, m.owned_by)
```

## Async

`AsyncPareta` mirrors the sync client; resource methods are `async def` and
streams are async iterators.

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        ep = await pa.endpoints.deploy(
            task="contract-key-fields", model="recommended", wait=True,
        )
        resp = await pa.chat.completions.create(
            model=ep.id,
            messages=[{"role": "user", "content": "Say hello."}],
        )
        print(resp.choices[0].message.content)

asyncio.run(main())
```

One async difference to note: `tasks.recommended()` and `tasks.leaderboard()`
are sync-only for now.

## Already using the OpenAI SDK?

You do not need this SDK just to call a deployed endpoint. Point the `openai`
client at your `base_url` plus your `pareta_sk_` key:

```python
from openai import OpenAI

client = OpenAI(api_key="pareta_sk_...", base_url="https://api.pareta.ai/v1")
resp = client.chat.completions.create(
    model="ep_a1b2c3",
    messages=[{"role": "user", "content": "hi"}],
)
```

This SDK's unique value is the control plane: deploy, operate, and eval models
from code.

## Next steps

- [Tasks](discovery.md) — browse the benchmark catalog, match intent to a task,
  and read leaderboards.
- [Endpoints](deploying-endpoints.md) — deploy, operate, and read endpoint metrics.
- [Evals](evaluation.md) — score candidate models on your own data before you
  deploy.
- [Errors](errors-and-retries.md) — the `ParetaError` hierarchy and retry behavior.
