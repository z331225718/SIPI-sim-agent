# -*- coding: utf-8 -*-
"""Fail closed on the P4B-02b170 parameter list longest run item core.

Charter fixes the value-level longest-run-item scope; cross-check evidence binds product
longest-run-item extraction against an independent reference. Verifier binds charter, source
map, evidence, Rust tokens, PLAN P4B-02b170.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02b170-parameter-list-longest-run-item-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4b-02b170-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b170-parameter-list-longest-run-item-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "parameter_list_longest_run_item_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b170.parameter-list-longest-run-item-stage.v1"
POLICY = "sipi.p4b-02b170.parameter-list-longest-run-item-v1.longest-run-item"


class ParameterListLongestRunItemError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParameterListLongestRunItemError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "parameter_list_longest_run_item_ported":
        raise ParameterListLongestRunItemError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("longest_run_item", "earliest_tie", "non_list_fail_closed")
    if any(admission.get(k) is not True for k in claimed):
        raise ParameterListLongestRunItemError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 2:
        raise ParameterListLongestRunItemError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn parameter_list_longest_run_item_v1",
        "pub enum ParameterListLongestRunItemErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ParameterListLongestRunItemError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4b-02b170-parameter-list-longest-run-item-crosscheck-evidence.v1":
        raise ParameterListLongestRunItemError("evidence_schema_invalid")
    if evidence.get("status") != "product_owned_self_crosscheck_unbound":
        raise ParameterListLongestRunItemError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 4:
        raise ParameterListLongestRunItemError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b170" not in plan_text:
        raise ParameterListLongestRunItemError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
    except ParameterListLongestRunItemError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}))
        return 1
    print(json.dumps({"schema": SCHEMA, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
