# -*- coding: utf-8 -*-
"""Fail closed on the P4A-03d typed IBIS Model-declaration core.

The charter fixes the typed Model_type set and the Model_type data-line
handling; the cross-check evidence binds product declarations against an
independent observer on the authorized as4c512m16md4v-053bin.ibs. The
verifier binds charter, source map, evidence, Rust tokens, PLAN P4A-03d.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4a-03d-model-declaration-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4a-03d-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03d-model-declaration-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ibis" / "src" / "model_declaration_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4a-03d.model-declaration-stage.v1"
POLICY = "sipi.p4a-03d.model-declaration.v1.typed-declaration-only"


class ModelDeclError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ModelDeclError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "typed_model_declaration_ported":
        raise ModelDeclError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("typed_model_type_set") is not True or admission.get("model_type_data_line") is not True:
        raise ModelDeclError("model_type_admission_drift")
    if admission.get("style_range_units") is not False or admission.get("behavior_profile") is not False:
        raise ModelDeclError("range_or_profile_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise ModelDeclError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub struct TypedModelDeclarationV1",
        "pub enum ModelTypeV1",
        "pub fn lift_model_declarations_v1",
        "pub enum ModelDeclarationErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ModelDeclError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4a-03d.model-declaration-crosscheck-evidence.v1":
        raise ModelDeclError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise ModelDeclError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 1 or not entries[0].get("matched"):
        raise ModelDeclError("evidence_entry_mismatch")
    if entries[0].get("product_declaration_count") != 67 or entries[0].get("observer_model_count") != 67:
        raise ModelDeclError("model_count_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4A-03d" not in plan_text:
        raise ModelDeclError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ModelDeclError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())