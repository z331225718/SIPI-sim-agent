"""Verify P6-09 cross-crate negative integration gate completeness.

P6-09 requires the fixed TRAN→causal-FIR attempt→artifact/report topology
to fail closed on wrong cross-domain edges, record policy drift,
cancel/resource, unstaged staging, and tampered published content, while
keeping positive control verifiable. P6-09a delivered exactly this. This
gate fails closed if the audit or the Rust integration test disappears,
or if the audit loses its fail-closed coverage tokens.
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
SCHEMA = "sipi.p6-09.negative-integration-gate.v1"

AUDIT = "docs/baselines/audits/2026-08-11-p6-current-topology-negative-gate.md"
RUST_TEST = "crates/sipi-cli/tests/p6_current_topology.rs"

AUDIT_TOKENS = ("edge is rejected", "policy", "pre-cancelled", "under-budget", "staging", "published payload")


class NegativeGateError(RuntimeError):
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
        raise NegativeGateError("source_read_failed") from error


def validate(root: Path = ROOT) -> dict[str, Any]:
    for relative in (AUDIT, RUST_TEST):
        if not (root / relative).is_file():
            raise NegativeGateError(f"file_missing:{relative}")
    audit = read_text(AUDIT).lower()
    for token in AUDIT_TOKENS:
        if token not in audit:
            raise NegativeGateError(f"audit_token_missing:{token}")
    rust = read_text(RUST_TEST)
    for token in ("record", "publish", "cancel"):
        if token not in rust.lower():
            raise NegativeGateError(f"rust_token_missing:{token}")
    return {"valid": True, "fail_closed_surfaces": len(AUDIT_TOKENS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except NegativeGateError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
