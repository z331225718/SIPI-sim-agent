"""Fail closed on the P5-02h canonical parameter JSON v2.

v2 adds bounded static arithmetic (documented grammar, IEEE doubles) to
v1; expressions whose operands lack canonical values stay
needs_matlab_oracle. The verifier binds counts, grammar, source hash,
and the PLAN P5-02h row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json.v2.yaml"
V1 = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-02.canonical-parameter-json.v2"
KEY_COUNT = 214
EVALUATED = 3
NEEDS_ORACLE = 20


class V2Error(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise V2Error("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    v2 = load_yaml(V2)
    if v2.get("schema") != SCHEMA or v2.get("status") != "canonical_parameter_json_v2_bounded_static_arithmetic":
        raise V2Error("v2_schema_or_status_invalid")
    if v2.get("key_count") != KEY_COUNT:
        raise V2Error("key_count_drift")
    if v2.get("statically_evaluated_calls") != EVALUATED or v2.get("needs_oracle_calls") != NEEDS_ORACLE:
        raise V2Error("evaluation_totals_drift")
    if v2.get("grammar") != {
        "numbers": "ieee_double_including_leading_dot",
        "operators": ["+", "-", "*", "/"],
        "parentheses": "allowed",
        "references": "param.X_or_OP.X_resolved_by_canonical_value",
        "functions": "forbidden",
    }:
        raise V2Error("grammar_drift")
    v1 = load_yaml(V1)
    if v2.get("source_sha256") != v1.get("source_sha256"):
        raise V2Error("source_hash_drift")
    keys = v2.get("keys")
    if not isinstance(keys, dict) or len(keys) != KEY_COUNT:
        raise V2Error("keys_drift")
    claims = v2.get("non_claims")
    expected = ["not_matlab_evaluation", "not_warning_contract", "not_parameter_design", "not_compute_parity", "not_release_evidence"]
    if not isinstance(claims, list) or claims != expected:
        raise V2Error("non_claims_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-02h" not in plan_text:
        raise V2Error("plan_row_missing")
    return {"valid": True, "evaluated": EVALUATED, "needs_oracle": NEEDS_ORACLE}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except V2Error as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
