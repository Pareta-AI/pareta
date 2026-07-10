# Changelog

## 1.0.0 — 2026-07-08

- Every POST now carries an `Idempotency-Key` header, generated once per
  logical call and re-sent verbatim on automatic retries — the server
  collapses all attempts of one request onto a single billed debit
  (fixes double-billing when a long-running request outlived a client
  timeout and the SDK retried it).
- Default request timeout raised 60s → 600s (long-document `model:"auto"`
  requests legitimately run 60–180s server-side; matches the OpenAI SDK
  default).

Auto-only major. `model:"auto"` is the product; the SDK, CLI, MCP server, and
agent skill now expose only the auto-first surface.

### BREAKING

- **`endpoints.*` removed** everywhere: the `client.endpoints` namespace
  (deploy / list / retrieve / start / stop / delete / metrics) is gone from
  the Python client (sync + async), the `pareta endpoints …` CLI group is
  gone, and the MCP server no longer registers `deploy_endpoint`,
  `list_endpoints`, `get_endpoint`, `start_endpoint`, `stop_endpoint`,
  `delete_endpoint`, `endpoint_metrics`, or `endpoint_cost`.
- **`tasks.leaderboard()` / `tasks.recommended()` removed** from the client,
  the CLI (`pareta tasks leaderboard|recommended`), and the MCP server
  (`get_leaderboard`, `recommended_model` tools). `tasks.match` stays as the
  discovery surface — and `evals` proves `"auto"` on your own data, which is
  the measurement that matters.
- **Public types removed**: `Endpoint`, `Leaderboard`, `LeaderboardEntry` are
  no longer exported (or defined). `FrontierModel` stays (returned by
  `evals.frontier_models()`).
- The `/pareta` agent skill and MCP toolset are now auto-only: call
  `model:"auto"`, prove it with evals, watch it with `auto metrics` — no
  deploy/operate path.

### Kept (unchanged)

- `chat.*` (defaults to `model="auto"`), `models.*`,
  `tasks.list/retrieve/match`, `evals.*` (sets, runs, frontier_models),
  `audio.*`, `auto.*` (metrics + compare_frontier), sync + async clients.

### Fixed

- CLI: `pareta auto metrics` / `pareta auto compare` crashed in `--json`
  handling (referenced a nonexistent `state.json_output` / `_print_json`);
  now use the real `--json` plumbing.

## 0.3.1 — 2026-07-05

- **Auto-first docs everywhere**: the README (PyPI/GitHub landing) now leads
  with `model="auto"`; migrating from OpenAI is the three-string change
  (base_url, api_key, `model="auto"`) with no deploy step; the streaming
  example, chat reference, and package docstrings lead with auto; the
  document-extraction walkthrough calls out the zero-setup auto path;
  `llms.txt` regenerated with the auto-first preamble.
- Fixed the `pyproject.toml` / `_version.py` version drift (0.2.1 vs 0.3.0).

## 0.3.0 — 2026-07-03

- **`model="auto"` is the product**: the quickstart, inference guide, CLI and
  MCP server now lead with the routing brain. `pareta chat` defaults to
  `--model auto`.
- New `client.auto` resource: `metrics()` (org rollup incl. projected savings
  vs frontier) and `compare_frontier()` (metered side-by-side against
  gpt-5.5 / gemini / claude).
- New CLI group: `pareta auto metrics`, `pareta auto compare`.
- MCP: `chat` defaults to auto; new `auto_metrics` + `compare_frontier` tools;
  `run_eval` documents `"auto"` as a benchmark contender.
- BREAKING (CLI): `pareta chat MODEL PROMPT` → `pareta chat PROMPT
  [--model MODEL]` (default `auto`).

All notable changes to the `pareta` Python SDK. This project adheres to
[Semantic Versioning](https://semver.org).

## 0.2.1 — 2026-06-25

Docs-only — no library, CLI, or MCP runtime behavior changes.

### Changed

- Recommend installing the `pareta-mcp` MCP server in its **own isolated
  environment** via [`uvx`](https://docs.astral.sh/uv/) or
  [`pipx`](https://pipx.pypa.io) rather than a plain `pip install`: its
  `mcp`/`starlette` dependencies can clash with an app's (e.g. FastAPI), and a
  `pip install --user` may leave the console script off your PATH. Updated the
  README (the registration snippet now points `command` at `uvx`) and the
  `pareta.mcp_server` module docstring accordingly.
- Documentation site: added dedicated **CLI** and **MCP server** guide pages at
  [docs.pareta.ai](https://docs.pareta.ai) (previously the CLI/MCP were covered
  only in the README).

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
