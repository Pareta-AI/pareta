"""`client.evals` — eval sets + runs (bring-your-own-data evaluation).

    # An eval set is DATA + INTENT (v2, breaking): intent is REQUIRED, task is
    # OPTIONAL — the binder resolves your intent + the data's shape to a
    # grading contract.
    pa.evals.propose_contract(items=[…], intent="…")   # preview the binding
    pa.evals.sets.create(items=[…], intent="…")        # auto-binds a clean match
    pa.evals.sets.create(items=[…], intent="…", task="invoice-extraction")  # or pin
    pa.evals.sets.upload_document(set_id, file, idx=…, field_name=…)  # blob tasks
    run = pa.evals.runs.create(eval_set=set_id, models=[…], wait=True)
    # or, in one call: runs.create(items=[…], intent="…", models=[…], wait=True)

`create` (and the inline `runs.create` sugar) require `intent`; with no `task`
they call `propose_contract` and auto-bind ONLY a clean single high/medium match
— a conflict, split, or ambiguity raises with the proposals so you pin `task=`.

Runs are metered (the org balance is debited for the compute); `run.cost` is the
billed total in dollars (floored to cents). `frontier=` accepts an explicit list
of frontier model ids, or the "all"/"benchmarked" roster keywords (resolved via
evals.frontier_models()).
"""

from __future__ import annotations

import io
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any

import httpx

from .._exceptions import ParetaError
from .._models import (
    EvalRun,
    EvalSet,
    ProposalResult,
    _eval_set_from_create,
    _eval_set_list,
    _frontier_models,
    _proposal_result,
)

_BASE = "/v1/eval-sets"
_PROPOSE = "/v1/eval-sets/propose-contract"
_RUNS = "/v1/eval-runs"
_FRONTIER = "/v1/eval/frontier-models"
_INLINE_MAX = 5 * 1024 * 1024  # matches backend _ATTACH_BLOB_INLINE_MAX


def _read_file(file) -> tuple[bytes, str]:
    """Accept a path (str/Path), raw bytes, or a binary file-like → (bytes, name)."""
    if isinstance(file, (bytes, bytearray)):
        return bytes(file), "upload"
    if isinstance(file, (str, Path)):
        p = Path(file)
        return p.read_bytes(), p.name
    if hasattr(file, "read"):
        data = file.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        return data, os.path.basename(getattr(file, "name", "") or "upload")
    raise TypeError("file must be a path, bytes, or a binary file-like object")


def _guess_mime(filename: str, override: str | None) -> str:
    return override or mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _require_intent(intent: str | None) -> str:
    """CB1 (v2 breaking): an eval set is DATA + INTENT — the same rows can mean
    different tasks, and only the caller knows which. Enforced client-side so
    the error is actionable before the request goes out (the server also 400s
    an intent-less create, which is how pre-v2 SDKs surface the change)."""
    intent = (intent or "").strip()
    if not intent:
        raise ValueError(
            "intent is required: one sentence describing what the model should "
            "do with each item (e.g. \"extract vendor, total and date from each "
            "invoice\"). Pass intent=\"...\" to evals.create / propose_contract.")
    return intent[:500]


def _items_jsonl(task: str, items: list[dict], intent: str,
                 name: str | None) -> tuple[dict, dict]:
    if not items:
        raise ValueError("items is required and must be non-empty")
    jsonl = "\n".join(json.dumps(it) for it in items).encode("utf-8")
    files = {"items": (f"items.{task}.jsonl", jsonl, "application/jsonl")}
    data = {"task_id": task, "intent": intent,
            "name": name or f"sdk eval set ({len(items)} items)"}
    return files, data


def _propose_multipart(items: list[dict], intent: str) -> tuple[dict, dict]:
    if not items:
        raise ValueError("items is required and must be non-empty")
    jsonl = "\n".join(json.dumps(it) for it in items).encode("utf-8")
    return ({"items": ("items.jsonl", jsonl, "application/jsonl")},
            {"intent": intent})


