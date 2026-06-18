# models

`client.models` lists the models you can call right now. It is the OpenAI-compatible model index: `GET /v1/models` returning only your deployed, url-bearing endpoints. Use it to discover the ids you pass to [`chat.completions.create(model=...)`](../guide/inference.md).

This is the inference-time view of your fleet. It deliberately shows less than [`endpoints.list()`](../guide/deploying-endpoints.md): only live, callable endpoints, and only the three fields the OpenAI `/v1/models` contract defines. When you want lifecycle and operations (deploy, start, stop, metrics), use the [endpoints](../guide/deploying-endpoints.md) namespace instead.

Two platform truths show up here:

- **Models are per-task aliases.** A `Model.id` is a callable endpoint id; the underlying open-weights model id never reaches you. The backend resolves it. You never see or pick a GPU.
- **Calling a model is metered.** Listing is free, but each completion against an id from this list debits your org balance. An empty balance raises `InsufficientCreditsError` (402) at call time. Top-up is browser-only.

## list

```python
def list(self) -> ModelList
```

**Route:** `GET /v1/models`

Returns a [`ModelList`](#modellist) of every deployed endpoint that has a live inference URL. Endpoints that are stopped, cold, or still deploying are omitted, because they have no `url` and so cannot be called. There are no parameters and no pagination.

```python
from pareta import Pareta

with Pareta.from_env() as pa:          # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
    models = pa.models.list()          # ModelList

    print(len(models), "callable models")
    for m in models:                   # ModelList is directly iterable
        print(m.id, "·", m.owned_by)
```

`m.id` is exactly what you feed to inference. Listing and calling compose directly:

```python
with Pareta.from_env() as pa:
    models = pa.models.list()
    if len(models) == 0:
        raise SystemExit("No live endpoints. Deploy one first: pa.endpoints.deploy(task=...)")

    first = models.data[0]             # a Model
    resp = pa.chat.completions.create(
        model=first.id,                # the callable endpoint id
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
| `data` | `list[Model]` | The deployed, callable models. |
| `__iter__()` | `Iterable[Model]` | Iterate models directly: `for m in models`. |
| `__len__()` | `int` | Number of callable models: `len(models)`. |

```python
models = pa.models.list()

len(models)          # int: how many endpoints are live and callable
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
| `id` | `str \| None` | The endpoint id. Pass it as `chat.completions.create(model=...)`. |
| `owned_by` | `str \| None` | `"pareta"` for your deployed open-weights endpoints, or a vendor name. |
| `created` | `int \| None` | Unix timestamp (seconds) when the endpoint was created. |

```python
for m in pa.models.list():
    print(m.id)         # str | None: usable as the `model` arg in inference
    print(m.owned_by)   # str | None: "pareta" or a vendor name
    print(m.created)    # int | None: Unix seconds

    m.to_dict()         # full raw record, nothing lost behind the typed layer
```

`Model.id` is a per-task alias, not the real open-weights model id. That is by design: the underlying model id never crosses into the SDK. You deploy with a task and an alias and you call with the resulting endpoint id; hardware is resolved for you. See [Core concepts](../guide/core-concepts.md) for the aliasing and GPU-hiding model.

## How this differs from `endpoints.list()`

Both list your fleet, but they answer different questions.

| | `models.list()` | `endpoints.list()` |
| --- | --- | --- |
| Returns | `ModelList` of `Model` | `list[Endpoint]` |
| Includes | Only live, url-bearing endpoints | All endpoints the org can access (any status) |
| Fields | `id`, `owned_by`, `created` | `id`, `name`, `model`, `status`, `task`, `url`, `is_live` |
| Use for | "What can I call right now?" | Deploy, start, stop, delete, inspect, metrics |
| Shape | OpenAI-compatible | Pareta-native |

If `models.list()` returns fewer entries than you expect, an endpoint is probably not live. Check its status with [`endpoints.list()`](../guide/deploying-endpoints.md) or `endpoints.retrieve(endpoint_id)`, and `endpoints.start(endpoint_id)` it if it is stopped.

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

- [Running inference](../guide/inference.md) — pass a `Model.id` to `chat.completions.create`.
- [Deploying endpoints](../guide/deploying-endpoints.md) — create the endpoints that show up here.
- [Discovering tasks](../guide/discovery.md) — find a task and its recommended model before you deploy.
- [Core concepts](../guide/core-concepts.md) — per-task aliases, hidden GPUs, and org-balance metering.
