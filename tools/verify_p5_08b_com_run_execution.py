# -*- coding: utf-8 -*-
"""Fail closed on the P5-08b COM run execution and result envelope core.

Charter fixes the COM run execution scope; cross-check evidence binds product
execution against an independent reference. Verifier binds charter, source map,
evidence, Rust tokens, PLAN P5-08b.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-08b-com-run-execution-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-08b-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-08b-com-run-execution-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "com_run_execution_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-08b.com-run-execution-stage.v1"
POLICY = "sipi.p5-08b.com-run-execution-v1.admission-to-result"


class ComRunExecutionError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ComRunExecutionError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "com_run_execution_ported":
        raise ComRunExecutionError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("com_run_execution_pipeline", "result_envelope_formatting",
               "unadmitted_request_handling", "fail_closed_on_execution_error")
    if any(admission.get(k) is not True for k in claimed):
        raise ComRunExecutionError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise ComRunExecutionError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn execute_com_run_v1",
        "pub struct ComRunResultEnvelopeV1",
        "COM_RUN_RESULT_SCHEMA_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ComRunExecutionError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-08b.com-run-execution-crosscheck-evidence.v1":
        raise ComRunExecutionError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise ComRunExecutionError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 3:
        raise ComRunExecutionError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-08b" not in plan_text:
        raise ComRunExecutionError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ComRunExecutionError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