def _bind_error(result: ProposalResult) -> ParetaError:
    """Turn a non-clean propose result into an actionable create-time error:
    the binder couldn't safely pick a contract for the stated intent, so the
    caller must choose. Quotes the intent back and lists what fit."""
    intent = result.intent or ""
    if result.conflict:
        c = result.conflict
        return ParetaError(
            f"intent {intent!r} describes a different job than the data's "
            f"shape supports (reads as {c.get('intended_task')!r}: "
            f"{c.get('reasoning')}). Pass task=<id> to pin a contract, or "
            "revise the intent.")
    if result.split:
        s = result.split
        return ParetaError(
            f"the dataset looks MIXED — {s.get('validated_n')}/{s.get('total_n')} "
            f"items fit {s.get('closest_task')!r}, the rest a different shape. "
            "Split the set or pass task=<id>.")
    # Zero-fit: the binder offers the custom-eval universal FLOOR (judged
    # win-rate vs the anchor). Per the precision ladder that's the user's
    # CHOICE — surface it explicitly rather than silently binding it.
    props = result.proposals
    if len(props) == 1 and props[0].task_id == "custom-eval":
        warn = f" ({props[0].warning})" if props[0].warning else ""
        return ParetaError(
            f"no specific grading contract fits this data for intent {intent!r}. "
            "The custom-eval universal floor is available — it grades by judged "
            f"win-rate vs the frontier anchor.{warn} Pass task=\"custom-eval\" to "
            "use it, or revise the data/intent for a specific contract.")
    options = [p.task_id for p in props] or (
        [result.closest_task] if result.closest_task else [])
    hint = (f" Candidates: {', '.join(o for o in options if o)}."
            if any(options) else "")
    return ParetaError(
        f"could not confidently bind a grading contract for intent {intent!r}."
        f"{hint} Pass task=<id> to pin one, or inspect "
        "evals.propose_contract(items, intent).")


def _merge_candidates(models, frontier_ids) -> list[str]:
    cands = list(models or []) + list(frontier_ids or [])
    if not cands:
        raise ValueError("models is required (the open candidates to evaluate)")
    return cands


def _resolve_frontier_from_roster(frontier, roster) -> list[str]:
    """Map an already-fetched roster (list[FrontierModel]) + a keyword to ids."""
    if frontier == "all":
        return [m.id for m in roster]
    if frontier == "benchmarked":
        return [m.id for m in roster if m.benchmarked]
    raise ValueError(
        f"unknown frontier keyword {frontier!r} (use 'all'/'benchmarked'/'none' or a list)")


# ── sync ──────────────────────────────────────────────────────────────
class EvalSets:
    def __init__(self, client):
        self._client = client

    def create(self, *, items: list[dict], intent: str, task: str | None = None,
               name: str | None = None) -> EvalSet:
        """Persist an eval set from your rows. `intent` is REQUIRED (v2): one
        sentence on what the model should do with each item. `task` is
        OPTIONAL — omit it and the binder resolves your intent + the data's
        shape to a grading contract (auto-binds a clean single match; raises
        with the proposals otherwise). Pass `task=<id>` to pin one explicitly."""
        intent = _require_intent(intent)
        if task is None:
            proposal = Evals(self._client).propose_contract(items=items, intent=intent)
            task = proposal.bound_task
            if task is None:
                raise _bind_error(proposal)
        files, data = _items_jsonl(task, items, intent, name)
        return self._client.request("POST", _BASE, files=files, data=data, cast=_eval_set_from_create)

    def list(self) -> list[EvalSet]:
        return self._client.request("GET", _BASE, cast=_eval_set_list)

    def retrieve(self, eval_set_id: str) -> EvalSet:
        raw = self._client.request("GET", f"{_BASE}/{eval_set_id}")
        return EvalSet((raw or {}).get("eval_set") or {})

    def delete(self, eval_set_id: str) -> None:
        self._client.request("DELETE", f"{_BASE}/{eval_set_id}")

    def upload_document(self, eval_set_id: str, file, *, idx: int, field_name: str, mime: str | None = None) -> dict:
        """Attach a binary doc (PDF/image) to one row's blob field. Collapses
        the 3-call signed-URL flow (or the inline path for small files) into one
        call. `idx` is the 0-based row, `field_name` the blob input field."""
        data, filename = _read_file(file)
        mime = _guess_mime(filename, mime)
        if len(data) < _INLINE_MAX:
            return self._client.request(
                "POST", f"{_BASE}/{eval_set_id}/attach-blob",
                files={"file": (filename, data, mime)},
                data={"idx": str(idx), "field_name": field_name, "mime": mime})
        # large file → signed-URL direct-to-storage
        minted = self._client.request(
            "POST", f"{_BASE}/{eval_set_id}/blob-upload-url",
            body={"idx": idx, "field_name": field_name, "mime": mime, "file_size": len(data)})
        put = httpx.put(minted["upload_url"], content=data,
                        headers={"Content-Type": mime}, timeout=600.0)
        if put.status_code not in (200, 201):
            raise ParetaError(f"blob upload PUT failed: {put.status_code}")
        return self._client.request(
            "POST", f"{_BASE}/{eval_set_id}/blob-upload-complete",
            body={"idx": idx, "field_name": field_name,
                  "storage_uri": minted["storage_uri"], "mime": mime})


