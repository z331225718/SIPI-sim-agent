"""Fail closed on the P5-04o receiver noise stage port.

The charter fixes the stage scope; the source map records the MIT
function mapping; the cross-check evidence binds product and oracle
results. The verifier binds charter, source map, evidence, Rust
tokens, and the PLAN P5-04o row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p5-04o-receiver-noise-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p5-04o-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04o-receiver-noise-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "receiver_noise_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-04o.receiver-noise-stage.v1"
POLICY = "sipi.p5-04o.receiver-noise-v1.filters-eta0-accm"


class ReceiverNoiseStageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReceiverNoiseStageError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "receiver_noise_stage_ported":
        raise ReceiverNoiseStageError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("crosstalk_noise") is not False:
        raise ReceiverNoiseStageError("admission_drift")
    if admission.get("search_loop") is not False:
        raise ReceiverNoiseStageError("search_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 5:
        raise ReceiverNoiseStageError("source_map_mapping_drift")
    if "_crosstalk_noise / _td_source_crosstalk_noise" not in source_map.get("not_ported", []):
        raise ReceiverNoiseStageError("source_map_not_ported_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn bessel_thomson_filter_v1",
        "pub fn butterworth_filter_v1",
        "pub fn raised_cosine_filter_v1",
        "pub fn receiver_noise_v1",
        "pub fn rx_ffe_frequency_response_v1",
        "pub const RECEIVER_NOISE_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ReceiverNoiseStageError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p5-04o.receiver-noise-crosscheck-evidence.v1":
        raise ReceiverNoiseStageError("evidence_schema_invalid")
    if evidence.get("status") != "receiver_noise_crosscheck_matched":
        raise ReceiverNoiseStageError("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 9 or any(not entry.get("matched") for entry in entries):
        raise ReceiverNoiseStageError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-04o" not in plan_text:
        raise ReceiverNoiseStageError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ReceiverNoiseStageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
