"""Fail closed on the P5-04j TX FFE grid stage port.

The charter fixes the stage scope; the source map records the MIT
function mapping; the cross-check evidence binds product and oracle
grid surfaces. The verifier binds charter, source map, evidence, Rust
tokens, and the PLAN P5-04j row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04j-tx-ffe-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04j-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04j-tx-ffe-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "tx_ffe_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04j.tx-ffe-stage.v1"
POLICY = "sipi.p5-04j.tx-ffe-v1.grid-build-reduce"


class TxFfeStageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TxFfeStageError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "tx_ffe_grid_stage_ported":
        raise TxFfeStageError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("dfe_bank") is not False or admission.get("rx_ffe") is not False:
        raise TxFfeStageError("admission_drift")
    if admission.get("equalizer_search") is not False:
        raise TxFfeStageError("search_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 5:
        raise TxFfeStageError("source_map_mapping_drift")
    if "DFE bank (dfe.py)" not in source_map.get("not_ported", []):
        raise TxFfeStageError("source_map_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn full_grid_matrix_v1",
        "pub fn build_txffe_grid_v1",
        "pub fn first_strict_best_v1",
        "pub fn select_fom_tracker_v1",
        "pub struct TxFfeGridV1",
        "pub const TX_FFE_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise TxFfeStageError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-04j.tx-ffe-crosscheck-evidence.v1":
        raise TxFfeStageError("evidence_schema_invalid")
    if evidence.get("status") != "tx_ffe_crosscheck_matched":
        raise TxFfeStageError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 7 or any(not entry.get("matched") for entry in entries):
        raise TxFfeStageError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04j" not in plan_text:
        raise TxFfeStageError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except TxFfeStageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
