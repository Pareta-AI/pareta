"""`pareta` — a Typer CLI over the SDK.

model:"auto" is the product: `pareta chat` sends every request to Pareta's
routing brain, `pareta evals run` proves it against frontier models on your
own data, and `pareta auto metrics` shows what your live traffic saves.

Installed with `pip install pareta[cli]` (wires the `pareta` console script).
Auth comes from the environment exactly like the SDK: `PARETA_API_KEY`
(+ optional `PARETA_BASE_URL`). Every command builds one `Pareta.from_env()`
client, maps `ParetaError` to a clean stderr message + a non-zero exit (never a
traceback), and renders results as rich tables — or as raw JSON with `--json`.

    pareta chat "summarize this"          # model:"auto" by default
    pareta tasks match "extract fields from invoices"
    pareta evals run --task contract-kie --file rows.jsonl --models auto --frontier
    pareta --json auto metrics
"""

from __future__ import annotations

import json
import sys
from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from ._client import Pareta
from ._exceptions import AuthenticationError, ParetaError, PermissionDeniedError

# stdout for data, stderr for diagnostics — keeps piped output clean.
_out = Console()
_err = Console(stderr=True)


class _State:
    """Carries the global `--json` flag down to every command via the Typer
    context object."""

    json: bool = False


# ── client + error handling ──────────────────────────────────────────────
def _client() -> Pareta:
    """Build a client from the environment. Raises `ParetaError` (missing key)
    that the command wrappers turn into a clean exit — no traceback."""
    return Pareta.from_env()


def _exit_code(exc: ParetaError) -> int:
    """2 for auth / usage problems the user can fix locally; 1 for genuine API
    errors."""
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        return 2
    # A bare ParetaError with no status is the missing-key / config case.
    if type(exc) is ParetaError:
        return 2
    return 1


def _fail(exc: ParetaError) -> "typer.Exit":
    """Print a one-line error to stderr and return the Exit to raise."""
    _err.print(f"[red]error:[/red] {exc}")
    return typer.Exit(code=_exit_code(exc))


def _emit(state: _State, obj: Any) -> None:
    """In `--json` mode, dump `obj` (using `.to_dict()` when present) as indented
    JSON. Used by the show/metrics/cost-style commands; list commands render a
    table in the non-json branch themselves."""
    payload = obj.to_dict() if hasattr(obj, "to_dict") else obj
    _out.print_json(json.dumps(payload, indent=2, default=str))


def _emit_json(payload: Any) -> None:
    _out.print_json(json.dumps(payload, indent=2, default=str))


def _state(ctx: typer.Context) -> _State:
    return ctx.ensure_object(_State)


def _dash(v: Any) -> str:
    """Render `None` as an em dash so tables stay aligned."""
    return "—" if v is None else str(v)


# ── app + global options ─────────────────────────────────────────────────
app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help='Pareta — model:"auto" inference, evals on your own data, auto metrics.',
)


def _version_callback(value: bool) -> None:
    if value:
        _out.print(__version__)
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    json_out: bool = typer.Option(
        False, "--json", "-j", help="Print raw JSON instead of tables."
    ),
    version: Optional[bool] = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True,
        help="Show the SDK version and exit.",
    ),
) -> None:
    """Pareta CLI. Reads PARETA_API_KEY (+ optional PARETA_BASE_URL)."""
    state = ctx.ensure_object(_State)
    state.json = json_out


# ── tasks ────────────────────────────────────────────────────────────────
tasks_app = typer.Typer(no_args_is_help=True, help="Browse the benchmark catalog + match intent.")
app.add_typer(tasks_app, name="tasks")


@tasks_app.command("list")
def tasks_list(ctx: typer.Context) -> None:
    """List the benchmark tasks in the catalog."""
    state = _state(ctx)
    try:
        tasks = _client().tasks.list()
    except ParetaError as e:
        raise _fail(e)
    if state.json:
        _emit_json([t.to_dict() for t in tasks])
        return
    table = Table(title="Tasks")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("scorer")
    table.add_column("blob input", justify="center")
    for t in tasks:
        table.add_row(_dash(t.id), _dash(t.default_scorer), "yes" if t.has_blob_input else "")
    _out.print(table)


