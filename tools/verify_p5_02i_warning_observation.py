"""Fail closed on the P5-02i warning-call observation.

The observation records every warning / fprintf-strong / msgbox-warning
call in the authorized MATLAB r4.80 source, hash-bound to the registry.
The verifier binds count, source hash, and the PLAN P5-02i row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
OBSERVATION = ROOT / "docs" / "baselines" / "p5-r480-warning-observation.v1.yaml"
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-02.warning-observation.v1"
MATLAB_ID = "com-r480-matlab-source"
WARNING_COUNT = 25


class WarningObservationError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WarningObservationError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    observation = load_yaml(OBSERVATION)
    if observation.get("schema") != SCHEMA or observation.get("status") != "warning_calls_observed_hash_bound":
        raise WarningObservationError("observation_schema_or_status_invalid")
    if observation.get("warning_call_count") != WARNING_COUNT:
        raise WarningObservationError("warning_count_drift")
    registry = load_yaml(REGISTRY)
    material = next((m for m in registry.get("materials", []) if m.get("id") == MATLAB_ID), None)
    if material is None or observation.get("source_sha256") != material.get("sha256", "").lower():
        raise WarningObservationError("source_hash_drift")
    warnings = observation.get("warnings")
    if not isinstance(warnings, list) or len(warnings) != WARNING_COUNT:
        raise WarningObservationError("warnings_drift")
    for warning in warnings:
        if not isinstance(warning.get("line"), int) or not warning.get("message") or warning.get("kind") not in ("warning", "fprintf_strong", "msgbox_warning"):
            raise WarningObservationError("warning_entry_invalid")
    claims = observation.get("non_claims")
    expected = ["not_a_product_warning_contract", "not_warning_conditions_derived", "not_release_evidence"]
    if not isinstance(claims, list) or claims != expected:
        raise WarningObservationError("non_claims_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-02i" not in plan_text:
        raise WarningObservationError("plan_row_missing")
    return {"valid": True, "warnings": WARNING_COUNT}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except WarningObservationError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
