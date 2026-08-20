# -*- coding: utf-8 -*-
"""Fail closed on the P4B-02b7 AMI parameter tree hierarchy core.

Charter fixes the parameter trees scope; cross-check evidence binds product
tree construction against an independent reference. Verifier binds charter,
source map, evidence, Rust tokens, PLAN P4B-02b7.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02b7-parameter-trees-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4b-02b7-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b7-parameter-trees-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "parameter_trees_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b7.parameter-trees-stage.v1"
POLICY = "sipi.p4b-02b7.parameter-trees-v1.ast-forms-to-tree"


class ParameterTreesError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParameterTreesError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "parameter_trees_ported":
        raise ParameterTreesError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("ast_forms_to_tree_hierarchy", "branch_and_leaf_classification",
               "duplicate_child_rejection", "fail_closed_on_invalid_node_name")
    if any(admission.get(k) is not True for k in claimed):
        raise ParameterTreesError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise ParameterTreesError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn build_parameter_trees_v1",
        "pub enum ParameterTreesErrorV1",
        "DuplicateChild",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ParameterTreesError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4b-02b7.parameter-trees-crosscheck-evidence.v1":
        raise ParameterTreesError("evidence_schema_invalid")
    if evidence.get("status") != "product_owned_self_crosscheck_unbound":
        raise ParameterTreesError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 3:
        raise ParameterTreesError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b7" not in plan_text:
        raise ParameterTreesError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ParameterTreesError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
