"""Pareta MCP server — drive Pareta from an AI agent (Claude Desktop, Cursor, …).

Exposes Pareta as Model Context Protocol tools over stdio, auto-first:

- inference: `chat` (model:"auto" — the routing brain — by default)
- proof: `run_eval` / `get_eval_run` (benchmark "auto" against frontier
  models on the user's own data), `auto_metrics`, `compare_frontier`
- discovery: `match_task`, `list_tasks`, `get_task`, `list_models`
- audio: `transcribe`, `speak`
- retrieval: `rerank`, `embed`

The agent calls these tools; the MCP client gates each call behind its own
per-tool approval, which is the only guardrail on the metered verbs (chat,
evals, audio, compare_frontier).

Install + register (run it in its own isolated env — like any MCP server)
-------------------------------------------------------------------------
Easiest is uvx (no install): point your MCP client's `command` at `uvx`. For
Claude Desktop, edit `claude_desktop_config.json` (Settings → Developer →
Edit Config):

    {
      "mcpServers": {
        "pareta": {
          "command": "uvx",
          "args": ["--from", "pareta[mcp]", "pareta-mcp"],
          "env": { "PARETA_API_KEY": "pareta_sk_…" }
        }
      }
    }

Prefer a persistent install? `pipx install "pareta[mcp]"` puts `pareta-mcp` on
PATH in a dedicated venv; then use `"command": "pareta-mcp"`. Avoid a plain
`pip install "pareta[mcp]"` into a shared/app environment — its mcp/starlette
dependencies can clash with e.g. FastAPI, and the console script may not be on
your PATH.

`PARETA_API_KEY` is required (mint a `pareta_sk_` key in the dashboard);
`PARETA_BASE_URL` is optional and defaults to https://api.pareta.ai. The key is
read lazily on the first tool call, so the server starts even if it is unset —
you just get a clear error back when a tool runs.

Run it directly for a smoke test:

    PARETA_API_KEY=pareta_sk_… uvx --from "pareta[mcp]" pareta-mcp
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from mcp.server.fastmcp import FastMCP

from ._client import Pareta
from ._exceptions import ParetaError

mcp = FastMCP("pareta")

# Built once on first use and reused. NOT constructed at import time: a missing
# PARETA_API_KEY must not crash the stdio server at startup — only when a tool
# actually runs (surfaced as a tool error, never a server crash).
_cached_client: Pareta | None = None

F = TypeVar("F", bound=Callable[..., dict])


def _client() -> Pareta:
    """Return the cached `Pareta` client, building it from the environment
    (`PARETA_API_KEY` + optional `PARETA_BASE_URL`) on first use."""
    global _cached_client
    if _cached_client is None:
        _cached_client = Pareta.from_env()
    return _cached_client


def _guard(fn: F) -> F:
    """Wrap a tool body so any `ParetaError` (missing key, HTTP error, …) is
    returned as an `{"error": …}` dict instead of raising — the
    agent reads a clean message rather than a traceback."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except ParetaError as e:
            return {"error": str(e), "type": type(e).__name__}

    return wrapper  # type: ignore[return-value]


# ── discovery ──────────────────────────────────────────────────────────────
@mcp.tool()
@_guard
def match_task(query: str, top_k: int = 5) -> dict[str, Any]:
    """Resolve a free-text intent to a Pareta task, capability, or 'unsupported'.

    Use this FIRST when the user describes what they want in plain language
    (e.g. "extract fields from invoices"). Returns the router's outcome `type`
    ('task' | 'capability' | 'unsupported' | 'none'), the chosen task id (when
    a benchmarked task fits), the matched capability lane, and the reasoning.
    Feed `chosen.task_id` into `run_eval` to prove model="auto" on the user's
    own data; inference itself is just `chat` (model="auto").
    """
    return _client().tasks.match(query, top_k=top_k).to_dict()


@mcp.tool()
@_guard
def list_tasks() -> dict[str, Any]:
    """List every benchmarked task in the Pareta catalog (id, scorer, whether it
    takes a document/image input). Browse this to find a task to eval on."""
    tasks = _client().tasks.list()
    return {"tasks": [t.to_dict() for t in tasks]}


@mcp.tool()
@_guard
def get_task(task_id: str) -> dict[str, Any]:
    """Retrieve one task's full schema and default scorer by id (e.g.
    'invoice-extraction'). Inspect this before building an eval set for it."""
    return _client().tasks.retrieve(task_id).to_dict()


@mcp.tool()
@_guard
def list_models() -> dict[str, Any]:
    """List the models your org can reach right now. Each `id` is usable as the
    `model` argument to `chat` (OpenAI-compatible), though `model="auto"` — the
    routing brain — is the recommended surface."""
    models = _client().models.list()
    return {"data": [m.to_dict() for m in models.data]}


