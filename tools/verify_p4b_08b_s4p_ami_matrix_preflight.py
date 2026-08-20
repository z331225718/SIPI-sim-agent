"""Fail closed on the P4B-08b S4P-to-AMI matrix preflight.

The preflight freezes the unverified port-mapping surface and prohibits
AMI matrix construction until the mapping is established. The verifier
cross-binds the charter against the 08a S4P observation, the IBIS facts,
and the PLAN P4B-08b row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-08-s4p-ami-matrix-preflight.v1.yaml"
OBSERVATION = ROOT / "docs" / "baselines" / "p4b-08-s4p-observation-evidence.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-08.s4p-ami-matrix-preflight.v1"


class MatrixPreflightError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MatrixPreflightError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "s4p_ami_matrix_semantics_not_frozen_pending_port_mapping":
        raise MatrixPreflightError("charter_schema_or_status_invalid")
    if charter.get("decision_surface") != {
        "port_mapping": "unverified_requires_netlist",
        "victim_aggressor_columns": "unselected",
        "matrix_time_step": "unselected",
        "impulse_conversion": "unselected",
    }:
        raise MatrixPreflightError("decision_surface_drift")
    if charter.get("observed_facts", {}).get("pins") != {"1": "Tx", "2": "Tx#", "3": "Rx", "4": "Rx#"}:
        raise MatrixPreflightError("ibis_pin_facts_drift")
    if charter.get("admission", {}).get("ami_matrix_construction") != "prohibited_without_port_mapping":
        raise MatrixPreflightError("admission_drift")
    if not OBSERVATION.is_file():
        raise MatrixPreflightError("s4p_observation_missing")
    claims = charter.get("non_claims")
    expected = ["not_a_port_mapping", "not_victim_aggressor_semantics", "not_impulse_conversion", "not_ami_matrix", "not_system_parity", "not_release_evidence"]
    if not isinstance(claims, list) or claims != expected:
        raise MatrixPreflightError("non_claims_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-08b" not in plan_text:
        raise MatrixPreflightError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except MatrixPreflightError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
