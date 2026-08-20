# -*- coding: utf-8 -*-
"""Fail closed on the P3B-05c deterministic PRBS9 sequence core.

The charter fixes the deterministic-core scope (PRBS9, seed 0b000000001,
seed-replay) and keeps TX injection / time-warp units / observables /
tolerance out of scope; the cross-check evidence binds the product LFSR
to an independent ITU-T O.150 reference. The verifier binds charter,
evidence, Rust tokens, and the PLAN P3B-05c row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p3b-05c-prbs9-sequence-stage.v1.yaml"
SOURCE_MAP = ROOT / "docs" / "baselines" / "p3b-05c-prbs9-mit-source-map.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p3b-05c-prbs9-crosscheck-evidence.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-link" / "src" / "prbs9_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p3b-05c.prbs9-sequence-stage.v1"
POLICY = "sipi.p3b-05c.prbs9-sequence.v1.deterministic-core"


class Prbs9Error(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Prbs9Error("document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter = load_yaml(CHARTER)
    if charter.get("schema") != SCHEMA or charter.get("status") != "prbs9_deterministic_core_ported":
        raise Prbs9Error("charter_schema_or_status_invalid")
    admission = charter.get("admission", {})
    if admission.get("prbs9_sequence_generation") is not True or admission.get("seed_replay") is not True:
        raise Prbs9Error("seed_admission_drift")
    if admission.get("injection_position") is not False:
        raise Prbs9Error("injection_admission_drift")
    if admission.get("time_warp_units_model") is not False:
        raise Prbs9Error("timewarp_admission_drift")
    source_map = load_yaml(SOURCE_MAP)
    if len(source_map.get("mapping", [])) != 4:
        raise Prbs9Error("source_map_mapping_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub struct Prbs9V1",
        "pub fn next_bit",
        "pub fn next_bytes",
        "pub fn restore",
        "pub const PRBS9_OWNER_SEED_BITS",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise Prbs9Error("implementation_binding_drift")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("schema") != "sipi.p3b-05c.prbs9-crosscheck-evidence.v1":
        raise Prbs9Error("evidence_schema_invalid")
    if evidence.get("status") != "matched_hash_bound":
        raise Prbs9Error("evidence_status_drift")
    entries = evidence.get("entries", [])
    if len(entries) != 1 or not entries[0].get("matched"):
        raise Prbs9Error("evidence_entry_mismatch")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P3B-05c" not in plan_text:
        raise Prbs9Error("plan_row_missing")
    return {"valid": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except Prbs9Error as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())