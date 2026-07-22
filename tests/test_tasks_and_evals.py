import json
from decimal import Decimal

import httpx
import pytest

from pareta import Task, TaskMatch, EvalSet, EvalRun, ProposalResult, ParetaError
from conftest import sync_client, json_response


# ── tasks ──────────────────────────────────────────────────────────────
def test_tasks_list():
    def handler(request):
        assert request.url.path == "/v1/tasks"
        return json_response(200, {"tasks": [
            {"id": "invoice-extraction", "default_scorer": "field_f1", "has_blob_input": True},
            {"id": "intent-classification", "default_scorer": "macro_f1", "has_blob_input": False},
        ]})

    pa = sync_client(handler)
    tasks = pa.tasks.list()
    assert [t.id for t in tasks] == ["invoice-extraction", "intent-classification"]
    assert tasks[0].has_blob_input is True


def test_tasks_match():
    def handler(request):
        body = json.loads(request.content)
        assert body == {"query": "extract dates from a contract", "top_k": 5}
        return json_response(200, {
            "query": body["query"], "matched": True,
            "chosen": {"task_id": "contract-key-fields", "score": 0.71, "confidence": "high"},
            "candidates": [{"task_id": "contract-key-fields", "score": 0.71, "confidence": "high"}],
            "ambiguous": False, "matcher": "keyword",
        })

    pa = sync_client(handler)
    m = pa.tasks.match("extract dates from a contract")
    assert isinstance(m, TaskMatch)
    assert m.matched and m.chosen.task_id == "contract-key-fields"
    assert m.chosen.confidence == "high"
    assert m.matcher == "keyword"


def test_tasks_match_reasoning_task_type():
    # Reasoning matcher shape: type/reasoning/confidence + a chosen task.
    def handler(request):
        return json_response(200, {
            "query": "extract line items from invoices", "type": "task",
            "matched": True, "matcher": "reason", "ambiguous": False,
            "reasoning": "grounded extraction over a document",
            "confidence": "high",
            "chosen": {"task_id": "invoice-extraction", "rank": 0, "score": None,
                       "confidence": "high", "category": "Document Extraction"},
            "capability": None,
            "candidates": [{"task_id": "invoice-extraction", "confidence": "high"}],
        })

    pa = sync_client(handler)
    m = pa.tasks.match("extract line items from invoices")
    assert m.type == "task"
    assert m.matcher == "reason"
    assert m.reasoning == "grounded extraction over a document"
    assert m.confidence == "high"
    assert m.chosen.task_id == "invoice-extraction"
    assert m.capability is None


def test_tasks_match_capability_type():
    def handler(request):
        return json_response(200, {
            "query": "summarize this email thread", "type": "capability",
            "matched": True, "matcher": "reason", "ambiguous": False,
            "reasoning": "open-ended text generation", "confidence": "high",
            "chosen": None,
            "capability": {"id": "chat", "label": "Chat", "category": "Chat",
                           "category_id": "chat", "desc": "General text chat."},
            "candidates": [],
        })

    pa = sync_client(handler)
    m = pa.tasks.match("summarize this email thread")
    assert m.type == "capability"
    cap = m.capability
    assert cap is not None
    assert cap.id == "chat"
    assert cap.label == "Chat"
    assert cap.category == "Chat"
    assert cap.category_id == "chat"
    assert cap.desc == "General text chat."
    assert m.chosen is None


def test_tasks_match_unsupported_type():
    def handler(request):
        return json_response(200, {
            "query": "generate a video of a cat", "type": "unsupported",
            "matched": False, "matcher": "reason", "ambiguous": False,
            "reasoning": "Pareta does not generate video.", "confidence": "high",
            "chosen": None, "capability": None, "candidates": [],
        })

    pa = sync_client(handler)
    m = pa.tasks.match("generate a video of a cat")
    assert m.type == "unsupported"
    assert m.matched is False
    assert m.reasoning == "Pareta does not generate video."
    assert m.capability is None and m.chosen is None


# ── eval sets ────────────────────────────────────────────────────────────
def test_eval_set_create_sends_multipart_jsonl():
    seen = {}

    def handler(request):
        seen["ctype"] = request.headers.get("content-type", "")
        seen["body"] = request.content
        return json_response(201, {"eval_set": {
            "id": "es_1", "task_id": "intent-classification", "item_count": 2,
            "scoring_strategy": "macro_f1"}})

    pa = sync_client(handler)
    es = pa.evals.sets.create(
        task="intent-classification", prompt="classify each utterance's intent",
        items=[{"input": {"text": "a"}, "expected": "x"}, {"input": {"text": "b"}, "expected": "y"}],
    )
    assert isinstance(es, EvalSet)
    assert es.id == "es_1" and es.item_count == 2
    assert seen["ctype"].startswith("multipart/form-data")
    # the JSONL (one row per line) + form fields (incl. the required prompt,
    # sent under the multipart field name "prompt" — v3 breaking rename)
    assert b"intent-classification" in seen["body"]
    assert b'name="prompt"' in seen["body"]
    assert b"classify each utterance" in seen["body"]
    assert b'"text": "a"' in seen["body"]


