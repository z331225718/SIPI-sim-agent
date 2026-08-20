# -*- coding: utf-8 -*-
"""Fail closed on the P5-02n deterministic warning-report aggregator.

Charter fixes the profile-agnostic aggregation scope; cross-check evidence
binds the product aggregated warning report against an independent reference.
Verifier binds charter, source map, evidence, Rust tokens, PLAN P5-02n.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-02n-warning-report-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-02n-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-02n-warning-report-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "warning_report_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-02n.warning-report-stage.v1"
POLICY = "sipi.p5-02n.warning-report.v1.aggregate"


class WarningReportError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WarningReportError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "warning_report_ported":
        raise WarningReportError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("sorted_active_code_union", "per_code_slice_listing", "flagged_total_count",
               "empty_input_fail_closed", "empty_slice_name_fail_closed")
    if any(admission.get(k) is not True for k in claimed):
        raise WarningReportError("delivered_admission_drift")
    if admission.get("mlse_der_cdr_contract") is not False:
        raise WarningReportError("full_contract_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 5:
        raise WarningReportError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn aggregate_warning_report_v1",
        "pub enum WarningReportErrorV1",
        "WarningCodeV1",
        "EmptySliceName",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise WarningReportError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-02n.warning-report-crosscheck-evidence.v1":
        raise WarningReportError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise WarningReportError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise WarningReportError("evidence_entry_mismatch")
    happy = [e for e in evidence["entries"] if e.get("product_ok") and e["reference_ok"]]
    failure = [e for e in evidence["entries"] if not e.get("product_ok") and not e["reference_ok"]]
    if not happy or not failure:
        raise WarningReportError("evidence_not_exercising_both_paths")
    union = [e for e in happy if e["label"] == "union_sorted"]
    if not union or union[0]["product_active"] != ["anti_causal", "high_freq_non_decay"]:
        raise WarningReportError("union_ordering_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-02n" not in plan_text:
        raise WarningReportError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except WarningReportError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
