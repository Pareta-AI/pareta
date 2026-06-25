"""Handle an 'unsupported' match gracefully (and route every match type).

`tasks.match` reasons about intent and returns ONE of four outcomes via the new
`type` field:

  - "task"        a specific benchmarked task fit (m.chosen.task_id) — deploy it.
  - "capability"  a general lane (chat/coding/agentic/vision/asr/tts) — deploy
                  general-<category_id>, or use pa.audio.* for speech.
  - "unsupported" Pareta does NOT do this at all (generating video/images/music,
                  taking real-world actions, fetching live data, etc.). This is a
                  correct, expected answer — not an error.
  - "none"        the LLM router was unavailable and the lexical fallback found
                  nothing confident.

A robust integration branches on `type` and, for "unsupported", fails *clearly*
rather than force-fitting an unrelated task. This script is a copy-pasteable
dispatcher you can drop in front of your deploy logic.

GAP: the "Don't see your task?" demand-capture route (POST /v1/task-requests)
requires a browser session (CSRF/cookie auth), so it is NOT reachable with a
`pareta_sk_` API key. From an SDK/server context, surface the unsupported result
to your own logs/UI and let a human file the request in the dashboard.

Run:
  export PARETA_API_KEY=pareta_sk_...
  python handle-unsupported-match.py
"""

from __future__ import annotations

from pareta import Pareta, ParetaError

# A few intents that exercise each branch.
QUERIES = [
    "extract the line items and totals from these invoices",  # → task
    "summarize this long email thread into three bullets",     # → capability (chat)
    "generate a 30-second video of a cat surfing",             # → unsupported
    "what's today's weather in Tokyo right now",               # → unsupported (live data)
]


def resolve(pa: Pareta, query: str) -> None:
    m = pa.tasks.match(query)
    match_type = m.type  # "task" | "capability" | "unsupported" | "none"

    if match_type == "task":
        task = m.chosen
        print(f"  TASK       → {task.task_id}  (confidence={m.confidence})")
        print(f"             deploy: pa.endpoints.deploy(task={task.task_id!r}, model='recommended', wait=True)")

    elif match_type == "capability":
        cap = m.capability  # typed Capability (or None)
        cap_id = cap.id if cap else None
        # chat/vision/agentic have dedicated general lanes; coding routes to the
        # benchmarked code-generation task; asr/tts use the audio routes.
        deploy_task = {
            "chat": "general-chat", "vision": "general-vision",
            "agentic": "general-agentic", "coding": "code-generation",
        }.get(cap_id)
        cap_label = cap.label if cap else None
        if cap_id in ("asr", "tts"):
            print(f"  CAPABILITY → {cap_label} (speech) — use pa.audio.* (see audio-transcribe-and-speak.py)")
        elif deploy_task:
            print(f"  CAPABILITY → {cap_label}  deploy task: {deploy_task}")
        else:
            print(f"  CAPABILITY → {cap_label} ({cap_id}) — pick a task in its category via pa.tasks.list()")

    elif match_type == "unsupported":
        # Expected, not an error. Pareta serves inference over text, documents,
        # images, and speech — it does not generate video/images/music, take
        # real-world actions, or fetch live data.
        print("  UNSUPPORTED → Pareta does not cover this request.")
        print(f"               reason: {m.reasoning}")
        print("               Action: tell the user, and (in the dashboard) file a")
        print("               'Don't see your task?' request — not reachable via API key.")

    else:  # "none" — router unavailable, lexical fallback found nothing
        print(f"  NO MATCH    → nothing confident (type={match_type!r}). Inspect candidates / rephrase.")
        for c in m.candidates:
            print(f"               candidate: {c.task_id}  score={c.score}  ({c.confidence})")


def main() -> None:
    pa = Pareta.from_env()  # reads PARETA_API_KEY (+ optional PARETA_BASE_URL)
    for q in QUERIES:
        print(f"\nquery: {q!r}")
        try:
            resolve(pa, q)
        except ParetaError as e:
            # Network / auth / 5xx — match itself failed, distinct from an
            # "unsupported" *result* (which is a successful 200 response).
            print(f"  match call failed: {e}")


if __name__ == "__main__":
    main()
