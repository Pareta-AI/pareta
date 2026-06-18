# Migrating from the OpenAI SDK

Pareta inference is OpenAI-compatible. If you already call `chat.completions.create(...)` through the `openai` SDK, you do not have to rewrite that code to run on Pareta. Point the OpenAI client at your Pareta base URL with a `pareta_sk_` key and your existing inference keeps working against a Pareta endpoint.

This page covers two things:

1. **Keep using `openai` for inference**, the smallest possible diff: change `base_url` and `api_key`, pass an endpoint id as `model`.
2. **Switch to the `pareta` SDK** for the things OpenAI does not do: deploying endpoints, evaluating models against frontier baselines on your own data, and discovering tasks.

The mental model: OpenAI gives you one client for one purpose (inference). Pareta splits that into a data plane (inference, which is OpenAI-compatible) and a control plane (deploy / eval / discover, which is Pareta-native). You migrate the data plane by changing two strings; you adopt the control plane when you want it.

## The one-diff migration

You have this today:

**Python**

```python
from openai import OpenAI

client = OpenAI(api_key="sk-...")  # talks to api.openai.com
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Extract the invoice total: ..."}],
)
print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
import OpenAI from "openai";

const client = new OpenAI({ apiKey: "sk-..." }); // talks to api.openai.com
const resp = await client.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "Extract the invoice total: ..." }],
});
console.log(resp.choices[0].message.content);
```

Change the client construction and the `model`:

**Python**

```python
from openai import OpenAI

client = OpenAI(
    api_key="pareta_sk_...",                 # a Pareta key, not an OpenAI key
    base_url="https://api.pareta.ai/v1",     # note the /v1 suffix
)
resp = client.chat.completions.create(
    model="ep_contract_kie",                 # a Pareta endpoint id, not "gpt-4o-mini"
    messages=[{"role": "user", "content": "Extract the invoice total: ..."}],
)
print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "pareta_sk_...",                 // a Pareta key, not an OpenAI key
  baseURL: "https://api.pareta.ai/v1",     // note the /v1 suffix
});
const resp = await client.chat.completions.create({
  model: "ep_contract_kie",                // a Pareta endpoint id, not "gpt-4o-mini"
  messages: [{ role: "user", content: "Extract the invoice total: ..." }],
});
console.log(resp.choices[0].message.content);
```

Three things changed, nothing else:

- **`api_key`** is a `pareta_sk_...` key (mint it in the dashboard; key management is browser-only). It rides in the same `Authorization: Bearer` header the OpenAI client already sends.
- **`base_url`** is `https://api.pareta.ai/v1`. The OpenAI client appends `/chat/completions` to whatever base URL you give it, and Pareta serves the route at `/v1/chat/completions`, so the base URL must include the `/v1` suffix.
- **`model`** is a Pareta endpoint id (for example `ep_contract_kie`), the value you get back from `endpoints.deploy(...).id`. It is not an OpenAI model name. See [Deploy a model and call it](./deploy-and-infer.md) for how to get one.

Streaming, `temperature`, `max_tokens`, `top_p`, `stop`, system messages, and the response shape (`resp.choices[0].message.content`, `resp.usage`) all behave exactly as they do against OpenAI, because the wire format is the same. Your existing response-parsing code does not change.

### Why this works

Pareta serves inference in the vLLM OpenAI-compatible format: data-only SSE for streams, the same request body, the same `ChatCompletion` / `ChatCompletionChunk` JSON shapes. The OpenAI SDK cannot tell the difference. The only Pareta-specific facts that leak through are the key prefix and the fact that `model` names an endpoint you deployed rather than a hosted vendor model.

## Where the OpenAI SDK stops

The OpenAI SDK is built around calling models that already exist on a vendor's servers. Pareta's reason to exist is the opposite: you bring a task, Pareta stands up an open-weights endpoint to serve it, and you measure it against frontier models on your own data before you commit. None of that has an OpenAI-SDK equivalent:

| You want to... | OpenAI SDK | Pareta SDK |
| --- | --- | --- |
| Call a model | `client.chat.completions.create(...)` | works as-is (OpenAI-compatible) |
| Stand up your own serving endpoint | not available | `pa.endpoints.deploy(task=..., model=...)` |
| Compare candidate models on your data | not available | `pa.evals.runs.create(...)` |
| Compare open models vs frontier baselines | not available | `frontier=` on the eval run |
| Find the right task / model for an intent | not available | `pa.tasks.match(...)`, `pa.tasks.leaderboard(...)` |
| List your callable endpoints | `client.models.list()` (vendor catalog) | `pa.models.list()` (your endpoints) |