def test_eval_set_create_requires_prompt():
    # CB1 v3: prompt is a required signature parameter (missing → TypeError),
    # and an empty/whitespace value fails fast with the actionable message
    # BEFORE any request goes out.
    pa = sync_client(lambda r: json_response(201, {"eval_set": {}}))
    with pytest.raises(TypeError):
        pa.evals.sets.create(task="t", items=[{"input": {}, "expected_output": {}}])
    with pytest.raises(ValueError, match="prompt is required"):
        pa.evals.sets.create(task="t", prompt="   ",
                             items=[{"input": {}, "expected_output": {}}])


def test_eval_set_create_requires_items():
    pa = sync_client(lambda r: json_response(201, {"eval_set": {}}))
    with pytest.raises(ValueError):
        pa.evals.sets.create(task="t", prompt="do it", items=[])


def test_eval_set_list_and_delete():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.method == "GET":
            return json_response(200, {"eval_sets": [{"id": "es_1", "name": "n"}]})
        return httpx.Response(204)

    pa = sync_client(handler)
    sets = pa.evals.sets.list()
    assert [s.id for s in sets] == ["es_1"]
    pa.evals.sets.delete("es_1")
    assert ("DELETE", "/v1/eval-sets/es_1") in seen


def test_upload_document_inline_for_small_file():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["ctype"] = request.headers.get("content-type", "")
        seen["body"] = request.content
        return json_response(200, {"kind": "blob", "uri": "gs://b/x", "mime": "application/pdf"})

    pa = sync_client(handler)
    out = pa.evals.sets.upload_document(
        "es_1", b"%PDF-1.4 small", idx=0, field_name="document", mime="application/pdf")
    assert out["uri"] == "gs://b/x"
    assert seen["path"] == "/v1/eval-sets/es_1/attach-blob"
    assert seen["ctype"].startswith("multipart/form-data")
    assert b"document" in seen["body"]   # field_name in the form


# ── eval runs ─────────────────────────────────────────────────────────────
def test_run_create_then_wait_polls_to_terminal():
    calls = {"n": 0}

    def handler(request):
        if request.method == "POST" and request.url.path == "/v1/eval-runs":
            body = json.loads(request.content)
            assert body["eval_set_id"] == "es_1"
            assert body["candidate_model_ids"] == ["qwen-1", "claude-opus-4-7"]  # models + frontier merged
            return json_response(202, {"run_id": "run_1", "status": "queued"})
        # GET /v1/eval-runs/run_1 — running, then completed
        calls["n"] += 1
        status = "completed" if calls["n"] >= 2 else "running"
        return json_response(200, {
            "run": {"id": "run_1", "eval_set_id": "es_1", "status": status,
                    "candidate_model_ids": ["qwen-1", "claude-opus-4-7"],
                    "total_cost_micro_usd": 1_234_567},
            "results": [
                {"model_id": "qwen-1", "kind": "open", "quality_mean": 0.91, "n_succeeded": 5, "error_count": 0,
                 "per_item": [{"idx": 0, "score": 0.0, "prediction": "the model said this"},
                              {"idx": 1, "score": 1.0, "prediction": "ok"}]},
            ],
        })

    pa = sync_client(handler)
    run = pa.evals.runs.create(
        eval_set="es_1", models=["qwen-1"], frontier=["claude-opus-4-7"],
        wait=True, poll_interval=0)
    assert isinstance(run, EvalRun)
    assert run.status == "completed"
    # §6 money convention: floored to cents
    assert run.cost == Decimal("1.23")
    assert run.cost_micro_usd == 1_234_567
    assert run.results[0].model_id == "qwen-1" and run.results[0].quality_mean == 0.91
    # per_item carries the raw prediction so a 0.0 score is debuggable
    items = run.results[0].per_item
    assert items[0].idx == 0 and items[0].score == 0.0
    assert items[0].prediction == "the model said this"


def test_run_create_from_items_autocreates_set():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.url.path == "/v1/eval-sets":
            return json_response(201, {"eval_set": {"id": "es_auto", "item_count": 1}})
        if request.url.path == "/v1/eval-runs":
            assert json.loads(request.content)["eval_set_id"] == "es_auto"
            return json_response(202, {"run_id": "run_2", "status": "queued"})
        return json_response(200, {})

    pa = sync_client(handler)
    run = pa.evals.runs.create(
        task="intent-classification", prompt="classify each utterance",
        items=[{"input": {"text": "a"}, "expected": "x"}],
        models=["qwen-1"], wait=False)
    assert run.id == "run_2"
    assert ("POST", "/v1/eval-sets") in seen and ("POST", "/v1/eval-runs") in seen


