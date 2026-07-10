"""`client.tasks` — browse the benchmark catalog + match free-text intent.

- list / retrieve: the catalog and a task's schema + default scorer.
- match: free-text intent → the task (or capability lane) Pareta covers it
  with. This is the discovery surface: feed the matched task into
  `client.evals` to prove `model="auto"` on your own data.
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
