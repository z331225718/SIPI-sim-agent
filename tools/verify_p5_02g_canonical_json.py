"""Fail closed on the P5-02g canonical parameter JSON v1.

The canonical JSON records literal defaults, resolved pure reference
chains, and needs_matlab_oracle markers (arithmetic expressions and
cycles stay unevaluated). The verifier binds counts, source hash, draft
ref, and the PLAN P5-02g row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json.v1.yaml"
DRAFT = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json-draft.v1.yaml"
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-02.canonical-parameter-json.v1"
MATLAB_ID = "com-r480-matlab-source"
KEY_COUNT = 214
RESOLVED_CALLS = 7
ORACLE_CALLS = 23


class CanonicalError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CanonicalError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    canonical = load_yaml(CANONICAL)
    if canonical.get("schema") != SCHEMA or canonical.get("status") != "canonical_parameter_json_v1_literals_and_reference_chains":
        raise CanonicalError("canonical_schema_or_status_invalid")
    if canonical.get("key_count") != KEY_COUNT:
        raise CanonicalError("key_count_drift")
    if canonical.get("resolved_default_calls") != RESOLVED_CALLS or canonical.get("needs_oracle_calls") != ORACLE_CALLS:
        raise CanonicalError("resolution_totals_drift")
    draft = load_yaml(DRAFT)
    if canonical.get("source_sha256") != draft.get("source_sha256"):
        raise CanonicalError("source_hash_drift")
    registry = load_yaml(REGISTRY)
    material = next((m for m in registry.get("materials", []) if m.get("id") == MATLAB_ID), None)
    if material is None or canonical.get("source_sha256") != material.get("sha256", "").lower():
        raise CanonicalError("registry_source_hash_drift")
    keys = canonical.get("keys")
    if not isinstance(keys, dict) or len(keys) != KEY_COUNT:
        raise CanonicalError("keys_drift")
    claims = canonical.get("non_claims")
    expected = ["not_arithmetic_evaluation", "not_warning_contract", "not_parameter_design", "not_compute_parity", "not_release_evidence"]
    if not isinstance(claims, list) or claims != expected:
        raise CanonicalError("non_claims_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-02g" not in plan_text:
        raise CanonicalError("plan_row_missing")
    return {"valid": True, "resolved": RESOLVED_CALLS, "needs_oracle": ORACLE_CALLS}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except CanonicalError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
