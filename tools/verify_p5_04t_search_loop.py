"""Fail closed on the P5-04t search-loop support stage port.

The charter fixes the stage scope; the source map records the MIT function
mapping; the cross-check evidence binds product and oracle results. The
verifier binds charter, source map, evidence, Rust tokens, and the PLAN
P5-04t row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04t-search-loop-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04t-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04t-search-loop-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "search_loop_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04t.search-loop-stage.v1"
POLICY = "sipi.p5-04t.search-loop.v1.nonmmse-no-rxffe"


class SearchLoopError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SearchLoopError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "search_loop_stage_ported":
        raise SearchLoopError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("candidate_evaluation") is not True:
        raise SearchLoopError("admission_candidate_should_be_true")
    if admission.get("search_loop") is not False:
        raise SearchLoopError("search_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 12:
        raise SearchLoopError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn rectangular_pulse_response_v1",
        "pub fn peak_window",
        "pub fn shift_matrix",
        "pub fn r480_sample_offsets",
        "pub fn skip_local_search",
        "pub fn anchored_cursor",
        "pub fn search_r480_nonmmse_no_xtalk_v1",
        "pub const SEARCH_LOOP_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise SearchLoopError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-04t.search-loop-crosscheck-evidence.v1":
        raise SearchLoopError("evidence_schema_invalid")
    if evidence.get("status") != "search_loop_support_crosscheck_matched":
        raise SearchLoopError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) < 18 or any(not entry.get("matched") for entry in entries):
        raise SearchLoopError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04t" not in plan_text:
        raise SearchLoopError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except SearchLoopError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
