# -*- coding: utf-8 -*-
"""Fail closed on the P3C-02i statistical eye contour core.

Charter fixes the statistical eye contour scope; cross-check evidence binds product contour
crossings against an independent reference. Verifier binds charter, source map, evidence,
Rust tokens, PLAN P3C-02i.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p3c-02i-statistical-eye-contour-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p3c-02i-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-02i-statistical-eye-contour-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "eye_contour_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p3c-02i.statistical-eye-contour-stage.v1"
POLICY = "sipi.p3c-02i.statistical-eye-contour.v1.q-threshold-contour"


class EyeContourError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EyeContourError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "statistical_eye_contour_ported":
        raise EyeContourError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("q_threshold_contour", "linear_q_interpolation", "edge_clamping")
    if any(admission.get(k) is not True for k in claimed):
        raise EyeContourError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 2:
        raise EyeContourError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn statistical_eye_contour_v1",
        "pub struct EyeGridV1",
        "pub struct EyeContourV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise EyeContourError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p3c-02i-statistical-eye-contour-crosscheck-evidence.v1":
        raise EyeContourError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise EyeContourError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 4:
        raise EyeContourError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P3C-02i" not in plan_text:
        raise EyeContourError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except EyeContourError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
