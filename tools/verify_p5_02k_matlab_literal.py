"""Fail closed on the P5-02k MATLAB numeric-literal stage port.

The charter fixes the vector/matrix literal scope and the oracle-limitation
boundary; the source map records the MIT function mapping; the cross-check
evidence binds product parser and agent-com parse_matlab_literal results.
The verifier binds charter, source map, evidence, Rust tokens, and the PLAN
P5-02k row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-02k-matlab-literal-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-02k-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-02k-matlab-literal-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "matlab_literal_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-02k.matlab-literal-stage.v1"
POLICY = "sipi.p5-02j.value-consumption.v1.default-resolution"


class MatlabLiteralError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MatlabLiteralError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "matlab_literal_vector_matrix_ported":
        raise MatlabLiteralError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("vector_literals") is not True or admission.get("matrix_literals") is not True:
        raise MatlabLiteralError("vector_matrix_admission_drift")
    if admission.get("two_part_colon_oracle_limitation") is not True:
        raise MatlabLiteralError("oracle_limitation_admission_drift")
    if admission.get("behavior_profile") is not False:
        raise MatlabLiteralError("profile_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 5:
        raise MatlabLiteralError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn parse_literal_v1",
        "pub enum LiteralV1",
        "fn parse_row",
        "fn colon_range",
        "fn expand_scaled_ones",
    )
    if any(token not in source for token in required_tokens):
        raise MatlabLiteralError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-02k.matlab-literal-crosscheck-evidence.v1":
        raise MatlabLiteralError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise MatlabLiteralError("evidence_status_drift")
    cases = evidence.get("cases", [])
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise MatlabLiteralError("evidence_entry_mismatch")
    for case in cases:
        if not case.get("matched"):
            raise MatlabLiteralError("evidence_unmatched_case")
    limits = evidence.get("oracle_limitations", [])
    if len(limits) != 1 or limits[0].get("id") != "colon_range_simple" or not limits[0].get("oracle_raises"):
        raise MatlabLiteralError("oracle_limitation_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-02k" not in plan_text:
        raise MatlabLiteralError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except MatlabLiteralError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
