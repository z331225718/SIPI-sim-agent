# -*- coding: utf-8 -*-
"""Fail closed on the P5-04x search-loop helpers cross-check.

Charter fixes the three helper semantics and the explicit-cross-check
scope; evidence binds product helpers against independent references.
Verifier binds charter, source map, evidence, Rust tokens, PLAN P5-04x.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04x-search-helpers-verification.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04x-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04t-search-helpers-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "search_loop_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04x.search-helpers-verification.v1"
POLICY = "sipi.p5-04t.search-loop.v1.nonmmse-no-rxffe"


class SearchHelpersError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SearchHelpersError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "search_loop_helpers_crosschecked":
        raise SearchHelpersError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("rectangular_pulse_running_sum") is not True or admission.get("shift_matrix_roll") is not True:
        raise SearchHelpersError("helper_admission_drift")
    if admission.get("behavior_profile") is not False:
        raise SearchHelpersError("profile_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 3:
        raise SearchHelpersError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn rectangular_pulse_response_v1",
        "pub fn peak_window",
        "pub fn shift_matrix",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise SearchHelpersError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-04x.search-helpers-crosscheck-evidence.v1":
        raise SearchHelpersError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise SearchHelpersError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 1 or not entries[0].get("matched"):
        raise SearchHelpersError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04x" not in plan_text:
        raise SearchHelpersError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except SearchHelpersError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())