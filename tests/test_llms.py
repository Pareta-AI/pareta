"""Drift guard: the agent-facing llms.txt / llms-full.txt must be regenerated
from sdk/docs/ whenever the docs change. Fails if they are stale (mirrors the
backend's openapi/catalog --check guards)."""

import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_llms.py"


def test_llms_txt_is_fresh():
    r = subprocess.run([sys.executable, str(_SCRIPT), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, (
        "llms.txt / llms-full.txt are stale vs sdk/docs/. "
        "Run: python sdk/scripts/build_llms.py\n" + r.stderr)
