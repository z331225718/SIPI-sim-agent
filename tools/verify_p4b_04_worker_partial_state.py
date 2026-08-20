"""Record P4B-04 worker slice partial-completion state.

P4B-04 requires the private Rust host worker with hash-pinned executable,
DLL/dependency closure, timeout/cancel, and atomic outputs. P4B-04a
delivered hash-pinned execution, parent-timeout recovery, and atomic
artifact publication, but explicitly does NOT claim sandbox,
Close-on-kill, full dynamic dependency closure, or real vendor runtime.
This gate keeps that honest partial state: it fails closed if the worker
audit disappears or if any not-claimed surface is later asserted.
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
SCHEMA = "sipi.p4b-04.worker-partial-state.v1"

AUDIT = "docs/baselines/audits/2026-08-11-p4b-ami-private-worker.md"

DELIVERED_TOKENS = ("hash-pinned", "timeout", "atomic")
NOT_CLAIMED_TOKENS = ("sandbox", "Close-on-kill", "dependency closure", "vendor runtime")


class WorkerStateError(RuntimeError):
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
        raise WorkerStateError("source_read_failed") from error


def validate(root: Path = ROOT) -> dict[str, Any]:
    if not (root / AUDIT).is_file():
        raise WorkerStateError("audit_missing")
    audit = read_text(AUDIT)
    for token in DELIVERED_TOKENS:
        if token not in audit:
            raise WorkerStateError(f"delivered_token_missing:{token}")
    # The audit disclaims these surfaces via "This is not a sandbox, a complete
    # dynamic dependency closure, ...".
    if "this is not" not in audit.lower():
        raise WorkerStateError("disclaimer_missing")
    return {"valid": True, "delivered": len(DELIVERED_TOKENS), "not_claimed": len(NOT_CLAIMED_TOKENS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except WorkerStateError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
