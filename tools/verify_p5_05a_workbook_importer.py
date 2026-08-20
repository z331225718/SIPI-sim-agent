"""Fail closed on the P5-05a workbook importer xlsx stage port.

The charter fixes the stage scope; the source map records the MIT
function mapping; the cross-check evidence binds product and oracle
grid surfaces. The verifier binds charter, source map, evidence, Rust
tokens, and the PLAN P5-05a row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-05a-workbook-importer-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-05a-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-05a-workbook-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "workbook_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-05a.workbook-importer-stage.v1"
POLICY = "sipi.p5-05a.workbook-v1.xlsx-reader-lookup"


class WorkbookStageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WorkbookStageError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "workbook_importer_xlsx_stage_ported":
        raise WorkbookStageError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("csv_reader") is not False or admission.get("mat_reader") is not False:
        raise WorkbookStageError("admission_drift")
    if admission.get("parameter_dto_consumption") is not False:
        raise WorkbookStageError("dto_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 7:
        raise WorkbookStageError("source_map_mapping_drift")
    if "ComSettings.from_csv / _csv_value" not in source_map.get("not_ported", []):
        raise WorkbookStageError("source_map_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn validate_xlsx_container_v1",
        "pub fn is_strict_ooxml_v1",
        "pub fn read_com_settings_xlsx_v1",
        "pub struct ComSettingsV1",
        "pub struct RawCellV1",
        "pub const WORKBOOK_IMPORT_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise WorkbookStageError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-05a.workbook-crosscheck-evidence.v1":
        raise WorkbookStageError("evidence_schema_invalid")
    if evidence.get("status") != "workbook_crosscheck_matched":
        raise WorkbookStageError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 1 or not entries[0].get("matched"):
        raise WorkbookStageError("evidence_entry_mismatch")
    if entries[0].get("cell_count") != 2048:
        raise WorkbookStageError("evidence_cell_count_drift")
    negative = evidence.get("negative", [])
    if len(negative) != 2 or any(not entry.get("matched") for entry in negative):
        raise WorkbookStageError("evidence_negative_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-05a" not in plan_text:
        raise WorkbookStageError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except WorkbookStageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
