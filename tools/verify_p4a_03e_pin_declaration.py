# -*- coding: utf-8 -*-
"""Fail closed on the P4A-03e typed [Pin] declaration core.

Charter fixes the pin-lifting scope; cross-check evidence binds product pins
against an independent observer on the authorized profile. Verifier binds
charter, source map, evidence, Rust tokens, PLAN P4A-03e.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4a-03e-pin-declaration-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4a-03e-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03e-pin-declaration-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ibis" / "src" / "pin_declaration_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4a-03e.pin-declaration-stage.v1"
POLICY = "sipi.p4a-03e.pin-declaration.v1.typed"


class PinDeclError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PinDeclError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "pin_declaration_ported":
        raise PinDeclError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("pin_row_lifting") is not True or admission.get("malformed_row_rejection") is not True:
        raise PinDeclError("pin_admission_drift")
    if admission.get("behavior_profile") is not False:
        raise PinDeclError("profile_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 3:
        raise PinDeclError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub struct TypedPinDeclarationV1",
        "pub fn lift_pin_declarations_v1",
        "pub enum PinDeclarationErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise PinDeclError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4a-03e.pin-declaration-crosscheck-evidence.v1":
        raise PinDeclError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise PinDeclError("evidence_status_drift")
    if evidence.get("product_pin_count") != evidence.get("observer_pin_count"):
        raise PinDeclError("evidence_count_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4A-03e" not in plan_text:
        raise PinDeclError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except PinDeclError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())