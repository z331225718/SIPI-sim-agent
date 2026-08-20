# -*- coding: utf-8 -*-
"""Fail closed on the P5-06g product COM chain oracle-checkpoint compare slice.

Charter fixes the execution of product COM chain + C4 profile compare against
bound MATLAB oracle references; cross-check evidence binds the product execution
to an independent Python reference. Verifier binds charter, source map, evidence,
PLAN P5-06g.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-06g-oracle-chain-compare-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-06g-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06g-oracle-chain-compare-crosscheck-evidence.v1.yaml"
ORACLE_REF = ROOT / "docs" / "baselines" / "p5-06e-com-oracle-metric-reference.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-06g.oracle-chain-compare-stage.v1"


class OracleChainCompareError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise OracleChainCompareError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "oracle_chain_compare_ported":
        raise OracleChainCompareError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("product_com_chain_invoked", "oracle_checkpoint_parameters_fed", "c4_profile_compare_executed", "fail_closed_on_mismatch")
    if any(admission.get(k) is not True for k in claimed):
        raise OracleChainCompareError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise OracleChainCompareError("source_map_mapping_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-06g.oracle-chain-compare-crosscheck-evidence.v1":
        raise OracleChainCompareError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise OracleChainCompareError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 2:
        raise OracleChainCompareError("evidence_entry_mismatch")
    oracle = load_yaml(ORACLE_REF)
    agg = oracle.get("aggregate_reference", {})
    for k in ("COM_dB", "ICN_mV", "ERL"):
        if k not in agg:
            raise OracleChainCompareError("oracle_reference_missing_metric")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-06g" not in plan_text:
        raise OracleChainCompareError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except OracleChainCompareError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