class EvalRuns:
    def __init__(self, client):
        self._client = client

    def _frontier_ids(self, frontier, eval_set, task) -> list[str]:
        """Resolve frontier= to a list of ids. None/'none' → []; a list → itself;
        'all'/'benchmarked' → fetch the roster for the task (from task=, else the
        eval set's task) and pick."""
        if frontier is None or frontier == "none":
            return []
        if isinstance(frontier, (list, tuple)):
            return list(frontier)
        if not isinstance(frontier, str):
            raise TypeError("frontier must be None, a list of ids, or 'all'/'benchmarked'/'none'")
        resolve_task = task or EvalSets(self._client).retrieve(eval_set).task_id
        if not resolve_task:
            raise ValueError("cannot resolve a frontier keyword without a task")
        roster = self._client.request("GET", _FRONTIER, params={"task": resolve_task}, cast=_frontier_models)
        return _resolve_frontier_from_roster(frontier, roster)

    def create(self, *, eval_set: str | None = None, task: str | None = None,
               items: list[dict] | None = None, intent: str | None = None,
               models, frontier=None,
               name: str | None = None, wait: bool = False,
               poll_interval: float = 3.0, timeout: float = 900.0) -> EvalRun:
        if eval_set is None:
            if not items:
                raise ValueError("pass eval_set=<id>, or items=… (+ intent=…) to create one")
            eval_set = EvalSets(self._client).create(
                items=items, intent=intent, task=task, name=name).id
        frontier_ids = self._frontier_ids(frontier, eval_set, task)
        candidate_model_ids = _merge_candidates(models, frontier_ids)
        started = self._client.request(
            "POST", _RUNS, body={"eval_set_id": eval_set, "candidate_model_ids": candidate_model_ids})
        run_id = started["run_id"]
        if wait:
            return self.wait(run_id, poll_interval=poll_interval, timeout=timeout)
        return EvalRun({"run": {"id": run_id, "status": started.get("status")}})

    def retrieve(self, run_id: str) -> EvalRun:
        return self._client.request("GET", f"{_RUNS}/{run_id}", cast=EvalRun)

    def wait(self, run_id: str, *, poll_interval: float = 3.0, timeout: float = 900.0) -> EvalRun:
        deadline = time.monotonic() + timeout
        while True:
            run = self.retrieve(run_id)
            if run.is_terminal:
                return run
            if time.monotonic() >= deadline:
                raise ParetaError(f"eval run {run_id} did not finish within {timeout:.0f}s")
            time.sleep(poll_interval)


class Evals:
    def __init__(self, client):
        self._client = client
        self.sets = EvalSets(client)
        self.runs = EvalRuns(client)

    def propose_contract(self, *, items: list[dict], intent: str) -> ProposalResult:
        """Which grading contract fits your data under your stated `intent`?
        Stateless discovery — nothing is persisted. Returns a ProposalResult
        (ranked proposals, the auto-bind decision, conflict/split reporting).
        `create(items, intent)` calls this under the hood; use it directly to
        preview the binding before committing."""
        intent = _require_intent(intent)
        files, data = _propose_multipart(items, intent)
        return self._client.request("POST", _PROPOSE, files=files, data=data,
                                    cast=_proposal_result)

    def frontier_models(self, task: str | None = None):
        """The frontier (vendor) roster you can evaluate against. With task=,
        each is annotated `benchmarked` + the roster is vision-filtered for
        document tasks. Feed ids into runs.create(frontier=[…])."""
        params = {"task": task} if task else None
        return self._client.request("GET", _FRONTIER, params=params, cast=_frontier_models)


