# models

`client.models` is the OpenAI-compatible model index: `GET /v1/models`. On Pareta it returns exactly one entry — **`"auto"`** — because there is only one model id to call. The resource exists so OpenAI-style tooling that discovers ids by listing keeps working unchanged; the id it discovers is the one you pass to [`chat.completions.create(model=...)`](../guide/inference.md).

Two platform truths show up here:

- **There is no model menu.** "Which model?" is the question `"auto"` answers for you, per request. The open-weights models auto routes across never appear in this list — they stay behind the one id, and you never see or pick a GPU.
- **Calling a model is metered.** Listing is free, but each completion against `"auto"` debits your org balance — one debit per request, no matter how many internal model calls auto's plan makes. An empty balance raises `InsufficientCreditsError` (402) at call time. Top-up is browser-only.

## list

```python
def list(self) -> ModelList
```

**Route:** `GET /v1/models`

Returns a [`ModelList`](#modellist) of the callable model ids — the single `"auto"` entry. There are no parameters and no pagination.

```python
from pareta import Pareta

with Pareta.from_env() as pa:          # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
    models = pa.models.list()          # ModelList

    for m in models:                   # ModelList is directly iterable
        print(m.id, "·", m.owned_by)   # auto · pareta
```

`m.id` is exactly what you feed to inference. Listing and calling compose directly, which is the contract generic OpenAI tooling relies on:

```python
with Pareta.from_env() as pa:
    first = pa.models.list().data[0]   # the "auto" entry
    resp = pa.chat.completions.create(
        model=first.id,                # == "auto"
        messages=[{"role": "user", "content": "What is the invoice total?"}],
    )
    print(resp.choices[0].message.content)
```

### Async

`AsyncModels.list` is the same call, awaited:

```python
import asyncio
from pareta import AsyncPareta

async def main():
    async with AsyncPareta.from_env() as pa:
        models = await pa.models.list()
        for m in models:
            print(m.id, m.owned_by)

asyncio.run(main())
```

## ModelList

The return value of `list()`. It wraps the raw `{"data": [...]}` payload and behaves like a lightweight collection.

| Member | Type | Description |
| --- | --- | --- |
| `data` | `list[Model]` | The callable model entries — `"auto"`. |
| `__iter__()` | `Iterable[Model]` | Iterate models directly: `for m in models`. |
| `__len__()` | `int` | Number of entries: `len(models)`. |

```python
models = pa.models.list()

len(models)          # int
models.data          # list[Model]: the underlying list
list(models)         # same elements, via __iter__
[m.id for m in models]
```

`ModelList` is not indexable directly. To grab one element, go through `.data` (`models.data[0]`) or iterate.

Like every Pareta response object, it keeps the raw server JSON. Reach anything not surfaced as a property with `models.to_dict()` or `models["data"]`.

## Model

One element of `ModelList.data`. It is the OpenAI-compatible model record, so it carries only three fields.

| Property | Type | Description |
| --- | --- | --- |
| `id` | `str \| None` | The model id — `"auto"`. Pass it as `chat.completions.create(model=...)`. |
| `owned_by` | `str \| None` | `"pareta"`. |
| `created` | `int \| None` | Unix timestamp (seconds). |

```python
for m in pa.models.list():
    print(m.id)         # str | None: usable as the `model` arg in inference
    print(m.owned_by)   # str | None: "pareta"
    print(m.created)    # int | None: Unix seconds

    m.to_dict()         # full raw record, nothing lost behind the typed layer
```

The ids of the open-weights models behind `"auto"` never cross into the SDK. That is by design: routing happens server-side, per request, and hardware is resolved for you. See [Core concepts](../guide/core-concepts.md) for the routing and metering model.

## Errors

`list()` makes a plain authenticated GET, so the failure modes are the standard ones. A bad or missing key raises `AuthenticationError` (401); transient 429/5xx and connection timeouts are retried automatically (`max_retries`, default 2) before surfacing as `RateLimitError`, `APIStatusError`, or `APITimeoutError`. All inherit from `ParetaError`.

```python
from pareta import Pareta, AuthenticationError, ParetaError

try:
    with Pareta.from_env() as pa:
        models = pa.models.list()
except AuthenticationError:
    print("Check PARETA_API_KEY (it should start with pareta_sk_).")
except ParetaError as e:
    print("Listing failed:", e)
```

`InsufficientCreditsError` (402) does **not** fire here. Listing is free; metering happens when you call a model. See [Errors and retries](../guide/errors-and-retries.md) for the full hierarchy.

## See also

- [Running inference](../guide/inference.md) — pass `"auto"` to `chat.completions.create`.
- [`tasks`](./tasks.md) — browse and match the catalog of tasks auto routes across.
- [Core concepts](../guide/core-concepts.md) — the routing brain, hidden models, and org-balance metering.