@tasks_app.command("match")
def tasks_match(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Free-text description of what you want to do."),
    top_k: int = typer.Option(5, "--top-k", help="How many candidate tasks to consider."),
) -> None:
    """Match a free-text intent to a task, capability, or 'unsupported'."""
    state = _state(ctx)
    try:
        match = _client().tasks.match(query, top_k=top_k)
    except ParetaError as e:
        raise _fail(e)
    if state.json:
        _emit(state, match)
        return
    _out.print(f"type:       [bold]{_dash(match.type)}[/bold]")
    _out.print(f"confidence: {_dash(match.confidence)}")
    if match.chosen is not None:
        _out.print(f"task:       [cyan]{_dash(match.chosen.task_id)}[/cyan]  (score {_dash(match.chosen.score)})")
    if match.capability is not None:
        cap = match.capability
        _out.print(f"capability: [cyan]{_dash(cap.id)}[/cyan]  {_dash(cap.label)}")
    if match.reasoning:
        _out.print(f"reasoning:  {match.reasoning}")
    if match.candidates:
        table = Table(title="Candidates")
        table.add_column("task_id", style="cyan")
        table.add_column("score", justify="right")
        table.add_column("confidence")
        for c in match.candidates:
            table.add_row(_dash(c.task_id), _dash(c.score), _dash(c.confidence))
        _out.print(table)


@tasks_app.command("show")
def tasks_show(
    ctx: typer.Context,
    task_id: str = typer.Argument(..., help="Task id (e.g. contract-kie)."),
) -> None:
    """Show a task's schema and default scorer."""
    state = _state(ctx)
    try:
        task = _client().tasks.retrieve(task_id)
    except ParetaError as e:
        raise _fail(e)
    _emit(state, task)


# ── models ───────────────────────────────────────────────────────────────
models_app = typer.Typer(no_args_is_help=True, help="The models your org can call.")
app.add_typer(models_app, name="models")


@models_app.command("list")
def models_list(ctx: typer.Context) -> None:
    """List the models your org can call."""
    state = _state(ctx)
    try:
        models = _client().models.list()
    except ParetaError as e:
        raise _fail(e)
    if state.json:
        _emit(state, models)
        return
    table = Table(title="Models")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("owned_by")
    table.add_column("created", justify="right")
    for m in models:
        table.add_row(_dash(m.id), _dash(m.owned_by), _dash(m.created))
    _out.print(table)


# ── evals ────────────────────────────────────────────────────────────────
evals_app = typer.Typer(no_args_is_help=True, help="Eval models on your own data.")
app.add_typer(evals_app, name="evals")


