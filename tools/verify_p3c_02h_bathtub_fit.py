# -*- coding: utf-8 -*-
"""Fail closed on the P3C-02h bathtub curve fit core.

Charter fixes the curve fit scope; cross-check evidence binds product fit coefficients and
residuals against an independent reference. Verifier binds charter, source map, evidence,
Rust tokens, PLAN P3C-02h.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p3c-02h-bathtub-curve-fit-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p3c-02h-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-02h-bathtub-curve-fit-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "bathtub_fit_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p3c-02h.bathtub-curve-fit-stage.v1"
POLICY = "sipi.p3c-02h.bathtub-curve-fit.v1.log-ber-poly-fit"


class BathtubFitError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BathtubFitError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "bathtub_curve_fit_ported":
        raise BathtubFitError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("log_ber_poly_fit", "gaussian_elimination", "residual_report")
    if any(admission.get(k) is not True for k in claimed):
        raise BathtubFitError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 2:
        raise BathtubFitError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn fit_bathtub_curve_v1",
        "pub struct BathtubCurveFitV1",
        "pub enum BathtubFitErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise BathtubFitError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p3c-02h-bathtub-curve-fit-crosscheck-evidence.v1":
        raise BathtubFitError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise BathtubFitError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 4:
        raise BathtubFitError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P3C-02h" not in plan_text:
        raise BathtubFitError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except BathtubFitError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
