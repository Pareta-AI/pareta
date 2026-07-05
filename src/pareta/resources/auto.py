"""The `auto` surface — Pareta's routing brain as a resource.

Calling the brain itself needs no special method: it is the standard
chat surface with ``model="auto"``::

    client.chat.completions.create(
        model="auto",
        messages=[{"role": "user", "content": "…"}],
    )

This resource carries the surfaces AROUND that call: the org-level
metrics rollup (requests, success, spend, projected savings vs
frontier) and the metered frontier comparison the Playground uses.
"""
from __future__ import annotations

from typing import Any


class Auto:
    def __init__(self, client):
        self._client = client

    def metrics(self) -> dict[str, Any]:
        """Your org's ``model="auto"`` traffic, rolled up: requests + success
        rate (30d), spend, hourly p50/p95/error buckets (7d), daily success
        cells (30d), and the PROJECTED savings vs frontier (frontier
        list-priced counterfactual; the measured number arrives with
        dual-run calibration)."""
        return self._client.request("GET", "/v1/auto/metrics")

    def compare_frontier(self, *, model: str,
                         messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Run one prompt against a frontier vendor for a side-by-side with
        ``model="auto"`` — METERED at the vendor's actual token cost (one
        debit per call; a failed vendor call bills $0). Allowed models:
        gpt-5.5, gemini-3-5-flash, gemini-3-1-pro, claude-sonnet-4-6.
        Returns ``{model, content, cost_micro_usd, latency_ms}``."""
        return self._client.request(
            "POST", "/v1/playground/frontier",
            body={"model": model, "messages": messages})


class AsyncAuto:
    def __init__(self, client):
        self._client = client

    async def metrics(self) -> dict[str, Any]:
        return await self._client.request("GET", "/v1/auto/metrics")

    async def compare_frontier(self, *, model: str,
                               messages: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._client.request(
            "POST", "/v1/playground/frontier",
            body={"model": model, "messages": messages})