@evals_app.command("run")
def evals_run(
    ctx: typer.Context,
    eval_set: Optional[str] = typer.Option(None, "--eval-set", help="Existing eval-set id to run."),
    task: Optional[str] = typer.Option(None, "--task", help="Task id to pin (optional; Pareta works out the scoring from --prompt otherwise)."),
    file: Optional[str] = typer.Option(None, "--file", help="JSONL of items, used to build a set on the fly."),
    prompt: Optional[str] = typer.Option(None, "--prompt", help="One sentence: what the model should do with each item (required to build a set)."),
    models: list[str] = typer.Option([], "--models", help="Open model id(s) to evaluate (repeatable)."),
    frontier: bool = typer.Option(False, "--frontier", help="Also evaluate the benchmarked frontier roster."),
    name: Optional[str] = typer.Option(None, "--name", help="Name for an on-the-fly eval set."),
    wait: bool = typer.Option(False, "--wait", help="Block until the run finishes."),
) -> None:
    """Run an eval on your own data. Either point at an existing --eval-set, or
    pass --file of JSONL items + --prompt (what the model should do with each
    item) to build one on the fly — Pareta works out how to score the results,
    or pin a task with --task. Include "auto" in --models to benchmark the
    routing brain itself; --frontier adds the task's benchmarked vendor models."""
    state = _state(ctx)
    if not models:
        _err.print("[red]error:[/red] --models is required (e.g. --models auto)")
        raise typer.Exit(code=2)
    # frontier flag → the 'benchmarked' roster keyword the SDK understands.
    frontier_arg = "benchmarked" if frontier else None
    try:
        items = _read_jsonl(file) if file else None
        if eval_set is None and not items:
            _err.print("[red]error:[/red] pass --eval-set <id>, or --file (with --prompt)")
            raise typer.Exit(code=2)
        run = _client().evals.runs.create(
            eval_set=eval_set, task=task, items=items, prompt=prompt,
            models=list(models), frontier=frontier_arg, name=name, wait=wait,
        )
    except (ValueError, TypeError) as e:
        _err.print(f"[red]error:[/red] {e}")
        raise typer.Exit(code=2)
    except ParetaError as e:
        raise _fail(e)
    if state.json:
        _emit(state, run)
        return
    _out.print(f"run id:  [cyan]{_dash(run.id)}[/cyan]")
    _out.print(f"status:  {_dash(run.status)}")
    if run.is_terminal:
        _out.print(f"cost:    ${run.cost}")
        if run.results:
            table = Table(title="Results")
            table.add_column("model", style="cyan")
            table.add_column("kind")
            table.add_column("quality", justify="right")
            table.add_column("mean cost (µ$)", justify="right")
            table.add_column("ok", justify="right")
            table.add_column("err", justify="right")
            for r in run.results:
                table.add_row(
                    _dash(r.model_id), _dash(r.kind), _dash(r.quality_mean),
                    _dash(r.mean_cost_micro_usd), _dash(r.n_succeeded), _dash(r.error_count),
                )
            _out.print(table)
        if run.error_detail:
            _err.print(f"[red]run error:[/red] {run.error_detail}")


@evals_app.command("propose")
def evals_propose(
    ctx: typer.Context,
    file: str = typer.Option(..., "--file", help="JSONL of items to preview scoring for."),
    prompt: str = typer.Option(..., "--prompt", help="One sentence: what the model should do with each item."),
) -> None:
    """Preview how your data would be scored under a stated prompt.
    Nothing is persisted — feed the chosen task id into `evals run --task`,
    or let `evals run --file --prompt` use a clean single match automatically."""
    state = _state(ctx)
    try:
        result = _client().evals.propose_contract(items=_read_jsonl(file), prompt=prompt)
    except (ValueError, TypeError) as e:
        _err.print(f"[red]error:[/red] {e}")
        raise typer.Exit(code=2)
    except ParetaError as e:
        raise _fail(e)
    if state.json:
        _emit(state, result)
        return
    if result.bound_task:
        _out.print(f"task:    [green]{result.bound_task}[/green] (`evals run --file … --prompt …` uses it automatically)")
    else:
        _out.print("[yellow]no clear match[/yellow] — choose a task below and pass it as --task")
    if result.message:
        _out.print(result.message)
    if result.proposals:
        table = Table(title="Proposals")
        table.add_column("task", style="cyan")
        table.add_column("confidence")
        table.add_column("fit", justify="right")
        table.add_column("why")
        for p in result.proposals:
            ev = p.evidence
            table.add_row(
                _dash(p.task_id), _dash(p.confidence),
                f"{ev.get('validated_n', '—')}/{ev.get('total_n', '—')}",
                (p.warning or ev.get("matcher_reason") or ""))
        _out.print(table)


def _read_jsonl(path: str) -> list[dict]:
    """Parse a JSONL file into a list of dicts (one object per non-blank line)."""
    from pathlib import Path

    items: list[dict] = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}:{i}: invalid JSON ({e.msg})")
    if not items:
        raise ValueError(f"{path}: no items found")
    return items


