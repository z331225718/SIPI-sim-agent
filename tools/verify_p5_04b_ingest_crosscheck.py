"""Fail closed on the P5-04b ingest cross-check evidence.

The evidence records product ingest sdd21 vs MATLAB oracle network
metrics at 26.56 GHz for the three synthetic fixtures. The verifier
binds per-entry deltas (tolerance 1.0 dB), overall status, target
frequency, and the PLAN P5-04b row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04b-ingest-crosscheck-evidence.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04b.ingest-crosscheck-evidence.v1"
TOLERANCE_DB = 1.0


class CrosscheckError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CrosscheckError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != SCHEMA or evidence.get("status") != "ingest_sdd21_crosscheck_matched":
        raise CrosscheckError("evidence_schema_or_status_invalid")
    if evidence.get("target_frequency_hz") != 2.656e10:
        raise CrosscheckError("target_frequency_drift")
    entries = evidence.get("entries")
    if not isinstance(entries, list) or len(entries) != 3:
        raise CrosscheckError("entries_drift")
    for entry in entries:
        if abs(entry.get("delta_db", 1e9)) > TOLERANCE_DB:
            raise CrosscheckError("delta_exceeds_tolerance:" + str(entry.get("material_id")))
        if not entry.get("series_sha256"):
            raise CrosscheckError("series_hash_missing:" + str(entry.get("material_id")))
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04b" not in plan_text:
        raise CrosscheckError("plan_row_missing")
    return {"valid": True, "entries": len(entries)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except CrosscheckError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
