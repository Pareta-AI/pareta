# `/pareta` agent skill

A single [`SKILL.md`](./SKILL.md) that teaches an AI coding agent to drive the
`pareta` CLI — call `model:"auto"` (Pareta routes every request to the best
model), benchmark it against frontier models on your own data, run retrieval
(rerank + embeddings), and monitor spend/quality/savings.

Claude Code and Codex use the **same** skill format (YAML frontmatter `name` +
`description` + a Markdown body), so the one file works in both. The agent loads
it automatically when a task matches, or you can invoke it explicitly as
`/pareta`.

## Prerequisite

The skill drives the `pareta` shell command, so install the CLI and set a key:

```bash
pipx install "pareta[cli]"        # or: pip install "pareta[cli]"
export PARETA_API_KEY="pareta_sk_…"   # mint one in the dashboard
```

## Install — Claude Code

Copy the skill into your personal skills directory (works from any project):

```bash
mkdir -p ~/.claude/skills/pareta
curl -fsSL https://raw.githubusercontent.com/Pareta-AI/pareta/main/skills/pareta/SKILL.md \
  -o ~/.claude/skills/pareta/SKILL.md
```

Or for one repo only, drop it at `.claude/skills/pareta/SKILL.md`. Then `/pareta`
is available (and Claude invokes it automatically when relevant).

## Install — Codex

Same file, different directory:

```bash
mkdir -p ~/.codex/skills/pareta
curl -fsSL https://raw.githubusercontent.com/Pareta-AI/pareta/main/skills/pareta/SKILL.md \
  -o ~/.codex/skills/pareta/SKILL.md
```

Or for one repo only, check it in at `.codex/skills/pareta/SKILL.md`. Codex loads
skills automatically when the task matches. (Codex custom prompts in
`~/.codex/prompts/` are deprecated in favor of skills.)

## Tools vs. skill

This skill is the **CLI-driver** path. If you'd rather give the agent Pareta's
control plane as structured **tools**, use the `pareta-mcp` MCP server instead —
see https://docs.pareta.ai/guide/mcp (works in Claude Code, Codex, Claude Desktop,
and Cursor). You can run both.
