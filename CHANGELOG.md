# Changelog

All notable changes to the `pareta` Python SDK. This project adheres to
[Semantic Versioning](https://semver.org).

## 0.2.0 — 2026-06-25

Purely additive — no breaking changes to the library API.

### Added

- **`pareta` CLI** (`pip install "pareta[cli]"`) — a Typer command-line interface
  over the SDK. Command groups: `tasks` (list / match / leaderboard / recommended
  / show), `models list`, `endpoints` (deploy / list / show / start / stop /
  delete / metrics / cost), `evals` (run + eval-sets), `chat`, and `audio`
  (transcribe / speak). `--json` on any command for machine-readable output.
  Console script: `pareta`.
- **`pareta-mcp` MCP server** (`pip install "pareta[mcp]"`) — a
  [Model Context Protocol](https://modelcontextprotocol.io) server (stdio) that
  exposes the full control plane as 19 tools, so an AI agent (Claude Desktop,
  Cursor, …) can discover, deploy, eval, and call models. Console script:
  `pareta-mcp`. See the README for the Claude Desktop config.
- **Audio** — `client.audio.transcriptions(...)` (speech-to-text) and
  `client.audio.speech(...)` (text-to-speech), metered per minute; also exposed
  via the CLI `audio` group and the MCP `transcribe` / `speak` tools.
- **`Endpoint.recommended_system_prompt` and `Endpoint.prompt_scaffold`** — the
  serving-time prompt guidance the backend stamps per endpoint, surfaced on the
  endpoint model.
- Capability-oriented examples + docs (benchmark your data, deploy-and-infer,
  handling an unsupported match).

## 0.1.0

### Added

- Initial release: synchronous (`Pareta`) and asynchronous (`AsyncPareta`)
  clients, `pareta_sk_` API-key auth, automatic retries with backoff, a typed
  exception hierarchy, and the control plane — `chat.completions` (OpenAI-
  compatible, streaming), `models`, `tasks` (browse + intent match), `endpoints`
  (deploy / operate / metrics), and `evals` (bring-your-own-data).
