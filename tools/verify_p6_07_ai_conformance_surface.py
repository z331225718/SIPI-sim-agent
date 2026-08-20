"""Verify P6-07 AI conformance surface completeness.

P6-07 requires AI to construct constructible requests from catalog/schema/
example, with admitted vs executed distinct, and stable process
diagnostics (code/stage/pointer/rule_id). This gate fails closed if the
AI conformance audit disappears or loses its constructible/admitted/
executed distinction tokens.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p6-07.ai-conformance-surface.v1"

AUDIT = "docs/baselines/audits/2026-08-11-p6-ai-conformance.md"
REQUIRED_TOKENS = ("constructible", "admitted", "executed")


class AiConformanceError(RuntimeError):
    pass


def git_tracked(relative: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", "--", relative],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
    )
    return completed.returncode == 0


def read_text(relative: str) -> str:
    try:
        return (ROOT / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise AiConformanceError("source_read_failed") from error


def validate(root: Path = ROOT) -> dict[str, Any]:
    if not (root / AUDIT).is_file():
        raise AiConformanceError("audit_missing")
    audit = read_text(AUDIT).lower()
    for token in REQUIRED_TOKENS:
        if token not in audit:
            raise AiConformanceError(f"audit_token_missing:{token}")
    return {"valid": True, "distinctions": len(REQUIRED_TOKENS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except AiConformanceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
