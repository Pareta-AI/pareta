"""Lightweight response objects for inference.

These are hand-written for the OpenAI-compatible chat surface so callers get
attribute access + autocomplete without a pydantic dependency. The plan (§10)
generates the full typed model set from the backend's OpenAPI schema later;
until then these cover the inference shapes the SDK returns.

Every object keeps the raw server JSON on `._raw` and exposes it via
`.to_dict()`, so nothing the API returns is ever lost behind the typed layer.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

_MICRO_PER_DOLLAR = 1_000_000
_MICRO_PER_CENT = 10_000


def _dollars_floored_to_cents(micro_usd: int | None) -> Decimal:
    """Money the user is billed → Decimal dollars, rounded DOWN to whole cents
    (SDK_PLAN §6). We floor (never round up) so the SDK never overstates a
    charge; micro-USD precision is kept on the `_micro_usd` accessor. A 5 µUSD
    run reads Decimal('0.00')."""
    micro = int(micro_usd or 0)
    return (Decimal(micro // _MICRO_PER_CENT) / 100).quantize(Decimal("0.01"))


class _Base:
    __slots__ = ("_raw",)

    def __init__(self, raw: dict[str, Any]):
        self._raw = raw or {}

    def to_dict(self) -> dict[str, Any]:
        return self._raw

    def __getitem__(self, key: str) -> Any:  # dict-style escape hatch
        return self._raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._raw.get(key, default)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._raw!r})"


class Usage(_Base):
    @property
    def prompt_tokens(self) -> int | None:
        return self._raw.get("prompt_tokens")

    @property
    def completion_tokens(self) -> int | None:
        return self._raw.get("completion_tokens")

    @property
    def total_tokens(self) -> int | None:
        return self._raw.get("total_tokens")


class Message(_Base):
    @property
    def role(self) -> str | None:
        return self._raw.get("role")

    @property
    def content(self) -> str | None:
        return self._raw.get("content")


class Choice(_Base):
    @property
    def index(self) -> int | None:
        return self._raw.get("index")

    @property
    def finish_reason(self) -> str | None:
        return self._raw.get("finish_reason")

    @property
    def message(self) -> Message:
        return Message(self._raw.get("message") or {})

    @property
    def delta(self) -> Message:
        """Streaming chunks carry `delta` instead of `message`."""
        return Message(self._raw.get("delta") or {})


class ChatCompletion(_Base):
    @property
    def id(self) -> str | None:
        return self._raw.get("id")

    @property
    def model(self) -> str | None:
        return self._raw.get("model")

    @property
    def created(self) -> int | None:
        return self._raw.get("created")

    @property
    def choices(self) -> list[Choice]:
        return [Choice(c) for c in (self._raw.get("choices") or [])]

    @property
    def usage(self) -> Usage:
        return Usage(self._raw.get("usage") or {})


class ChatCompletionChunk(ChatCompletion):
    """One SSE delta. `chunk.choices[0].delta.content` is the incremental text."""


class Model(_Base):
    @property
    def id(self) -> str | None:
        return self._raw.get("id")

    @property
    def owned_by(self) -> str | None:
        return self._raw.get("owned_by")

    @property
    def created(self) -> int | None:
        return self._raw.get("created")


class ModelList(_Base):
    @property
    def data(self) -> list[Model]:
        return [Model(m) for m in (self._raw.get("data") or [])]

    def __iter__(self) -> Iterable[Model]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self._raw.get("data") or [])


class Endpoint(_Base):
    """A deployed endpoint. `id` (== name) is what you pass to
    `chat.completions.create(model=…)`. `model` is the per-task public alias
    (real ids never cross the D3 boundary); `to_dict()` has the full record."""

    @property
    def id(self) -> str | None:
        return self._raw.get("id") or self._raw.get("name")

    @property
    def name(self) -> str | None:
        return self._raw.get("name")

    @property
    def model(self) -> str | None:
        return self._raw.get("model")

    @property
    def status(self) -> str | None:
        return self._raw.get("status")

    @property
    def task(self) -> str | None:
        return self._raw.get("taskName") or self._raw.get("task")

    @property
    def url(self) -> str | None:
        return self._raw.get("url")

    @property
    def is_live(self) -> bool:
        return self._raw.get("status") == "live"

    @property
    def recommended_system_prompt(self) -> str | None:
        """For a structured-extraction endpoint (contract / SEC / ICD …), the
        system prompt the benchmark was measured with. The proxy applies it
        automatically when you send no `system` message, so a deployed model
        matches its leaderboard quality by default; it's returned here so you can
        read it, or override it by sending your own `system` message. `None` when
        the task has no injectable prompt (see `prompt_scaffold` for classifiers)."""
        return self._raw.get("recommendedSystemPrompt")

    @property
    def prompt_scaffold(self) -> str | None:
        """For a fixed-label classification endpoint, a copy-and-customize `system`
        prompt template. Unlike `recommended_system_prompt` it is NEVER auto-applied
        — the label set is yours, not the benchmark's — so you fill in your own
        categories and send it as your `system` message. `None` for other tasks."""
        return self._raw.get("promptScaffold")


def _endpoint_list(raw) -> list[Endpoint]:
    """GET /v1/endpoints returns a bare JSON array."""
    return [Endpoint(e) for e in (raw or [])]


# ── tasks ─────────────────────────────────────────────────────────────
class Task(_Base):
    @property
    def id(self) -> str | None:
        return self._raw.get("id")

    @property
    def default_scorer(self) -> str | None:
        return self._raw.get("default_scorer")

    @property
    def has_blob_input(self) -> bool:
        return bool(self._raw.get("has_blob_input"))


def _task_list(raw) -> list[Task]:
    """GET /v1/tasks → {"tasks": [...]}."""
    return [Task(t) for t in ((raw or {}).get("tasks") or [])]


class TaskMatchCandidate(_Base):
    @property
    def task_id(self) -> str | None:
        return self._raw.get("task_id")

    @property
    def score(self) -> float | None:
        return self._raw.get("score")

    @property
    def confidence(self) -> str | None:
        return self._raw.get("confidence")


class Capability(_Base):
    """A general capability lane (chat / coding / agentic / vision / asr / tts)
    the match resolved to — returned on `TaskMatch.capability` when
    `TaskMatch.type == "capability"`. `id` is the lane id; `category` /
    `category_id` point at its catalog category."""

    @property
    def id(self) -> str | None:
        return self._raw.get("id")

    @property
    def label(self) -> str | None:
        return self._raw.get("label")

    @property
    def category(self) -> str | None:
        return self._raw.get("category")

    @property
    def category_id(self) -> str | None:
        return self._raw.get("category_id")

    @property
    def desc(self) -> str | None:
        return self._raw.get("desc")


class TaskMatch(_Base):
    """Result of tasks.match(): an LLM router reasons about intent and returns
    ONE outcome via `.type`:

      - "task"        a benchmarked task fit → `.chosen.task_id`, deploy it.
      - "capability"  a general lane → `.capability` (chat/coding/agentic/
                      vision/asr/tts).
      - "unsupported" Pareta does not cover this request (a correct answer, not
                      an error); `.reasoning` explains why.
      - "none"        the router was unavailable and the lexical fallback found
                      nothing confident.

    Legacy keys (`.matched`, `.chosen`, `.candidates`, `.ambiguous`, `.matcher`)
    are kept for backward compatibility; `.reasoning` / `.confidence` are
    populated by the reasoning matcher."""

    @property
    def query(self) -> str | None:
        return self._raw.get("query")

    @property
    def type(self) -> str | None:
        """One of 'task' | 'capability' | 'unsupported' | 'none'."""
        return self._raw.get("type")

    @property
    def matched(self) -> bool:
        return bool(self._raw.get("matched"))

    @property
    def chosen(self) -> TaskMatchCandidate | None:
        c = self._raw.get("chosen")
        return TaskMatchCandidate(c) if c else None

    @property
    def capability(self) -> Capability | None:
        """The general lane this matched (only when `.type == "capability"`)."""
        c = self._raw.get("capability")
        return Capability(c) if c else None

    @property
    def candidates(self) -> list[TaskMatchCandidate]:
        return [TaskMatchCandidate(c) for c in (self._raw.get("candidates") or [])]

    @property
    def ambiguous(self) -> bool:
        return bool(self._raw.get("ambiguous"))

    @property
    def reasoning(self) -> str | None:
        """The router's natural-language rationale (reasoning matcher only)."""
        return self._raw.get("reasoning")

    @property
    def confidence(self) -> str | None:
        """Match confidence ('high' | 'medium' | 'low'); None on the lexical
        fallback."""
        return self._raw.get("confidence")

    @property
    def matcher(self) -> str | None:
        """'reason' (LLM router) or 'keyword' (lexical fallback)."""
        return self._raw.get("matcher")


