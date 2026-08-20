# -*- coding: utf-8 -*-
"""Fail closed on the P5-02m deterministic warning detector core.

Charter fixes the mechanical-warning scope (keeps the full oracle warning
contract out); cross-check evidence binds product detectors against an
independent reference. Verifier binds charter, source map, evidence, Rust
tokens, PLAN P5-02m.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-02m-warning-detector-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-02m-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-02m-warning-detector-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "warning_detector_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-02m.warning-detector-stage.v1"
POLICY = "sipi.p5-02m.warning-detector.v1.deterministic"


class WarningDetectorError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WarningDetectorError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "deterministic_warning_detector_ported":
        raise WarningDetectorError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("anti_causal_precursor_fraction") is not True or admission.get("high_freq_non_decay") is not True:
        raise WarningDetectorError("detector_admission_drift")
    if admission.get("full_warning_contract") is not False or admission.get("behavior_profile") is not False:
        raise WarningDetectorError("contract_or_profile_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 3:
        raise WarningDetectorError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn anti_causal_precursor_fraction_v1",
        "pub fn detect_anti_causal_v1",
        "pub fn detect_high_freq_non_decay_v1",
        "pub enum WarningDetectorErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise WarningDetectorError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-02m.warning-detector-crosscheck-evidence.v1":
        raise WarningDetectorError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise WarningDetectorError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise WarningDetectorError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-02m" not in plan_text:
        raise WarningDetectorError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except WarningDetectorError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())