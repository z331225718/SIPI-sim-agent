# -*- coding: utf-8 -*-
"""Fail closed on the P5-08a COM run-request admission preflight core.

Charter fixes the non-conformance request-side admission scope; cross-check
evidence binds the product admission verdict against an independent reference.
Verifier binds charter, source map, evidence, Rust tokens, PLAN P5-08a.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-08a-com-run-admission-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-08a-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-08a-com-run-admission-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "com_run_admission_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-08a.com-run-admission-stage.v1"
POLICY = "sipi.p5-08a.com-run-request.v1.admission"
REQUEST_SCHEMA = "sipi.com.run-request.v1"


class ComRunAdmissionError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ComRunAdmissionError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "com_run_admission_ported":
        raise ComRunAdmissionError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("schema_id_match", "artifact_binding_check", "non_empty_scalar_params")
    if any(admission.get(k) is not True for k in claimed):
        raise ComRunAdmissionError("delivered_admission_drift")
    if admission.get("no_com_execution") is not True or admission.get("no_conformance_admission") is not True:
        raise ComRunAdmissionError("conformance_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise ComRunAdmissionError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn com_run_admission_v1",
        "pub enum ComRunAdmissionErrorV1",
        "COM_RUN_REQUEST_SCHEMA_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ComRunAdmissionError("implementation_binding_drift")
    if REQUEST_SCHEMA not in source:
        raise ComRunAdmissionError("request_schema_constant_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-08a.com-run-admission-crosscheck-evidence.v1":
        raise ComRunAdmissionError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise ComRunAdmissionError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise ComRunAdmissionError("evidence_entry_mismatch")
    admitted = [e for e in evidence["entries"] if e.get("admitting")]
    rejected = [e for e in evidence["entries"] if not e.get("admitting", False) and e.get("product_ok")]
    hard = [e for e in evidence["entries"] if not e.get("product_ok")]
    if not admitted or not rejected or not hard:
        raise ComRunAdmissionError("evidence_not_exercising_all_paths")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-08a" not in plan_text:
        raise ComRunAdmissionError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ComRunAdmissionError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
