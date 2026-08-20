"""Verify P4A-05 conformance matrix and unsupported-boundary completeness.

P4A-05 requires the public/product fixture set, the malformed/unsupported
matrix, and the oracle compare. P4A-05a delivered the versioned
conformance matrix with accepted DC scope, product-owned implementations,
and unsupported entries; P4A-04d delivered the two-fresh-custody oracle
compare. This gate fails closed if the matrix loses its unsupported/
not_assessed entries, its boundary_recorded status, or its accepted
DC profile, or if the oracle-compare evidence audit disappears.
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
SCHEMA = "sipi.p4a-05.conformance-matrix-complete.v1"

MATRIX = "docs/baselines/p4a-ibis-conformance-matrix.v1.yaml"
ORACLE_AUDIT = "docs/baselines/audits/2026-08-11-p4a-ibis-input-typ-static-compare.md"

REQUIRED_STATUSES = {"implemented_self_tested", "external_profile_accepted", "unsupported", "not_assessed"}
REQUIRED_UNSUPPORTED_IDS = {
    "non-input-models",
    "non-typical-corners-and-pvt",
    "package-pin-vt-ramp-network",
    "ami-and-algorithmic-model",
    "file-url-and-default-route",
}


class MatrixCompleteError(RuntimeError):
    pass


def load_yaml(relative: str) -> dict[str, Any]:
    if yaml is None:
        raise MatrixCompleteError("pyyaml_unavailable")
    value = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MatrixCompleteError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    if not (root / MATRIX).is_file():
        raise MatrixCompleteError("matrix_missing")
    matrix = load_yaml(MATRIX)
    if matrix.get("schema") != "sipi.p4a-ibis-conformance-matrix.v1":
        raise MatrixCompleteError("matrix_schema_invalid")
    if matrix.get("status") != "boundary_recorded":
        raise MatrixCompleteError("matrix_status_drift")
    entries = {entry.get("id"): entry for entry in matrix.get("entries", []) if isinstance(entry, dict)}
    if not entries:
        raise MatrixCompleteError("matrix_empty")
    statuses = {entry.get("status") for entry in entries.values() if entry.get("status") in REQUIRED_STATUSES}
    if "external_profile_accepted" not in statuses:
        raise MatrixCompleteError("accepted_profile_missing")
    for entry_id in REQUIRED_UNSUPPORTED_IDS:
        entry = entries.get(entry_id)
        if entry is None or entry.get("status") not in {"unsupported", "not_assessed"}:
            raise MatrixCompleteError(f"unsupported_entry_missing:{entry_id}")

    # The oracle compare evidence audit must remain tracked.
    if not (root / ORACLE_AUDIT).is_file():
        raise MatrixCompleteError("oracle_audit_missing")
    return {"valid": True, "entries": len(entries)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except MatrixCompleteError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
