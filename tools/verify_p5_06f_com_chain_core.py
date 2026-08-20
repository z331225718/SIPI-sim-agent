# -*- coding: utf-8 -*-
"""Fail closed on the P5-06f fixed-tap COM chain composition core.

Binds the charter, source map, cross-check evidence, implementation
tokens and the PLAN P5-06f row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-06f-com-chain-core.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-06f-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06f-com-chain-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "com_chain_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-06f.com-chain-core.v1"
POLICY = "sipi.p5-06f.com-chain-v1.fixed-tap-cursor-residual-noise-metrics"


class ChainError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ChainError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "fixed_tap_chain_composition_ported":
        raise ChainError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("stages_composed", "fixed_taps_caller_supplied", "per_stage_checkpoints_reported", "fail_closed_on_stage_rejection")
    if any(admission.get(k) is not True for k in claimed):
        raise ChainError("delivered_admission_drift")
    if admission.get("product_vs_oracle_compare") is not False:
        raise ChainError("admission_overclaim")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 5 or len(source_map.get("not_ported", [])) != 5:
        raise ChainError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn run_com_chain_v1",
        "pub struct ComChainControlsV1",
        "pub struct ComChainReportV1",
        "pub const COM_CHAIN_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ChainError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-06f.com-chain-crosscheck-evidence.v1":
        raise ChainError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise ChainError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 2:
        raise ChainError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-06f" not in plan_text:
        raise ChainError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ChainError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
