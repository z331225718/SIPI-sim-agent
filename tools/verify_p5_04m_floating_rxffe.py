"""Fail closed on the P5-04m floating RxFFE stage port.

The charter fixes the stage scope; the source map records the MIT
function mapping; the cross-check evidence binds product and oracle
results including rejection parity. The verifier binds charter, source
map, evidence, Rust tokens, and the PLAN P5-04m row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04m-floating-rxffe-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04m-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04m-floating-rxffe-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "rx_ffe_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04m.floating-rxffe-stage.v1"
POLICY = "sipi.p5-04m.rx-ffe-v1.floating-bank-force"


class FloatingStageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FloatingStageError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "floating_rxffe_stage_ported":
        raise FloatingStageError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("equalizer_search") is not False:
        raise FloatingStageError("search_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise FloatingStageError("source_map_mapping_drift")
    if "equalizer search (search.py)" not in source_map.get("not_ported", []):
        raise FloatingStageError("source_map_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn force_floating_rx_ffe_v1",
        "pub const FLOATING_RX_FFE_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise FloatingStageError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-04m.floating-rxffe-crosscheck-evidence.v1":
        raise FloatingStageError("evidence_schema_invalid")
    if evidence.get("status") != "floating_rxffe_crosscheck_matched":
        raise FloatingStageError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 3 or any(not entry.get("matched") for entry in entries):
        raise FloatingStageError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04m" not in plan_text:
        raise FloatingStageError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except FloatingStageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
