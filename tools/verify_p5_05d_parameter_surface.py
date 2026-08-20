"""Fail closed on the P5-05d parameter surface report stage port.

The charter fixes the report scope; the source map records the MIT
mapping plus the canonical observation; the cross-check evidence binds
product and oracle pair surfaces. The verifier binds charter, source
map, evidence, Rust tokens, and the PLAN P5-05d row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-05d-parameter-surface-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-05d-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-05d-surface-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "parameter_surface_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-05d.parameter-surface-stage.v1"
POLICY = "sipi.p5-05d.parameter-surface-v1.key-extract-classify"


class SurfaceStageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SurfaceStageError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "parameter_surface_report_stage_ported":
        raise SurfaceStageError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("value_consumption") is not False:
        raise SurfaceStageError("admission_drift")
    if admission.get("behavior_profile") is not False:
        raise SurfaceStageError("profile_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 3:
        raise SurfaceStageError("source_map_mapping_drift")
    if "value consumption / default resolution (P5-02 consumption surface)" not in source_map.get("not_ported", []):
        raise SurfaceStageError("source_map_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn extract_parameter_pairs_v1",
        "pub fn classify_parameter_surface_v1",
        "pub struct ParameterSurfaceReportV1",
        "pub const PARAMETER_SURFACE_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise SurfaceStageError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-05d.surface-crosscheck-evidence.v1":
        raise SurfaceStageError("evidence_schema_invalid")
    if evidence.get("status") != "surface_crosscheck_matched":
        raise SurfaceStageError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 3 or any(not entry.get("matched") for entry in entries):
        raise SurfaceStageError("evidence_entry_mismatch")
    xlsx = next(entry for entry in entries if entry.get("id") == "xlsx_authorized_config")
    if xlsx.get("pairs") != 137 or xlsx.get("consumed") != 82 or xlsx.get("unconsumed") != 41:
        raise SurfaceStageError("evidence_xlsx_surface_drift")
    canonical = evidence.get("canonical", {})
    if canonical.get("key_count") != 214:
        raise SurfaceStageError("evidence_canonical_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-05d" not in plan_text:
        raise SurfaceStageError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except SurfaceStageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