For everything in the bottom rows, install and use the `pareta` SDK. It also speaks OpenAI-compatible inference through `pa.chat.completions.create(...)`, so once you adopt it you can drop the second `openai` client entirely and use one library for both planes.

## Switching to the `pareta` SDK

Install it and construct the client from the environment. `Pareta.from_env()` reads `PARETA_API_KEY` and the optional `PARETA_BASE_URL` (default `https://api.pareta.ai`, no `/v1` suffix, the SDK adds route prefixes itself):

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()  # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv(); // reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
```

The Python client is a context manager, which releases the HTTP connection cleanly:

**Python**

```python
with Pareta.from_env() as pa:
    resp = pa.chat.completions.create(
        model="ep_contract_kie",
        messages=[{"role": "user", "content": "Hello"}],
    )
    print(resp.choices[0].message.content)
```

**TypeScript**

```typescript
// No context manager in TS — there is no owned connection to close; just construct
// the client and await the call.
const pa = Pareta.fromEnv();
const resp = await pa.chat.completions.create({
  model: "ep_contract_kie",
  messages: [{ role: "user", content: "Hello" }],
});
console.log(resp.choices[0].message.content);
```

### Inference looks the same, with one rename

The OpenAI call maps one-to-one onto the Pareta call. The arguments and the response shape are identical:

**Python**

```python
# OpenAI:
resp = openai_client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "..."}],
    temperature=0,
    max_tokens=512,
)

# Pareta:
resp = pa.chat.completions.create(
    model="ep_contract_kie",   # endpoint id instead of a vendor model name
    messages=[{"role": "user", "content": "..."}],
    temperature=0,             # extra OpenAI params pass straight through
    max_tokens=512,
)

choice = resp.choices[0]
print(choice.message.content)
print(choice.finish_reason)       # "stop", "length", ...
print(resp.usage.total_tokens)    # prompt_tokens + completion_tokens
```

**TypeScript**

```typescript
// OpenAI:
const resp = await openaiClient.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "..." }],
  temperature: 0,
  max_tokens: 512,
});

// Pareta:
const resp = await pa.chat.completions.create({
  model: "ep_contract_kie",   // endpoint id instead of a vendor model name
  messages: [{ role: "user", content: "..." }],
  temperature: 0,             // extra OpenAI params pass straight through
  max_tokens: 512,
});

const choice = resp.choices[0];
console.log(choice.message.content);
console.log(choice.finishReason);      // "stop", "length", ...
console.log(resp.usage.totalTokens);   // promptTokens + completionTokens
```

`model` and `messages` are both required; passing either falsy raises `ValueError` before any request goes out. Any extra OpenAI keyword argument (`temperature`, `max_tokens`, `top_p`, `stop`, `frequency_penalty`, ...) is forwarded verbatim as a request-body field.

Streaming is the same shape as OpenAI too. `stream=True` returns an iterator of `ChatCompletionChunk`, and the incremental text is on `chunk.choices[0].delta.content`:

**Python**

```python
for chunk in pa.chat.completions.create(
    model="ep_contract_kie",
    messages=[{"role": "user", "content": "Summarize this clause: ..."}],
    stream=True,
):
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
print()
```

**TypeScript**

```typescript
const stream = pa.chat.completions.create({
  model: "ep_contract_kie",
  messages: [{ role: "user", content: "Summarize this clause: ..." }],
  stream: true,
});
for await (const chunk of stream) {
  const delta = chunk.choices[0].delta.content;
  if (delta) process.stdout.write(delta);
}
console.log();
```

See [Streaming chat completions](./streaming-chat.md) for the full streaming details and the async variant.

### Listing models means something different

In the OpenAI SDK, `client.models.list()` returns the vendor's hosted catalog. In Pareta, `pa.models.list()` returns **your org's deployed, callable endpoints**, the OpenAI-compatible subset with a live `url`. Each `Model.id` is an endpoint id you can pass straight to `chat.completions.create(model=...)`:

**Python**

```python
for m in pa.models.list():
    print(m.id, m.owned_by)   # m.id is callable as `model=...`
