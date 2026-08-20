# -*- coding: utf-8 -*-
"""Fail closed on the P4A-03l typed IBIS submodel & add submodel core.

Charter fixes the submodel declaration scope; cross-check evidence binds product
lifting against an independent reference. Verifier binds charter, source map,
evidence, Rust tokens, PLAN P4A-03l.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4a-03l-submodel-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4a-03l-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03l-submodel-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ibis" / "src" / "submodel_declaration_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4a-03l.submodel-stage.v1"
POLICY = "sipi.p4a-03l.submodel-declaration-v1.typed-submodel"


class SubmodelError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SubmodelError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "submodel_declaration_ported":
        raise SubmodelError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("typed_submodel_declaration", "typed_add_submodel",
               "submodel_type_mode_validation", "fail_closed_on_invalid_input")
    if any(admission.get(k) is not True for k in claimed):
        raise SubmodelError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise SubmodelError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn lift_submodel_declaration_v1",
        "pub fn lift_add_submodel_v1",
        "TypedSubmodelDeclarationV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise SubmodelError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4a-03l.submodel-crosscheck-evidence.v1":
        raise SubmodelError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise SubmodelError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 3:
        raise SubmodelError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4A-03l" not in plan_text:
        raise SubmodelError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except SubmodelError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
