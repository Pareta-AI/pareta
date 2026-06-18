# Pareta Python SDK

`pareta` is the Python client for [Pareta](https://pareta.ai). It does four things:

- **Deploys open-weights models** as live endpoints. You name a task and a model; Pareta picks the GPU and serving config. There is no hardware knob.
- **Serves metered OpenAI-compatible inference.** A deployed endpoint speaks the OpenAI chat-completions wire format, so this SDK and the stock `openai` client are interchangeable against it.
- **Evaluates models on your own data.** Score open candidates and frontier baselines on your rows, then read per-model quality and cost.
- **Browses the benchmark catalog.** Match a sentence to a task, read its leaderboard, and find the model worth deploying.

A few platform truths shape the whole API:

- **GPUs are hidden.** `endpoints.deploy()` takes a task and a model, never hardware.
- **Models are per-task aliases.** Open-weights ids are masked to public aliases like `qwen-vl-2`. Real ids never cross the SDK boundary. Frontier (vendor) ids are in the clear.
- **Inference and evals are metered against your org balance.** A successful call debits credit. An empty balance raises `InsufficientCreditsError` (402). An eval run reports its billed total on `run.cost` (dollars). Top-up is browser-only; the SDK never touches billing.

## Install

```bash
pip install pareta        # or: uv add pareta / poetry add pareta
```

## Hello world

Mint a `pareta_sk_` key in the dashboard, export it as `PARETA_API_KEY`, then deploy and call a model:

```python
from pareta import Pareta

pa = Pareta.from_env()                                                  # reads PARETA_API_KEY
ep = pa.endpoints.deploy(task="contract-key-fields", model="recommended", wait=True)
resp = pa.chat.completions.create(
    model=ep.id,                                                        # the endpoint id
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
)
print(resp.choices[0].message.content)
```

## Guide

Start-to-finish, in reading order. See the [guide index](./guide/README.md).

- [Installation & authentication](./guide/installation.md) — install `pareta`, authenticate with a `pareta_sk_` key, make a first metered call.
- [Quickstart](./guide/quickstart.md) — deploy the recommended model and run inference end to end in about a dozen lines.
- [Core concepts](./guide/core-concepts.md) — tasks, open vs frontier models, per-task aliases, hidden hardware, metering, and the match to leaderboard to eval to deploy funnel.
- [Running inference](./guide/inference.md) — `chat.completions.create`, streaming, passthrough params, `models.list`, and metering errors.
- [Deploying & operating endpoints](./guide/deploying-endpoints.md) — `deploy` wait semantics, lifecycle, and `metrics`.
- [Finding the right model](./guide/discovery.md) — match intent, rank with `leaderboard`/`recommended`, list frontier baselines.
- [Evaluating on your own data](./guide/evaluation.md) — `evals.sets` and `evals.runs`, per-model quality/CIs/cost, and the metered run total.
- [Errors, retries & timeouts](./guide/errors-and-retries.md) — the `ParetaError` hierarchy, which errors to catch, and the retry policy.
- [Async usage](./guide/async.md) — `AsyncPareta`, async iteration, and fanning out with `asyncio.gather`.
- [Configuration](./guide/configuration.md) — `api_key`, `base_url`, timeouts, retries, custom `httpx` clients, and lifecycle.

## Examples

Copy-paste workflows for real jobs. See the [examples index](./examples/README.md).

- [Deploy a model and call it](./examples/deploy-and-infer.md) — the two-call deploy-then-infer workflow.
- [From a sentence to a deployed winner](./examples/find-and-deploy-best-model.md) — the full match to eval to deploy funnel.
- [Benchmark models on your own data](./examples/evaluate-on-your-data.md) — eval open candidates against frontier baselines and read `run.cost`.
- [Document extraction (PDF/image)](./examples/document-extraction.md) — the blob-task loop: upload documents, eval, deploy, infer.
- [Streaming chat completions](./examples/streaming-chat.md) — iterate `ChatCompletionChunk` objects and accumulate text.
- [Concurrent calls with AsyncPareta](./examples/concurrent-async.md) — fan out inference and eval calls with `asyncio.gather`.
- [Cost & quality monitoring](./examples/cost-and-metrics.md) — read what calls cost and watch a live endpoint with `endpoints.metrics()`.
- [Migrating from the OpenAI SDK](./examples/migrate-from-openai.md) — keep using `openai` against Pareta, and when to switch to `pareta`.

## Reference

Field-by-field API docs. See the [reference index](./reference/README.md).

- [Client](./reference/client.md) — `Pareta` and `AsyncPareta`: `from_env`, constructor params, lifecycle, and the five resource namespaces.
- [chat.completions](./reference/chat.md) — `chat.completions.create`, return types, streaming, and the error surface.
- [models](./reference/models.md) — `models.list()` and the `Model` fields.
- [endpoints](./reference/endpoints.md) — `deploy`/`list`/`retrieve`/`start`/`stop`/`delete`, the `Endpoint` object, and `metrics(id)`.
- [tasks](./reference/tasks.md) — `list`/`retrieve`/`match`/`leaderboard`/`recommended` and their response models.
- [evals](./reference/evals.md) — `evals.sets`, `evals.runs`, and `evals.frontier_models`.
- [Exceptions](./reference/exceptions.md) — the `ParetaError` hierarchy and status-to-class mapping.
- [Response types](./reference/types.md) — every response object plus the `.cost` vs `.cost_micro_usd` money convention.
- [Underlying HTTP API](./reference/http-api.md) — the `/v1` routes the SDK wraps.