```

**TypeScript**

```typescript
const models = await pa.models.list();
for (const m of models) {
  console.log(m.id, m.ownedBy); // m.id is callable as `model: ...`
}
```

If you want full endpoint records (status, task, the deployed model alias) rather than the OpenAI-compatible subset, use `pa.endpoints.list()` instead, which returns `Endpoint` objects.

## Three platform facts that have no OpenAI equivalent

These are the differences that matter once you are past the inference call. They are not gotchas; they are the point of the platform.

### 1. You deploy your own endpoint, and GPUs are hidden

There is no "pick gpt-4o" step. You pick a **task** and let Pareta serve an open-weights model for it. `deploy()` takes a task and a model and nothing about hardware, no GPU, tensor-parallel, quantization, or run-mode knob. Pareta resolves the serving class from its registry.

**Python**

```python
# Deploy the recommended open model for a task, block until it is live.
endpoint = pa.endpoints.deploy(
    task="contract-key-fields",   # required: a subtask id from the catalog
    model="recommended",          # default; resolves to the task's curated pick
    wait=True,                    # block until live and return the Endpoint
)
print(endpoint.id)        # the value you pass as `model` to chat.completions.create
print(endpoint.is_live)   # True after a wait=True deploy
```

**TypeScript**

```typescript
// Deploy the recommended open model for a task, block until it is live.
const endpoint = await pa.endpoints.deploy({
  task: "contract-key-fields",   // required: a subtask id from the catalog
  model: "recommended",          // default; resolves to the task's curated pick
  wait: true,                    // block until live and return the Endpoint
});
console.log(endpoint.id);        // the value you pass as `model` to chat.completions.create
console.log(endpoint.isLive);    // true after a wait: true deploy
```

`endpoint.id` (the name) is what `chat.completions.create(model=...)` expects, not `endpoint.model`, which is the per-task alias of the weights that were deployed. Full walkthrough in [Deploy a model and call it](./deploy-and-infer.md).

### 2. Models are per-task aliases, not raw weight ids

OpenAI model names are global and stable (`gpt-4o-mini`). Pareta open-weights models are exposed as **per-task public aliases**; the real open-weights ids never cross into the SDK. So `endpoints.deploy(model=...)`, the rows in `pa.tasks.leaderboard(task_id)`, `endpoint.model`, and `result.model_id` on an eval run are all aliases. Frontier (vendor) ids, OpenAI, Anthropic, and so on, are passed in the clear, because those are public vendor model names. The practical upshot: pass `model="recommended"` (or a task's alias) to deploy, and let Pareta resolve it; do not try to pass a HuggingFace repo id.

### 3. Inference and evals are metered against your org balance

OpenAI bills the account behind the key out of band; you never see a price on the response. On Pareta, the same key debits a shared **org balance**, and the eval path surfaces the cost back to you in dollars.

- **Inference debits on success.** Each completed `chat.completions.create()` call debits the org balance. Cost is metered server-side, not returned on the completion object.
- **Evals debit for open + frontier compute**, and the run reports its spend: `run.cost` is a `Decimal` in dollars (floored to whole cents per Pareta's billing convention, for example 5 micro-USD reads `Decimal("0.00")`), with the raw integer on `run.cost_micro_usd`.
- **A zero balance raises `InsufficientCreditsError` (402)** on both the inference and eval paths.
- **Top-up is browser-only.** The SDK consumes credit; it never exposes balance, payment methods, or a way to add funds. There is no API call for it.

**Python**

```python
from pareta import InsufficientCreditsError

try:
    resp = pa.chat.completions.create(
        model="ep_contract_kie",
        messages=[{"role": "user", "content": "..."}],
    )
except InsufficientCreditsError:
    print("Org balance is empty. Top up in the dashboard, then retry.")
```

**TypeScript**

```typescript
import { Pareta, InsufficientCreditsError } from "pareta";