# ── async ─────────────────────────────────────────────────────────────
class AsyncEvalSets:
    def __init__(self, client):
        self._client = client

    async def create(self, *, items: list[dict], intent: str, task: str | None = None,
                     name: str | None = None) -> EvalSet:
        intent = _require_intent(intent)
        if task is None:
            proposal = await AsyncEvals(self._client).propose_contract(items=items, intent=intent)
            task = proposal.bound_task
            if task is None:
                raise _bind_error(proposal)
        files, data = _items_jsonl(task, items, intent, name)
        return await self._client.request("POST", _BASE, files=files, data=data, cast=_eval_set_from_create)

    async def list(self) -> list[EvalSet]:
        return await self._client.request("GET", _BASE, cast=_eval_set_list)

    async def retrieve(self, eval_set_id: str) -> EvalSet:
        raw = await self._client.request("GET", f"{_BASE}/{eval_set_id}")
        return EvalSet((raw or {}).get("eval_set") or {})

    async def delete(self, eval_set_id: str) -> None:
        await self._client.request("DELETE", f"{_BASE}/{eval_set_id}")

    async def upload_document(self, eval_set_id: str, file, *, idx: int, field_name: str, mime: str | None = None) -> dict:
        data, filename = _read_file(file)
        mime = _guess_mime(filename, mime)
        if len(data) < _INLINE_MAX:
            return await self._client.request(
                "POST", f"{_BASE}/{eval_set_id}/attach-blob",
                files={"file": (filename, data, mime)},
                data={"idx": str(idx), "field_name": field_name, "mime": mime})
        minted = await self._client.request(
            "POST", f"{_BASE}/{eval_set_id}/blob-upload-url",
            body={"idx": idx, "field_name": field_name, "mime": mime, "file_size": len(data)})
        async with httpx.AsyncClient(timeout=600.0) as c:
            put = await c.put(minted["upload_url"], content=data, headers={"Content-Type": mime})
        if put.status_code not in (200, 201):
            raise ParetaError(f"blob upload PUT failed: {put.status_code}")
        return await self._client.request(
            "POST", f"{_BASE}/{eval_set_id}/blob-upload-complete",
            body={"idx": idx, "field_name": field_name,
                  "storage_uri": minted["storage_uri"], "mime": mime})


class AsyncEvalRuns:
    def __init__(self, client):
        self._client = client

    async def _frontier_ids(self, frontier, eval_set, task) -> list[str]:
        if frontier is None or frontier == "none":
            return []
        if isinstance(frontier, (list, tuple)):
            return list(frontier)
        if not isinstance(frontier, str):
            raise TypeError("frontier must be None, a list of ids, or 'all'/'benchmarked'/'none'")
        resolve_task = task
        if not resolve_task:
            got = await AsyncEvalSets(self._client).retrieve(eval_set)
            resolve_task = got.task_id
        if not resolve_task:
            raise ValueError("cannot resolve a frontier keyword without a task")
        roster = await self._client.request("GET", _FRONTIER, params={"task": resolve_task}, cast=_frontier_models)
        return _resolve_frontier_from_roster(frontier, roster)

    async def create(self, *, eval_set: str | None = None, task: str | None = None,
                     items: list[dict] | None = None, intent: str | None = None,
                     models, frontier=None,
                     name: str | None = None, wait: bool = False,
                     poll_interval: float = 3.0, timeout: float = 900.0) -> EvalRun:
        if eval_set is None:
            if not items:
                raise ValueError("pass eval_set=<id>, or items=… (+ intent=…) to create one")
            created = await AsyncEvalSets(self._client).create(
                items=items, intent=intent, task=task, name=name)
            eval_set = created.id
        frontier_ids = await self._frontier_ids(frontier, eval_set, task)
        candidate_model_ids = _merge_candidates(models, frontier_ids)
        started = await self._client.request(
            "POST", _RUNS, body={"eval_set_id": eval_set, "candidate_model_ids": candidate_model_ids})
        run_id = started["run_id"]
        if wait:
            return await self.wait(run_id, poll_interval=poll_interval, timeout=timeout)
        return EvalRun({"run": {"id": run_id, "status": started.get("status")}})

    async def retrieve(self, run_id: str) -> EvalRun:
        return await self._client.request("GET", f"{_RUNS}/{run_id}", cast=EvalRun)

    async def wait(self, run_id: str, *, poll_interval: float = 3.0, timeout: float = 900.0) -> EvalRun:
        import asyncio
        deadline = time.monotonic() + timeout
        while True:
            run = await self.retrieve(run_id)
            if run.is_terminal:
                return run
            if time.monotonic() >= deadline:
                raise ParetaError(f"eval run {run_id} did not finish within {timeout:.0f}s")
            await asyncio.sleep(poll_interval)


class AsyncEvals:
    def __init__(self, client):
        self._client = client
        self.sets = AsyncEvalSets(client)
        self.runs = AsyncEvalRuns(client)

    async def propose_contract(self, *, items: list[dict], intent: str) -> ProposalResult:
        intent = _require_intent(intent)
        files, data = _propose_multipart(items, intent)
        return await self._client.request("POST", _PROPOSE, files=files, data=data,
                                          cast=_proposal_result)

    async def frontier_models(self, task: str | None = None):
        params = {"task": task} if task else None
        return await self._client.request("GET", _FRONTIER, params=params, cast=_frontier_models)
