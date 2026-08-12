"""Fail-closed verifier for the owner-approved P3C fixed-rational execution contract."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-fixed-rational-execution-contract.v1.yaml"
PRELIGHT = ROOT / "docs" / "baselines" / "p3c-product-rational-candidate-policy-preflight.v1.yaml"
FIXED = ROOT / "docs" / "baselines" / "p3c-fixed-pole-rational-identification-core.v1.yaml"
RELEASE = ROOT / "docs" / "baselines" / "release-capability-publication.v1.yaml"
SCHEMA = "sipi.p3c-fixed-rational-execution-contract.v1"


class VerificationError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("execution_contract_schema_invalid")
    if document.get("status") != "product_fixed_rational_execution_contract_specified_real_model_hardening_and_sealed_s4p_runtime_pending":
        raise VerificationError("execution_contract_status_invalid")
    if document.get("predecessor_bindings") != {
        "rational_route_preflight_sha256": _sha256(PRELIGHT),
        "fixed_pole_identification_sha256": _sha256(FIXED),
    }:
        raise VerificationError("execution_contract_predecessor_drift")
    expected_model = {
        "fit_route": "fixed_allowlisted_orders_8_12_16_final_for_selected_profile",
        "domain": "continuous_time", "signal_kind": "real_siso_scalar_differential_transfer",
        "canonical_authority": "positive_imaginary_pole_residue_pairs",
        "canonical_expression": "H(s)=sum_over_pairs(2*Re(r_k/(s-p_k)))",
        "strictly_proper_required": True, "direct_term": "prohibited", "derivative_term": "prohibited",
        "explicit_delay": "prohibited", "relocating_vector_fit": "not_required_for_selected_profile",
        "pole_residue_realness": {
            "positive_imaginary_member": "canonical_stored_member_only",
            "negative_imaginary_member": "exact_conjugate_derived_only",
            "fitting": "real_constrained_basis_required",
            "postfit_average_projection_or_imaginary_discard": "prohibited",
            "stability": "every_pole_strictly_left_half_plane",
            "pair_order": "ascending_positive_imaginary_frequency",
            "nonfinite_or_unpaired_model": "reject",
        },
    }
    if document.get("model_contract") != expected_model:
        raise VerificationError("execution_contract_model_invalid")
    if document.get("fit_admission") != {
        "reference_core": "p3c_fixed_pole_rational_identification_core_v1", "required_orders": [8, 12, 16],
        "relative_rms_error_max": 0.005, "maximum_normalized_absolute_error_max": 0.03,
        "dc_relative_error_max": 0.005, "failed_fit": "reject_without_algorithm_fallback",
    }:
        raise VerificationError("execution_contract_fit_admission_invalid")
    if document.get("out_of_band_policy") != {
        "strategy": "global_strictly_proper_rational_continuation", "product_semantics": True,
        "ads_equivalence_claim": "prohibited", "band_limit_filter": "prohibited", "phase_delay_extraction": "prohibited",
    }:
        raise VerificationError("execution_contract_out_of_band_invalid")
    if document.get("source_policy") != {
        "signal": "differential_prbs9_levels_plus_minus_1_volt", "edge": "linear_ramp",
        "edge_duration_seconds": 1.0e-16, "transition_interval": "half_open_ui_boundary_to_boundary_plus_100as",
        "plateau_after_transition": True, "unchanged_symbol": "hold_previous_level",
        "ads_edge_shape_equivalence_claim": "prohibited",
    }:
        raise VerificationError("execution_contract_source_invalid")
    if document.get("time_and_state_policy") != {
        "ui_seconds": 3.125e-11, "osr": 32, "dt_seconds": 9.765625e-13, "sample_count": 49056,
        "output_interval": "half_open_0_to_3x511_ui", "output_strobe": "y_at_n_times_dt_for_n_0_to_49055",
        "initial_state": "zero", "first_symbol": "level_effective_at_t0_without_preceding_bit_or_initial_ramp",
        "ui_boundary_order": "record_output_then_advance_new_source_segment",
        "warmup": "first_two_prbs_periods_are_explicit_input_only",
    }:
        raise VerificationError("execution_contract_time_state_invalid")
    if document.get("recurrence_policy") != {
        "representation": "conjugate_pair_analytic_piecewise_affine_input_recurrence",
        "pair_output": "sum_2_times_real_pair_state", "numerical_primitives": "fixed_complex_exponential_and_expm1",
        "generic_matrix_exponential": "prohibited", "ode_solver": "prohibited", "adaptive_step": "prohibited",
        "resampling": "prohibited", "alignment_gain_dc_or_polarity_fit": "prohibited",
        "passivity_enforcement": "none_diagnostic_only", "pole_or_residue_repair": "prohibited",
        "finite_or_imaginary_residual_failure": "reject",
    }:
        raise VerificationError("execution_contract_recurrence_invalid")
    if document.get("caller_surface") != {
        "caller_overrides": "prohibited", "public_cli": "absent", "artifact_input_or_output": "absent",
        "external_s4p_custody_admitted": False,
    }:
        raise VerificationError("execution_contract_caller_surface_invalid")
    expected_admission = {
        "execution_contract_specified": True, "real_constrained_fit_hardening_implemented": False,
        "sealed_s4p_admission_implemented": False, "analytic_stepping_implemented": False,
        "candidate_waveform_generated": False, "external_reference_binding_evaluated": False,
        "candidate_metric_acceptance_evaluated": False, "accepted_receiver": False,
        "product_runtime_invoked": False, "p4b_ami_runtime_invoked": False, "release_ledger_promoted": False,
    }
    if document.get("admission") != expected_admission:
        raise VerificationError("execution_contract_promotion_invalid")
    required_blockers = {
        "real_constrained_fixed_pole_fit_hardening_missing", "selected_external_s4p_artifact_admission_missing",
        "analytic_direct_stepping_implementation_missing", "candidate_waveform_generation_missing",
        "external_reference_binding_missing", "accepted_receiver_stage_missing", "statistical_eye_contour_semantics_missing",
    }
    if not required_blockers <= set(document.get("blockers", [])):
        raise VerificationError("execution_contract_blocker_missing")
    fixed = yaml.safe_load(FIXED.read_text(encoding="utf-8"))
    if fixed.get("admission", {}).get("state_space_model_generated") is not False:
        raise VerificationError("unconstrained_fit_promoted")
    release = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    compare = next((row for row in release.get("rows", []) if row.get("id") == "compare"), None)
    if not isinstance(compare, dict) or "metric_profile_semantics_not_implemented" not in compare.get("blockers", []):
        raise VerificationError("release_compare_gate_promoted")
    return {"valid": True, "execution_contract_specified": True, "analytic_stepping_implemented": False}


def main() -> int:
    try:
        print(verify(yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"fixed_rational_execution_contract_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
