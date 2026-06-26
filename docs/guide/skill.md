# The `/pareta` skill

A [Pareta skill](https://github.com/Pareta-AI/pareta/blob/main/skills/pareta/SKILL.md) teaches an AI coding agent to drive the `pareta` CLI as a slash command — match a task to an open-weights model, deploy it (Pareta picks the GPU), run metered inference, and benchmark models on your own data. It's a single `SKILL.md` that works in both Claude Code and Codex, because they share the same skill format.

## Skill vs. MCP server

Two ways to put Pareta inside a coding agent — and you can use both:

- **The [MCP server](mcp.md)** gives the agent Pareta's control plane as structured **tools** (`deploy_endpoint`, `run_eval`, …) it calls directly. Best when you want first-class, auto-discovered tools.
- **This skill** is **instructions** — a `SKILL.md` the agent reads and follows, driving the `pareta` shell command. Best when you want a `/pareta` slash command and a guided workflow, and you've already installed the CLI.

## Prerequisite

The skill drives the CLI, so install it and set a key:

```bash
pipx install "pareta[cli]"            # or: pip install "pareta[cli]"
export PARETA_API_KEY="pareta_sk_…"   # mint one in the dashboard
```

## Install in Claude Code

Copy the skill into your personal skills directory (available from any project):

```bash
mkdir -p ~/.claude/skills/pareta
curl -fsSL https://raw.githubusercontent.com/Pareta-AI/pareta/main/skills/pareta/SKILL.md \
  -o ~/.claude/skills/pareta/SKILL.md
```

For a single repo, drop it at `.claude/skills/pareta/SKILL.md` instead. Then `/pareta` is available — and Claude Code also invokes it automatically when a request matches.

## Install in Codex

Codex uses the same skill format; only the directory differs:

```bash
mkdir -p ~/.codex/skills/pareta
curl -fsSL https://raw.githubusercontent.com/Pareta-AI/pareta/main/skills/pareta/SKILL.md \
  -o ~/.codex/skills/pareta/SKILL.md
```

For a single repo, check it in at `.codex/skills/pareta/SKILL.md`. Codex loads skills automatically when the task matches. (Codex's older custom prompts in `~/.codex/prompts/` are deprecated in favor of skills.)

## What it does

Once installed, ask in plain language — *"find the cheapest open model that extracts key fields from contracts and deploy it."* The skill walks the agent through:

1. `pareta tasks match` — resolve the intent to a benchmarked task.
2. `pareta tasks leaderboard` — rank open models, the recommended pick, and frontier savings.
3. `pareta endpoints deploy --wait` — stand up the endpoint (Pareta picks the GPU).
4. `pareta chat` — run inference; `pareta evals run` — benchmark on your own JSONL data.
5. `pareta endpoints stop` / `cost` / `metrics` — operate and clean up.

It bakes in the guardrails: deploy / inference / eval **spend your org balance**, so the agent confirms before provisioning or spending, and stops endpoints it deployed when the work is done.

## Next steps

- [MCP server](mcp.md) — the tools-over-a-server alternative (Claude Code, Codex, Claude Desktop, Cursor).
- [The `pareta` CLI](cli.md) — the command surface the skill drives.
- [Installation & authentication](installation.md) — install the CLI and mint a `pareta_sk_` key.
