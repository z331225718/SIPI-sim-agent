"""Fail closed on the P3B-05 seed/noise/jitter decision-surface preflight.

The preflight freezes the unselected decision surface (required profile,
injection position, units model, seed replay, observables, tolerance)
pending owner decision and prohibits deterministic seed, noise/jitter
profile, or receiver-stage implementations before that decision. The
verifier cross-binds the charter against the PLAN P3B-05 row, the P3B-05a
rejection gate, and the causal-FIR request schema id.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3b-05-seed-noise-jitter-decision-preflight.v1.yaml"
PLAN = ROOT / "PLAN.md"
REJECTION_GATE = ROOT / "tools" / "verify_p3b_05a_causal_fir_request_rejection.py"
CONTRACTS = ROOT / "crates" / "sipi-contracts" / "src" / "lib.rs"
SCHEMA = "sipi.p3b-05.seed-noise-jitter-decision-preflight.v1"
REQUEST_SCHEMA_ID = "sipi.link.causal-fir-request.v1"


class SeedNoiseJitterPreflightError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SeedNoiseJitterPreflightError("document_not_mapping")
    return value


def verify_document(document: object) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise SeedNoiseJitterPreflightError("schema_invalid")
    if document.get("status") != "seed_noise_jitter_semantics_not_frozen_pending_owner_decision":
        raise SeedNoiseJitterPreflightError("status_invalid")
    if document.get("decision_surface") != {
        "required_profile": "unselected_pending_owner_decision",
        "injection_position": "unselected_pending_owner_decision",
        "units_model": "unselected_pending_owner_decision",
        "seed_replay": "unselected_pending_owner_decision",
        "observables": "unselected_pending_owner_decision",
        "tolerance": "unselected_pending_owner_decision",
    }:
        raise SeedNoiseJitterPreflightError("decision_surface_drift")
    if document.get("blocker_linkage") != {
        "plan_row": "P3B-05",
        "rejection_gate": "tools/verify_p3b_05a_causal_fir_request_rejection.py",
        "request_schema_id": REQUEST_SCHEMA_ID,
    }:
        raise SeedNoiseJitterPreflightError("blocker_linkage_drift")
    if document.get("admission") != {
        "deterministic_seed_implementation": "prohibited_without_owner_decision",
        "noise_jitter_profile_implementation": "prohibited_without_owner_decision",
        "receiver_stage_semantics": "prohibited_without_owner_decision",
        "product_runtime_invoked": False,
        "release_promoted": False,
    }:
        raise SeedNoiseJitterPreflightError("admission_drift")
    claims = document.get("non_claims")
    expected_claims = ["not_a_profile_choice", "not_an_injection_choice", "not_a_units_model_choice", "not_a_seed_replay_choice", "not_a_tolerance_choice", "not_acceptance_evidence"]
    if not isinstance(claims, list) or claims != expected_claims:
        raise SeedNoiseJitterPreflightError("non_claims_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P3B-05b" not in plan_text:
        raise SeedNoiseJitterPreflightError("plan_row_missing")
    if "**P3B-05a 已完成" not in plan_text:
        raise SeedNoiseJitterPreflightError("plan_p3b_05a_row_missing")
    if not REJECTION_GATE.is_file():
        raise SeedNoiseJitterPreflightError("rejection_gate_missing")
    contracts = CONTRACTS.read_text(encoding="utf-8")
    if REQUEST_SCHEMA_ID not in contracts:
        raise SeedNoiseJitterPreflightError("request_schema_id_missing")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": document["status"],
        "seed_noise_jitter_decision_surface": "frozen_unselected",
        "seed_noise_jitter_implementation": "prohibited",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        result = verify_document(load_yaml(arguments.core))
    except (OSError, ValueError, yaml.YAMLError, SeedNoiseJitterPreflightError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
