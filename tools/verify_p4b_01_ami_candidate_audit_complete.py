"""Verify P4B-01 AMI candidate quarantine audit completeness.

P4B-01 requires auditing the sipi-ami candidate material origin,
implementer exposure, dependency licensing, and standard basis. P4B-01a
delivered the quarantine provenance/license/exposure preflight: it
records Git-object identity, locked dependency closures, bounded exposure
labels, and requires quarantine/unknown source-map state. This gate fails
closed if the preflight report or its audit evidence disappears, or if
the report claims promotion eligibility.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4b-01.ami-candidate-audit-complete.v1"

PREFLIGHT = "tools/verify_p4b_ami_candidate_preflight.py"
AUDIT = "docs/baselines/audits/2026-08-10-p4b-ami-candidate-quarantine-preflight.md"


class AuditCompleteError(RuntimeError):
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
        raise AuditCompleteError("source_read_failed") from error


def validate(root: Path = ROOT) -> dict[str, Any]:
    for relative in (PREFLIGHT, AUDIT):
        if not (root / relative).is_file():
            raise AuditCompleteError(f"file_missing:{relative}")
    preflight = read_text(PREFLIGHT)
    for token in ("source_map", "dependency", "exposure", "promotion_eligible"):
        if token not in preflight:
            raise AuditCompleteError(f"preflight_token_missing:{token}")
    audit = read_text(AUDIT)
    for token in ("quarantine", "dependency", "exposure", "promotion_eligible"):
        if token not in audit:
            raise AuditCompleteError(f"audit_token_missing:{token}")
    # The audit must keep the candidate un-promoted.
    if "promotion_eligible: false" not in audit:
        raise AuditCompleteError("promotion_claim_possible")
    return {"valid": True, "elements": 4}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except AuditCompleteError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
