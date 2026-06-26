---
name: pareta
description: >-
  Deploy, benchmark, and call open-weights model endpoints on Pareta using the
  `pareta` CLI. Use when the user wants to find the best open model for a task,
  deploy an open-weights endpoint (Pareta picks the GPU), run inference against
  it, replace a frontier vendor API with a cheaper open one, or benchmark models
  on their own data. Drives the `pareta` shell command; auth is the
  `PARETA_API_KEY` env var.
---

# Pareta

[Pareta](https://pareta.ai) is a marketplace + control plane for open-weights
models: you match a task to a model, deploy it as an OpenAI-compatible endpoint
(Pareta picks the GPU — there is no hardware knob), run metered inference, and
benchmark candidates on your own data. This skill drives the `pareta` CLI.

## Before you start

1. **CLI present?** Check with `pareta --version`. If missing, install it:
   `pipx install "pareta[cli]"` (isolated, recommended) or `pip install "pareta[cli]"`.
2. **Authenticated?** The CLI reads `PARETA_API_KEY` (a `pareta_sk_` key from the
   dashboard) and optional `PARETA_BASE_URL`. If `PARETA_API_KEY` is unset, stop
   and ask the user to export it — do not guess a key.
3. **Parsing output?** Add the global `--json` flag *before* the subcommand
   (`pareta --json <group> <cmd>`) to get machine-readable JSON instead of a table.

## Money + safety (read before deploying or calling)

Several actions **spend the user's org balance or start paid GPUs** — confirm with
the user before running them, and report what each will cost where you can:

- `endpoints deploy` / `endpoints start` — spin up **paid GPU capacity**.
- `chat`, `evals run`, `audio transcribe`, `audio speak` — **metered** per call/token/minute.
- `endpoints delete` — **destructive and irreversible** (prompts unless `--yes`).

A deployed endpoint keeps billing until you `endpoints stop` it. When you finish a
task you started, stop (or delete) any endpoint you deployed unless the user wants
it kept warm. Never run a destructive or spending command speculatively.

## The core workflow

### 1. Turn the user's intent into a task

```bash
pareta --json tasks match "extract the key fields from these contracts"
```

Read the `type` (`task` | `capability` | `unsupported` | `none`), the chosen
`task_id`, and the reasoning. If `unsupported`, tell the user Pareta has no
benchmarked task for this and stop — don't force a deploy.

### 2. See which model to use

```bash
pareta tasks leaderboard contract-key-fields    # open models ranked + recommended + frontier savings
pareta tasks recommended contract-key-fields    # just the default deployable pick
```

Surface the recommended open model and how it compares to the frontier baseline
(quality + cost-per-request) so the user can choose.

### 3. Deploy (paid — confirm first)

```bash
pareta endpoints deploy --task contract-key-fields --wait              # recommended model
pareta endpoints deploy --task contract-key-fields --model qwen-1 --wait   # a specific pick
```

`--wait` blocks until the endpoint is live and prints its id (e.g.
`ep_contract_kie`). Without `--wait` it streams provisioning progress. The id is
what you pass to `chat`.

### 4. Call it (metered)

```bash
pareta chat ep_contract_kie "What is the contract's effective date?"
echo "Summarize this clause: ..." | pareta chat ep_contract_kie       # or pipe stdin
```

### 5. Benchmark on the user's own data (metered)

When the user has labeled rows (a JSONL file, one object per line), prove which
model wins on *their* data — optionally against frontier baselines:

```bash
pareta evals run --task contract-key-fields --file rows.jsonl \
  --models qwen-1 --models qwen-2 --frontier --wait
```

`--models` is repeatable and required (the open candidates). `--frontier` adds the
task's benchmarked vendor models as baselines. Read the per-model quality + mean
cost from the results.

### 6. Operate + clean up

```bash
pareta endpoints list                 # your endpoints + status
pareta endpoints metrics ep_contract_kie    # latency / throughput
pareta endpoints cost ep_contract_kie       # spend over the window
pareta endpoints stop ep_contract_kie       # halt GPU billing (resumable with `start`)
pareta endpoints delete ep_contract_kie --yes   # destructive
```

## Other surfaces

- `pareta models list` — the deployed, callable models your org can reach now.
- `pareta tasks list` / `pareta tasks show <task>` — browse the benchmark catalog.
- `pareta audio transcribe <file>` / `pareta audio speak "<text>" --out out.wav` — speech in/out (metered per minute).
- `pareta evals sets create|list|show|delete` — manage reusable eval sets.

`pareta --help` (or `pareta <group> --help`) documents the full tree. Full docs:
https://docs.pareta.ai.