# ── eval ───────────────────────────────────────────────────────────────────
@mcp.tool()
@_guard
def run_eval(
    models: list[str],
    eval_set: str | None = None,
    task: str | None = None,
    items: list[dict[str, Any]] | None = None,
    frontier: list[str] | None = None,
    name: str | None = None,
    wait: bool = True,
) -> dict[str, Any]:
    """Run a bring-your-own-data eval comparing `models` (candidate model ids —
    include "auto") on a task, optionally against `frontier` vendor model ids.

    Provide EITHER `eval_set` (an existing eval-set id) OR both `task` and
    `items` (a list of row dicts) to create one inline. METERED: the run debits
    your org balance for the compute. With `wait=True` (default) this blocks
    until the run finishes and returns the results + billed cost; `wait=False`
    returns immediately with the run id to poll via `get_eval_run`.
    

    TIP: include "auto" in the candidate models to benchmark Pareta's
    routing brain itself against frontier models on this data — the
    cost-quality result is the product's core claim, measured on YOUR data.
    """
    run = _client().evals.runs.create(
        eval_set=eval_set,
        task=task,
        items=items,
        models=models,
        frontier=frontier,
        name=name,
        wait=wait,
    )
    return run.to_dict()


@mcp.tool()
@_guard
def get_eval_run(run_id: str) -> dict[str, Any]:
    """Retrieve an eval run by id: its status, per-model results (quality + cost),
    and the billed total. Poll this after a `run_eval` started with wait=False."""
    return _client().evals.runs.retrieve(run_id).to_dict()


# ── inference ──────────────────────────────────────────────────────────────
@mcp.tool()
@_guard
def chat(prompt: str, model: str = "auto") -> dict[str, Any]:
    """Send a single-turn prompt to Pareta and return the assistant's text
    reply (non-streaming).

    The DEFAULT `model="auto"` is Pareta's routing brain — it plans the
    request, routes each part to the cheapest model that holds frontier-grade
    quality, verifies, and answers. This is the recommended way to call
    Pareta. Pass a specific model id (from `list_models`) only when you
    deliberately want one model. METERED: a successful completion debits the
    org balance (a failed one bills $0).
    Returns `{"text": …, "model": …, "usage": …}`.
    """
    completion = _client().chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}]
    )
    choices = completion.choices
    text = choices[0].message.content if choices else None
    return {"text": text, "model": completion.model, "usage": completion.usage.to_dict()}


@mcp.tool()
@_guard
def auto_metrics() -> dict[str, Any]:
    """The org's `model="auto"` traffic, rolled up: requests + success rate
    (30d), spend, hourly p50/p95/error buckets (7d), daily success cells, and
    the PROJECTED savings vs frontier (labeled projected until dual-run
    calibration). Read-only, free."""
    return _client().auto.metrics()


@mcp.tool()
@_guard
def compare_frontier(prompt: str, model: str = "gpt-5.5") -> dict[str, Any]:
    """Run one prompt against a frontier vendor for a side-by-side with
    `chat` (model="auto"). Allowed: gpt-5.5, gemini-3-5-flash,
    gemini-3-1-pro, claude-sonnet-4-6. METERED at the vendor's actual token
    cost (a failed vendor call bills $0). Returns
    `{"model", "content", "cost_micro_usd", "latency_ms"}`."""
    return _client().auto.compare_frontier(
        model=model, messages=[{"role": "user", "content": prompt}])


# ── audio ──────────────────────────────────────────────────────────────────
@mcp.tool()
@_guard
def transcribe(path: str, language: str | None = None) -> dict[str, Any]:
    """Transcribe a local audio file (speech-to-text). `path` is a file path on
    this machine; `language` is an optional ISO hint (omit to auto-detect).
    METERED per minute of input audio. Returns `{"text", "language", "duration_s"}`."""
    result = _client().audio.transcriptions(path, language=language)
    return result.to_dict()


@mcp.tool()
@_guard
def speak(text: str, voice: str | None = None, out_path: str = "speech.mp3") -> dict[str, Any]:
    """Synthesize `text` to speech (text-to-speech) and save it to `out_path` on
    this machine. `voice` is optional (omit for the default Kokoro voice).
    METERED per minute of output audio. Returns the saved path plus the audio's
    sample rate, duration, and format."""
    speech = _client().audio.speech(text, voice=voice)
    speech.save(out_path)
    return {
        "saved_to": out_path,
        "sample_rate": speech.sample_rate,
        "duration_s": speech.duration_s,
        "format": speech.format,
    }


# ── rerank ─────────────────────────────────────────────────────────────────
@mcp.tool()
@_guard
def rerank(query: str, documents: list[str], top_n: int | None = None) -> dict[str, Any]:
    """Rank `documents` by relevance to `query` (document reranking). Returns
    `{"results": [{"index", "relevance_score"}, ...]}` ordered most-relevant-
    first; `index` points into YOUR documents list and scores are calibrated
    P(relevant) in (0, 1). `top_n` truncates the response (all documents are
    still scored). METERED per document scored."""
    result = _client().rerank(query, documents, top_n=top_n)
    return result.to_dict()


@mcp.tool()
@_guard
def embed(texts: list[str], input_type: str | None = None) -> dict[str, Any]:
    """Embed texts into unit-normalized vectors (semantic search / RAG
    recall). `input_type="query"` for the search side, omit for documents.
    Returns {"vectors": [[...], ...], "prompt_tokens": N}. METERED per
    input token."""
    result = _client().embeddings(texts, input_type=input_type)
    return {"vectors": result.vectors, "prompt_tokens": result.prompt_tokens}


def main() -> None:
    """Console-script entrypoint (`pareta-mcp`): run the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
