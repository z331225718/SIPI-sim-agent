"""Fail closed on the P5-02f canonical parameter JSON draft.

The draft classifies every observed xls_parameter call's required flag
and default expression (literal / reference / none) without evaluating
anything, hash-bound to the reference and registry. The verifier binds
draft counts, source hash, classification totals, and the PLAN P5-02f
row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json-draft.v1.yaml"
REFERENCE = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-reference.v1.yaml"
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-02.canonical-parameter-json-draft.v1"
MATLAB_ID = "com-r480-matlab-source"
KEY_COUNT = 214
CALL_COUNT = 229
LITERAL_DEFAULTS = 163
REFERENCE_DEFAULTS = 30


class DraftError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DraftError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    draft = load_yaml(DRAFT)
    if draft.get("schema") != SCHEMA or draft.get("status") != "canonical_parameter_json_draft_defaults_classified_not_evaluated":
        raise DraftError("draft_schema_or_status_invalid")
    if draft.get("key_count") != KEY_COUNT or draft.get("call_count") != CALL_COUNT:
        raise DraftError("count_drift")
    if draft.get("literal_default_calls") != LITERAL_DEFAULTS or draft.get("reference_default_calls") != REFERENCE_DEFAULTS:
        raise DraftError("classification_totals_drift")
    reference = load_yaml(REFERENCE)
    if draft.get("source_sha256") != reference.get("source_sha256"):
        raise DraftError("source_hash_drift")
    registry = load_yaml(REGISTRY)
    material = next((m for m in registry.get("materials", []) if m.get("id") == MATLAB_ID), None)
    if material is None or draft.get("source_sha256") != material.get("sha256", "").lower():
        raise DraftError("registry_source_hash_drift")
    keys = draft.get("keys")
    if not isinstance(keys, dict) or len(keys) != KEY_COUNT:
        raise DraftError("keys_drift")
    for key, entry in keys.items():
        if not isinstance(entry, dict) or not entry.get("calls") or not entry.get("occurrences"):
            raise DraftError(f"key_entry_incomplete:{key}")
    claims = draft.get("non_claims")
    expected = ["not_defaults_resolved", "not_warning_contract", "not_parameter_design", "not_compute_parity", "not_release_evidence"]
    if not isinstance(claims, list) or claims != expected:
        raise DraftError("non_claims_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-02f" not in plan_text:
        raise DraftError("plan_row_missing")
    return {"valid": True, "keys": KEY_COUNT, "literal_defaults": LITERAL_DEFAULTS, "reference_defaults": REFERENCE_DEFAULTS}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except DraftError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