try {
  const resp = await pa.chat.completions.create({
    model: "ep_contract_kie",
    messages: [{ role: "user", content: "..." }],
  });
} catch (e) {
  if (e instanceof InsufficientCreditsError) {
    console.log("Org balance is empty. Top up in the dashboard, then retry.");
  } else {
    throw e;
  }
}
```

Note that this error reaches the OpenAI client too: if you stayed on the one-diff `openai`-SDK path, a 402 surfaces there as an OpenAI status error rather than as `pareta.InsufficientCreditsError`. Mapping it to a typed exception is one more reason to adopt the `pareta` SDK.

## Evaluate before you commit (the OpenAI SDK can't do this)

The biggest reason to reach for the `pareta` SDK rather than the bare `openai` client: before you wire a model into production, run your own data through a set of candidate open models and frontier baselines and read back quality and cost. There is no OpenAI-SDK analog.

**Python**

```python
from pareta import Pareta

pa = Pareta.from_env()

run = pa.evals.runs.create(
    task="contract-key-fields",
    items=[
        {"input": "...", "expected": "..."},
        {"input": "...", "expected": "..."},
    ],
    models=["contract-kie-1", "contract-kie-2"],  # per-task open-model aliases
    frontier="benchmarked",                       # frontier baselines on this task's leaderboard
    wait=True,                                     # poll until terminal, then return
)

print(run.status)            # "completed" or "failed"
print(run.cost)              # Decimal dollars (floored to cents)

for r in run.results:
    print(r.model_id, r.kind, r.quality_mean, r.mean_cost_micro_usd)
```

**TypeScript**

```typescript
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

const run = await pa.evals.runs.create({
  task: "contract-key-fields",
  items: [
    { input: "...", expected: "..." },
    { input: "...", expected: "..." },
  ],
  models: ["contract-kie-1", "contract-kie-2"], // per-task open-model aliases
  frontier: "benchmarked",                      // frontier baselines on this task's leaderboard
  wait: true,                                   // poll until terminal, then return
});

console.log(run.status);     // "completed" or "failed"
console.log(run.cost);       // dollar string, floored to cents ("1.23")

for (const r of run.results) {
  console.log(r.modelId, r.kind, r.qualityMean, r.meanCostMicroUsd);
}
```

`frontier=` accepts `None`/`"none"` (no baselines), `"all"` (every frontier model for the task), `"benchmarked"` (the frontier models on the task's leaderboard), or an explicit list of frontier ids. You can pull the roster with `pa.evals.frontier_models(task="contract-key-fields")` to see what is available, including which entries are `vision`-capable and which are `benchmarked` on that task. See the evaluation walkthrough for eval sets, document uploads, and the async path.

## Discovery: turning intent into a task

If you do not yet know which task id to deploy or eval against, the `tasks` resource maps free-text intent onto the catalog. Again, no OpenAI equivalent:

**Python**

```python
match = pa.tasks.match("pull key fields out of vendor contracts", top_k=5)
if match.matched and match.chosen:
    task_id = match.chosen.task_id
    print("best task:", task_id, "confidence:", match.chosen.confidence)

# Once you have a task id, see what "recommended" will deploy and how models rank:
print(pa.tasks.recommended(task_id))      # the deployable alias deploy(model=...) will use
board = pa.tasks.leaderboard(task_id)
for entry in board.models:
    print(entry.name, entry.kind, entry.quality, entry.cost_per_request_micro_usd)
