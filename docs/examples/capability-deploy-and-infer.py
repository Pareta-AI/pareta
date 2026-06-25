"""Capability flow: a sentence → a capability → a deployed open model → inference.

Some jobs don't map to a *benchmarked* task — "summarize this", "describe this
image", "plan the steps to do X". For those, `tasks.match` returns a general
**capability** lane (chat / vision / agentic / coding / classification) instead
of a specific task id. The chat / vision / agentic lanes are backed by a real,
deployable catalog task named `general-<id>` (capability `chat` → task
`general-chat`), so you deploy and call them exactly like any other open model.

Pipeline:
  1. tasks.match("...")  → a capability (type == "capability")
  2. capability.id  → the deployable task (CAPABILITY_TASK)
  3. endpoints.deploy(task=..., model="recommended", wait=True)
  4. chat.completions.create(model=endpoint.id, ...)   # per-TOKEN metered

Run:
  export PARETA_API_KEY=pareta_sk_...
  python capability-deploy-and-infer.py
"""

from __future__ import annotations

from pareta import Pareta

# Maps a capability id to the catalog task you deploy for it.
#   - chat / vision / agentic have dedicated bring-your-own-data general lanes.
#   - coding routes to the benchmarked code-generation task (no `general-coding`).
#   - classification → use the moderation/intent classifiers, or your own task.
#   - asr / tts are speech lanes: no deploy, use the /v1/audio/* routes instead
#     (see audio-transcribe-and-speak.py).
CAPABILITY_TASK = {
    "chat": "general-chat",
    "vision": "general-vision",
    "agentic": "general-agentic",
    "coding": "code-generation",
}
_SPEECH_CAPABILITIES = {"asr", "tts"}


def main() -> None:
    pa = Pareta.from_env()  # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)

    # 1. Free-text intent → a match. With no benchmarked task to fit, the
    #    reasoning router returns a general capability lane.
    m = pa.tasks.match("summarize this support thread and draft a friendly reply")

    # `m.type` is one of "task" | "capability" | "unsupported" | "none". The
    # reasoning router also fills `m.reasoning` / `m.confidence`, and `m.capability`
    # (a typed Capability) when the match is a general lane.
    match_type = m.type
    print(f"query     : {m.query}")
    print(f"match type: {match_type}  (confidence={m.confidence})")
    print(f"reasoning : {m.reasoning}")

    if match_type == "task":
        # A specific benchmarked task fit — use the normal task funnel instead.
        # (See find-and-deploy-best-model.md.)
        task_id = m.chosen.task_id
        print(f"This mapped to a benchmarked task ({task_id}); deploy that directly.")
    elif match_type == "capability":
        capability = m.capability
        cap_id = capability.id if capability else None
        print(f"capability: {capability.label if capability else None}  (id={cap_id})")

        if cap_id in _SPEECH_CAPABILITIES:
            # asr / tts live on the audio endpoints, not chat completions.
            raise SystemExit(
                f"Capability {cap_id!r} is a speech lane — use the /v1/audio/* "
                "routes (see audio-transcribe-and-speak.py)."
            )

        # 2. Map the capability to the catalog task you deploy for it.
        task_id = CAPABILITY_TASK.get(cap_id)
        if task_id is None:
            raise SystemExit(
                f"No deployable task wired for capability {cap_id!r}; "
                "browse pa.tasks.list() for the right task in its category."
            )
    else:
        # "unsupported" / "none" — Pareta doesn't cover this. Handle it gracefully
        # (see handle-unsupported-match.py).
        raise SystemExit(
            f"No supported match for this request (type={match_type!r}). "
            "Rephrase, or capture it as a task request."
        )

    # 3. Deploy the recommended open model for the task. Pareta resolves the GPU
    #    and serving config — you never pass hardware. wait=True blocks until the
    #    endpoint is live and returns the Endpoint.
    print(f"\nDeploying recommended open model for {task_id} ...")
    endpoint = pa.endpoints.deploy(task=task_id, model="recommended", wait=True)
    print(f"endpoint  : {endpoint.id}  (model alias: {endpoint.model}, status: {endpoint.status})")

    # 4. Run OpenAI-compatible inference. NOTE: capability endpoints are billed
    #    PER TOKEN (open-ended request shapes), not the per-request floor used by
    #    fixed benchmarked tasks. A successful completion debits the org balance;
    #    a zero balance raises InsufficientCreditsError (402).
    resp = pa.chat.completions.create(
        model=endpoint.id,
        messages=[
            {"role": "user", "content": "Summarize this in one sentence: the customer's order "
                                        "shipped late and they'd like a refund or a discount."},
        ],
        max_tokens=400,
    )
    print("\n--- completion ---")
    print(resp.choices[0].message.content)

    usage = resp.usage
    print(
        f"\ntokens: prompt={usage.prompt_tokens} "
        f"completion={usage.completion_tokens} total={usage.total_tokens}  "
        "(per-token metered against your org balance)"
    )

    # Tidy up: stop the endpoint so it isn't billed while idle. Drop the leading
    # `#` to actually run it.
    # pa.endpoints.stop(endpoint.id)


if __name__ == "__main__":
    main()
