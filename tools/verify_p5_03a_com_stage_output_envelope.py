"""Fail closed on the P5-03a sipi-com typed stage-output envelope.

The charter fixes the envelope structure (14 output metrics, 3 network
roles, 6 checkpoints, finite-or-infinity metric values) bound to the
P5-06b observed surface. The verifier binds charter, Rust source
tokens, basis surface, and the PLAN P5-03a row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-03a-com-stage-output-envelope.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "lib.rs"
BASIS = ROOT / "docs" / "baselines" / "p5-06-oracle-metric-surface.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-03a.com-stage-output-envelope.v1"
POLICY = "sipi.p5-03a.com-stage-output-envelope-v1.typed-structure-only"


class EnvelopeError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EnvelopeError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "typed_stage_output_envelope_specified_no_computation":
        raise EnvelopeError("charter_schema_or_status_invalid")
    if charter.get("envelope") != {
        "output_metrics": "fourteen_observed_keys",
        "network_roles": ["THRU", "FEXT1", "NEXT1"],
        "checkpoints": ["TXLE_taps", "DFE_taps", "tail_RSS", "sigma_N", "sgm_Ani__isi_xt_noise", "itick"],
        "metric_value": "finite_or_infinity",
    }:
        raise EnvelopeError("envelope_drift")
    if charter.get("admission", {}).get("computation") is not False:
        raise EnvelopeError("admission_drift")
    if not BASIS.is_file():
        raise EnvelopeError("basis_surface_missing")
    if not SOURCE.is_file():
        raise EnvelopeError("source_missing")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub struct ComMetricValueV1",
        "pub struct ComOutputMetricsV1",
        "pub struct ComNetworkMetricV1",
        "pub struct ComCaseCheckpointV1",
        "pub const COM_STAGE_OUTPUT_ENVELOPE_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise EnvelopeError("implementation_binding_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-03a" not in plan_text:
        raise EnvelopeError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except EnvelopeError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