```

**TypeScript**

```typescript
const match = await pa.tasks.match("pull key fields out of vendor contracts", { topK: 5 });
if (match.matched && match.chosen?.taskId) {
  const taskId = match.chosen.taskId;
  console.log("best task:", taskId, "confidence:", match.chosen.confidence);

  // Once you have a task id, see what "recommended" will deploy and how models rank:
  console.log(await pa.tasks.recommended(taskId)); // the deployable alias deploy(model: ...) will use
  const board = await pa.tasks.leaderboard(taskId);
  for (const entry of board.models) {
    console.log(entry.name, entry.kind, entry.quality, entry.costPerRequestMicroUsd);
  }
}
```

`match()` raises `ValueError` on an empty query. `recommended()` and `leaderboard()` are available on the synchronous `tasks` resource.

## Errors: from OpenAI exceptions to Pareta exceptions

If you keep the `openai` client, you keep OpenAI's exception types. If you adopt the `pareta` SDK, errors become Pareta exceptions, all subclasses of `ParetaError`, mapped per HTTP status:

**Python**

```python
from pareta import (
    ParetaError,               # base class; also raised on a failed deploy
    AuthenticationError,       # 401 - bad or missing key
    InsufficientCreditsError,  # 402 - org out of credit; top up in the dashboard
    PermissionDeniedError,     # 403
    NotFoundError,             # 404 - unknown endpoint or task
    RateLimitError,            # 429 - throttled (auto-retried)
    EndpointNotReadyError,     # 503 - endpoint stopped, cold, or provider down
    BadRequestError,           # 400/422 - malformed request
)
```

**TypeScript**

```typescript
import {
  ParetaError,              // base class; also raised on a failed deploy
  AuthenticationError,      // 401 - bad or missing key
  InsufficientCreditsError, // 402 - org out of credit; top up in the dashboard
  PermissionDeniedError,    // 403
  NotFoundError,            // 404 - unknown endpoint or task
  RateLimitError,           // 429 - throttled (auto-retried)
  EndpointNotReadyError,    // 503 - endpoint stopped, cold, or provider down
  BadRequestError,          // 400/422 - malformed request
} from "pareta";
```

The rough correspondence to OpenAI: `AuthenticationError` ↔ 401, `RateLimitError` ↔ 429, `BadRequestError` ↔ 400/422, `NotFoundError` ↔ 404. The two without OpenAI analogs are `InsufficientCreditsError` (402, the org-balance gate above) and `EndpointNotReadyError` (503, raised when you call an endpoint that is stopped or still cold, start it with `pa.endpoints.start(endpoint_id)` and retry). The client auto-retries 429s and transient 5xx/timeouts with exponential backoff (`max_retries`, default 2).

## Async

`AsyncPareta` mirrors the sync client exactly, same arguments, same response shapes, with `async def` methods and async iterators for streams:

**Python**

```python
import asyncio
from pareta import AsyncPareta


async def main():
    async with AsyncPareta.from_env() as pa:
        resp = await pa.chat.completions.create(
            model="ep_contract_kie",
            messages=[{"role": "user", "content": "Extract the total: ..."}],
        )
        print(resp.choices[0].message.content)

        # Streaming: await create() once to get the async iterator, then `async for`.
        stream = await pa.chat.completions.create(
            model="ep_contract_kie",
            messages=[{"role": "user", "content": "Summarize: ..."}],
            stream=True,
        )
        async for chunk in stream:
            print(chunk.choices[0].delta.content or "", end="")
        print()


asyncio.run(main())
```

**TypeScript**

```typescript
// There is no AsyncPareta in TS — the one `Pareta` client is already async.
// Every I/O method returns a Promise (await it); streaming returns an
// AsyncIterable (for await … of it). The sync/async split simply doesn't exist.
import { Pareta } from "pareta";

const pa = Pareta.fromEnv();

const resp = await pa.chat.completions.create({
  model: "ep_contract_kie",
  messages: [{ role: "user", content: "Extract the total: ..." }],
});
console.log(resp.choices[0].message.content);

// Streaming: create({ stream: true }) returns the async iterator directly.
const stream = pa.chat.completions.create({
  model: "ep_contract_kie",
  messages: [{ role: "user", content: "Summarize: ..." }],
  stream: true,
});
for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0].delta.content || "");
}
console.log();
```

This is the same async shape the `openai` SDK uses (`AsyncOpenAI`, `await create(...)`, `async for chunk`), so async migrations are as small as the sync ones. In TypeScript there is no second client at all — `Pareta` is Promise-only, so there is nothing to migrate between sync and async.

## Migration checklist

- [ ] Mint a `pareta_sk_` key in the dashboard.
- [ ] Deploy an endpoint for your task and grab `endpoint.id`, see [Deploy a model and call it](./deploy-and-infer.md).
- [ ] **Staying on `openai`?** Set `base_url="https://api.pareta.ai/v1"`, `api_key="pareta_sk_..."`, and `model=<endpoint id>`. Done.
- [ ] **Adopting `pareta`?** Swap `OpenAI(...)` for `Pareta.from_env()` and `client.chat...` for `pa.chat...`. Inference args and response shapes are unchanged.
- [ ] Map your error handling: 402 becomes `InsufficientCreditsError`, 503 becomes `EndpointNotReadyError`.
- [ ] Keep your org balance funded (top-up is browser-only); a zero balance stops both inference and evals.

## Next steps

- [Deploy a model and call it](./deploy-and-infer.md), get the endpoint id you pass as `model`.
- [Streaming chat completions](./streaming-chat.md), the full streaming and async story.
