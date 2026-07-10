# Guide

A start-to-finish path through the Pareta SDK, from your first install to running it async in production. Read it in order the first time; come back to any page on its own later.

The throughline: you send every request to `model="auto"` (Pareta plans, routes to benchmark-proven open specialists, verifies, and falls back to a frontier model when needed), and you prove it wins on your data with an eval before you commit. There is nothing to deploy and no model to pick. Inference and evals are metered against your org balance.

Almost every example builds the client with `Pareta.from_env()`, which reads `PARETA_API_KEY` and an optional `PARETA_BASE_URL`.

1. [Installation & authentication](./installation.md) — install `pareta` (pip/uv/poetry), authenticate with a `pareta_sk_` key via `Pareta.from_env()` or `api_key=`, and make a first metered OpenAI-compatible call.
2. [Quickstart](./quickstart.md) — `model="auto"` end to end in about a dozen lines, with streaming, metering, and benchmarking it against frontier models on your data.
3. [Core concepts](./core-concepts.md) — tasks and capabilities, how auto plans/routes/verifies, frontier baselines, hidden hardware, and balance metering.
4. [Running inference](./inference.md) — `chat.completions.create` with `model="auto"`: completions, streaming chunks, passthrough params, `models.list`, async, metering errors, and pointing the `openai` SDK at `base_url`.
5. [Evaluating on your own data](./evaluation.md) — benchmark `"auto"` against frontier baselines on your own rows with `evals.sets` and `evals.runs`, reading per-contender quality/CIs/cost and the metered run total.
6. [Errors, retries & timeouts](./errors-and-retries.md) — the `ParetaError` hierarchy and status-to-class mapping, which errors to catch (402/404/503/429), automatic retries with backoff, and request vs eval-wait timeouts.
7. [Async usage](./async.md) — `AsyncPareta`: `async with`/`aclose` lifecycle, awaiting every method, `async for` on chat streams, and fanning out work concurrently with `asyncio.gather`.
8. [Configuration](./configuration.md) — building the client: `api_key`, `base_url` (prod vs staging), `timeout`, `max_retries`, injecting your own `httpx` client, env vars, and lifecycle.
9. [The `pareta` CLI](./cli.md) — the same surface as a shell command (`pip install "pareta[cli]"`): `chat`/`tasks`/`models`/`evals`/`auto`/`audio`, with `--json` everywhere.
10. [MCP server](./mcp.md) — expose Pareta to an AI agent (Claude Code, Codex, Claude Desktop, Cursor) as tools (`pip install "pareta[mcp]"`); set it up with `uvx`/`pipx`.
11. [The `/pareta` skill](./skill.md) — a `SKILL.md` that drives the CLI as a slash command in Claude Code and Codex (same file works in both).

## Where to go next

- Working examples for specific jobs: [Examples](../examples/README.md).
- Field-by-field API docs: [Reference](../reference/README.md).
