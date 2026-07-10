# Migrating from the OpenAI SDK

Pareta inference is OpenAI-compatible. If you already call `chat.completions.create(...)` through the `openai` SDK, you do not have to rewrite that code to run on Pareta. Point the OpenAI client at your Pareta base URL with a `pareta_sk_` key, set `model="auto"`, and your existing inference keeps working — with Pareta planning each request, routing it to benchmark-proven open specialists, and falling back to a frontier model when that's the right call.

This page covers two things:

1. **Keep using `openai` for inference**, the smallest possible diff: change `base_url`, `api_key`, and `model="auto"`. No deploy step, nothing to provision.
2. **Switch to the `pareta` SDK** for the things OpenAI does not do: evaluating `"auto"` against frontier baselines on your own data, reading your auto metrics, and matching intent to the task catalog.

The mental model: OpenAI gives you one client for one purpose (inference against a model you name). Pareta splits that into a data plane (inference, OpenAI-compatible, where `"auto"` names the routing brain rather than a fixed model) and a control plane (evaluate / match / monitor, which is Pareta-native). You migrate the data plane by changing three strings; you adopt the control plane when you want proof.

## The one-diff migration

The whole migration, as the diff you'd actually commit — removed lines are your OpenAI code today, added lines are the Pareta version:

**Python**

```diff
 from openai import OpenAI

-client = OpenAI(api_key="sk-...")  # talks to api.openai.com
+client = OpenAI(
+    api_key="pareta_sk_...",                 # a Pareta key, not an OpenAI key
+    base_url="https://api.pareta.ai/v1",     # note the /v1 suffix
+)
 resp = client.chat.completions.create(
-    model="gpt-4o-mini",
+    model="auto",                            # the routing brain, not a fixed model
     messages=[{"role": "user", "content": "Extract the invoice total: ..."}],
 )
 print(resp.choices[0].message.content)
```

**TypeScript**

```diff
 import OpenAI from "openai";

-const client = new OpenAI({ apiKey: "sk-..." }); // talks to api.openai.com
+const client = new OpenAI({
+  apiKey: "pareta_sk_...",                 // a Pareta key, not an OpenAI key
+  baseURL: "https://api.pareta.ai/v1",     // note the /v1 suffix
+});
 const resp = await client.chat.completions.create({
-  model: "gpt-4o-mini",
+  model: "auto",                           // the routing brain, not a fixed model
   messages: [{ role: "user", content: "Extract the invoice total: ..." }],
 });
 console.log(resp.choices[0].message.content);
```

Three things changed, nothing else:

- **`api_key`** is a `pareta_sk_...` key (mint it in the dashboard; key management is browser-only). It rides in the same `Authorization: Bearer` header the OpenAI client already sends.
- **`base_url`** is `https://api.pareta.ai/v1`. The OpenAI client appends `/chat/completions` to whatever base URL you give it, and Pareta serves the route at `/v1/chat/completions`, so the base URL must include the `/v1` suffix.
- **`model`** is the literal string `"auto"` — Pareta's routing brain, and the only model id. There is nothing to deploy or provision first, and no model to pick: "which model?" is the question Pareta answers for you, per request.

Streaming, `temperature`, `max_tokens`, `top_p`, `stop`, system messages, and the response shape (`resp.choices[0].message.content`, `resp.usage`) all behave exactly as they do against OpenAI, because the wire format is the same. Your existing response-parsing code does not change.

### Why this works

Pareta serves inference in the vLLM OpenAI-compatible format: data-only SSE for streams, the same request body, the same `ChatCompletion` / `ChatCompletionChunk` JSON shapes. The OpenAI SDK cannot tell the difference. The only Pareta-specific facts that leak through are the key prefix and the fact that `"auto"` names the routing brain rather than a hosted vendor model.

## Where the OpenAI SDK stops

The OpenAI SDK is built around calling a model you name. Pareta's reason to exist is the opposite: `"auto"` answers "which model?" for you, per request — and the SDK's job is to let you prove that routing on your own data, watch what it costs, and check what it covers. None of that has an OpenAI-SDK equivalent:

| You want to... | OpenAI SDK | Pareta SDK |
| --- | --- | --- |
| Call a model | `client.chat.completions.create(...)` | works as-is (OpenAI-compatible) |
| Benchmark `"auto"` vs frontier baselines on your data | not available | `pa.evals.runs.create(...)` |
| Find the grading contract for your eval data | not available | `pa.tasks.match(...)` |
| Watch requests, success rate, spend, projected savings | not available | `pa.auto.metrics()` |
| Run one prompt against a frontier vendor, side-by-side | not available | `pa.auto.compare_frontier(...)` |
| List callable model ids | `client.models.list()` (vendor catalog) | `pa.models.list()` (the single `"auto"` entry) |

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
        model="auto",
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
  model: "auto",
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
    model="auto",              # the routing brain instead of a vendor model name
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
  model: "auto",              // the routing brain instead of a vendor model name
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
    model="auto",
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
  model: "auto",
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

