"""Fail closed on the P5-04q candidate-helper stage port.

The charter fixes the stage scope; the source map records the MIT
function mapping; the cross-check evidence binds product and oracle
results. The verifier binds charter, source map, evidence, Rust
tokens, and the PLAN P5-04q row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04q-candidate-helpers-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04q-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04q-candidate-helpers-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "candidate_helpers_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04q.candidate-helpers-stage.v1"
POLICY = "sipi.p5-04q.candidate-helpers-v1.reject-bounds-jitter"


class CandidateHelpersError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CandidateHelpersError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "candidate_helpers_stage_ported":
        raise CandidateHelpersError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("candidate_evaluation") is not False:
        raise CandidateHelpersError("admission_drift")
    if admission.get("search_loop") is not False:
        raise CandidateHelpersError("search_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 7:
        raise CandidateHelpersError("source_map_mapping_drift")
    if "_evaluate_candidate" not in source_map.get("not_ported", []):
        raise CandidateHelpersError("source_map_not_ported_drift")
    if "search_r480_nonmmse_no_xtalk / search loop" not in source_map.get("not_ported", []):
        raise CandidateHelpersError("source_map_search_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn r480_pdf_bin_size_v1",
        "pub fn r480_bbn_q_factor_v1",
        "pub fn cannot_improve_fom_v1",
        "pub fn candidate_ber_q_v1",
        "pub fn dfe_candidate_bounds_v1",
        "pub fn jitter_response_v1",
        "pub fn jitter_sigma_v1",
        "pub struct DfeCandidateParamsV1",
        "pub enum CandidateErrorV1",
        "pub const CANDIDATE_HELPERS_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise CandidateHelpersError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-04q.candidate-helpers-crosscheck-evidence.v1":
        raise CandidateHelpersError("evidence_schema_invalid")
    if evidence.get("status") != "candidate_helpers_crosscheck_matched":
        raise CandidateHelpersError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 16 or any(not entry.get("matched") for entry in entries):
        raise CandidateHelpersError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04q" not in plan_text:
        raise CandidateHelpersError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except CandidateHelpersError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
