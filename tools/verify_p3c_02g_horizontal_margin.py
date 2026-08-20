# -*- coding: utf-8 -*-
"""Fail closed on the P3C-02g horizontal-margin core.

Charter fixes the margin scope and composes P3C-02f bathtub opening;
cross-check evidence binds product margins against an independent reference.
Verifier binds charter, source map, evidence, Rust tokens, PLAN P3C-02g.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p3c-02g-horizontal-margin-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p3c-02g-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-02g-horizontal-margin-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "horizontal_margin_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p3c-02g.horizontal-margin-stage.v1"
POLICY = "sipi.p3c-02g.horizontal-margin.v1.timing"


class MarginError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MarginError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "horizontal_margin_estimator_ported":
        raise MarginError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("margin_from_eye_width") is not True or admission.get("composed_bathtub_margin") is not True:
        raise MarginError("margin_admission_drift")
    if admission.get("bathtub_curve_fit") is not False or admission.get("eye_folding_bins") is not False:
        raise MarginError("curve_or_eye_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 3:
        raise MarginError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub struct HorizontalMarginsV1",
        "pub fn compute_horizontal_margins_v1",
        "pub fn margins_from_bathtub_v1",
        "pub enum HorizontalMarginErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise MarginError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p3c-02g.horizontal-margin-crosscheck-evidence.v1":
        raise MarginError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise MarginError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise MarginError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P3C-02g" not in plan_text:
        raise MarginError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except MarginError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())