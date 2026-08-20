"""Fail closed on the P5-02e canonical parameter key reference.

The reference records the xls_parameter key inventory observed in the
owner-authorized MATLAB r4.80 source, hash-bound to the material
registry. The verifier binds reference, registry hash, key/call counts,
and the PLAN P5-02e row; expression resolution and contracts stay
explicitly out of scope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-reference.v1.yaml"
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-02.canonical-parameter-reference.v1"
MATLAB_ID = "com-r480-matlab-source"
KEY_COUNT = 214
CALL_COUNT = 229


class ReferenceError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReferenceError("document_not_mapping")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def validate(root: Path = ROOT) -> dict[str, Any]:
    reference = load_yaml(REFERENCE)
    if reference.get("schema") != SCHEMA or reference.get("status") != "canonical_parameter_keys_observed_hash_bound":
        raise ReferenceError("reference_schema_or_status_invalid")
    if reference.get("key_count") != KEY_COUNT or reference.get("call_count") != CALL_COUNT:
        raise ReferenceError("key_or_call_count_drift")
    registry = load_yaml(REGISTRY)
    material = next((m for m in registry.get("materials", []) if m.get("id") == MATLAB_ID), None)
    if material is None:
        raise ReferenceError("registry_material_missing")
    if reference.get("source_sha256") != material.get("sha256", "").lower():
        raise ReferenceError("source_hash_drift")
    keys = reference.get("keys")
    if not isinstance(keys, dict) or len(keys) != KEY_COUNT:
        raise ReferenceError("keys_inventory_drift")
    for key, entry in keys.items():
        if not isinstance(entry, dict) or not entry.get("call_texts") or not entry.get("lines"):
            raise ReferenceError(f"key_entry_incomplete:{key}")
    claims = reference.get("non_claims")
    expected = ["not_a_product_contract", "not_parameter_defaults_resolved", "not_warning_contract", "not_compute_parity", "not_release_evidence"]
    if not isinstance(claims, list) or claims != expected:
        raise ReferenceError("non_claims_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-02e" not in plan_text:
        raise ReferenceError("plan_row_missing")
    return {"valid": True, "keys": KEY_COUNT, "calls": CALL_COUNT}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ReferenceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
