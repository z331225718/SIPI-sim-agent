"""Fail closed on the P5-04n search support stage port.

The charter fixes the stage scope; the source map records the MIT
function mapping; the cross-check evidence binds product and oracle
results. The verifier binds charter, source map, evidence, Rust
tokens, and the PLAN P5-04n row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04n-search-support-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04n-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04n-search-support-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "search_support_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04n.search-support-stage.v1"
POLICY = "sipi.p5-04n.search-support-v1.params-frequency-candidates"


class SearchSupportStageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SearchSupportStageError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "search_support_stage_ported":
        raise SearchSupportStageError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("receiver_noise") is not False or admission.get("crosstalk_noise") is not False:
        raise SearchSupportStageError("admission_drift")
    if admission.get("search_loop") is not False:
        raise SearchSupportStageError("search_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 7:
        raise SearchSupportStageError("source_map_mapping_drift")
    if "_receiver_noise (bessel/butterworth/raised-cosine chain)" not in source_map.get("not_ported", []):
        raise SearchSupportStageError("source_map_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn indexed_config_value_v1",
        "pub fn qualified_ctle_pair_v1",
        "pub fn ctle_frequency_response_v1",
        "pub fn apply_ctle_candidate_v1",
        "pub struct CtleParamsV1",
        "pub const SEARCH_SUPPORT_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise SearchSupportStageError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-04n.search-support-crosscheck-evidence.v1":
        raise SearchSupportStageError("evidence_schema_invalid")
    if evidence.get("status") != "search_support_crosscheck_matched":
        raise SearchSupportStageError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 19 or any(not entry.get("matched") for entry in entries):
        raise SearchSupportStageError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04n" not in plan_text:
        raise SearchSupportStageError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except SearchSupportStageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
