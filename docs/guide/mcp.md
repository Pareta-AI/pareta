# MCP server

`pareta-mcp` is a [Model Context Protocol](https://modelcontextprotocol.io) server that exposes Pareta to an AI agent (Claude Desktop, Cursor, …) as tools — so the agent can call `model="auto"`, match a task, run an eval on your data, and read auto's metrics on your behalf. It ships with the Python package (`pip install "pareta[mcp]"`) and speaks stdio, so any MCP-capable client can drive it regardless of your project's language.

## Install it in its own environment

Like any MCP server, `pareta-mcp` has its own dependency tree (the `mcp` runtime, which pulls in `starlette`). Install it **isolated** — not into an application or project virtualenv, where those dependencies can clash with, say, a FastAPI app, and where the console script may not land on your PATH.

The simplest path is [`uvx`](https://docs.astral.sh/uv/): it runs the server on demand in an ephemeral, isolated environment with nothing to install ahead of time. Point your MCP client's `command` at `uvx`:

```json
{
  "mcpServers": {
    "pareta": {
      "command": "uvx",
      "args": ["--from", "pareta[mcp]", "pareta-mcp"],
      "env": { "PARETA_API_KEY": "pareta_sk_…" }
    }
  }
}
```

Prefer a persistent install? [`pipx`](https://pipx.pypa.io) puts `pareta-mcp` on your PATH in a dedicated venv:

```bash
pipx install "pareta[mcp]"
```

…then point the client's `command` straight at the script:

```json
{
  "mcpServers": {
    "pareta": {
      "command": "pareta-mcp",
      "env": { "PARETA_API_KEY": "pareta_sk_…" }
    }
  }
}
```

Avoid a plain `pip install "pareta[mcp]"` into a shared/app environment — its `mcp`/`starlette` dependencies can clash with the app's FastAPI, and the console script may not land on your PATH.

### Claude Desktop

In Claude Desktop, open **Settings → Developer → Edit Config** to edit `claude_desktop_config.json`, add one of the JSON blocks above, and restart the app. The `pareta` tools then appear in the tool menu.

### Claude Code

[Claude Code](https://docs.claude.com/en/docs/claude-code) speaks MCP natively — add the server in one command. The flags go *before* the `--`; everything after it is the server's launch command:

```bash
claude mcp add pareta --scope user \
  --env PARETA_API_KEY=pareta_sk_… \
  -- uvx --from "pareta[mcp]" pareta-mcp
```

`--scope user` makes it available in every project; `--scope local` (the default) is this project only, and `--scope project` writes a shared `.mcp.json`. Verify with `claude mcp list` (or `/mcp` inside a session): `pareta` should show **connected** with its tools.

To commit it for a team without hardcoding the key, add a project-root `.mcp.json` and reference the key from the environment — Claude Code expands `${PARETA_API_KEY}` at startup:

```json
{
  "mcpServers": {
    "pareta": {
      "command": "uvx",
      "args": ["--from", "pareta[mcp]", "pareta-mcp"],
      "env": { "PARETA_API_KEY": "${PARETA_API_KEY}" }
    }
  }
}
```

### Codex

[Codex](https://developers.openai.com/codex) reads MCP servers from `~/.codex/config.toml`. Add a `[mcp_servers.pareta]` table with the same stdio command:

```toml
[mcp_servers.pareta]
command = "uvx"
args = ["--from", "pareta[mcp]", "pareta-mcp"]

[mcp_servers.pareta.env]
PARETA_API_KEY = "pareta_sk_…"
```

### Cursor and other MCP clients

Any MCP client takes the same stdio command. Use the JSON form from above (in Cursor, **Settings → MCP → Add**): point `command` at `uvx`, `args` at `["--from", "pareta[mcp]", "pareta-mcp"]`, and put `PARETA_API_KEY` in `env`.

## Authenticate

Set `PARETA_API_KEY` (a `pareta_sk_` key from the [dashboard](https://pareta.ai)) in the server's `env`, as shown above; `PARETA_BASE_URL` is optional and defaults to the production API. The key is read lazily on the first tool call, so the server starts even if it's unset — you get a clear error back when a tool runs, never a crashed server.

## Smoke-test it

Run the server directly to confirm it starts. It then waits for an MCP client to connect over stdio — there's no interactive output, so Ctrl-C to exit:

```bash
PARETA_API_KEY=pareta_sk_… uvx --from "pareta[mcp]" pareta-mcp
```

## The tools

The tools are grouped the same way as the SDK and CLI:

- **Inference** — `chat` (metered). The default `model="auto"` is the product: Pareta plans the request, routes it to benchmark-proven open specialists, verifies, and falls back to a frontier model when that's the right call.
- **Discovery** — `match_task`, `list_tasks`, `get_task`, `list_models`. Start with `match_task` to turn a plain-language goal into a task; `list_models` returns exactly one entry, `auto`.
- **Eval** — `run_eval`, `get_eval_run` (bring-your-own-data, metered). Pass `"auto"` among the candidate models to benchmark Pareta's routing itself against frontier baselines on your data.
- **Auto** — `auto_metrics` (read-only, free) and `compare_frontier` (metered: one prompt against a frontier vendor for a side-by-side with `chat`).
- **Audio** — `transcribe`, `speak` (metered per minute).
- **Retrieval** — `rerank` (metered per document scored), `embed` (metered per input token).
- **Images** — `generate_image` (metered flat per image). Saves the PNG to a path you give it — the bytes never enter the agent's context.

A typical agent flow: `match_task("pull the key fields out of contracts")` → `run_eval(models=["auto"], task, items)` → `chat(prompt)`.

## Spending money is gated by your client's approval

Some tools cost money: `chat` / `run_eval` / `compare_frontier` / `transcribe` / `speak` / `rerank` / `embed` / `generate_image` debit your org balance. The server deliberately adds **no** second confirmation layer — **your MCP client's per-tool-call approval is the guardrail.** Keep approval prompts on for the `pareta` server, and review the arguments (which task, which rows, which prompt) before approving a metered call. Tool errors — a missing key, an out-of-credit balance — come back as a clean `{"error": …}` message the agent can read, not a crash.

## Next steps

- [The `/pareta` skill](skill.md) — the slash-command alternative: a `SKILL.md` that drives the CLI (Claude Code & Codex), instead of tools-over-a-server.
- [The `pareta` CLI](cli.md) — the same commands from your shell.
- [Core concepts](core-concepts.md) — tasks, `model="auto"`, and the metering the agent is driving.