# ── audio (speech) ─────────────────────────────────────────────────────
class Transcription(_Base):
    """Speech-to-text result from `audio.transcriptions(...)`.
    `.text` is the transcript; `.duration_s` is the input audio length that was
    metered (per minute)."""

    @property
    def text(self) -> str | None:
        return self._raw.get("text")

    @property
    def language(self) -> str | None:
        return self._raw.get("language")

    @property
    def duration_s(self) -> float | None:
        return self._raw.get("duration_s")

    def __str__(self) -> str:
        return self.text or ""


class Speech(_Base):
    """Text-to-speech result from `audio.speech(...)`. `.audio` is the decoded
    audio bytes (use `.save(path)` to write a file); `.duration_s` is the output
    audio length that was metered (per minute)."""

    @property
    def audio(self) -> bytes:
        """The synthesized audio, base64-decoded to raw bytes."""
        b64 = self._raw.get("audio_base64") or ""
        from base64 import b64decode

        return b64decode(b64) if b64 else b""

    @property
    def audio_base64(self) -> str | None:
        return self._raw.get("audio_base64")

    @property
    def sample_rate(self) -> int | None:
        return self._raw.get("sample_rate")

    @property
    def duration_s(self) -> float | None:
        return self._raw.get("duration_s")

    @property
    def format(self) -> str | None:
        """Container/codec of the returned audio (e.g. 'wav')."""
        return self._raw.get("format")

    def save(self, path) -> "Speech":
        """Write the decoded audio bytes to `path` (str or os.PathLike).
        Returns self for chaining."""
        from pathlib import Path

        Path(path).write_bytes(self.audio)
        return self


