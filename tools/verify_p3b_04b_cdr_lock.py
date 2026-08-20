# -*- coding: utf-8 -*-
"""Fail closed on the P3B-04b CDR lock semantics core.

Charter fixes the CDR lock semantics scope; cross-check evidence binds product lock tracking
against an independent reference. Verifier binds charter, source map, evidence, Rust tokens,
PLAN P3B-04b.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p3b-04b-cdr-lock-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p3b-04b-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p3b-04b-cdr-lock-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-channel" / "src" / "cdr_lock_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p3b-04b.cdr-lock-stage.v1"
POLICY = "sipi.p3b-04b.cdr-lock.v1.acquisition-hysteresis"


class CdrLockError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CdrLockError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "cdr_lock_semantics_ported":
        raise CdrLockError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    claimed = ("hysteresis_lock_machine", "reset_cancel_semantics", "per_sample_records")
    if any(admission.get(k) is not True for k in claimed):
        raise CdrLockError("delivered_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 2:
        raise CdrLockError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn track_cdr_lock_v1",
        "pub struct CdrLockTrackerV1",
        "pub enum CdrLockStateV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise CdrLockError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p3b-04b-cdr-lock-crosscheck-evidence.v1":
        raise CdrLockError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise CdrLockError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count") or evidence.get("case_count") != 4:
        raise CdrLockError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P3B-04b" not in plan_text:
        raise CdrLockError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except CdrLockError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
