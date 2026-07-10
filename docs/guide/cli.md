# The `pareta` CLI

The `pareta` command is the SDK in your shell: call `model="auto"`, match a task, run an eval on your own data, and read auto's metrics — each as one command, rendered as a table or, with `--json`, as machine-readable output for scripts. It ships with the Python package (`pip install "pareta[cli]"`) and, once installed, works from any shell regardless of your project's language.

## Install

The CLI is an optional extra on the Python package — it adds `typer` + `rich`:

```bash
pip install "pareta[cli]"
```

Because the install puts a `pareta` console script on your PATH, an isolated install with [`pipx`](https://pipx.pypa.io) is often cleaner — it keeps the CLI and its dependencies out of your project's environment while still putting the command on your PATH:

```bash
pipx install "pareta[cli]"
```

Either way you get the same command. Confirm it:

```bash
pareta --version
```

## Authenticate

The CLI reads the same environment as the SDK — `PARETA_API_KEY` (required) and the optional `PARETA_BASE_URL`. Mint a `pareta_sk_` key in the [dashboard](https://pareta.ai) and export it:

```bash
export PARETA_API_KEY="pareta_sk_…"
```

There is no `login` command and no config file: auth *is* the environment, so the same export works in your shell, a Makefile, or CI. A missing or bad key prints a one-line error to stderr and exits non-zero (`2` for an auth/config problem you can fix locally, `1` for a genuine API error) — never a traceback.

## Output: tables or `--json`

Every command prints a human-readable table by default. Add the global `--json` (or `-j`) flag — **before** the subcommand — to get the raw JSON the SDK returns instead, for piping into `jq` or a script:

```bash
pareta --json models list | jq '.[].id'
```

Data goes to stdout and diagnostics to stderr, so piped output stays clean.

## Command tree

`pareta --help` (or `pareta <group> --help`) documents the whole tree. The groups mirror the SDK's resource namespaces.

### `chat` — one-shot inference

```bash
pareta chat "Summarize this contract clause: …"           # prompt as an argument
echo "Summarize this clause: …" | pareta chat             # or piped on stdin
pareta chat "Tell me a story" --stream                    # stream tokens as they arrive
```

Every chat goes to `model="auto"`: Pareta plans the request, routes it to benchmark-proven open specialists, verifies, and falls back to a frontier model when that's the right call — one request, one debit. Inference is metered.

### `tasks` — browse the catalog + match intent

```bash
pareta tasks match "pull the key fields out of these contracts"   # intent → task / capability / unsupported
pareta tasks list                                                 # every benchmarked task auto routes across
pareta tasks show contract-key-fields                             # one task's schema + default scorer
```

`match` answers "can Pareta do X?" — it resolves free text to a benchmarked task, a capability lane, or an honest `unsupported`. `--top-k` (default 5) controls how many candidate tasks it considers.

### `models` — the model catalog

```bash
pareta models list            # exactly one entry: "auto"
```

There is one model id. Everything behind it — planning, routing, verification, frontier fallback — is Pareta's job, per request.

### `evals` — benchmark on your own data

```bash
# Build a set on the fly from a JSONL file and benchmark "auto" against the frontier baselines:
pareta evals run --task contract-key-fields --file rows.jsonl \
  --models auto --frontier --wait

# Or run an existing eval set:
pareta evals run --eval-set es_abc --models auto --wait

# Manage eval sets (your data rows):
pareta evals sets create --task contract-key-fields --file rows.jsonl
pareta evals sets list
pareta evals sets show es_abc
pareta evals sets delete es_abc --yes
```

`--models` is required — pass `auto` to benchmark Pareta's routing itself. `--frontier` adds the task's benchmarked vendor models as baselines, which is the comparison that matters. Each item in `--file` is one JSON object per line; eval runs are metered against your org balance.

### `auto` — watch it and compare it

```bash
pareta auto metrics                                              # requests + success rate (30d), spend, projected savings vs frontier
pareta auto compare "Summarize this clause: …"                   # one prompt: auto vs a frontier vendor, side by side with both bills
pareta auto compare "Summarize this clause: …" --frontier claude-sonnet-4-6
```

`metrics` is read-only and free. `compare` is metered — it makes two real calls, one to `auto` and one to the vendor at the vendor's actual token cost (a failed vendor call bills $0). Allowed vendors: `gpt-5.5`, `gemini-3-5-flash`, `gemini-3-1-pro`, `claude-sonnet-4-6`.

### `audio` — speech in and out

```bash
pareta audio transcribe meeting.wav                         # speech-to-text (prints the transcript)
pareta audio speak "Hello from Pareta" --out hello.wav      # text-to-speech (writes an audio file)
```

Both are metered per minute of audio.

## Scripting

Because every command takes `--json` and exits non-zero on failure, the CLI composes into shell pipelines and CI. For example, check that a job is routable, benchmark `auto` on your own rows, then run the real call:

```bash
export PARETA_API_KEY="pareta_sk_…"

pareta --json tasks match "pull the key fields out of these contracts" | jq -r '.type'
pareta evals run --task contract-key-fields --file rows.jsonl --models auto --frontier --wait
pareta chat "What is the contract's effective date? …"
```

## Next steps

- [MCP server](mcp.md) — expose the same commands to an AI agent (Claude Desktop, Cursor) as tools.
- [Installation & authentication](installation.md) — the underlying SDK, the `pareta_sk_` key, and `from_env()`.
- [Core concepts](core-concepts.md) — tasks, `model="auto"`, and the metering behind every command.
- [Evaluating on your own data](evaluation.md) — the eval surface behind the `evals` group.
