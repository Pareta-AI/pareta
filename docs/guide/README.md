# Guide

A start-to-finish path through the Pareta SDK, from your first install to running it async in production. Read it in order the first time; come back to any page on its own later.

The throughline: you send every request to `model="auto"` (Pareta plans, routes to benchmark-proven open specialists, verifies, and falls back to a frontier model when needed), and you prove it wins on your data with an eval before you commit. Dedicated endpoints exist for pinning one model. Inference and evals are metered against your org balance; model ids are per-task aliases.

Almost every example builds the client with `Pareta.from_env()`, which reads `PARETA_API_KEY` and an optional `PARETA_BASE_URL`.

1. [Installation & authentication](./installation.md) — install `pareta` (pip/uv/poetry), authenticate with a `pareta_sk_` key via `Pareta.from_env()` or `api_key=`, and make a first metered OpenAI-compatible call.
2. [Quickstart](./quickstart.md) — `model="auto"` end to end in about a dozen lines, with streaming, metering, and benchmarking it against frontier models on your data.
3. [Core concepts](./core-concepts.md) — tasks, open vs frontier models, per-task aliases, hidden hardware, balance metering, and the match to leaderboard to eval to deploy funnel.
4. [Running inference](./inference.md) — call deployed endpoints with `chat.completions.create`: completions, streaming chunks, passthrough params, `models.list`, async, metering errors, and pointing the `openai` SDK at `base_url`.
5. [Deploying & operating endpoints](./deploying-endpoints.md) — the control plane: `deploy` (`wait=True` Endpoint vs `wait=False` progress-event stream), `list`/`retrieve`/`start`/`stop`/`delete`, and `metrics(id)`. No GPU knob.
6. [Finding the right model](./discovery.md) — the discovery loop: match intent to a task, rank models via `leaderboard`/`recommended`, and list frontier baselines to eval against.
7. [Evaluating on your own data](./evaluation.md) — score open candidates and frontier baselines on your own rows with `evals.sets` and `evals.runs`, reading per-model quality/CIs/cost and the metered run total.
8. [Errors, retries & timeouts](./errors-and-retries.md) — the `ParetaError` hierarchy and status-to-class mapping, which errors to catch (402/404/503/429), automatic retries with backoff, and request vs eval-wait timeouts.
9. [Async usage](./async.md) — `AsyncPareta`: `async with`/`aclose` lifecycle, awaiting every method, `async for` on chat and deploy streams, and fanning out work concurrently with `asyncio.gather`.
10. [Configuration](./configuration.md) — building the client: `api_key`, `base_url` (prod vs staging), `timeout`, `max_retries`, injecting your own `httpx` client, env vars, and lifecycle.
11. [The `pareta` CLI](./cli.md) — the same control plane as a shell command (`pip install "pareta[cli]"`): `tasks`/`models`/`endpoints`/`evals`/`chat`/`audio`, with `--json` everywhere.
12. [MCP server](./mcp.md) — expose the control plane to an AI agent (Claude Code, Codex, Claude Desktop, Cursor) as tools (`pip install "pareta[mcp]"`); set it up with `uvx`/`pipx`.
13. [The `/pareta` skill](./skill.md) — a `SKILL.md` that drives the CLI as a slash command in Claude Code and Codex (same file works in both).

## Where to go next

- Working examples for specific jobs: [Examples](../examples/README.md).
- Field-by-field API docs: [Reference](../reference/README.md).
