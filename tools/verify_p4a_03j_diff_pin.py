# -*- coding: utf-8 -*-
"""Fail closed on the P4A-03j typed IBIS diff pin declaration core.

Charter fixes the diff pin declaration scope; cross-check evidence binds product
lifting against an independent reference. Verifier binds charter, source map,
evidence, Rust tokens, PLAN P4A-03j.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4a-03j-diff-pin-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4a-03j-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03j-diff-pin-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ibis" / "src" / "diff_pin_declaration_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4a-03j.diff-pin-stage.v1"
POLICY = "sipi.p4a-03j.diff-pin-declaration-v1.typed-diff-pin"


class DiffPinError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DiffPinError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "diff_pin_declaration_ported":
        raise DiffPinError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("typed_diff_pin_declaration", "differential_threshold_validation",
               "ascii_pin_name_validation", "fail_closed_on_invalid_input")
    if any(admission.get(k) is not True for k in claimed):
        raise DiffPinError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise DiffPinError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn lift_diff_pin_declaration_v1",
        "pub struct TypedDiffPinDeclarationV1",
        "DiffPinDeclarationErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise DiffPinError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4a-03j.diff-pin-crosscheck-evidence.v1":
        raise DiffPinError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise DiffPinError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 3:
        raise DiffPinError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4A-03j" not in plan_text:
        raise DiffPinError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except DiffPinError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
