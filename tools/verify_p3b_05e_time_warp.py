# -*- coding: utf-8 -*-
"""Fail closed on the P3B-05e time-warp shift core.

Charter fixes the deterministic per-sample linear-interpolation time-warp
scope; cross-check evidence binds product behaviour against an independent
reference. Verifier binds charter, source map, evidence, Rust tokens, PLAN
P3B-05e.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p3b-05e-time-warp-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p3b-05e-time-warp-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p3b-05e-time-warp-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-link" / "src" / "time_warp_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p3b-05e.time-warp-stage.v1"
POLICY = "sipi.p3b-05e.time-warp-shift.v1.linear-per-sample"


class TimeWarpError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TimeWarpError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "time_warp_shift_ported":
        raise TimeWarpError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("linear_interpolation_shift", "per_sample_shift_vector", "same_grid_output",
               "out_of_domain_fail_closed", "empty_length_nan_fail_closed", "deterministic_no_statistics")
    if any(admission.get(k) is not True for k in claimed):
        raise TimeWarpError("delivered_admission_drift")
    if admission.get("jitter_model") is not False or admission.get("noise_model") is not False:
        raise TimeWarpError("jitter_or_noise_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise TimeWarpError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn time_warp_shift_v1",
        "pub enum TimeWarpErrorV1",
        "OutOfDomain",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise TimeWarpError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p3b-05e.time-warp-crosscheck-evidence.v1":
        raise TimeWarpError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise TimeWarpError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise TimeWarpError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P3B-05e" not in plan_text:
        raise TimeWarpError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except TimeWarpError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
