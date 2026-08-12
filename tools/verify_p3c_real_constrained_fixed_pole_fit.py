"""Fail-closed verifier for P3C real-constrained fixed-pole hardening."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-real-constrained-fixed-pole-fit.v1.yaml"
CONTRACT = ROOT / "docs" / "baselines" / "p3c-fixed-rational-execution-contract.v1.yaml"
MODULE = ROOT / "crates" / "sipi-channel" / "src" / "p3c_real_constrained_fixed_pole_fit_v1.rs"
SCHEMA = "sipi.p3c-real-constrained-fixed-pole-fit.v1"


class VerificationError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("real_constrained_schema_invalid")
    if document.get("status") != "product_owned_real_constrained_fixed_pole_identification_implemented_sealed_s4p_and_stepping_blocked":
        raise VerificationError("real_constrained_status_invalid")
    if document.get("execution_contract_sha256") != _sha256(CONTRACT):
        raise VerificationError("real_constrained_contract_drift")
    if document.get("input_boundary") != {
        "source_type": "selected_p3c_static_differential_transfer_v1", "product_owned_memory_only": True,
        "required_first_frequency_hz": 0.0, "required_last_frequency_hz": 4.0e10,
        "minimum_samples": 32, "external_s4p_custody_admitted": False,
        "ads_grid_or_waveform_input": "prohibited",
    }:
        raise VerificationError("real_constrained_input_invalid")
    expected_algorithm = {
        "model_domain": "continuous_time", "normalized_variable": "s=j*f/40000000000",
        "canonical_model": "positive_imaginary_pole_residue_pairs",
        "pair_response": "r_over_s_minus_p_plus_conjugate_r_over_s_minus_conjugate_p",
        "coefficient_basis": "stacked_real_and_imaginary_real_constrained_least_squares",
        "direct_term": "prohibited", "derivative_term": "prohibited", "explicit_delay": "prohibited",
        "pole_relocation": "prohibited", "pole_reflection_or_repair": "prohibited",
        "residue_average_projection_or_imaginary_discard": "prohibited", "orders": [8, 12, 16],
        "positive_imaginary_poles": "log_spaced_10mhz_to_40ghz_with_negative_real_part_0.05_times_imaginary_magnitude",
        "pair_order": "ascending_positive_imaginary_frequency", "weighting": "inverse_reference_magnitude_floor_1e-15",
        "rank_precheck": "thin_svd_relative_smallest_singular_value_gt_1e-12",
        "residue_solver": "faer_0_24_4_column_pivoted_qr_single_thread_no_rayon",
        "order_selection": "first_allowlisted_order_passing_all_metrics",
    }
    if document.get("algorithm") != expected_algorithm:
        raise VerificationError("real_constrained_algorithm_invalid")
    if document.get("fit_admission") != {
        "relative_rms_error_max": 0.005, "maximum_normalized_absolute_error_max": 0.03,
        "dc_relative_error_max": 0.005, "zero_signal_norm": "reject", "zero_dc_reference": "reject",
        "nonfinite_or_unpaired_model": "reject",
    }:
        raise VerificationError("real_constrained_metrics_invalid")
    expected_admission = {
        "real_constrained_fixed_pole_identification_implemented": True,
        "sealed_s4p_admission_implemented": False, "analytic_stepping_implemented": False,
        "candidate_waveform_generated": False, "external_reference_binding_evaluated": False,
        "candidate_metric_acceptance_evaluated": False, "accepted_receiver": False,
        "product_runtime_invoked": False, "p4b_ami_runtime_invoked": False, "release_ledger_promoted": False,
    }
    if document.get("admission") != expected_admission:
        raise VerificationError("real_constrained_promotion_invalid")
    required_blockers = {
        "selected_external_s4p_artifact_admission_missing", "analytic_direct_stepping_implementation_missing",
        "candidate_waveform_generation_missing", "external_reference_binding_missing",
        "accepted_receiver_stage_missing", "statistical_eye_contour_semantics_missing",
    }
    if not required_blockers <= set(document.get("blockers", [])):
        raise VerificationError("real_constrained_blocker_missing")
    module = MODULE.read_text(encoding="utf-8")
    required_source = [
        "Mat::<f64>::from_fn", "positive_imaginary_poles_normalized", "pair_basis", "residue.conj()",
        "thin_svd", "col_piv_qr", "const ORDERS: [usize; 3] = [8, 12, 16];",
    ]
    if any(token not in module for token in required_source):
        raise VerificationError("real_constrained_source_drift")
    forbidden_source = ["vecfit", "rayon", "relocate_poles", "average_residue", "projection", "state_space"]
    if any(token in module for token in forbidden_source):
        raise VerificationError("real_constrained_forbidden_source_surface")
    return {"valid": True, "real_constrained": True, "candidate_waveform_generated": False}


def main() -> int:
    try:
        print(verify(yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"real_constrained_fixed_pole_verification_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
