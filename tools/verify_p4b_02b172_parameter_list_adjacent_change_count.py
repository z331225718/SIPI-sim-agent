# -*- coding: utf-8 -*-
"""Fail closed on the P4B-02b172 parameter list adjacent change count core.

Charter fixes the value-level adjacent-change-count scope; cross-check evidence binds product
change-count computation against an independent reference. Verifier binds charter, source
map, evidence, Rust tokens, PLAN P4B-02b172.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02b172-parameter-list-adjacent-change-count-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4b-02b172-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b172-parameter-list-adjacent-change-count-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "parameter_list_adjacent_change_count_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b172.parameter-list-adjacent-change-count-stage.v1"
POLICY = "sipi.p4b-02b172.parameter-list-adjacent-change-count-v1.adjacent-change-count"


class ParameterListAdjacentChangeCountError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParameterListAdjacentChangeCountError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "parameter_list_adjacent_change_count_ported":
        raise ParameterListAdjacentChangeCountError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("adjacent_change_count", "changes_equals_runs_minus_one", "non_list_fail_closed")
    if any(admission.get(k) is not True for k in claimed):
        raise ParameterListAdjacentChangeCountError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 2:
        raise ParameterListAdjacentChangeCountError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn parameter_list_adjacent_change_count_v1",
        "pub enum ParameterListAdjacentChangeCountErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ParameterListAdjacentChangeCountError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4b-02b172-parameter-list-adjacent-change-count-crosscheck-evidence.v1":
        raise ParameterListAdjacentChangeCountError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise ParameterListAdjacentChangeCountError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 4:
        raise ParameterListAdjacentChangeCountError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b172" not in plan_text:
        raise ParameterListAdjacentChangeCountError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
    except ParameterListAdjacentChangeCountError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}))
        return 1
    print(json.dumps({"schema": SCHEMA, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
