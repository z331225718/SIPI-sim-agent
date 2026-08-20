# -*- coding: utf-8 -*-
"""Fail closed on the P4B-02b93 parameter tree typed-leaf type counts core.

Charter fixes the typed-leaf type counting scope; cross-check evidence binds product counting
against an independent reference. Verifier binds charter, source map, evidence, Rust tokens,
PLAN P4B-02b93.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02b93-parameter-tree-typed-leaf-type-counts-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4b-02b93-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b93-parameter-tree-typed-leaf-type-counts-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "parameter_tree_typed_leaf_type_counts_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b93.parameter-tree-typed-leaf-type-counts-stage.v1"
POLICY = "sipi.p4b-02b93.parameter-tree-typed-leaf-type-counts-v1.typed-leaf-type-counts"


class ParameterTreeTypedLeafTypeCountsError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParameterTreeTypedLeafTypeCountsError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "parameter_tree_typed_leaf_type_counts_ported":
        raise ParameterTreeTypedLeafTypeCountsError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("typed_leaf_type_counts", "sum_invariant", "total_no_error_path")
    if any(admission.get(k) is not True for k in claimed):
        raise ParameterTreeTypedLeafTypeCountsError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 2:
        raise ParameterTreeTypedLeafTypeCountsError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn count_parameter_tree_typed_leaves_by_type_v1",
        "pub struct ParameterTreeTypedLeafTypeCountsV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ParameterTreeTypedLeafTypeCountsError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4b-02b93-parameter-tree-typed-leaf-type-counts-crosscheck-evidence.v1":
        raise ParameterTreeTypedLeafTypeCountsError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise ParameterTreeTypedLeafTypeCountsError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 4:
        raise ParameterTreeTypedLeafTypeCountsError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b93" not in plan_text:
        raise ParameterTreeTypedLeafTypeCountsError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
    except ParameterTreeTypedLeafTypeCountsError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}))
        return 1
    print(json.dumps({"schema": SCHEMA, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
