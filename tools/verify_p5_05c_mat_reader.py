"""Fail closed on the P5-05c MATLAB v5 reader stage port.

The charter fixes the stage scope; the source map records the MIT
function mapping; the cross-check evidence binds product and oracle
grid surfaces. The verifier binds charter, source map, evidence, Rust
tokens, and the PLAN P5-05c row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-05c-mat-reader-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-05c-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-05c-mat-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "mat_reader_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-05c.mat-reader-stage.v1"
POLICY = "sipi.p5-05c.mat-reader-v1.matv5-cell-parameter"


class MatReaderStageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MatReaderStageError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "mat_reader_stage_ported":
        raise MatReaderStageError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("nested_cells") is not False:
        raise MatReaderStageError("admission_drift")
    if admission.get("parameter_dto_consumption") is not False:
        raise MatReaderStageError("dto_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise MatReaderStageError("source_map_mapping_drift")
    if "nested cell arrays" not in source_map.get("not_ported", []):
        raise MatReaderStageError("source_map_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn read_com_settings_mat_v1",
        "pub const MAT_READER_POLICY_V1",
        POLICY,
        "FLAGS_LOGICAL",
    )
    if any(token not in source for token in required_tokens):
        raise MatReaderStageError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-05c.mat-crosscheck-evidence.v1":
        raise MatReaderStageError("evidence_schema_invalid")
    if evidence.get("status") != "mat_crosscheck_matched":
        raise MatReaderStageError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 1 or not entries[0].get("matched"):
        raise MatReaderStageError("evidence_entry_mismatch")
    if entries[0].get("rows") != 3 or entries[0].get("columns") != 4:
        raise MatReaderStageError("evidence_grid_drift")
    negative = evidence.get("negative", [])
    if len(negative) != 2 or any(not entry.get("matched") for entry in negative):
        raise MatReaderStageError("evidence_negative_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-05c" not in plan_text:
        raise MatReaderStageError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except MatReaderStageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
