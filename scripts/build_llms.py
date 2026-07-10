#!/usr/bin/env python
"""build_llms.py — generate llms.txt + llms-full.txt from sdk/docs/.

These are the AGENT-facing docs surface (llmstxt.org): llms.txt is a curated
index a coding agent reads first; llms-full.txt is the entire docs concatenated
into one self-contained file an agent can ingest in a single read. Both are
GENERATED from sdk/docs/*.md (the single source of truth) — never hand-edited —
and a CI drift guard (--check) fails if they're stale.

The generator is language-aware. Pareta ships one SDK per language (Python
today, TypeScript next), but they SHARE one set of docs: each page carries
stacked ```python / ```typescript code blocks (Path A in SDK_TS_PLAN.md — no
MDX <Tabs>, so the markdown stays renderer-agnostic and feeds llms.txt
verbatim). So there is ONE flat SECTIONS list and ONE set of URLs covering
every SDK; only the language-specific INTRO text is parametrized, via LANGUAGES.
Any new TS-specific page slots into guide/examples/reference and is added to
SECTIONS like any other. All SDKs share BASE_URL = https://docs.pareta.ai.

    python sdk/scripts/build_llms.py            # regenerate
    python sdk/scripts/build_llms.py --check    # exit 1 if they'd change

Output: sdk/docs/llms.txt, sdk/docs/llms-full.txt. When the Docusaurus site is
wired, these are also served at https://docs.pareta.ai/llms.txt (+ -full).
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
BASE_URL = "https://docs.pareta.ai"


@dataclass(frozen=True)
class Language:
    """One SDK's install/import one-liner — the only language-specific text.

    The docs themselves are shared (stacked code blocks per page), so a language
    is just how you install it and the symbol you import. Add an entry here and
    its blurb appears in both files automatically.
    """

    name: str
    install: str
    import_hint: str


LANGUAGES: list[Language] = [
    Language("Python", "pip install pareta", "from pareta import Pareta"),
    Language("TypeScript/JavaScript", "npm install pareta",
             'import { Pareta } from "pareta"'),
]

# General, language-neutral product summary (the blockquote at the top of both
# files). Anything language-specific lives in LANGUAGES, surfaced by _sdk_blurb.
INTRO = (
    'Pareta is one OpenAI-compatible endpoint with one model id: `"auto"`. '
    "Each request is planned, routed to benchmark-proven open specialists, "
    "verified, and falls back to a frontier model when that's the right call — "
    "one request, one bill. Its SDKs also let you benchmark `\"auto\"` against "
    "frontier models on your own data, read your auto traffic metrics, and "
    "find the grading contract that scores your eval data (`tasks.match`). "
    "Authenticate with a `pareta_sk_` key from the dashboard or the "
    "`PARETA_API_KEY` environment variable."
)

# Pages EXCLUDED from the published docs set (llms.txt, llms-full.txt, and the
# Docusaurus site). Founder decision, 2026-07-08 (auto-only surface):
# deploy/endpoint/leaderboard docs are removed from publish entirely —
# model:"auto" routes every request; tasks exist publicly only as eval
# grading contracts (reframed 2026-07-10). The source .md files stay on disk in sdk/docs/. This list must stay in
# sync with docs-site/sidebars.js and the docs-plugin `exclude` globs in
# docs-site/docusaurus.config.js.
EXCLUDED: frozenset[str] = frozenset({
    "guide/deploying-endpoints",
    "guide/discovery",
    "examples/deploy-and-infer",
    "examples/find-and-deploy-best-model",
    "reference/endpoints",
})

# Canonical reading order (mirrors the section index pages). One flat list — each
# page covers every SDK via stacked code blocks. README index files are
# intentionally excluded — llms.txt links content pages directly.
SECTIONS: list[tuple[str, str, list[str]]] = [
    ("Guide", "guide", [
        "installation", "quickstart", "core-concepts", "inference",
        "evaluation", "errors-and-retries",
        "async", "configuration", "cli", "mcp", "skill",
    ]),
    ("Examples", "examples", [
        "icd-coding", "retrieval", "extraction", "text-classification",
        "summarization", "text-to-speech", "speech-to-text",
        "evaluate-on-your-data",
        "document-extraction", "streaming-chat", "concurrent-async",
        "cost-and-metrics", "migrate-from-openai",
    ]),
    ("Reference", "reference", [
        "client", "chat", "models", "tasks", "evals", "audio",
        "rerank", "embeddings",
        "exceptions", "types", "http-api",
    ]),
]


def _sdk_blurb() -> str:
    """One line naming every SDK and how to install/import it — from LANGUAGES."""
    sdks = "; ".join(
        f"{lang.name} (`{lang.install}`, `{lang.import_hint}`)"
        for lang in LANGUAGES
    )
    return (
        "Pareta ships one SDK per language, all sharing these docs and the same "
        f"`/v1` HTTP API: {sdks}."
    )


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
    # Guard: an excluded page must never be re-added to SECTIONS by accident.
    listed = {f"{section}/{stem}" for _, section, stems in SECTIONS for stem in stems}
    banned = sorted(listed & EXCLUDED)
    if banned:
        raise SystemExit(
            f"build_llms: pages in SECTIONS are on the EXCLUDED list "
            f"(founder decision 2026-07-08, auto-only surface): {banned}")

    blurb = _sdk_blurb()
    index_lines = [f"# Pareta\n", f"> {INTRO}\n", f"{blurb}\n"]
    full_lines = [
        "# Pareta SDKs — full documentation\n",
        f"> {INTRO}\n",
        f"{blurb}\n",
        "This file concatenates the entire Pareta SDK documentation (guide + "
        "examples + reference, every language) for single-read agent "
        "consumption. Source: sdk/docs/ in the repo; browsable at "
        "https://docs.pareta.ai.\n",
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
        "for the underlying /v1 HTTP API the SDKs wrap.")
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