# ── evals sets ───────────────────────────────────────────────────────────
sets_app = typer.Typer(no_args_is_help=True, help="Manage eval sets (your data rows).")
evals_app.add_typer(sets_app, name="sets")


@sets_app.command("create")
def sets_create(
    ctx: typer.Context,
    file: str = typer.Option(..., "--file", help="JSONL file of items (one object per line)."),
    prompt: str = typer.Option(..., "--prompt", help="One sentence: what the model should do with each item."),
    task: Optional[str] = typer.Option(None, "--task", help="Task id to pin (optional; Pareta works out the scoring from --prompt otherwise)."),
    name: Optional[str] = typer.Option(None, "--name", help="Optional eval-set name."),
) -> None:
    """Create an eval set from a JSONL file of items. `--prompt` (what the model
    should do with each item) is required; Pareta works out the scoring from
    it, or pin a task with `--task`."""
    state = _state(ctx)
    try:
        items = _read_jsonl(file)
        es = _client().evals.sets.create(items=items, prompt=prompt, task=task, name=name)
    except (ValueError, TypeError) as e:
        _err.print(f"[red]error:[/red] {e}")
        raise typer.Exit(code=2)
    except ParetaError as e:
        raise _fail(e)
    if state.json:
        _emit(state, es)
        return
    _out.print(f"created eval set [cyan]{_dash(es.id)}[/cyan]  ({_dash(es.item_count)} items)")


@sets_app.command("list")
def sets_list(ctx: typer.Context) -> None:
    """List your eval sets."""
    state = _state(ctx)
    try:
        sets = _client().evals.sets.list()
    except ParetaError as e:
        raise _fail(e)
    if state.json:
        _emit_json([s.to_dict() for s in sets])
        return
    table = Table(title="Eval sets")
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("task")
    table.add_column("name")
    table.add_column("items", justify="right")
    for s in sets:
        table.add_row(_dash(s.id), _dash(s.task_id), _dash(s.name), _dash(s.item_count))
    _out.print(table)


@sets_app.command("show")
def sets_show(
    ctx: typer.Context,
    eval_set_id: str = typer.Argument(..., help="Eval-set id."),
) -> None:
    """Show one eval set."""
    state = _state(ctx)
    try:
        es = _client().evals.sets.retrieve(eval_set_id)
    except ParetaError as e:
        raise _fail(e)
    _emit(state, es)


