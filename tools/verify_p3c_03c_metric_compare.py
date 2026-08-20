# -*- coding: utf-8 -*-
"""Fail closed on the P3C-03c profile-agnostic metric-compare engine.

Charter fixes the profile-agnostic scope and keeps the specific metric
profile (C4) out of scope. Cross-check evidence binds product allowed-error
and pass/fail against an independent reference. Verifier binds charter,
source map, evidence, Rust tokens, PLAN P3C-03c.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p3c-03c-metric-compare-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p3c-03c-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-03c-metric-compare-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-compare" / "src" / "metric_compare_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p3c-03c.metric-compare-stage.v1"
POLICY = "sipi.p3c-03c.metric-compare.v1.profile-agnostic"


class MetricCompareError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MetricCompareError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "metric_compare_engine_ported":
        raise MetricCompareError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("named_metric_compare") is not True or admission.get("profile_agnostic") is not True:
        raise MetricCompareError("profile_agnostic_admission_drift")
    if admission.get("specific_metric_profile") is not False:
        raise MetricCompareError("specific_profile_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise MetricCompareError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub struct MetricSpecV1",
        "pub struct MetricProfileV1",
        "pub fn compare_metric_profile_v1",
        "pub enum MetricCompareErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise MetricCompareError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p3c-03c.metric-compare-crosscheck-evidence.v1":
        raise MetricCompareError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise MetricCompareError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise MetricCompareError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P3C-03c" not in plan_text:
        raise MetricCompareError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except MetricCompareError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())