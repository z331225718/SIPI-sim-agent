# -*- coding: utf-8 -*-
"""Fail closed on the P4B-02b61 AMI text form heads counting core.

Charter fixes the form heads scope; cross-check evidence binds product head counts against an
independent reference. Verifier binds charter, source map, evidence, Rust tokens, PLAN P4B-02b61.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02b61-ami-text-form-heads-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4b-02b61-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b61-ami-text-form-heads-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "ami_text_form_heads_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b61.ami-text-form-heads-stage.v1"
POLICY = "sipi.p4b-02b61.ami-text-form-heads-v1.head-counts"


class AmiTextFormHeadsError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AmiTextFormHeadsError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "ami_text_form_heads_ported":
        raise AmiTextFormHeadsError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("head_spelling_counts", "raw_spelling_preserved", "empty_or_invalid_head_fail_closed")
    if any(admission.get(k) is not True for k in claimed):
        raise AmiTextFormHeadsError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 2:
        raise AmiTextFormHeadsError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn count_ami_text_form_heads_v1",
        "pub enum AmiTextFormHeadsErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise AmiTextFormHeadsError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4b-02b61-ami-text-form-heads-crosscheck-evidence.v1":
        raise AmiTextFormHeadsError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise AmiTextFormHeadsError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 4:
        raise AmiTextFormHeadsError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b61" not in plan_text:
        raise AmiTextFormHeadsError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except AmiTextFormHeadsError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
