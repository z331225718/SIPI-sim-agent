"""Fail-closed verifier for the nonexecuting P3C rational-route charter."""

from __future__ import annotations

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-product-rational-candidate-policy-preflight.v1.yaml"
STATIC = ROOT / "docs" / "baselines" / "p3c-selected-four-port-static-bench.v1.yaml"
SWEEP = ROOT / "docs" / "baselines" / "p3c-ads-explicit-convolution-sweep-observation.v1.yaml"
SCHEMA = "sipi.p3c-product-rational-candidate-policy-preflight.v1"


class VerificationError(ValueError):
    pass


def verify(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("rational_policy_schema_invalid")
    if document.get("status") != "product_rational_candidate_route_selected_nonexecuting_fit_source_step_and_out_of_band_policy_pending":
        raise VerificationError("rational_policy_status_invalid")
    expected_input = {
        "source": "p3c_selected_four_port_static_bench_v1",
        "scalar_transfer": "Hdiff=(S21-S23-S41+S43)/4",
        "frequency_nodes": "original_selected_s4p_nodes_only",
        "external_s4p_custody_admitted": False,
        "ads_n2048_grid_product_input": "prohibited",
        "ads_waveform_or_adaptive_output_product_input": "prohibited",
    }
    if document.get("input_boundary") != expected_input:
        raise VerificationError("rational_policy_input_boundary_invalid")
    expected_model = {
        "domain": "continuous_time",
        "signal_kind": "real_siso_scalar_differential_transfer",
        "canonical_authority": "pole_residue",
        "canonical_expression": "H(s)=sum(r_k/(s-p_k))",
        "frequency_variable": "s=j*2*pi*f",
        "strictly_proper_required": True,
        "direct_term": "prohibited",
        "derivative_term": "prohibited",
        "state_space_representation": "deterministic_derived_only",
        "explicit_delay": "pending_owner_policy",
        "passivity_enforcement": "pending_owner_policy",
    }
    if document.get("selected_model_route") != expected_model:
        raise VerificationError("rational_policy_model_route_invalid")
    pending_fit = {
        "frequency_scaling", "dc_constraint", "sample_weighting", "initial_poles", "order_ladder_and_maximum",
        "iteration_and_relocation_rule", "least_squares_solver_and_rank_tolerance", "convergence_and_order_selection",
        "fit_error_metrics_and_tolerances", "stability_margin_and_conjugate_canonicalization",
        "near_cancellation_and_duplicate_pole_policy", "fit_implementation_identity_and_threading",
    }
    pending_execution = {
        "out_of_band_continuation_or_band_limit", "source_between_strobes", "first_symbol_and_ui_boundary_ownership",
        "initial_state", "strobe_mapping", "pole_residue_recurrence_and_numeric_identity", "finite_and_imaginary_residual_policy",
    }
    if document.get("pending_fit_policy") != {field: "pending_owner_policy" for field in pending_fit}:
        raise VerificationError("rational_policy_fit_not_pending")
    expected_execution = {field: "pending_owner_policy" for field in pending_execution}
    expected_execution.update({"adaptive_step_or_resampling": "prohibited", "alignment_gain_dc_or_polarity_fit": "prohibited"})
    if document.get("pending_execution_policy") != expected_execution:
        raise VerificationError("rational_policy_execution_not_pending")
    expected_envelope = {
        "tracked_coefficients": False,
        "required_bindings": ["selected_s4p_identity", "hdiff_digest", "policy_digest", "fit_implementation_identity", "order", "canonical_pole_residue_digest", "fit_metrics", "stable", "strictly_proper"],
        "caller_override": "prohibited",
    }
    if document.get("future_model_envelope") != expected_envelope:
        raise VerificationError("rational_policy_envelope_invalid")
    expected_admission = {
        "executor_admission": False, "fitter_implemented": False, "state_space_model_generated": False,
        "candidate_waveform_generated": False, "external_reference_binding_evaluated": False,
        "candidate_metric_acceptance_evaluated": False, "accepted_receiver": False,
        "product_runtime_invoked": False, "p4b_ami_runtime_invoked": False, "release_ledger_promoted": False,
    }
    if document.get("admission") != expected_admission:
        raise VerificationError("rational_policy_promotion_invalid")
    blockers = set(document.get("blockers", []))
    required_blockers = {
        "exact_rational_fit_algorithm_and_numerics_missing", "out_of_band_policy_missing",
        "source_between_strobes_policy_missing", "strobe_and_initial_state_policy_missing",
        "external_selected_s4p_static_custody_missing", "candidate_waveform_generation_missing",
        "external_reference_binding_missing", "accepted_receiver_stage_missing", "statistical_eye_contour_semantics_missing",
    }
    if not required_blockers <= blockers:
        raise VerificationError("rational_policy_blocker_missing")
    static = yaml.safe_load(STATIC.read_text(encoding="utf-8"))
    sweep = yaml.safe_load(SWEEP.read_text(encoding="utf-8"))
    if static.get("implementation", {}).get("time_domain_executor") != "not_implemented":
        raise VerificationError("static_executor_promoted")
    if sweep.get("selected_external_candidate", {}).get("product_policy_selected") is not False:
        raise VerificationError("ads_candidate_promoted")
    return {"valid": True, "executor_admission": False, "model_route": "pole_residue_pending_policy"}


def main() -> int:
    try:
        print(verify(yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"rational_policy_preflight_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
