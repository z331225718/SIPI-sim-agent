# -*- coding: utf-8 -*-
"""Fail closed on the P4B-02b5 AMI runtime-parameter-table core.

Charter fixes the profile-agnostic runtime-table scope; cross-check evidence
binds product runtime-parameter resolution against an independent reference.
Verifier binds charter, source map, evidence, Rust tokens, PLAN P4B-02b5.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02b5-ami-runtime-params-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4b-02b5-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b5-ami-runtime-params-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "ami_runtime_params_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b5.ami-runtime-params-stage.v1"
POLICY = "sipi.p4b-02b5.ami-runtime-params.v1.typed"


class RuntimeParamsError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeParamsError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "ami_runtime_params_ported":
        raise RuntimeParamsError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("in_candidate_overrides_default", "in_default_fallback_without_candidate",
               "in_missing_both_is_error", "out_info_omitted_without_candidate",
               "out_info_carried_with_candidate", "sorted_name_order",
               "candidate_type_mismatch_rejected")
    if any(admission.get(k) is not True for k in claimed):
        raise RuntimeParamsError("delivered_admission_drift")
    if admission.get("ami_runtime_execution") is not False or admission.get("reserved_name_catalog") is not False:
        raise RuntimeParamsError("runtime_or_reserved_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 6:
        raise RuntimeParamsError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn build_ami_runtime_params_v1",
        "pub enum RuntimeParamsErrorV1",
        "MissingRuntimeValue",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise RuntimeParamsError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4b-02b5.ami-runtime-params-crosscheck-evidence.v1":
        raise RuntimeParamsError("evidence_schema_invalid")
    if evidence.get("status") != "product_owned_self_crosscheck_unbound":
        raise RuntimeParamsError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise RuntimeParamsError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b5" not in plan_text:
        raise RuntimeParamsError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except RuntimeParamsError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
