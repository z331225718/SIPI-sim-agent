"""Fail closed on any attempt to treat the PRBS9 metric preflight as acceptance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-prbs9-waveform-jitter-preflight.v1.yaml"
P4B = ROOT / "docs/baselines/p4b-ads-pcie-gen5-dual-ami-asset-preflight.v1.yaml"
PUBLICATION = ROOT / "docs/baselines/release-capability-publication.v1.yaml"
SCHEMA = "sipi.p3c-prbs9-waveform-jitter-preflight.v1"

EXPECTED: dict[str, Any] = {
    "schema": SCHEMA,
    "status": "specified_preflight_only_pending_generator_reference_and_jitter_tolerance",
    "authority": {
        "actor": "user",
        "decision_ref": "user-conversation-2026-08-11-p3c-prbs9-metrics",
        "scope": "policy_only_not_runtime_or_acceptance",
    },
    "prbs": {
        "polynomial": "x9+x5+1",
        "symbols": [-1.0, 1.0],
        "samples_per_ui": 32,
        "reference_and_candidate_same_seed_required": True,
        "generator_convention": "pending_owner_input",
        "seed": None,
        "sequence_period_hash_sha256": None,
        "pending": ["lfsr_form", "shift_direction", "feedback_timing", "output_timing", "bit_to_symbol_mapping", "nonzero_seed", "sequence_period_hash"],
    },
    "waveform": {
        "reference_origin": "ads_same_bench_external_reference_pending_identity",
        "strict_index_comparison_required": True,
        "alignment": "prohibited",
        "resampling": "prohibited",
        "gain_fit": "prohibited",
        "dc_removal": "prohibited",
        "polarity_flip": "prohibited",
        "ui_seconds": None,
        "sample_origin": "pending_owner_input",
        "window": "pending_owner_input",
        "reference_identity": None,
        "reference_stage": "pending_owner_input",
        "candidate_stage": "pending_owner_input",
        "relative_rms_error_limit": 0.01,
        "relative_rms_formula": "pending_owner_approved_normalization",
        "acceptance_ready": False,
    },
    "jitter": {
        "signal_class": "nrz",
        "observable": "crossing_time_tie_rms",
        "cdr": "not_required_for_fixed_ui_eye_folding",
        "tolerance_seconds": None,
        "crossing_threshold_volts": None,
        "interpolation": "pending_owner_input",
        "edge_selection": "pending_owner_input",
        "ideal_crossing_schedule": "pending_owner_input",
        "missing_extra_or_multiple_crossing_policy": "fail_closed_pending_owner_matching_rule",
        "zero_mean_tie_removal": "prohibited_without_owner_amendment",
        "acceptance_ready": False,
    },
    "statistical_eye": {
        "status": "blocked_missing_immutable_pybert_observation_and_contour_semantics",
        "snr": "excluded",
        "contour": "pending_immutable_source_ber_axes_noise_jitter_and_tolerance",
    },
    "admission": {
        "acceptance_ready": False,
        "promotion_eligible": False,
        "runtime_invoked": False,
        "ads_runtime_invoked": False,
        "ami_runtime_invoked": False,
        "external_reference_observed": False,
        "release_ledger_promoted": False,
    },
    "blockers": [
        "generator_convention_seed_and_period_identity_missing",
        "ads_reference_identity_and_same_stage_waveform_missing",
        "ui_sample_origin_and_window_missing",
        "relative_rms_normalization_formula_missing",
        "jitter_crossing_and_tolerance_semantics_missing",
        "statistical_eye_contour_semantics_missing",
        "accepted_receiver_stage_missing",
    ],
    "non_claims": [
        "Not a PRBS generator implementation or a generated bit sequence.",
        "Not ADS, AMI, DLL, PyBERT, channel, receiver, or CDR runtime evidence.",
        "Not waveform, eye, jitter, bathtub, BER, SNR, or statistical-contour acceptance.",
        "Not an alignment, resampling, phase removal, gain fit, DC removal, or polarity transform authorization.",
        "Not a release, worker admission, external asset admission, or product capability promotion.",
    ],
}


class PreflightError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PreflightError("document_not_mapping")
    return value


def verify_document(document: object, root: Path = ROOT) -> dict[str, Any]:
    if document != EXPECTED:
        raise PreflightError("preflight_policy_drift")
    p4b = load_yaml(root / P4B.relative_to(ROOT))
    if p4b.get("status") != "external_only_identity_observed_worker_blocked":
        raise PreflightError("p4b_runtime_admission_drift")
    publication = json.loads((root / PUBLICATION.relative_to(ROOT)).read_text(encoding="utf-8"))
    compare = next((row for row in publication.get("rows", []) if row.get("id") == "compare"), None)
    if not isinstance(compare, dict) or compare.get("acceptance_state") != "specified" or "metric_profile_semantics_not_implemented" not in compare.get("blockers", []):
        raise PreflightError("release_compare_metric_gate_drift")
    return {
        "schema": SCHEMA,
        "status": EXPECTED["status"],
        "acceptance_ready": False,
        "runtime_invoked": False,
        "release_ledger_promoted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        result = verify_document(load_yaml(arguments.preflight))
    except (OSError, ValueError, yaml.YAMLError, PreflightError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
