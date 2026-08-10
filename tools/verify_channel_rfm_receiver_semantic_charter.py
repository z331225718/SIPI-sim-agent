"""Verify the pending owner-semantic charter preflight for the required RFM profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.channel.receiver-semantic-charter.v1"
PROFILE_ID = "channel-rfm-block-2-current-drive-v1"
DECISION_REF = "user-confirmed-2026-08-10-channel-rfm-receiver"
RECEIVER_SCHEMA = "sipi.receiver-semantics.v1"
RECEIVER_SCHEMA_PATH = "crates/sipi-contracts/schemas/sipi.receiver-semantics.v1.schema.json"
PENDING = "pending_owner_approval"
PENDING_DECISIONS = {
    "product_stimulus_and_causal_link_waveform",
    "dfe_model_and_adaptation",
    "dfe_tap_order_cursor_units_and_sign",
    "cdr_detector_phase_frequency_update_lock_reset_and_cancel",
    "ber_reference_bits_polarity_alignment_threshold_ties_window_metric",
    "external_oracle_stage_scope_and_tolerances",
}
PROPOSAL = {
    "approval_required",
    "input",
    "reference_bits",
    "cdr",
    "normalization",
    "dfe",
    "decision_and_ber",
    "external_compare",
}


def _load(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("pyyaml is unavailable")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("semantic charter must be a YAML object")
    return value


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def verify_document(document: object, root: Path = ROOT) -> dict:
    blockers: list[str] = []
    required = {"schema", "status", "profile_id", "decision_ref", "receiver_contract", "pending_decisions", "proposed_v1", "non_claims"}
    if not _exact(document, required):
        return {"valid": False, "blockers": ["charter has unknown or missing fields"]}
    if document["schema"] != SCHEMA or document["status"] != PENDING or document["profile_id"] != PROFILE_ID or document["decision_ref"] != DECISION_REF:
        blockers.append("charter identity or pending status is invalid")
    contract = document["receiver_contract"]
    if not _exact(contract, {"schema", "schema_path", "schema_sha256"}) or contract.get("schema") != RECEIVER_SCHEMA or contract.get("schema_path") != RECEIVER_SCHEMA_PATH or not isinstance(contract.get("schema_sha256"), str) or len(contract["schema_sha256"]) != 64:
        blockers.append("receiver contract binding is invalid")
    else:
        schema_path = root / RECEIVER_SCHEMA_PATH
        if not schema_path.is_file() or hashlib.sha256(schema_path.read_bytes()).hexdigest() != contract["schema_sha256"]:
            blockers.append("receiver contract schema hash does not match")
    decisions = document["pending_decisions"]
    if not _exact(decisions, PENDING_DECISIONS) or any(value != PENDING for value in decisions.values()):
        blockers.append("all required owner decisions must remain explicitly pending")
    proposal = document["proposed_v1"]
    if not _exact(proposal, PROPOSAL) or proposal.get("approval_required") is not True:
        blockers.append("proposed receiver model is incomplete or not explicitly pending approval")
    elif not _valid_proposal(proposal):
        blockers.append("proposed receiver model has unsafe or inconsistent bounds")
    non_claims = document["non_claims"]
    if not isinstance(non_claims, list) or len(non_claims) < 3 or not all(isinstance(item, str) and item for item in non_claims):
        blockers.append("charter non-claims are incomplete")
    return {"valid": not blockers, "status": document.get("status"), "pending_decision_count": len(decisions) if isinstance(decisions, dict) else 0, "blockers": blockers}


def _valid_proposal(proposal: dict) -> bool:
    input_ = proposal["input"]
    bits = proposal["reference_bits"]
    cdr = proposal["cdr"]
    normalization = proposal["normalization"]
    dfe = proposal["dfe"]
    ber = proposal["decision_and_ber"]
    compare = proposal["external_compare"]
    return (
        _exact(input_, {"receive_samples", "start_seconds", "sample_interval_seconds", "ui_seconds", "samples_per_ui", "ctle", "ffe"})
        and input_ == {"receive_samples": 1024, "start_seconds": 0.0, "sample_interval_seconds": 1e-12, "ui_seconds": 8e-12, "samples_per_ui": 8, "ctle": "bypass", "ffe": "bypass"}
        and _exact(bits, {"count", "source", "positive_voltage_is_one", "training_symbols", "measurement_symbols", "training_requires_both_symbols"})
        and bits == {"count": 128, "source": "caller_supplied_external_comparator_only", "positive_voltage_is_one": True, "training_symbols": 32, "measurement_symbols": 96, "training_requires_both_symbols": True}
        and _exact(cdr, {"kind", "phase_candidates", "training_symbol_count", "selection", "minimum_relative_margin", "phase_tracking"})
        and cdr == {"kind": "data_aided_fixed_phase_v1", "phase_candidates": 8, "training_symbol_count": 32, "selection": "maximum_class_separation", "minimum_relative_margin": 0.01, "phase_tracking": "forbidden"}
        and _exact(normalization, {"center", "amplitude", "minimum_absolute_amplitude_volts", "normalized_threshold"})
        and normalization == {"center": "mean_one_and_zero_midpoint", "amplitude": "half_class_separation", "minimum_absolute_amplitude_volts": 1e-6, "normalized_threshold": 0.0}
        and _exact(dfe, {"kind", "postcursor_taps", "tap_delays_ui", "training_step", "initial_coefficients", "training_uses_reference_past_symbols", "measurement_uses_prior_hard_decisions", "adaptation_after_training"})
        and dfe == {"kind": "fixed_training_postcursor_dfe_v1", "postcursor_taps": 5, "tap_delays_ui": [1, 2, 3, 4, 5], "training_step": 0.25, "initial_coefficients": "zero", "training_uses_reference_past_symbols": True, "measurement_uses_prior_hard_decisions": True, "adaptation_after_training": "forbidden"}
        and _exact(ber, {"zero_decision", "discrete_observables", "discrete_comparison", "continuous_stage_tolerance"})
        and ber["zero_decision"] == "erasure_and_error"
        and ber["discrete_observables"] == ["cdr_phase", "lock_state", "measurement_decisions", "error_count", "ber"]
        and ber["discrete_comparison"] == "exact"
        and ber["continuous_stage_tolerance"] == {"absolute_volts": 1e-9, "relative": 1e-6}
        and _exact(compare, {"require_matching_receive_waveform_hash", "require_matching_reference_bits_hash", "stage_unobservable_status"})
        and compare == {"require_matching_receive_waveform_hash": True, "require_matching_reference_bits_hash": True, "stage_unobservable_status": "blocked"}
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--charter", type=Path, default=ROOT / "docs/baselines/channel-rfm-receiver-semantic-charter.v1.yaml")
    args = parser.parse_args()
    try:
        report = verify_document(_load(args.charter))
    except (OSError, RuntimeError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
