"""Verify the blocked additive PRBS9 finite-edge source policy v2 charter."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-prbs9-impulse-candidate-source-projection.v2.yaml"
SCHEMA = "sipi.p3c-prbs9-impulse-candidate-source-projection.v2"


class VerificationError(ValueError):
    pass


def verify_document(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("schema_invalid")
    if document.get("status") != "owner_confirmed_v2_source_projection_implemented_external_observation_pending":
        raise VerificationError("status_invalid")
    if document.get("authority") != {"actor": "user", "decision_ref": "user-confirmed-2026-08-14-p3c-finite-edge-boundary-projection-v2", "scope": "selected_candidate_source_projection_v2_only_not_metric_or_release_policy"}:
        raise VerificationError("authority_invalid")
    policy = document.get("policy_candidate")
    expected_policy = {"name": "finite_edge_boundary_pretransition_phase1_new_level", "source_amplitude_volts_differential": [-1.0, 1.0], "sample_zero": {"symbol": "first_symbol", "value": "current_symbol_level", "predecessor": "absent"}, "ui_boundary_for_global_ui_greater_than_zero": {"phase_0": "prior_symbol_level", "phases_1_through_31": "current_symbol_level"}, "period_boundary": "applies_same_prior_symbol_rule", "unchanged_symbol": "prior_and_current_levels_equal_without_special_case", "timebase": {"samples_per_ui": 32, "sample_interval_bits": "3d712e0be826d695", "periods": 3, "warmup_periods": 2}, "forbidden": ["sample_axis_shift", "prbs_rotation", "interpolation", "resampling", "gain_fit", "dc_removal", "polarity_flip", "runtime_projection_mode", "caller_projection_override", "half_scale_product_stimulus"]}
    if policy != expected_policy:
        raise VerificationError("policy_invalid")
    implementation = document.get("implementation_boundary")
    if not isinstance(implementation, dict) or implementation.get("new_api") != "generate_selected_p3c_prbs9_impulse_candidate_v2" or implementation.get("v1_api_unchanged") != "generate_selected_p3c_prbs9_impulse_candidate_v1":
        raise VerificationError("version_boundary")
    confirmation = document.get("owner_confirmation")
    if confirmation != {"phase_0_prior_phase_1_current": True, "sample_zero_first_symbol_current": True, "product_amplitude_remains_plus_or_minus_one_volt": True, "v2_selected_policy_v1_historical_only": True}:
        raise VerificationError("owner_confirmation_gate")
    true_keys = {"finite_edge_boundary_projection_v2_specified", "selected_source_projection_v2_implemented"}
    false_keys = {"product_projection_v2_source_strobe_match_observed", "current_v2_candidate_waveform_evaluated", "selected_highloss_waveform_only_profile_accepted", "source_explains_full_channel_residual", "causal_fir_admitted", "accepted_receiver", "acceptance_ready", "release_ledger_promoted"}
    admission = document.get("admission")
    if (
        not isinstance(admission, dict)
        or set(admission) != true_keys | false_keys
        or any(admission[key] is not True for key in true_keys)
        or any(admission[key] is not False for key in false_keys)
    ):
        raise VerificationError("gate_promotion")
    if document.get("blockers") != [
        "v2_source_only_strobe_observation_missing",
        "v2_candidate_waveform_observation_missing",
        "accepted_receiver_stage_missing",
        "statistical_eye_contour_semantics_missing",
    ]:
        raise VerificationError("blockers_invalid")
    if any(token in str(document).lower() for token in ("file://", "http://", "https://", "c:\\", "waveform: [", "samples: [")):
        raise VerificationError("evidence_leak")
    return {"valid": True, "owner_confirmation_pending": False, "v2_implemented": True, "release_admitted": False}


def main() -> int:
    try:
        result = verify_document(yaml.safe_load(PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_prbs9_impulse_candidate_source_projection_v2_failed:{error}")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
