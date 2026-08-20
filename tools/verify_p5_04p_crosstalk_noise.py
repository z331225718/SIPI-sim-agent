"""Fail closed on the P5-04p crosstalk noise stage port.

The charter fixes the stage scope; the source map records the MIT
function mapping; the cross-check evidence binds product and oracle
results. The verifier binds charter, source map, evidence, Rust
tokens, and the PLAN P5-04p row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04p-crosstalk-noise-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04p-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04p-crosstalk-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "crosstalk_noise_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04p.crosstalk-noise-stage.v1"
POLICY = "sipi.p5-04p.crosstalk-noise-v1.fext-next-integration"


class CrosstalkStageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CrosstalkStageError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "crosstalk_noise_stage_ported":
        raise CrosstalkStageError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("candidate_evaluation") is not False:
        raise CrosstalkStageError("admission_drift")
    if admission.get("search_loop") is not False:
        raise CrosstalkStageError("search_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 3:
        raise CrosstalkStageError("source_map_mapping_drift")
    if "_evaluate_candidate / search loop" not in source_map.get("not_ported", []):
        raise CrosstalkStageError("source_map_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn crosstalk_noise_v1",
        "pub fn td_source_crosstalk_noise_v1",
        "pub struct XtalkParamsV1",
        "pub const CROSSTALK_NOISE_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise CrosstalkStageError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-04p.crosstalk-crosscheck-evidence.v1":
        raise CrosstalkStageError("evidence_schema_invalid")
    if evidence.get("status") != "crosstalk_crosscheck_matched":
        raise CrosstalkStageError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 5 or any(not entry.get("matched") for entry in entries):
        raise CrosstalkStageError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04p" not in plan_text:
        raise CrosstalkStageError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except CrosstalkStageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
