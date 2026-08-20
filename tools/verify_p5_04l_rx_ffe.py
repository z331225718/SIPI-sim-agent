"""Fail closed on the P5-04l RX FFE stage port.

The charter fixes the stage scope; the source map records the MIT
function mapping; the cross-check evidence binds product and oracle
results. The verifier binds charter, source map, evidence, Rust
tokens, and the PLAN P5-04l row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04l-rx-ffe-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04l-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04l-rx-ffe-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "rx_ffe_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04l.rx-ffe-stage.v1"
POLICY = "sipi.p5-04l.rx-ffe-v1.apply-force-fixed"


class RxFfeStageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RxFfeStageError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "rx_ffe_fixed_stage_ported":
        raise RxFfeStageError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("floating_rxffe") is not False:
        raise RxFfeStageError("admission_drift")
    if admission.get("equalizer_search") is not False:
        raise RxFfeStageError("search_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise RxFfeStageError("source_map_mapping_drift")
    if "force_floating_rx_ffe (floating RxFFE bank branch)" not in source_map.get("not_ported", []):
        raise RxFfeStageError("source_map_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn apply_rx_ffe_v1",
        "pub fn force_rx_ffe_v1",
        "pub struct ForcedRxFfeResultV1",
        "pub const RX_FFE_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise RxFfeStageError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-04l.rx-ffe-crosscheck-evidence.v1":
        raise RxFfeStageError("evidence_schema_invalid")
    if evidence.get("status") != "rx_ffe_crosscheck_matched":
        raise RxFfeStageError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 4 or any(not entry.get("matched") for entry in entries):
        raise RxFfeStageError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04l" not in plan_text:
        raise RxFfeStageError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except RxFfeStageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
