# -*- coding: utf-8 -*-
"""Fail closed on the P3C-03d dB-domain tolerance core.

Charter fixes the dB absolute-difference rule and the owner 0.1 dB constant;
cross-check evidence binds product passes against an independent reference.
Verifier binds charter, source map, evidence, Rust tokens, PLAN P3C-03d.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p3c-03d-db-tolerance-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p3c-03d-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-03d-db-tolerance-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "db_tolerance_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p3c-03d.db-tolerance-stage.v1"
POLICY = "sipi.p3c-03d.db-tolerance.v1.0p1db"


class DbTolError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DbTolError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "db_tolerance_check_ported":
        raise DbTolError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("db_absolute_difference") is not True or admission.get("owner_0p1db_constant") is not True:
        raise DbTolError("db_admission_drift")
    if admission.get("behavior_profile") is not False:
        raise DbTolError("profile_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise DbTolError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn db_tolerance_check_v1",
        "pub fn owner_db_tolerance_check_v1",
        "pub struct DbToleranceResultV1",
        "pub const OWNER_DB_TOLERANCE_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise DbTolError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p3c-03d.db-tolerance-crosscheck-evidence.v1":
        raise DbTolError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise DbTolError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise DbTolError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P3C-03d" not in plan_text:
        raise DbTolError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except DbTolError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())