# ── evals ─────────────────────────────────────────────────────────────
class EvalSet(_Base):
    @property
    def id(self) -> str | None:
        return self._raw.get("id")

    @property
    def task_id(self) -> str | None:
        return self._raw.get("task_id")

    @property
    def name(self) -> str | None:
        return self._raw.get("name")

    @property
    def item_count(self) -> int | None:
        return self._raw.get("item_count")

    @property
    def scoring_strategy(self) -> str | None:
        return self._raw.get("scoring_strategy")


def _eval_set_from_create(raw) -> EvalSet:
    """POST /v1/eval-sets → {"eval_set": {...}}."""
    return EvalSet((raw or {}).get("eval_set") or {})


def _eval_set_list(raw) -> list[EvalSet]:
    """GET /v1/eval-sets → {"eval_sets": [...]}."""
    return [EvalSet(e) for e in ((raw or {}).get("eval_sets") or [])]


class EvalResult(_Base):
    """One model's aggregate on an eval run. `model_id` is the per-task public
    alias; `kind` ('open' | 'frontier') is populated once Slice 4 formalizes the
    result schema."""

    @property
    def model_id(self) -> str | None:
        return self._raw.get("model_id")

    @property
    def kind(self) -> str | None:
        return self._raw.get("kind")

    @property
    def quality_mean(self) -> float | None:
        return self._raw.get("quality_mean")

    @property
    def quality_ci_low(self) -> float | None:
        return self._raw.get("quality_ci_low")

    @property
    def quality_ci_high(self) -> float | None:
        return self._raw.get("quality_ci_high")

    @property
    def mean_cost_micro_usd(self) -> int | None:
        return self._raw.get("mean_cost_micro_usd")

    @property
    def n_succeeded(self) -> int | None:
        return self._raw.get("n_succeeded")

    @property
    def error_count(self) -> int | None:
        return self._raw.get("error_count")