@sets_app.command("delete")
def sets_delete(
    ctx: typer.Context,
    eval_set_id: str = typer.Argument(..., help="Eval-set id."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Delete an eval set (destructive — prompts unless --yes)."""
    if not yes:
        typer.confirm(f"Delete eval set {eval_set_id}?", abort=True)
    try:
        _client().evals.sets.delete(eval_set_id)
    except ParetaError as e:
        raise _fail(e)
    _out.print(f"[red]deleted[/red] {eval_set_id}")


# ── auto (the routing brain's surrounding surfaces) ─────────────────────
auto_app = typer.Typer(no_args_is_help=True,
                       help='model:"auto" — metrics + frontier comparison.')
app.add_typer(auto_app, name="auto")


@auto_app.command("metrics")
def auto_metrics(ctx: typer.Context) -> None:
    """Your org's model:"auto" traffic: requests, success rate, spend, and
    the PROJECTED savings vs frontier. Read-only, free."""
    state = _state(ctx)
    try:
        m = _client().auto.metrics()
    except ParetaError as e:
        raise _fail(e)
    if state.json:
        _emit_json(m)
        return
    _out.print(f"requests (30d):     {m.get('requests_30d')}")
    sr = m.get("success_rate_30d")
    _out.print(f"success rate:       {sr * 100:.1f}%" if sr is not None else "success rate:       —")
    _out.print(f"spend (30d):        ${(m.get('billed_micro_usd_30d') or 0) / 1e6:.4f}")
    sv = m.get("savings_vs_frontier_micro_usd_30d")
    mult = m.get("savings_multiple_30d")
    if sv is not None:
        _out.print(f"savings vs frontier: ${sv / 1e6:.4f}"
                   + (f" ({mult}x cheaper, projected)" if mult else " (projected)"))


@auto_app.command("compare")
def auto_compare(
    ctx: typer.Context,
    prompt: str = typer.Argument(..., help="The prompt to compare on."),
    frontier: str = typer.Option("gpt-5.5", "--frontier", "-f",
                                 help="Frontier model: gpt-5.5, gemini-3-5-flash, "
                                      "gemini-3-1-pro, claude-sonnet-4-6."),
) -> None:
    """Run one prompt against model:"auto" AND a frontier vendor, side by
    side, with both bills. METERED: two real calls."""
    state = _state(ctx)
    try:
        client = _client()
        auto_c = client.chat.completions.create(
            model="auto", messages=[{"role": "user", "content": prompt}])
        auto_text = auto_c.choices[0].message.content if auto_c.choices else ""
        fr = client.auto.compare_frontier(
            model=frontier, messages=[{"role": "user", "content": prompt}])
    except ParetaError as e:
        raise _fail(e)
    if state.json:
        _emit_json({"auto": {"content": auto_text},
                    "frontier": fr})
        return
    _out.print("[bold]Pareta (auto)[/bold]")
    _out.print(auto_text or "")
    _out.print(f"\n[bold]{fr.get('model')}[/bold]  "
               f"(${(fr.get('cost_micro_usd') or 0) / 1e6:.4f} · "
               f"{(fr.get('latency_ms') or 0) / 1000:.1f}s)")
    _out.print(fr.get("content") or "")


# ── chat ─────────────────────────────────────────────────────────────────
@app.command("chat")
def chat(
    ctx: typer.Context,
    prompt: Optional[str] = typer.Argument(None, help="Prompt text (omit to read from stdin)."),
    model: str = typer.Option("auto", "--model", "-m",
                              help='Model to call. The default "auto" is the routing '
                                   "brain — Pareta picks the best model per request."),
    stream: bool = typer.Option(False, "--stream", "-s", help="Stream tokens to stdout."),
) -> None:
    """Send a one-shot chat completion (default model: "auto" — the routing
    brain). Reads the prompt from the argument or, if omitted, from stdin."""
    state = _state(ctx)
    text = prompt if prompt is not None else sys.stdin.read()
    if not text or not text.strip():
        _err.print("[red]error:[/red] no prompt provided (pass it as an argument or on stdin)")
        raise typer.Exit(code=2)
    messages = [{"role": "user", "content": text}]
    try:
        client = _client()
        if stream:
            chunks = client.chat.completions.create(model=model, messages=messages, stream=True)
            got = False
            for chunk in chunks:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    got = True
                    sys.stdout.write(delta)
                    sys.stdout.flush()
            if got:
                sys.stdout.write("\n")
                sys.stdout.flush()
            return
        resp = client.chat.completions.create(model=model, messages=messages)
    except ParetaError as e:
        raise _fail(e)
    if state.json:
        _emit(state, resp)
        return
    content = resp.choices[0].message.content if resp.choices else None
    _out.print(content or "")


# ── retrieval (rerank + embed) ───────────────────────────────────────────
def _read_lines(path: str) -> list[str]:
    """Read a text file into non-blank lines (one document/text per line)."""
    from pathlib import Path

    lines = [ln for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        raise ValueError(f"{path}: no lines found")
    return lines


def _texts_from(positional: Optional[list[str]], file: Optional[str], what: str) -> list[str]:
    """Exactly one source: positional args OR --file."""
    if positional and file:
        raise ValueError(f"pass {what} as arguments OR --file, not both")
    if not positional and not file:
        raise ValueError(f"no {what} given (pass them as arguments or via --file)")
    return _read_lines(file) if file else list(positional or [])


def _snippet(text: str, width: int = 70) -> str:
    """One-line preview for tables: collapse whitespace, truncate."""
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


@app.command("rerank")
def rerank(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="The query to rank documents against."),
    documents: Optional[list[str]] = typer.Argument(None, help="Documents to score (or use --file)."),
    file: Optional[str] = typer.Option(None, "--file", help="File with one document per line."),
    top_n: Optional[int] = typer.Option(None, "--top-n", help="Return only the N most relevant "
                                        "(all documents are still scored and metered)."),
) -> None:
    """Rank documents by relevance to a query, most relevant first.
    Metered per document scored."""
    state = _state(ctx)
    try:
        docs = _texts_from(documents, file, "documents")
        ranked = _client().rerank(query, docs, top_n=top_n)
    except (ValueError, OSError) as e:
        _err.print(f"[red]error:[/red] {e}")
        raise typer.Exit(code=2)
    except ParetaError as e:
        raise _fail(e)
    if state.json:
        _emit(state, ranked)
        return
    table = Table(title="Rerank")
    table.add_column("rank", justify="right")
    table.add_column("score", justify="right")
    table.add_column("index", justify="right")
    table.add_column("document")
    for rank, r in enumerate(ranked.results, 1):
        doc = docs[r.index] if 0 <= r.index < len(docs) else ""
        table.add_row(str(rank), f"{r.relevance_score:.3f}", str(r.index), _snippet(doc))
    _out.print(table)
    scored = ranked.pairs if ranked.pairs is not None else len(docs)
    _out.print(f"{scored} documents scored (metered per document)")


@app.command("embed")
def embed(
    ctx: typer.Context,
    texts: Optional[list[str]] = typer.Argument(None, help="Texts to embed (or use --file)."),
    file: Optional[str] = typer.Option(None, "--file", help="File with one text per line."),
    input_type: str = typer.Option("document", "--type", help='Embedding side: "query" or "document".'),
    out: Optional[str] = typer.Option(None, "--out", help='Write vectors as JSONL rows '
                                      '{"index": i, "vector": [...]}.'),
) -> None:
    """Embed texts into unit-normalized vectors. Vectors are written with
    --out (JSONL) or dumped with --json — the table shows sizes only.
    Metered per input token."""
    state = _state(ctx)
    if input_type not in ("query", "document"):
        _err.print('[red]error:[/red] --type must be "query" or "document"')
        raise typer.Exit(code=2)
    try:
        inputs = _texts_from(texts, file, "texts")
        emb = _client().embeddings(inputs, input_type=input_type)
    except (ValueError, OSError) as e:
        _err.print(f"[red]error:[/red] {e}")
        raise typer.Exit(code=2)
    except ParetaError as e:
        raise _fail(e)
    if out is not None:
        from pathlib import Path

        try:
            with Path(out).open("w", encoding="utf-8") as f:
                for i, vec in enumerate(emb.vectors):
                    f.write(json.dumps({"index": i, "vector": vec}) + "\n")
        except OSError as e:
            _err.print(f"[red]error:[/red] cannot write {out}: {e}")
            raise typer.Exit(code=2)
        _err.print(f"[green]wrote[/green] {out}  ({len(emb.vectors)} vectors)")
    if state.json:
        _emit(state, emb)
        return
    table = Table(title="Embeddings")
    table.add_column("index", justify="right")
    table.add_column("chars", justify="right")
    table.add_column("dim", justify="right")
    for i, (text, vec) in enumerate(zip(inputs, emb.vectors)):
        table.add_row(str(i), str(len(text)), str(len(vec)))
    _out.print(table)
    _out.print(f"{len(inputs)} texts, {_dash(emb.prompt_tokens)} prompt tokens "
               "(metered per input token)")


# ── audio ────────────────────────────────────────────────────────────────
audio_app = typer.Typer(no_args_is_help=True, help="Speech — transcribe (ASR) + speak (TTS).")
app.add_typer(audio_app, name="audio")


@audio_app.command("transcribe")
def audio_transcribe(
    ctx: typer.Context,
    file: str = typer.Argument(..., help="Audio file to transcribe."),
    language: Optional[str] = typer.Option(None, "--language", help="ISO language hint (omit to auto-detect)."),
) -> None:
    """Transcribe an audio file (speech-to-text)."""
    state = _state(ctx)
    try:
        result = _client().audio.transcriptions(file, language=language)
    except ParetaError as e:
        raise _fail(e)
    if state.json:
        _emit(state, result)
        return
    _out.print(result.text or "")


@audio_app.command("speak")
def audio_speak(
    ctx: typer.Context,
    text: str = typer.Argument(..., help="Text to synthesize."),
    voice: Optional[str] = typer.Option(None, "--voice", help="Voice id (omit for the default)."),
    out: Optional[str] = typer.Option(None, "--out", help="Output file (default: speech.wav)."),
) -> None:
    """Synthesize speech from text (text-to-speech) and write it to a file."""
    state = _state(ctx)
    try:
        speech = _client().audio.speech(text, voice=voice)
    except ParetaError as e:
        raise _fail(e)
    dest = out or f"speech.{speech.format or 'wav'}"
    speech.save(dest)
    if state.json:
        _emit_json({"file": dest, "sample_rate": speech.sample_rate,
                    "duration_s": speech.duration_s, "format": speech.format})
        return
    _out.print(f"[green]wrote[/green] {dest}  ({_dash(speech.duration_s)}s)")


# ── images ───────────────────────────────────────────────────────────────
@app.command("image")
def image(
    ctx: typer.Context,
    prompt: str = typer.Argument(..., help="Text prompt describing the image."),
    size: Optional[str] = typer.Option(None, "--size", help="Delivery size, e.g. 1024x1024 (default), 2048x2048, 2560x1440."),
    seed: Optional[int] = typer.Option(None, "--seed", help="Pin the noise seed for reproducibility."),
    out: Optional[str] = typer.Option(None, "--out", help="Output file (default: image.png)."),
) -> None:
    """Generate an image from a prompt and write it to a file.
    Billed FLAT per image — every size costs the same."""
    state = _state(ctx)
    try:
        result = _client().images.generate(prompt, size=size, seed=seed)
    except ValueError as e:
        _err.print(f"[red]error:[/red] {e}")
        raise typer.Exit(code=2)
    except ParetaError as e:
        raise _fail(e)
    dest = out or "image.png"
    result.save(dest)
    if state.json:
        _emit_json({"file": dest, "size": result.size, "model": result.model})
        return
    _out.print(f"[green]wrote[/green] {dest}  ({result.size}, {result.model})")


@app.command("image-edit")
def image_edit(
    ctx: typer.Context,
    image: str = typer.Argument(..., help="Reference image file to edit (PNG/JPEG, ≤25MB)."),
    prompt: str = typer.Argument(..., help="Plain-language edit instruction."),
    seed: Optional[int] = typer.Option(None, "--seed", help="Pin the noise seed for reproducibility."),
    out: Optional[str] = typer.Option(None, "--out", help="Output file (default: edited.png)."),
) -> None:
    """Edit an image with an instruction (no mask) and write the result.
    The output keeps the reference's aspect ratio. Billed FLAT per edit."""
    state = _state(ctx)
    # The CLI argument is documented as a FILE — fail a typo'd path locally
    # instead of letting the SDK's path-or-base64 fallback ship the path
    # string to the server as "base64" (opaque 400).
    import os as _os
    if not _os.path.isfile(image):
        _err.print(f"[red]error:[/red] no such image file: {image}")
        raise typer.Exit(code=2)
    try:
        result = _client().images.edit(image, prompt, seed=seed)
    except (ValueError, TypeError, OSError) as e:
        _err.print(f"[red]error:[/red] {e}")
        raise typer.Exit(code=2)
    except ParetaError as e:
        raise _fail(e)
    dest = out or "edited.png"
    result.save(dest)
    if state.json:
        _emit_json({"file": dest, "size": result.size, "model": result.model})
        return
    _out.print(f"[green]wrote[/green] {dest}  ({result.size}, {result.model})")


if __name__ == "__main__":  # pragma: no cover
    app()
