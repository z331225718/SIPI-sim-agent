# -*- coding: utf-8 -*-
"""Fail closed on the P3B-05d PRBS9 TX-injection waveform core.

Charter fixes the deterministic waveform scope on top of P3B-05c; keeps the
time-warp jitter/observables/tolerance out. Cross-check evidence binds product
waveforms against an independent reference. Verifier binds charter, source map,
evidence, Rust tokens, PLAN P3B-05d.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p3b-05d-prbs9-inject-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p3b-05d-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p3b-05d-inject-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-link" / "src" / "prbs9_inject_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p3b-05d.prbs9-inject-stage.v1"
POLICY = "sipi.p3b-05d.prbs9-inject.v1.tx-waveform"


class InjectError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise InjectError("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "prbs9_inject_waveform_ported":
        raise InjectError("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("bit_to_waveform_mapping") is not True or admission.get("tx_injection_basis") is not True:
        raise InjectError("inject_admission_drift")
    if admission.get("time_warp_jitter_model") is not False or admission.get("observables") is not False:
        raise InjectError("jitter_observable_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 3:
        raise InjectError("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn prbs9_inject_waveform_v1",
        "pub fn owner_default_inject_waveform_v1",
        "pub enum InjectWaveformErrorV1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise InjectError("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p3b-05d.inject-crosscheck-evidence.v1":
        raise InjectError("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise InjectError("evidence_status_drift")
    if evidence.get("matched_count") != evidence.get("case_count"):
        raise InjectError("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P3B-05d" not in plan_text:
        raise InjectError("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except InjectError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())