"""Fail closed validation for the pending ADS OR/product raw DTFT charter."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-ads-or-product-raw-dtft-charter.v1.yaml"


class VerificationError(ValueError):
    pass


def fail(condition: bool, reason: str) -> None:
    if condition:
        raise VerificationError(reason)


def verify(document: object) -> dict[str, object]:
    fail(not isinstance(document, dict), "shape")
    required = {"schema", "status", "authority", "predecessor", "external_help_allowlist", "ads_surface", "product_response", "dtft", "freshness", "prohibitions", "admission", "blockers", "non_claims"}
    fail(set(document) != required, "shape")
    fail(document["schema"] != "sipi.p3c.ads-or-product-raw-dtft-charter.v1", "schema")
    fail(document["status"] != "specified_owner_authorized_external_diagnostic_pending", "status")
    fail(document["authority"] != {"actor": "user", "decision_ref": "user-authorized-cmp1-or-payload-2026-08-15", "scope": "one_fixed_ads_cmp1_or_to_product_raw_periodic_dtft_observation_only"}, "authority")
    fail(document["predecessor"] != {"path": "docs/baselines/p3c-ads-s0-product-bounded-dtft-observation-evidence.v1.yaml", "result": "ads_s0_product_bounded_delta_observed_not_cause_attribution"}, "predecessor")
    fail(document["external_help_allowlist"] != {"basename": "Transient_Simulation_Parameters.html", "byte_length": 150522, "sha256": "45372e9c7c79492bf6023a4e860f05a20caf0ef5e2a083407c119909afc187bf", "surface": "CMP1_OR", "documented_meaning": "original_spectrum"}, "help")
    fail(document["ads_surface"] != {"matrix_dimension": 4, "members_per_surface": 16, "member_axes_must_match_exactly": True, "axis": "cmp1_or_native_all_finite_strictly_increasing_frequency_nodes", "selected_reduction": "s21_minus_s23_minus_s41_plus_s43_over_4", "source_payload_read_authorization": "authorized"}, "ads_surface")
    fail(document["product_response"] != {"type": "SelectedP3cRawPeriodicResponseV1", "sample_count": 51200, "sample_interval_seconds": 9.765625e-13, "source": "selected_fixed_ieee_bsd_uniform_spectrum_inverse_transform_leaf", "causality": "prohibited", "truncation": "prohibited", "convolution": "prohibited"}, "product")
    fail(document["dtft"] != {"evaluation_axis": "ads_cmp1_or_native_exact_nodes_only", "definition": "sum_n_0_to_51199_h_of_n_times_exp_negative_j_2pi_f_n_dt", "window": "rectangular_full_response", "normalization": "none", "time_origin": "sample_zero", "summation_order": "ascending_n", "rotor": "one_fixed_negative_sign_complex_rotor_per_frequency", "caller_overrides": "prohibited"}, "dtft")
    fail(document["freshness"] != {"clean_archive_required": True, "fresh_runs": 2, "source_before_copy_after_identity_required": True}, "freshness")
    fail(document["prohibitions"] != ["ads_or_to_s0_resampling_or_nearest_bin", "product_frequency_interpolation", "delay_or_phase_removal", "gain_or_dc_fit", "alignment", "causality", "truncation", "convolution", "candidate_waveform_generation", "ads_algorithm_oracle_fitting"], "prohibitions")
    false = {"ads_or_product_raw_axis_bound", "product_raw_dtft_invoked", "ads_precausality_product_raw_delta_observed", "ads_algorithm_reproduced", "causality_or_interpolation_cause_identified", "raw_periodic_response_admitted_as_causal_fir", "candidate_waveform_accepted", "release_ledger_promoted"}
    fail(not isinstance(document["admission"], dict) or set(document["admission"]) != false or any(document["admission"][key] is not False for key in false), "gates")
    fail(document["blockers"] != ["two_fresh_external_cmp1_or_product_raw_observations_missing", "ads_original_product_raw_delta_not_cause_attribution"], "blockers")
    forbidden = ("file://", "http://", "https://", "c:\\", "spectrum: [", "waveform: [", "candidate_waveform_accepted: true")
    fail(any(token in str(document).lower() for token in forbidden), "leak")
    return {"valid": True, "external_payload_authorized": True, "admitted": False}


if __name__ == "__main__":
    try:
        print(verify(yaml.safe_load(PATH.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_ads_or_product_raw_dtft_charter_failed:{error}")
        raise SystemExit(1)