In the OpenAI SDK, `client.models.list()` returns the vendor's hosted catalog — the menu you pick from. In Pareta there is no menu: `pa.models.list()` returns exactly one entry, `"auto"`, because which model serves a request is decided per request, behind that id. The call exists so OpenAI-style tooling that discovers ids by listing keeps working:

**Python**

```python
for m in pa.models.list():
    print(m.id, m.owned_by)   # auto pareta — m.id is callable as `model=...`
```

**TypeScript**

```typescript
const models = await pa.models.list();
for (const m of models) {
  console.log(m.id, m.ownedBy); // auto pareta — m.id is callable as `model: ...`
}
```

## Three platform facts that have no OpenAI equivalent

These are the differences that matter once you are past the inference call. They are not gotchas; they are the point of the platform.

### 1. There is no model picker, and GPUs are hidden

There is no "pick gpt-4o" step — and no Pareta equivalent of one. Every request goes to `"auto"`, and Pareta plans it, routes each part to benchmark-proven open specialists, verifies checkable outputs, and falls back to a frontier model when that's the right call. Nothing to deploy, no hardware knob anywhere in the API: no GPU, tensor-parallel, quantization, or run-mode setting. Serving is Pareta's problem.

To see *what* auto routes across, browse the task catalog with `pa.tasks.list()` or map a sentence of intent onto it with `pa.tasks.match(...)` — see [Discovery](#discovery-checking-what-auto-covers) below.

### 2. Open-weights models stay behind `"auto"`

OpenAI model names are global and stable (`gpt-4o-mini`). Pareta's open-weights models never cross into the SDK at all — no HuggingFace repo ids, no model roster to browse. The only place model names appear in the clear is the frontier (vendor) side: eval baselines and `pa.auto.compare_frontier(model=...)` take public vendor ids (`gpt-5.5`, `claude-sonnet-4-6`, ...), because those are public names. Everything open-weights is a routing decision behind the one id you already pass.

### 3. Inference and evals are metered against your org balance

OpenAI bills the account behind the key out of band; you never see a price on the response. On Pareta, the same key debits a shared **org balance**, and the eval path surfaces the cost back to you in dollars.

- **Inference debits on success — one debit per request.** Each completed `chat.completions.create()` call debits the org balance once, no matter how many internal model calls auto's plan makes; orchestration overhead is Pareta's cost, not yours. Cost is metered server-side, not returned on the completion object.
- **Evals debit for auto + frontier compute**, and the run reports its spend: `run.cost` is a `Decimal` in dollars (floored to whole cents per Pareta's billing convention, for example 5 micro-USD reads `Decimal("0.00")`), with the raw integer on `run.cost_micro_usd`. A FAILED run is not charged.
- **A zero balance raises `InsufficientCreditsError` (402)** on both the inference and eval paths.
- **Top-up is browser-only.** The SDK consumes credit; it never exposes balance, payment methods, or a way to add funds. There is no API call for it.

**Python**

```python
from pareta import InsufficientCreditsError

try:
    resp = pa.chat.completions.create(
        model="auto",
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
    model: "auto",
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

The biggest reason to reach for the `pareta` SDK rather than the bare `openai` client: before you trust the routing in production, run your own data through `"auto"` and frontier baselines and read back per-contender quality and cost. There is no OpenAI-SDK analog.

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
    models=["auto"],          # the candidate you ship
    frontier="benchmarked",   # frontier models benchmarked on this task, as baselines
    wait=True,                # poll until terminal, then return
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
  models: ["auto"],          // the candidate you ship
  frontier: "benchmarked",   // frontier models benchmarked on this task, as baselines
  wait: true,                // poll until terminal, then return
});

console.log(run.status);     // "completed" or "failed"
console.log(run.cost);       // dollar string, floored to cents ("1.23")

for (const r of run.results) {
  console.log(r.modelId, r.kind, r.qualityMean, r.meanCostMicroUsd);
}
```

`frontier=` accepts `None`/`"none"` (no baselines), `"all"` (every frontier model for the task), `"benchmarked"` (the frontier models with a benchmark score on the task), or an explicit list of frontier ids. You can pull the roster with `pa.evals.frontier_models(task="contract-key-fields")` to see what is available, including which entries are `vision`-capable and which are `benchmarked` on that task. See [Evaluate on your data](./evaluate-on-your-data.md) for eval sets, document uploads, and the async path.

## Discovery: checking what auto covers

Benchmarking on your own data needs a grading contract, and `tasks.match(...)` finds it from a plain-English description of your dataset — the `task` an eval run validates rows against and scores with. Again, no OpenAI equivalent:

**Python**

```python
match = pa.tasks.match("pull key fields out of vendor contracts", top_k=5)
if match.type == "task" and match.chosen:
    task_id = match.chosen.task_id          # a benchmarked task, e.g. for evals.runs.create(task=...)
    print("best task:", task_id, "confidence:", match.confidence)
```

**TypeScript**

```typescript
const match = await pa.tasks.match("pull key fields out of vendor contracts", { topK: 5 });
if (match.matched && match.chosen?.taskId) {
  const taskId = match.chosen.taskId;       // a benchmarked task, e.g. for evals.runs.create({ task })
  console.log("best task:", taskId, "confidence:", match.chosen.confidence);
}
```

`match.type` (Python) is one of `"task"` (a benchmarked task fit), `"capability"` (a general lane like chat or coding), `"unsupported"` (a correct "no", not an error), or `"none"`. Browse the full catalog with `pa.tasks.list()` or one task with `pa.tasks.retrieve(task_id)`. `match()` raises `ValueError` on an empty query.

## Errors: from OpenAI exceptions to Pareta exceptions

If you keep the `openai` client, you keep OpenAI's exception types. If you adopt the `pareta` SDK, errors become Pareta exceptions, all subclasses of `ParetaError`, mapped per HTTP status:

**Python**

```python
from pareta import (
    ParetaError,               # base class
    AuthenticationError,       # 401 - bad or missing key
    InsufficientCreditsError,  # 402 - org out of credit; top up in the dashboard
    PermissionDeniedError,     # 403
    NotFoundError,             # 404 - unknown task or resource id
    RateLimitError,            # 429 - throttled (auto-retried)
    EndpointNotReadyError,     # 503 - a serving backend is warming (auto-retried)
    BadRequestError,           # 400/422 - malformed request
)
```

**TypeScript**

```typescript
import {
  ParetaError,              // base class
  AuthenticationError,      // 401 - bad or missing key
  InsufficientCreditsError, // 402 - org out of credit; top up in the dashboard
  PermissionDeniedError,    // 403
  NotFoundError,            // 404 - unknown task or resource id
  RateLimitError,           // 429 - throttled (auto-retried)
  EndpointNotReadyError,    // 503 - a serving backend is warming (auto-retried)
  BadRequestError,          // 400/422 - malformed request
} from "pareta";
```

The rough correspondence to OpenAI: `AuthenticationError` ↔ 401, `RateLimitError` ↔ 429, `BadRequestError` ↔ 400/422, `NotFoundError` ↔ 404. The two without OpenAI analogs are `InsufficientCreditsError` (402, the org-balance gate above) and `EndpointNotReadyError` (503, a serving backend behind auto is warming or briefly unavailable; the client retries 503s automatically, so if it surfaces, wait briefly and retry the call). The client auto-retries 429s and transient 5xx/timeouts with exponential backoff (`max_retries`, default 2).

## Async

`AsyncPareta` mirrors the sync client exactly, same arguments, same response shapes, with `async def` methods and async iterators for streams:

**Python**

```python
import asyncio
from pareta import AsyncPareta


async def main():
    async with AsyncPareta.from_env() as pa:
        resp = await pa.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": "Extract the total: ..."}],
        )
        print(resp.choices[0].message.content)

        # Streaming: await create() once to get the async iterator, then `async for`.
        stream = await pa.chat.completions.create(
            model="auto",
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
  model: "auto",
  messages: [{ role: "user", content: "Extract the total: ..." }],
});
console.log(resp.choices[0].message.content);

// Streaming: create({ stream: true }) returns the async iterator directly.
const stream = pa.chat.completions.create({
  model: "auto",
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
- [ ] **Staying on `openai`?** Set `base_url="https://api.pareta.ai/v1"`, `api_key="pareta_sk_..."`, and `model="auto"`. Done — nothing to deploy.
- [ ] **Adopting `pareta`?** Swap `OpenAI(...)` for `Pareta.from_env()` and `client.chat...` for `pa.chat...`. Inference args and response shapes are unchanged.
- [ ] Benchmark it: run your own data through `pa.evals` with `models=["auto"]` and a frontier baseline before you commit.
- [ ] Map your error handling: 402 becomes `InsufficientCreditsError`, 503 becomes `EndpointNotReadyError`.
- [ ] Keep your org balance funded (top-up is browser-only); a zero balance stops both inference and evals.
- [ ] (Optional) Watch the routing pay for itself: `pa.auto.metrics()` — requests, success rate, spend, projected savings vs frontier.

## Next steps

- [Evaluate on your data](./evaluate-on-your-data.md), the proof step: `"auto"` vs frontier baselines on your own rows.
- [Streaming chat completions](./streaming-chat.md), the full streaming and async story.
- [Cost & quality monitoring](./cost-and-metrics.md), watch your `"auto"` traffic with `auto.metrics()`.
