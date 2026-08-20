# -*- coding: utf-8 -*-
"""Fail closed on the P3C-04y C4-vs-oracle compare slice.

Charter fixes the end-to-end P3C-03 compare against bound MATLAB oracle
references; cross-check evidence binds the product compare (compare engine
over the C4 profile + per-case references and per-case candidates) to
an independent reference. Verifier binds charter, source map, evidence,
PLAN P3C-04y.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p3c-04y-c4-oracle-compare-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p3c-04y-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-04y-c4-oracle-compare-crosscheck-evidence.v1.yaml"
ORACLE_REF = ROOT / "docs" / "baselines" / "p5-06e-com-oracle-metric-reference.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p3c-04y.c4-oracle-compare-stage.v1"
POLICY = "sipi.p3c-03c.c4-profile.v1.com-icn-erl-1pct"


class C4OracleCompareError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise C4OracleCompareError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "c4_oracle_compare_ported":
        raise C4OracleCompareError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("c4_oracle_reference_bound", "compare_engine_end_to_end", "case_level_compare", "fail_closed_on_mismatch", "profile_compare_execution")
    if any(admission.get(k) is not True for k in claimed):
        raise C4OracleCompareError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise C4OracleCompareError("source_map_mapping_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p3c-04y.c4-oracle-compare-crosscheck-evidence.v1":
        raise C4OracleCompareError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise C4OracleCompareError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 2:
        raise C4OracleCompareError("evidence_entry_mismatch")
    # Both cases must pass against their per-case C4 references.
    by_label = {e["label"]: e for e in evidence["entries"]}
    c1 = by_label.get("case_1")
    c2 = by_label.get("case_2")
    if not c1 or not c2:
        raise C4OracleCompareError("evidence_cases_missing")
    if not (c1["product_passed"] and c1["reference_passed"]):
        raise C4OracleCompareError("case1_pass_drift")
    if not (c2["product_passed"] and c2["reference_passed"]):
        raise C4OracleCompareError("case2_pass_drift")
    c2_map = {x["name"]: x for x in c2["product_results"]}
    if not (c2_map["COM_dB"]["passed"] is True and c2_map["ICN_mV"]["passed"] is True and c2_map["ERL"]["passed"] is True):
        raise C4OracleCompareError("case2_metric_distribution_drift")
    oracle = load_yaml(ORACLE_REF)
    agg = oracle.get("aggregate_reference", {})
    for k in ("COM_dB", "ICN_mV", "ERL"):
        if k not in agg:
            raise C4OracleCompareError("oracle_reference_missing_metric")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P3C-04y" not in plan_text:
        raise C4OracleCompareError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except C4OracleCompareError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())