"""Fail closed on the P5-04r C2M vertical-eye stage port.

The charter fixes the stage scope; the source map records the MIT function
mapping; the cross-check evidence binds product and oracle results. The
verifier binds charter, source map, evidence, Rust tokens, and the PLAN
P5-04r row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04r-c2m-eye-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04r-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04r-c2m-eye-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "c2m_eye_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04r.c2m-eye-stage.v1"
POLICY = "sipi.p5-04r.c2m-vertical-eye.v1.signal-pdf-reduction"


class C2mEyeError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise C2mEyeError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "c2m_eye_stage_ported":
        raise C2mEyeError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("candidate_evaluation") is not False:
        raise C2mEyeError("admission_drift")
    if admission.get("search_loop") is not False:
        raise C2mEyeError("search_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 10:
        raise C2mEyeError("source_map_mapping_drift")
    if "calculate_c2m_eye (full-contour public eye)" not in source_map.get("not_ported", []):
        raise C2mEyeError("source_map_not_ported_drift")
    if "_evaluate_candidate" not in source_map.get("not_ported", []):
        raise C2mEyeError("source_map_eval_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn calculate_c2m_vertical_eye_v1",
        "pub enum C2mEyeErrorV1",
        "pub const C2M_EYE_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise C2mEyeError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-04r.c2m-eye-crosscheck-evidence.v1":
        raise C2mEyeError("evidence_schema_invalid")
    if evidence.get("status") != "c2m_eye_crosscheck_matched":
        raise C2mEyeError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 4 or any(not entry.get("matched") for entry in entries):
        raise C2mEyeError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04r" not in plan_text:
        raise C2mEyeError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except C2mEyeError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