def test_propose_contract_and_taskless_autobind():
    """propose_contract returns a ProposalResult; a task-less create auto-binds
    ONLY a clean single high/medium proposal (CB1 §7)."""
    posts = []

    def handler(request):
        posts.append(request.url.path)
        if request.url.path == "/v1/eval-sets/propose-contract":
            # v3: the propose multipart carries the "prompt" form field
            assert b'name="prompt"' in request.content
            return json_response(200, {
                "proposals": [{"task_id": "intent-classification", "confidence": "high",
                               "evidence": {"validated_n": 5, "total_n": 5}}],
                "homogeneous": True, "split": None, "prompt": "classify each utterance"})
        if request.url.path == "/v1/eval-sets":
            # the bound task_id must ride the create multipart
            assert b"intent-classification" in request.content
            return json_response(201, {"eval_set": {"id": "es_bound", "task_id": "intent-classification"}})
        return json_response(200, {})

    pa = sync_client(handler)
    result = pa.evals.propose_contract(
        items=[{"input": {"text": "a"}, "expected_output": {"label": "x"}}] * 5,
        prompt="classify each utterance")
    assert result.bound_task == "intent-classification" and result.is_clean

    es = pa.evals.sets.create(
        items=[{"input": {"text": "a"}, "expected_output": {"label": "x"}}] * 5,
        prompt="classify each utterance")   # no task → binds via propose
    assert es.id == "es_bound"
    assert posts == ["/v1/eval-sets/propose-contract", "/v1/eval-sets/propose-contract", "/v1/eval-sets"]


def test_taskless_create_does_not_autobind_custom_eval_floor():
    """review-caught: the zero-fit custom-eval OFFER has the same clean shape
    as a real bind (homogeneous, one medium proposal, no conflict). It must
    NOT auto-bind — the floor is a CHOICE (pass task="custom-eval" to opt in);
    a task-less create surfaces the offer instead of silently binding it."""
    posted = []

    def handler(request):
        posted.append(request.url.path)
        if request.url.path == "/v1/eval-sets/propose-contract":
            return json_response(200, {
                "proposals": [{"task_id": "custom-eval", "confidence": "medium",
                               "evidence": {"validated_n": 5, "total_n": 5}}],
                "homogeneous": True, "split": None,
                "prompt": "grade the tone of each reply",
                "message": "no specific grading contract fits this shape"})
        return json_response(201, {"eval_set": {"id": "es_x"}})

    pa = sync_client(handler)
    result = pa.evals.propose_contract(
        items=[{"input": {"t": "a"}, "expected_output": {"r": "b"}}] * 5,
        prompt="grade the tone of each reply")
    assert result.bound_task is None and result.is_clean is False

    with pytest.raises(ParetaError, match="custom-eval"):
        pa.evals.sets.create(
            items=[{"input": {"t": "a"}, "expected_output": {"r": "b"}}] * 5,
            prompt="grade the tone of each reply")   # no task → must NOT bind
    # only the propose call happened — never a create POST
    assert "/v1/eval-sets" not in posted

    # explicit opt-in works: task="custom-eval" binds without consulting the binder
    posted.clear()
    es = pa.evals.sets.create(
        items=[{"input": {"t": "a"}, "expected_output": {"r": "b"}}] * 5,
        prompt="grade the tone of each reply", task="custom-eval")
    assert es.id == "es_x"
    assert posted == ["/v1/eval-sets"]   # no propose call when task is pinned


def test_taskless_create_raises_on_conflict():
    """A conflict (or any non-clean result) refuses to auto-bind and raises
    with the prompt quoted — never a silent wrong bind."""
    def handler(request):
        return json_response(200, {
            "proposals": [{"task_id": "intent-classification", "confidence": "low",
                           "evidence": {}}],
            "homogeneous": True, "split": None, "prompt": "summarize each utterance",
            "conflict": {"intended_task": "summarization", "reasoning": "prompt says summarize"}})

    pa = sync_client(handler)
    with pytest.raises(ParetaError, match="summarize each utterance"):
        pa.evals.sets.create(
            items=[{"input": {"text": "a"}, "expected_output": {"label": "x"}}] * 5,
            prompt="summarize each utterance")


def test_run_create_frontier_keyword_needs_resolvable_task():
    # A frontier keyword with eval_set= but no task, and an eval set whose
    # task can't be resolved, raises a clear error (resolution covered in
    # test_slice4_discovery).
    def handler(request):
        if request.url.path.startswith("/v1/eval-sets/"):
            return json_response(200, {"eval_set": {"id": "es_1"}})  # no task_id
        return json_response(202, {"run_id": "x", "status": "queued"})

    pa = sync_client(handler)
    with pytest.raises(ValueError):
        pa.evals.runs.create(eval_set="es_1", models=["qwen-1"], frontier="benchmarked")
