"""Fail closed on the P5-05b CSV reader stage port.

The charter fixes the stage scope; the source map records the MIT
function mapping; the cross-check evidence binds product and oracle
grid surfaces. The verifier binds charter, source map, evidence, Rust
tokens, and the PLAN P5-05b row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-05b-csv-reader-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-05b-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-05b-csv-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "csv_reader_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-05b.csv-reader-stage.v1"
POLICY = "sipi.p5-05b.csv-reader-v1.rfc4180-utf8sig"


class CsvReaderStageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CsvReaderStageError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "csv_reader_stage_ported":
        raise CsvReaderStageError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("mat_reader") is not False:
        raise CsvReaderStageError("admission_drift")
    if admission.get("parameter_dto_consumption") is not False:
        raise CsvReaderStageError("dto_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise CsvReaderStageError("source_map_mapping_drift")
    if "ComSettings.from_mat / _matlab_cell_value" not in source_map.get("not_ported", []):
        raise CsvReaderStageError("source_map_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn read_com_settings_csv_v1",
        "pub fn csv_value_v1",
        "pub const CSV_READER_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise CsvReaderStageError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-05b.csv-crosscheck-evidence.v1":
        raise CsvReaderStageError("evidence_schema_invalid")
    if evidence.get("status") != "csv_crosscheck_matched":
        raise CsvReaderStageError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 1 or not entries[0].get("matched"):
        raise CsvReaderStageError("evidence_entry_mismatch")
    if entries[0].get("rows") != 11:
        raise CsvReaderStageError("evidence_rows_drift")
    negative = evidence.get("negative", [])
    if len(negative) != 1 or not negative[0].get("matched"):
        raise CsvReaderStageError("evidence_negative_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-05b" not in plan_text:
        raise CsvReaderStageError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except CsvReaderStageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
