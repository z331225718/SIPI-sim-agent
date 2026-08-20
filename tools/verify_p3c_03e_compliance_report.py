# -*- coding: utf-8 -*-
"""Fail closed on the P3C-03e compliance report core.

Charter fixes the profile-agnostic compare-report scope; cross-check evidence
binds product reports against an independent reference. Verifier binds charter,
source map, evidence, Rust tokens, PLAN P3C-03e.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p3c-03e-compliance-report-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p3c-03e-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-03e-compliance-report-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "compliance_report_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p3c-03e.compliance-report-stage.v1"
POLICY = "sipi.p3c-03e.compliance-report.v1.profile"


class ComplianceReportError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ComplianceReportError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "compliance_report_ported":
        raise ComplianceReportError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("per_metric_verdict") is not True or admission.get("overall_pass") is not True:
        raise ComplianceReportError("report_admission_drift")
    if admission.get("specific_metric_profile") is not False or admission.get("behavior_profile") is not False:
        raise ComplianceReportError("profile_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 3:
        raise ComplianceReportError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn compliance_report_v1",
        "pub struct MetricComplianceV1",
        "pub struct ComplianceReportV1",
        "pub enum ComplianceErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ComplianceReportError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p3c-03e.compliance-report-crosscheck-evidence.v1":
        raise ComplianceReportError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise ComplianceReportError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise ComplianceReportError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P3C-03e" not in plan_text:
        raise ComplianceReportError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ComplianceReportError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())