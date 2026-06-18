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
models from code. Those land slice by slice — see `SDK_PLAN.md`.

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

Slice 1 (this release): core client, auth, retries, typed errors,
`chat.completions`, `models`. Endpoints, tasks, and evals land next
(`SDK_PLAN.md` §11).
