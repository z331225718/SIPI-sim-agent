"""Fail closed on the P5-06b oracle metric surface.

The surface records the structured metric keys observed in the P5-06a
summary: network roles/keys, output metric keys, checkpoint keys, case
count, hash-bound to the summary.json hash. The verifier binds the
surface, evidence, and the PLAN P5-06b row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SURFACE = ROOT / "docs" / "baselines" / "p5-06-oracle-metric-surface.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06-matlab-oracle-first-run-evidence.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-06.oracle-metric-surface.v1"
EXPECTED_OUTPUT_KEYS = [
    "COM_dB", "CTLE_DC_gain_dB", "ERL", "ERL11", "ERL22", "FOM", "ICN_mV",
    "IL_dB_channel_only_at_Fnq", "Peak_ISI_XTK_and_Noise_interference_at_BER_mV",
    "VEC_dB", "VEO_mV", "fitted_IL_dB_at_Fnq", "g_DC_HP", "itick",
]
EXPECTED_ROLES = ["THRU", "FEXT1", "NEXT1"]


class SurfaceError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SurfaceError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    surface = load_yaml(SURFACE)
    if surface.get("schema") != SCHEMA or surface.get("status") != "oracle_metric_surface_observed_hash_bound":
        raise SurfaceError("surface_schema_or_status_invalid")
    if surface.get("network_roles") != EXPECTED_ROLES:
        raise SurfaceError("network_roles_drift")
    if surface.get("output_metric_keys") != EXPECTED_OUTPUT_KEYS:
        raise SurfaceError("output_metric_keys_drift")
    if surface.get("case_count") != 2:
        raise SurfaceError("case_count_drift")
    evidence = load_yaml(EVIDENCE)
    summary_hash = evidence.get("output_file_hashes", {}).get("summary.json")
    if surface.get("source_sha256") != summary_hash:
        raise SurfaceError("summary_hash_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-06b" not in plan_text:
        raise SurfaceError("plan_row_missing")
    return {"valid": True, "output_keys": len(EXPECTED_OUTPUT_KEYS)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except SurfaceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