class LeaderboardEntry(_Base):
    @property
    def name(self) -> str | None:
        return self._raw.get("name")

    @property
    def kind(self) -> str | None:
        return self._raw.get("kind")

    @property
    def quality(self) -> float | None:
        return self._raw.get("quality")

    @property
    def cost_per_request_micro_usd(self) -> int | None:
        return self._raw.get("cost_per_request_micro_usd")

    @property
    def context_k(self) -> int | None:
        return self._raw.get("context_k")

    @property
    def run_mode(self) -> str | None:
        return self._raw.get("run_mode")


class Leaderboard(_Base):
    """Models ranked for a task. `recommended` is the deployable pick;
    `frontier` is the savings baseline."""

    @property
    def task_id(self) -> str | None:
        return self._raw.get("task_id")

    @property
    def metric(self) -> str | None:
        return self._raw.get("metric")

    @property
    def cost_unit(self) -> str | None:
        return self._raw.get("cost_unit")

    @property
    def recommended(self) -> str | None:
        return self._raw.get("recommended")

    @property
    def models(self) -> list[LeaderboardEntry]:
        return [LeaderboardEntry(m) for m in (self._raw.get("models") or [])]

    @property
    def frontier(self) -> LeaderboardEntry | None:
        f = self._raw.get("frontier")
        return LeaderboardEntry(f) if f else None


class FrontierModel(_Base):
    """A vendor frontier model you can evaluate against (from the eval pool).
    `benchmarked` (only when a task is given) = it's on that task's leaderboard."""

    @property
    def id(self) -> str | None:
        return self._raw.get("id")

    @property
    def vendor(self) -> str | None:
        return self._raw.get("vendor")

    @property
    def vision(self) -> bool:
        return bool(self._raw.get("vision"))

    @property
    def benchmarked(self) -> bool:
        return bool(self._raw.get("benchmarked"))


def _leaderboard(raw) -> Leaderboard:
    return Leaderboard(raw or {})


def _frontier_models(raw) -> list[FrontierModel]:
    return [FrontierModel(m) for m in ((raw or {}).get("frontier_models") or [])]


class EvalRun(_Base):
    """Wraps the GET /v1/eval-runs/{id} envelope {"run": {...}, "results": [...]}.

    `cost` is the billed total as Decimal dollars floored to cents (§6);
    `cost_micro_usd` is the raw integer."""

    @property
    def _run(self) -> dict:
        return self._raw.get("run") or {}

    @property
    def id(self) -> str | None:
        return self._run.get("id")

    @property
    def eval_set_id(self) -> str | None:
        return self._run.get("eval_set_id")

    @property
    def status(self) -> str | None:
        return self._run.get("status")

    @property
    def is_terminal(self) -> bool:
        return self._run.get("status") in ("completed", "failed")

    @property
    def candidate_models(self) -> list[str]:
        return list(self._run.get("candidate_model_ids") or [])

    @property
    def error_detail(self) -> str | None:
        return self._run.get("error_detail")

    @property
    def cost_micro_usd(self) -> int:
        return int(self._run.get("total_cost_micro_usd") or 0)

    @property
    def cost(self) -> Decimal:
        return _dollars_floored_to_cents(self._run.get("total_cost_micro_usd"))

    @property
    def results(self) -> list[EvalResult]:
        return [EvalResult(r) for r in (self._raw.get("results") or [])]
