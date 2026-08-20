# -*- coding: utf-8 -*-
"""Fail closed on the P4B-02b68 parameter tree path prefix enumeration core.

Charter fixes the path prefix scope; cross-check evidence binds product prefix enumeration
against an independent reference. Verifier binds charter, source map, evidence, Rust tokens,
PLAN P4B-02b68.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02b68-parameter-tree-path-prefixes-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4b-02b68-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b68-parameter-tree-path-prefixes-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "parameter_tree_path_prefixes_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b68.parameter-tree-path-prefixes-stage.v1"
POLICY = "sipi.p4b-02b68.parameter-tree-path-prefixes-v1.ancestor-chain-enumeration"


class ParameterTreePathPrefixError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParameterTreePathPrefixError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "parameter_tree_path_prefixes_ported":
        raise ParameterTreePathPrefixError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("ancestor_chain_enumeration", "full_path_included", "empty_path_fail_closed")
    if any(admission.get(k) is not True for k in claimed):
        raise ParameterTreePathPrefixError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 2:
        raise ParameterTreePathPrefixError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn enumerate_parameter_tree_path_prefixes_v1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ParameterTreePathPrefixError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4b-02b68-parameter-tree-path-prefixes-crosscheck-evidence.v1":
        raise ParameterTreePathPrefixError("evidence_schema_invalid")
    if evidence.get("status") != "product_owned_self_crosscheck_unbound":
        raise ParameterTreePathPrefixError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 4:
        raise ParameterTreePathPrefixError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b68" not in plan_text:
        raise ParameterTreePathPrefixError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ParameterTreePathPrefixError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
