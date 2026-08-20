# -*- coding: utf-8 -*-
"""Fail closed on the P3C-03 C4 owner metric-profile definition core.

Charter fixes the C4 COM metric-profile scope (COM_dB / ICN_mV / ERL, < 1%
relative tolerance, caller-supplied finite reference); cross-check evidence
binds the product C4 profile to an independent reference. Verifier binds
charter, source map, evidence, Rust tokens, PLAN P3C-04x (C4 profile).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p3c-04x-c4-profile-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p3c-04x-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-04x-c4-profile-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-compare" / "src" / "c4_metric_profile_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p3c-04x.c4-profile-stage.v1"
POLICY = "sipi.p3c-03c.c4-profile.v1.com-icn-erl-1pct"
C4_TOLERANCE = 0.01


class C4ProfileError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise C4ProfileError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "c4_metric_profile_ported":
        raise C4ProfileError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("c4_metric_set", "one_percent_relative_tolerance", "reference_caller_supplied",
               "missing_nonfinite_reference_fail_closed", "compare_engine_compatible")
    if any(admission.get(k) is not True for k in claimed):
        raise C4ProfileError("delivered_admission_drift")
    if admission.get("reference_from_oracle") is not False:
        raise C4ProfileError("hardcoded_reference_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise C4ProfileError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub const C4_METRICS",
        "pub const C4_RELATIVE_TOLERANCE_V1",
        "pub fn c4_metric_specs_v1",
        "C4ProfileErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise C4ProfileError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p3c-04x.c4-profile-crosscheck-evidence.v1":
        raise C4ProfileError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise C4ProfileError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise C4ProfileError("evidence_entry_mismatch")
    happy = [e for e in evidence["entries"] if e.get("product_ok") and e["reference_ok"]]
    failure = [e for e in evidence["entries"] if not e.get("product_ok") and not e["reference_ok"]]
    if not happy or not failure:
        raise C4ProfileError("evidence_not_exercising_both_paths")
    full = [e for e in happy if e["label"] == "full_references"]
    if not full:
        raise C4ProfileError("full_profile_case_missing")
    names = [s["name"] for s in full[0]["product_specs"]]
    if names != ["COM_dB", "ICN_mV", "ERL"]:
        raise C4ProfileError("c4_metric_order_drift")
    if any(s["relative_tolerance"] != C4_TOLERANCE for s in full[0]["product_specs"]):
        raise C4ProfileError("tolerance_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P3C-04x" not in plan_text:
        raise C4ProfileError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except C4ProfileError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
