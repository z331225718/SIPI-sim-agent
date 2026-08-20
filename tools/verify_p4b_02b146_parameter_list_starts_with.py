# -*- coding: utf-8 -*-
"""Fail closed on the P4B-02b146 parameter list starts-with core.

Charter fixes the list-value prefix relation scope; cross-check evidence binds product prefix
checking against an independent reference. Verifier binds charter, source map, evidence, Rust
tokens, PLAN P4B-02b146.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02b146-parameter-list-starts-with-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4b-02b146-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b146-parameter-list-starts-with-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "parameter_list_starts_with_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b146.parameter-list-starts-with-stage.v1"
POLICY = "sipi.p4b-02b146.parameter-list-starts-with-v1.prefix-check"


class ParameterListStartsWithError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParameterListStartsWithError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "parameter_list_starts_with_ported":
        raise ParameterListStartsWithError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("prefix_check", "element_wise_byte_equality", "non_list_fail_closed")
    if any(admission.get(k) is not True for k in claimed):
        raise ParameterListStartsWithError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 2:
        raise ParameterListStartsWithError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn list_starts_with_v1",
        "pub enum ParameterListStartsWithErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ParameterListStartsWithError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4b-02b146-parameter-list-starts-with-crosscheck-evidence.v1":
        raise ParameterListStartsWithError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise ParameterListStartsWithError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 4:
        raise ParameterListStartsWithError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b146" not in plan_text:
        raise ParameterListStartsWithError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
    except ParameterListStartsWithError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}))
        return 1
    print(json.dumps({"schema": SCHEMA, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
