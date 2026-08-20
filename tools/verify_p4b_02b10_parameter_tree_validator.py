# -*- coding: utf-8 -*-
"""Fail closed on the P4B-02b10 AMI parameter tree structure validator core.

Charter fixes the parameter tree validator scope; cross-check evidence binds product
tree validation against an independent reference. Verifier binds charter, source map,
evidence, Rust tokens, PLAN P4B-02b10.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02b10-parameter-tree-validator-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4b-02b10-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b10-parameter-tree-validator-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "parameter_tree_validator_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b10.parameter-tree-validator-stage.v1"
POLICY = "sipi.p4b-02b10.parameter-tree-validator-v1.tree-invariants-validation"


class ParameterTreeValidatorError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParameterTreeValidatorError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "parameter_tree_validator_ported":
        raise ParameterTreeValidatorError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("ast_forms_to_tree_hierarchy", "branch_and_leaf_classification",
               "duplicate_child_rejection", "fail_closed_on_invalid_node_name")
    if any(admission.get(k) is not True for k in claimed):
        raise ParameterTreeValidatorError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise ParameterTreeValidatorError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn validate_parameter_trees_v1",
        "pub enum ParameterTreeValidatorErrorV1",
        "ExceededMaxDepth",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ParameterTreeValidatorError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4b-02b10-parameter-tree-validator-crosscheck-evidence.v1":
        raise ParameterTreeValidatorError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise ParameterTreeValidatorError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 3:
        raise ParameterTreeValidatorError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b10" not in plan_text:
        raise ParameterTreeValidatorError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ParameterTreeValidatorError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
