# -*- coding: utf-8 -*-
"""Fail closed on the P3C-02e Q-factor/BER estimator core.

Charter fixes the estimator scope (Q-factor method, 0.1 dB tolerance),
keeps eye-fold/bathtub-curve output; the cross-check evidence binds
product conversions to scipy. Verifier binds charter, source map,
evidence, Rust tokens, PLAN P3C-02e.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p3c-02e-qfactor-ber-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p3c-02e-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-02e-qfactor-ber-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "qfactor_ber_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p3c-02e.qfactor-ber-stage.v1"
POLICY = "sipi.p3c-02e.qfactor-ber.v1.estimator"


class QFactorBerError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QFactorBerError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "qfactor_ber_estimator_ported":
        raise QFactorBerError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("q_bounds_ber_conversion") is not True or admission.get("tolerance_0p1db_recorded") is not True:
        raise QFactorBerError("q_admission_drift")
    if admission.get("eye_folding_bins") is not False or admission.get("bathtub_curve_fit") is not False:
        raise QFactorBerError("eye_or_bathtub_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise QFactorBerError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn q_factor_to_ber_v1",
        "pub fn ber_to_q_factor_v1",
        "pub fn estimate_q_factor_v1",
        "pub enum QFactorBerErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise QFactorBerError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p3c-02e.qfactor-ber-crosscheck-evidence.v1":
        raise QFactorBerError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise QFactorBerError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise QFactorBerError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P3C-02e" not in plan_text:
        raise QFactorBerError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except QFactorBerError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())