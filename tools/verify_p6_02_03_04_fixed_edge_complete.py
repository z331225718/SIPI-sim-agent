"""Verify P6-02/03/04 fixed TRAN-to-link edge completeness.

P6-02 requires the fixed tran-rc-pulse voltage_in to become the
DirectLaunch causal-FIR stimulus; P6-03 requires the dedicated edge
schema/identity record; P6-04 requires cooperative RunContext attempt
and atomic composite project publication. All were delivered by the
"a" sub-items. This gate fails closed if the edge spec or its three
audits disappear, or if the fixed composite route loses its binding.
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
SCHEMA = "sipi.p6-02-03-04.fixed-edge-complete.v1"

SPEC = "docs/clean-room/specs/p6-tran-to-link-edge.v1.md"
EDGE_AUDIT = "docs/baselines/audits/2026-08-11-p6-tran-to-link-edge.md"
RECORD_AUDIT = "docs/baselines/audits/2026-08-11-p6-tran-to-link-edge-record.md"
ATTEMPT_AUDIT = "docs/baselines/audits/2026-08-11-p6-tran-to-link-edge-attempt.md"
PUBLICATION = "docs/baselines/release-capability-publication.v1.yaml"


class FixedEdgeError(RuntimeError):
    pass


def load_yaml(relative: str) -> dict[str, Any]:
    if yaml is None:
        raise FixedEdgeError("pyyaml_unavailable")
    value = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FixedEdgeError("document_not_mapping")
    return value


def read_text(relative: str) -> str:
    try:
        return (ROOT / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise FixedEdgeError("source_read_failed") from error


def validate(root: Path = ROOT) -> dict[str, Any]:
    for relative in (SPEC, EDGE_AUDIT, RECORD_AUDIT, ATTEMPT_AUDIT, PUBLICATION):
        if not (root / relative).is_file():
            raise FixedEdgeError(f"file_missing:{relative}")
    spec = read_text(SPEC)
    for token in ("DirectLaunch", "voltage_in", "causal-FIR"):
        if token not in spec:
            raise FixedEdgeError(f"spec_token_missing:{token}")
    for audit in (EDGE_AUDIT, RECORD_AUDIT, ATTEMPT_AUDIT):
        text = read_text(audit)
        if "P6-0" not in text and "tran" not in text.lower():
            raise FixedEdgeError(f"audit_unrelated:{audit}")
    record = read_text(RECORD_AUDIT)
    if "sha-256" not in record.lower() and "sha256" not in record.lower():
        raise FixedEdgeError("identity_record_missing")
    attempt = read_text(ATTEMPT_AUDIT)
    for token in ("cancel", "artifact"):
        if token not in attempt.lower():
            raise FixedEdgeError(f"attempt_token_missing:{token}")
    publication = load_yaml(PUBLICATION)
    project = next((r for r in publication.get("rows", []) if isinstance(r, dict) and r.get("id") == "project-run"), None)
    if project is None or project.get("acceptance_state") != "specified":
        raise FixedEdgeError("project_run_binding_invalid")
    return {"valid": True, "items": 3}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except FixedEdgeError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
