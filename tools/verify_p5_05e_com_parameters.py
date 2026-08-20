# -*- coding: utf-8 -*-
"""Fail closed on the P5-05e COM typed parameter DTO core.

Charter fixes the merge rule (workbook priority, default fallback, unconsumed
retention, missing-value hard error); cross-check evidence binds product merge
against an independent reference. Verifier binds charter, source map, evidence,
Rust tokens, PLAN P5-05e.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-05e-com-parameters-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-05e-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-05e-com-parameters-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "com_parameters_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-05e.com-parameters-stage.v1"
POLICY = "sipi.p5-05e.com-parameters-v1.typed-dto"


class ComParametersError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ComParametersError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "com_parameter_dto_merged":
        raise ComParametersError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("workbook_value_priority") is not True or admission.get("default_fallback") is not True or admission.get("unconsumed_retained") is not True:
        raise ComParametersError("merge_admission_drift")
    if admission.get("behavior_profile") is not False:
        raise ComParametersError("profile_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise ComParametersError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub struct ComParametersV1",
        "pub fn merge_com_parameters_v1",
        "pub enum ComParametersErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ComParametersError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-05e.com-parameters-crosscheck-evidence.v1":
        raise ComParametersError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise ComParametersError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 1 or not entries[0].get("matched"):
        raise ComParametersError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-05e" not in plan_text:
        raise ComParametersError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ComParametersError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())