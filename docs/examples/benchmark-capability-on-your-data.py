"""Benchmark a capability lane on YOUR OWN data, open vs. frontier.

A capability (chat / coding / agentic / vision) is just a normal benchmarkable
category: the deployable task is `general-<category_id>`, and you can run your
own rows through it against the open candidates AND vendor frontier baselines —
same eval surface as any of the 31 numbered tasks. The only difference: these
lanes ship with NO pre-baked quality/cost numbers (the leaderboard is open
model(s) + frontier), so the benchmark is entirely on *your* data.

This script:
  1. builds an eval set from a handful of your prompt/answer rows,
  2. runs it against the open recommended model + a frontier baseline,
  3. prints the ranked results and the billed cost.

Eval runs are metered: the org balance is debited for the open AND frontier
compute used; `run.cost` is the billed total in dollars (floored to cents).

Run:
  export PARETA_API_KEY=pareta_sk_...
  python benchmark-capability-on-your-data.py
"""

from __future__ import annotations

from pareta import Pareta

TASK = "general-chat"  # the deployable task behind capability:chat

# Your own labeled rows. Every row is {"input": {...}, "expected_output": {...}}
# (both JSON objects); the inner field names match the task's input/output schema —
# for general-chat that's a prompt in, and a reference response the scorer grades against.
ROWS = [
    {"input": {"prompt": "Summarize in one sentence: the meeting is moved to 3pm Friday."},
     "expected_output": {"response": "The meeting is now at 3pm on Friday."}},
    {"input": {"prompt": "Rewrite politely: send me the report now."},
     "expected_output": {"response": "Could you please send me the report when you have a moment?"}},
    {"input": {"prompt": "What is the capital of France?"},
     "expected_output": {"response": "Paris."}},
]


def main() -> None:
    pa = Pareta.from_env()  # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)

    # Which open model(s) lead this lane (and the frontier baseline)?
    lb = pa.tasks.leaderboard(TASK)
    open_models = [m.name for m in lb.models if m.kind == "open"]
    print(f"open candidates for {TASK}: {open_models or '(none listed)'}")
    print(f"recommended open pick     : {lb.recommended}")

    # The frontier (vendor) roster you can benchmark AGAINST on this task.
    frontier = pa.evals.frontier_models(task=TASK)
    print(f"frontier baselines        : {[f.id for f in frontier]}")

    # Run YOUR rows through the recommended open model + the benchmarked frontier
    # models in one call. evals.runs.create builds the eval set inline (task= +
    # items= + prompt=), kicks off the run, and (wait=True) polls to completion.
    candidates = [lb.recommended] if lb.recommended else open_models[:1]
    print(f"\nbenchmarking {candidates} vs frontier on {len(ROWS)} of your rows ...")
    run = pa.evals.runs.create(
        task=TASK,
        items=ROWS,
        prompt="answer each prompt as instructed",
        models=candidates,          # open candidate(s)
        frontier="benchmarked",     # add the task's benchmarked frontier baselines
        wait=True,
    )

    print(f"\nrun {run.id}  status={run.status}  billed=${run.cost}")
    # Rank by quality (higher is better); each result is open or frontier.
    ranked = sorted(run.results, key=lambda r: (r.quality_mean or 0.0), reverse=True)
    for r in ranked:
        cost_per = (r.mean_cost_micro_usd or 0) / 1e6
        print(
            f"  {r.model_id:32}  kind={r.kind or '?':8}  "
            f"quality={r.quality_mean}  mean_cost=${cost_per:.6f}/row  "
            f"(n={r.n_succeeded}, errors={r.error_count})"
        )

    print(
        "\nPick the cheapest open model whose quality clears your bar, then "
        "deploy it: pa.endpoints.deploy(task=TASK, model=<that model_id>, wait=True)."
    )


if __name__ == "__main__":
    main()
