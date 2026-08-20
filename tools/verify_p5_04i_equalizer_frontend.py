"""Fail closed on the P5-04i equalizer front-end stage port.

The charter fixes the stage scope; the source map records the MIT
function mapping; the cross-check evidence binds product and oracle
results. The verifier binds charter, source map, evidence, Rust
tokens, and the PLAN P5-04i row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04i-equalizer-frontend-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04i-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04i-frontend-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "equalizer_frontend_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04i.equalizer-frontend-stage.v1"
POLICY = "sipi.p5-04i.equalizer-frontend-v1.cursor-ctle"


class FrontendStageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FrontendStageError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "equalizer_frontend_stage_ported":
        raise FrontendStageError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("tx_ffe_grid") is not False or admission.get("dfe_bank") is not False:
        raise FrontendStageError("admission_drift")
    if admission.get("equalizer_search") is not False:
        raise FrontendStageError("search_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise FrontendStageError("source_map_mapping_drift")
    if "tx_ffe grid (tx_ffe.py)" not in source_map.get("not_ported", []):
        raise FrontendStageError("source_map_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn cursor_sample_index_v1",
        "pub fn fd_ctle_v1",
        "pub fn td_ctle_v1",
        "pub struct CursorSampleV1",
        "pub const EQUALIZER_FRONTEND_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise FrontendStageError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-04i.frontend-crosscheck-evidence.v1":
        raise FrontendStageError("evidence_schema_invalid")
    if evidence.get("status") != "frontend_crosscheck_matched":
        raise FrontendStageError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 7 or any(not entry.get("matched") for entry in entries):
        raise FrontendStageError("evidence_entry_mismatch")
    kinds = {entry.get("kind") for entry in entries}
    if kinds != {"cursor", "fd_ctle", "td_ctle"}:
        raise FrontendStageError("evidence_kind_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04i" not in plan_text:
        raise FrontendStageError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except FrontendStageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
