# -*- coding: utf-8 -*-
"""Fail closed on the P4B-02b64 parameter profile selection core.

Charter fixes the profile selection scope; cross-check evidence binds product profile selection
against an independent reference. Verifier binds charter, source map, evidence, Rust tokens,
PLAN P4B-02b64.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02b64-parameter-profile-select-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4b-02b64-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b64-parameter-profile-select-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "parameter_profile_select_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b64.parameter-profile-select-stage.v1"
POLICY = "sipi.p4b-02b64.parameter-profile-select-v1.name-set-selection"


class ParameterProfileSelectionError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParameterProfileSelectionError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "parameter_profile_select_ported":
        raise ParameterProfileSelectionError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("name_set_selection", "missing_parameter_fail_closed", "empty_selection_fail_closed")
    if any(admission.get(k) is not True for k in claimed):
        raise ParameterProfileSelectionError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 2:
        raise ParameterProfileSelectionError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn select_parameter_profile_v1",
        "pub struct ParameterProfileSelectionV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ParameterProfileSelectionError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4b-02b64-parameter-profile-select-crosscheck-evidence.v1":
        raise ParameterProfileSelectionError("evidence_schema_invalid")
    if evidence.get("status") != "product_owned_self_crosscheck_unbound":
        raise ParameterProfileSelectionError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 4:
        raise ParameterProfileSelectionError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b64" not in plan_text:
        raise ParameterProfileSelectionError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ParameterProfileSelectionError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
