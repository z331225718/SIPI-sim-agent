# -*- coding: utf-8 -*-
"""Fail closed on the P4A-03k typed IBIS series switch groups core.

Charter fixes the series switch groups scope; cross-check evidence binds product
lifting against an independent reference. Verifier binds charter, source map,
evidence, Rust tokens, PLAN P4A-03k.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4a-03k-series-switch-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p4a-03k-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03k-series-switch-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ibis" / "src" / "series_switch_groups_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4a-03k.series-switch-stage.v1"
POLICY = "sipi.p4a-03k.series-switch-groups-v1.typed-switch-groups"


class SeriesSwitchError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SeriesSwitchError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "series_switch_groups_ported":
        raise SeriesSwitchError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("typed_series_switch_groups_declaration", "state_models_validation",
               "ascii_group_name_validation", "fail_closed_on_invalid_input")
    if any(admission.get(k) is not True for k in claimed):
        raise SeriesSwitchError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise SeriesSwitchError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn lift_series_switch_group_v1",
        "pub struct TypedSeriesSwitchGroupV1",
        "SeriesSwitchGroupsErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise SeriesSwitchError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p4a-03k.series-switch-crosscheck-evidence.v1":
        raise SeriesSwitchError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise SeriesSwitchError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 3:
        raise SeriesSwitchError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4A-03k" not in plan_text:
        raise SeriesSwitchError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except SeriesSwitchError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
