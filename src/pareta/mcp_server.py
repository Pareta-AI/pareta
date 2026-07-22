"""Pareta MCP server — drive Pareta from an AI agent (Claude Desktop, Cursor, …).

Exposes Pareta as Model Context Protocol tools over stdio, auto-first:

- inference: `chat` (model:"auto" — the routing brain — by default)
- proof: `run_eval` / `get_eval_run` (benchmark "auto" against frontier
  models on the user's own data), `auto_metrics`, `compare_frontier`
- eval scoring: `propose_contract` (Pareta works out how to score your data
  from your prompt), `match_task`, `list_tasks`, `get_task`; models: `list_models`
- audio: `transcribe`, `speak`
- retrieval: `rerank`, `embed`
- images: `generate_image` (saves to disk — bytes never enter context)

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


# ── tasks (how evals score data) ───────────────────────────────────────────────────
@mcp.tool()
@_guard
def match_task(query: str, top_k: int = 5) -> dict[str, Any]:
    """Find the task that scores a dataset the user wants to benchmark.

    Use this when the user wants to EVALUATE on their own data: a plain-English
    description of the dataset (e.g. "invoices with labeled fields") returns the
    task id whose scorer grades it. Returns the outcome `type` ('task' |
    'capability' | 'unsupported' | 'none'), the chosen task id, the matched
    lane, and the reasoning. Feed `chosen.task_id` into `run_eval`. NOT needed
    for inference — send any generation job straight to `chat` (model="auto");
    a no-match is a statement about scoring, not serving.
    """
    return _client().tasks.match(query, top_k=top_k).to_dict()


@mcp.tool()
@_guard
def list_tasks() -> dict[str, Any]:
    """List every benchmarked task in the Pareta catalog — each says how an
    eval scores your data (id, scorer, whether it takes a document/image
    input). Browse this when building an eval."""
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
    """List the models visible to your org. Informational: these ids show up
    as eval baselines and in results. Inference goes to `chat` with
    model="auto" — standard orgs cannot call other ids directly."""
    models = _client().models.list()
    return {"data": [m.to_dict() for m in models.data]}


# ── eval ───────────────────────────────────────────────────────────────────
@mcp.tool()
@_guard
def propose_contract(items: list[dict[str, Any]], prompt: str) -> dict[str, Any]:
    """How would your data be scored under your stated `prompt`? Pareta
    matches a dataset (list of {"input":…, "expected_output":…} rows) + one
    sentence on what the model should do with each item to a catalog task.
    Stateless — nothing is persisted. Returns ranked proposals + `bound_task`
    (how a task-less create would score this set, or null when the user must
    choose — e.g. "custom-eval", a judge panel grading each answer against
    what was asked for). Feed `bound_task` (or a chosen proposal's task_id)
    into `run_eval` as `task`, or call `run_eval` with `prompt` and Pareta
    works out the scoring."""
    result = _client().evals.propose_contract(items=items, prompt=prompt)
    # to_dict() is the raw server payload; surface the SDK-computed decision
    # the docstring promises (raw JSON has no bound_task/is_clean).
    return {**result.to_dict(), "bound_task": result.bound_task,
            "is_clean": result.is_clean}


@mcp.tool()
@_guard
def run_eval(
    models: list[str],
    eval_set: str | None = None,
    task: str | None = None,
    items: list[dict[str, Any]] | None = None,
    prompt: str | None = None,
    frontier: list[str] | None = None,
    name: str | None = None,
    wait: bool = True,
) -> dict[str, Any]:
    """Run a bring-your-own-data eval comparing `models` (candidate model ids —
    include "auto") on a task, optionally against `frontier` vendor model ids.

    Provide EITHER `eval_set` (an existing eval-set id) OR `items` (a list of
    row dicts) + `prompt` (one sentence on what the model should do with each
    item — REQUIRED to build a set) to create one inline. Pareta works out how
    to score the results from your prompt; pass `task` to pin one explicitly.
    METERED: the run debits your org balance for the compute. With `wait=True`
    (default) this blocks until the run finishes and returns the results +
    billed cost; `wait=False` returns immediately with the run id to poll via
    `get_eval_run`.

    TIP: include "auto" in the candidate models to benchmark Pareta's
    routing brain itself against frontier models on this data — the
    cost-quality result is the product's core claim, measured on YOUR data.
    """
    run = _client().evals.runs.create(
        eval_set=eval_set,
        task=task,
        items=items,
        prompt=prompt,
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
def _chat_content(prompt: str, image_paths: list[str] | None):
    """Build the message content: a bare string for text-only, or an
    OpenAI-style multimodal list (text + image_url blocks) when local
    images/PDFs are attached. Pareta's vision lane reads the images; PDFs are
    rasterized server-side."""
    if not image_paths:
        return prompt
    import base64
    import mimetypes
    import os

    parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for p in image_paths:
        path = os.path.expanduser(p)
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as e:
            # _guard only catches ParetaError; turn a bad path into a clean
            # agent-readable message instead of a raw traceback.
            raise ParetaError(f"could not read image path {p!r}: {e}") from e
        mime = mimetypes.guess_type(path)[0] or "image/png"
        b64 = base64.b64encode(data).decode("ascii")
        parts.append({"type": "image_url",
                      "image_url": {"url": f"data:{mime};base64,{b64}"}})
    return parts


@mcp.tool()
@_guard
def chat(prompt: str, model: str = "auto",
         image_paths: list[str] | None = None) -> dict[str, Any]:
    """Send a single-turn prompt to Pareta and return the assistant's text
    reply (non-streaming).

    The DEFAULT `model="auto"` is Pareta's routing brain — it plans the
    request, routes each part to the cheapest model that holds frontier-grade
    quality, verifies, and answers. "auto" is the inference surface — other
    model ids only work for orgs with the direct-model entitlement.

    `image_paths`: optional local image or PDF file paths — attach receipts,
    screenshots, scanned documents, etc. and Pareta routes them to its vision
    lane (PDFs are rasterized server-side).

    METERED: a successful completion debits the org balance (a failed one bills
    $0). Returns `{"text", "model", "usage"}` plus the per-call receipt:
    `billed_micro_usd` (what Pareta charged), `frontier_would_have_cost_micro_usd`
    (what one list-priced frontier call would have cost), and
    `savings_vs_frontier_x` (e.g. 17.0 = 17× cheaper)."""
    completion = _client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": _chat_content(prompt, image_paths)}],
    )
    choices = completion.choices
    text = choices[0].message.content if choices else None
    out: dict[str, Any] = {
        "text": text, "model": completion.model, "usage": completion.usage.to_dict(),
    }
    if completion.billed_micro_usd is not None:
        out["billed_micro_usd"] = completion.billed_micro_usd
        out["billed_usd"] = round(completion.billed_micro_usd / 1_000_000, 6)
    if completion.frontier_would_have_cost_micro_usd is not None:
        out["frontier_would_have_cost_micro_usd"] = completion.frontier_would_have_cost_micro_usd
        out["frontier_would_have_cost_usd"] = round(
            completion.frontier_would_have_cost_micro_usd / 1_000_000, 6)
    if completion.savings_factor is not None:
        out["savings_vs_frontier_x"] = completion.savings_factor
    return out


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


@mcp.tool()
@_guard
def generate_image(prompt: str, path: str, size: str | None = None) -> dict[str, Any]:
    """Generate one image from a text prompt and SAVE it to `path` (.png) —
    the image bytes are written to disk, not returned (they would not fit in
    context). `size` e.g. "1024x1024" (default) or "2560x1440"; every size
    bills the same FLAT per-image price. METERED per image. Returns
    {"path", "size", "model"}."""
    result = _client().images.generate(prompt, size=size)
    result.save(path)
    return {"path": path, "size": result.size, "model": result.model}


@mcp.tool()
@_guard
def edit_image(image_path: str, prompt: str, output_path: str) -> dict[str, Any]:
    """Edit the image at `image_path` with a plain-language instruction (no
    mask) and SAVE the result to `output_path` (.png) — image bytes are read
    from and written to disk, never returned (they would not fit in context).
    The output keeps the reference's aspect ratio. METERED flat per edit.
    Returns {"path", "size", "model"}."""
    import os as _os

    # `image_path` is a PATH by contract — fail locally on a typo instead of
    # the SDK's path-or-base64 fallback sending the string to the server.
    if not _os.path.isfile(image_path):
        raise FileNotFoundError(f"no such image file: {image_path}")
    result = _client().images.edit(image_path, prompt)
    result.save(output_path)
    return {"path": output_path, "size": result.size, "model": result.model}


def main() -> None:
    """Console-script entrypoint (`pareta-mcp`): run the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
