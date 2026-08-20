# -*- coding: utf-8 -*-
"""Fail closed on the P4B-02b14 AMI parameter tree structural visitor core.

Charter fixes the parameter tree visitor scope; cross-check evidence binds product
tree traversal against an independent reference. Verifier binds charter, source map,
evidence, Rust tokens, PLAN P4B-02b14.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02b14-parameter-tree-visitor-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4b-02b14-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b14-parameter-tree-visitor-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "parameter_tree_visitor_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b14.parameter-tree-visitor-stage.v1"
POLICY = "sipi.p4b-02b14.parameter-tree-visitor-v1.tree-structural-traversal"


class ParameterTreeVisitorError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParameterTreeVisitorError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "parameter_tree_visitor_ported":
        raise ParameterTreeVisitorError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("tree_structural_traversal", "enter_leave_branch_events",
               "visit_leaf_events", "fail_closed_on_empty_tree_list")
    if any(admission.get(k) is not True for k in claimed):
        raise ParameterTreeVisitorError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise ParameterTreeVisitorError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn traverse_parameter_trees_v1",
        "pub enum ParameterTreeVisitorErrorV1",
        "EnterBranch",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ParameterTreeVisitorError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4b-02b14-parameter-tree-visitor-crosscheck-evidence.v1":
        raise ParameterTreeVisitorError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise ParameterTreeVisitorError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 3:
        raise ParameterTreeVisitorError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b14" not in plan_text:
        raise ParameterTreeVisitorError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ParameterTreeVisitorError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
