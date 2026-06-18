#!/usr/bin/env python
"""build_llms.py — generate llms.txt + llms-full.txt from sdk/docs/.

These are the AGENT-facing docs surface (llmstxt.org): llms.txt is a curated
index a coding agent reads first; llms-full.txt is the entire docs concatenated
into one self-contained file an agent can ingest in a single read. Both are
GENERATED from sdk/docs/*.md (the single source of truth) — never hand-edited —
and a CI drift guard (--check) fails if they're stale.

    python sdk/scripts/build_llms.py            # regenerate
    python sdk/scripts/build_llms.py --check    # exit 1 if they'd change

Output: sdk/docs/llms.txt, sdk/docs/llms-full.txt. When the Docusaurus site is
wired, these are also served at https://docs.pareta.ai/llms.txt (+ -full).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
BASE_URL = "https://docs.pareta.ai"

INTRO = (
    "Pareta is a marketplace + control plane for open-weights models. The "
    "`pareta` Python SDK lets you deploy task-specific open-weights endpoints "
    "(Pareta picks the GPU), run metered OpenAI-compatible inference, browse a "
    "per-task benchmark catalog, and evaluate models on your own data — then "
    "deploy the winner. Install with `pip install pareta`; authenticate with a "
    "`pareta_sk_` key from the dashboard or `PARETA_API_KEY`."
)

# Canonical reading order (mirrors the section index pages). README index files
# are intentionally excluded — llms.txt links content pages directly.
SECTIONS: list[tuple[str, str, list[str]]] = [
    ("Guide", "guide", [
        "installation", "quickstart", "core-concepts", "inference",
        "deploying-endpoints", "discovery", "evaluation", "errors-and-retries",
        "async", "configuration",
    ]),
    ("Examples", "examples", [
        "deploy-and-infer", "find-and-deploy-best-model", "evaluate-on-your-data",
        "document-extraction", "streaming-chat", "concurrent-async",
        "cost-and-metrics", "migrate-from-openai",
    ]),
    ("Reference", "reference", [
        "client", "chat", "models", "endpoints", "tasks", "evals",
        "exceptions", "types", "http-api",
    ]),
]


def _title(md: str, fallback: str) -> str:
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _summary(md: str) -> str:
    """First real prose paragraph after the H1, collapsed to one line."""
    lines = md.splitlines()
    # skip to after the first H1
    i = 0
    for idx, line in enumerate(lines):
        if line.startswith("# "):
            i = idx + 1
            break
    buf: list[str] = []
    for line in lines[i:]:
        s = line.strip()
        if not s:
            if buf:
                break
            continue
        if s.startswith(("#", "```", "|", "-", "*", ">")):
            if buf:
                break
            continue
        buf.append(s)
    text = " ".join(buf)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # strip md links, keep text
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 200:
        text = text[:197].rsplit(" ", 1)[0] + "…"
    return text


def _read(section: str, stem: str) -> str | None:
    p = DOCS / section / f"{stem}.md"
    return p.read_text() if p.exists() else None


def build() -> tuple[str, str]:
    index_lines = [f"# Pareta\n", f"> {INTRO}\n"]
    full_lines = [
        "# Pareta SDK — full documentation\n",
        f"> {INTRO}\n",
        "This file concatenates the entire Pareta SDK documentation (guide + "
        "examples + reference) for single-read agent consumption. Source: "
        "sdk/docs/ in the repo; browsable at https://docs.pareta.ai.\n",
    ]
    missing: list[str] = []
    for label, section, stems in SECTIONS:
        index_lines.append(f"\n## {label}\n")
        for stem in stems:
            md = _read(section, stem)
            if md is None:
                missing.append(f"{section}/{stem}.md")
                continue
            title = _title(md, stem)
            summary = _summary(md)
            url = f"{BASE_URL}/{section}/{stem}"
            index_lines.append(f"- [{title}]({url}): {summary}")
            full_lines.append(f"\n\n---\n\n<!-- {section}/{stem}.md -->\n\n{md.rstrip()}\n")
    # Optional machine-readable contract.
    index_lines.append("\n## Optional\n")
    index_lines.append(
        f"- [OpenAPI spec]({BASE_URL}/openapi.json): machine-readable contract "
        "for the underlying /v1 HTTP API the SDK wraps.")
    index_lines.append(
        f"- [llms-full.txt]({BASE_URL}/llms-full.txt): the entire docs in one file.")

    if missing:
        raise SystemExit(f"build_llms: missing doc pages: {missing}")
    return "\n".join(index_lines) + "\n", "\n".join(full_lines) + "\n"


def main() -> int:
    llms, full = build()
    out_index = DOCS / "llms.txt"
    out_full = DOCS / "llms-full.txt"
    if "--check" in sys.argv:
        cur_i = out_index.read_text() if out_index.exists() else ""
        cur_f = out_full.read_text() if out_full.exists() else ""
        if cur_i != llms or cur_f != full:
            print("llms.txt / llms-full.txt are STALE. Run: python sdk/scripts/build_llms.py",
                  file=sys.stderr)
            return 1
        print("llms.txt + llms-full.txt up to date.")
        return 0
    out_index.write_text(llms)
    out_full.write_text(full)
    print(f"Wrote {out_index} ({len(llms)} bytes) + {out_full} ({len(full)} bytes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
