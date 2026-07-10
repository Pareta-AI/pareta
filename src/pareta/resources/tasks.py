"""`client.tasks` — the grading-contract directory for evals.

A task names how a dataset is scored: the row shape + the scorer. Inference
never takes a task id (`model="auto"` routes everything); you need one exactly
when benchmarking your own data via `client.evals`.

- list / retrieve: browse the contracts and a contract's row schema + scorer.
- match: a plain-English description of your dataset → the contract that
  grades it (feed the matched task id into `evals.runs.create(task=...)`).
"""

from __future__ import annotations

from .._models import Task, TaskMatch, _task_list

_BASE = "/v1/tasks"


class Tasks:
    def __init__(self, client):
        self._client = client

    def list(self) -> list[Task]:
        return self._client.request("GET", _BASE, cast=_task_list)

    def retrieve(self, task_id: str, *, examples_n: int | None = None) -> Task:
        params = {"examples_n": examples_n} if examples_n is not None else None
        return self._client.request("GET", f"{_BASE}/{task_id}", params=params, cast=Task)

    def match(self, query: str, *, top_k: int = 5) -> TaskMatch:
        if not query or not query.strip():
            raise ValueError("query is required")
        return self._client.request(
            "POST", f"{_BASE}/match", body={"query": query, "top_k": top_k}, cast=TaskMatch)


class AsyncTasks:
    def __init__(self, client):
        self._client = client

    async def list(self) -> list[Task]:
        return await self._client.request("GET", _BASE, cast=_task_list)

    async def retrieve(self, task_id: str, *, examples_n: int | None = None) -> Task:
        params = {"examples_n": examples_n} if examples_n is not None else None
        return await self._client.request("GET", f"{_BASE}/{task_id}", params=params, cast=Task)

    async def match(self, query: str, *, top_k: int = 5) -> TaskMatch:
        if not query or not query.strip():
            raise ValueError("query is required")
        return await self._client.request(
            "POST", f"{_BASE}/match", body={"query": query, "top_k": top_k}, cast=TaskMatch)
