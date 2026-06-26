# The `pareta` CLI

The `pareta` command is the SDK's control plane in your shell: match a task, read a leaderboard, deploy and operate endpoints, run an eval, and call a model — each as one command, rendered as a table or, with `--json`, as machine-readable output for scripts. It ships with the Python package (`pip install "pareta[cli]"`) and, once installed, works from any shell regardless of your project's language.

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

### `tasks` — browse the catalog + match intent

```bash
pareta tasks match "pull the key fields out of these contracts"   # intent → task / capability / unsupported
pareta tasks list                                                 # every benchmarked task
pareta tasks show contract-key-fields                             # one task's schema + default scorer
pareta tasks leaderboard contract-key-fields                      # open models ranked + the frontier baseline
pareta tasks recommended contract-key-fields                      # the model `deploy` picks by default
```

### `models` — the endpoints you can call

```bash
pareta models list            # deployed, callable models (each id works as a chat target)
```

### `endpoints` — deploy + operate

```bash
pareta endpoints deploy --task contract-key-fields                          # deploy the recommended model (streams progress)
pareta endpoints deploy --task contract-key-fields --model qwen-1 --wait    # pick a model, block until live
pareta endpoints list                                                       # your org's endpoints + status
pareta endpoints show ep_contract_kie                                       # one endpoint's full record
pareta endpoints stop ep_contract_kie                                       # halt GPU billing (resumable)
pareta endpoints start ep_contract_kie                                      # resume a stopped endpoint
pareta endpoints metrics ep_contract_kie                                    # latency / throughput
pareta endpoints cost ep_contract_kie                                       # spend over the reporting window
pareta endpoints delete ep_contract_kie --yes                               # destructive; prompts unless --yes
```

Without `--wait`, `deploy` streams the provisioning events as they happen; with `--wait` it blocks and prints the live endpoint. Pareta picks the GPU and serving config — there is no hardware flag.

### `evals` — benchmark on your own data

```bash
# Build a set on the fly from a JSONL file and compare two open models, with frontier baselines:
pareta evals run --task contract-key-fields --file rows.jsonl \
  --models qwen-1 --models qwen-2 --frontier --wait

# Or run an existing eval set:
pareta evals run --eval-set es_abc --models qwen-1 --wait

# Manage eval sets (your data rows):
pareta evals sets create --task contract-key-fields --file rows.jsonl
pareta evals sets list
pareta evals sets show es_abc
pareta evals sets delete es_abc --yes
```

`--models` is repeatable and required (the open candidates to evaluate). `--frontier` adds the task's benchmarked vendor models as baselines. Each item in `--file` is one JSON object per line; eval runs are metered against your org balance.

### `chat` — one-shot inference

```bash
pareta chat ep_contract_kie "Summarize this contract clause: …"     # prompt as an argument
echo "Summarize this clause: …" | pareta chat ep_contract_kie        # or piped on stdin
pareta chat ep_contract_kie "Tell me a story" --stream               # stream tokens as they arrive
```

The first argument is an endpoint/model id (from `endpoints list` or `models list`). Inference is metered.

### `audio` — speech in and out

```bash
pareta audio transcribe meeting.wav                         # speech-to-text (prints the transcript)
pareta audio speak "Hello from Pareta" --out hello.wav      # text-to-speech (writes an audio file)
```

Both are metered per minute of audio.

## Scripting

Because every command takes `--json` and exits non-zero on failure, the CLI composes into shell pipelines and CI. For example, deploy the recommended model for a task, capture its id, call it, then pause billing:

```bash
export PARETA_API_KEY="pareta_sk_…"

EP=$(pareta --json endpoints deploy --task contract-key-fields --wait | jq -r '.id')
pareta chat "$EP" "What is the contract's effective date?"
pareta endpoints stop "$EP"          # pause billing when you're done
```

## Next steps

- [MCP server](mcp.md) — expose the same control plane to an AI agent (Claude Desktop, Cursor) as tools.
- [Installation & authentication](installation.md) — the underlying SDK, the `pareta_sk_` key, and `from_env()`.
- [Finding the right model](discovery.md) — the match → leaderboard → recommended loop the `tasks` group drives.
- [Deploying & operating endpoints](deploying-endpoints.md) — the deploy / lifecycle / metrics surface behind the `endpoints` group.
