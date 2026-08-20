"""Verify P2-04 TRAN semantic freeze completeness (fixed-profile surface).

P2-04 requires fixing time integration, initial condition, tolerance,
step control, output sampling, and measurement semantics. For the
current fixed-profile surface all six are frozen: P2-03 freeze records
integrator/initial/step/sampling/measurement semantics, and the
tran-rc-pulse acceptance contract fixes the concrete tolerances
(time 1e-15, v(in) 1e-9/1e-9, v(out) 2e-6/5e-4, index-aligned, explicit
IC). This gate fails closed if any of those frozen constants drift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p2-04.semantic-freeze-complete.v1"

FREEZE = "docs/baselines/p2-03-tran-semantic-freeze.v1.yaml"
ACCEPTANCE = "docs/baselines/tran-rc-pulse-acceptance.v1.yaml"

EXPECTED_TOLERANCES = {
    "time": {"absolute_tolerance_seconds": 1.0e-15, "relative_tolerance": 0.0},
    "voltage_in": {"absolute_tolerance_volts": 1.0e-9, "relative_tolerance": 1.0e-9},
    "voltage_out": {"absolute_tolerance_volts": 2.0e-6, "relative_tolerance": 5.0e-4},
}


class FreezeCompleteError(RuntimeError):
    pass


def load_yaml(relative: str) -> dict[str, Any]:
    if yaml is None:
        raise FreezeCompleteError("pyyaml_unavailable")
    value = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FreezeCompleteError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    for relative in (FREEZE, ACCEPTANCE):
        if not (root / relative).is_file():
            raise FreezeCompleteError(f"file_missing:{relative}")

    freeze = load_yaml(FREEZE)
    if freeze.get("schema") != "sipi.p2-03.tran-semantic-freeze.v1":
        raise FreezeCompleteError("freeze_schema_invalid")
    policy = freeze.get("solver_policy", {})
    if policy.get("integrator") != "backward_euler_f64":
        raise FreezeCompleteError("integrator_drift")
    if policy.get("initial_condition") != "explicit_only":
        raise FreezeCompleteError("initial_condition_drift")
    if policy.get("stepping") != "fixed_breakpoint_union":
        raise FreezeCompleteError("stepping_drift")
    if policy.get("output_sampling") != "reported_at_requested_axis_only":
        raise FreezeCompleteError("sampling_drift")
    if policy.get("measurement_semantics") != "not_implemented":
        raise FreezeCompleteError("measurement_drift")

    acceptance = load_yaml(ACCEPTANCE)
    if acceptance.get("schema") != "sipi.tran.rc-pulse.acceptance.v1":
        raise FreezeCompleteError("acceptance_schema_invalid")
    acc = acceptance.get("acceptance", {})
    if acc.get("acceptance_ready") is not True:
        raise FreezeCompleteError("acceptance_not_ready")
    if acc.get("sample_alignment") != "index_aligned_no_interpolation":
        raise FreezeCompleteError("alignment_drift")
    time_axis = acc.get("time_axis", {})
    voltage_in = acc.get("voltage_in", {})
    voltage_out = acc.get("voltage_out", {})
    if time_axis.get("absolute_tolerance_seconds") != EXPECTED_TOLERANCES["time"]["absolute_tolerance_seconds"]:
        raise FreezeCompleteError("time_tolerance_drift")
    if voltage_in.get("absolute_tolerance_volts") != EXPECTED_TOLERANCES["voltage_in"]["absolute_tolerance_volts"] or voltage_in.get("relative_tolerance") != EXPECTED_TOLERANCES["voltage_in"]["relative_tolerance"]:
        raise FreezeCompleteError("voltage_in_tolerance_drift")
    if voltage_out.get("absolute_tolerance_volts") != EXPECTED_TOLERANCES["voltage_out"]["absolute_tolerance_volts"] or voltage_out.get("relative_tolerance") != EXPECTED_TOLERANCES["voltage_out"]["relative_tolerance"]:
        raise FreezeCompleteError("voltage_out_tolerance_drift")
    ic = acc.get("initial_condition", {})
    if ic.get("mode") != "explicit_without_op":
        raise FreezeCompleteError("ic_mode_drift")
    integration = acc.get("integration", {})
    if integration.get("method") != "backward_euler":
        raise FreezeCompleteError("integration_method_drift")

    return {"valid": True, "elements": 6}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except FreezeCompleteError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
