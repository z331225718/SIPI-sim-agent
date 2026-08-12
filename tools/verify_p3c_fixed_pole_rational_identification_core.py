"""Fail-closed verifier for the P3C fixed-pole rational identification core."""

from __future__ import annotations

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-fixed-pole-rational-identification-core.v1.yaml"
MODULE = ROOT / "crates" / "sipi-channel" / "src" / "p3c_fixed_pole_rational_fit_v1.rs"
MANIFEST = ROOT / "crates" / "sipi-channel" / "Cargo.toml"
SCHEMA = "sipi.p3c-fixed-pole-rational-identification-core.v1"


class VerificationError(ValueError):
    pass


def verify(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("fixed_pole_schema_invalid")
    if document.get("status") != "product_owned_fixed_pole_residue_identification_specified_relocating_fit_and_executor_blocked":
        raise VerificationError("fixed_pole_status_invalid")
    expected_input = {
        "source_type": "selected_p3c_static_differential_transfer_v1", "product_owned_memory_only": True,
        "required_first_frequency_hz": 0.0, "required_last_frequency_hz": 4.0e10,
        "minimum_samples": 32, "external_s4p_custody_admitted": False,
        "ads_grid_or_waveform_input": "prohibited",
    }
    if document.get("input_boundary") != expected_input:
        raise VerificationError("fixed_pole_input_boundary_invalid")
    expected_algorithm = {
        "model_domain": "continuous_time", "normalized_variable": "s=j*f/40000000000",
        "canonical_form": "sum(r_k/(s-p_k))", "direct_term": "prohibited",
        "derivative_term": "prohibited", "explicit_delay": "prohibited", "pole_relocation": "prohibited",
        "pole_reflection_or_repair": "prohibited", "orders": [8, 12, 16],
        "initial_poles": "conjugate_pairs_log_spaced_10mhz_to_40ghz_with_negative_real_part_0.05_times_imaginary_magnitude",
        "weighting": "inverse_reference_magnitude_floor_1e-15",
        "rank_precheck": "thin_svd_relative_smallest_singular_value_gt_1e-12",
        "residue_solver": "faer_0_24_4_column_pivoted_qr_single_thread_no_rayon",
        "order_selection": "first_allowlisted_order_passing_all_metrics",
    }
    if document.get("algorithm") != expected_algorithm:
        raise VerificationError("fixed_pole_algorithm_invalid")
    if document.get("fit_admission") != {
        "relative_rms_error_max": 0.005, "maximum_normalized_absolute_error_max": 0.03,
        "dc_relative_error_max": 0.005, "zero_signal_norm": "reject", "zero_dc_reference": "reject",
    }:
        raise VerificationError("fixed_pole_metrics_invalid")
    expected_admission = {
        "fixed_pole_residue_identification_implemented": True, "relocating_vector_fit_implemented": False,
        "state_space_model_generated": False, "candidate_waveform_generated": False,
        "external_reference_binding_evaluated": False, "candidate_metric_acceptance_evaluated": False,
        "accepted_receiver": False, "product_runtime_invoked": False, "p4b_ami_runtime_invoked": False,
        "release_ledger_promoted": False,
    }
    if document.get("admission") != expected_admission:
        raise VerificationError("fixed_pole_promotion_invalid")
    required_blockers = {
        "full_relocating_vector_fit_policy_and_implementation_missing", "selected_external_s4p_artifact_admission_missing",
        "out_of_band_continuation_or_band_limit_policy_missing", "source_between_strobes_policy_missing",
        "strobe_initial_state_and_recurrence_policy_missing", "candidate_waveform_generation_missing",
        "external_reference_binding_missing", "accepted_receiver_stage_missing", "statistical_eye_contour_semantics_missing",
    }
    if not required_blockers <= set(document.get("blockers", [])):
        raise VerificationError("fixed_pole_blocker_missing")
    module = MODULE.read_text(encoding="utf-8")
    manifest = MANIFEST.read_text(encoding="utf-8")
    required_source = [
        "const ORDERS: [usize; 3] = [8, 12, 16];", "const RELATIVE_RANK_TOLERANCE: f64 = 1.0e-12;",
        "const RELATIVE_RMS_LIMIT: f64 = 0.005;", "const MAX_NORMALIZED_ABSOLUTE_LIMIT: f64 = 0.03;",
        "const DC_RELATIVE_LIMIT: f64 = 0.005;", "thin_svd", "col_piv_qr",
    ]
    if any(token not in module for token in required_source):
        raise VerificationError("fixed_pole_source_drift")
    forbidden_source = ["vecfit", "rayon", "relocate_poles", "fit_problem"]
    if any(token in module for token in forbidden_source):
        raise VerificationError("fixed_pole_forbidden_source_surface")
    if "faer = { version = \"0.24.4\", default-features = false, features = [\"std\", \"linalg\"] }" not in manifest:
        raise VerificationError("fixed_pole_dependency_drift")
    return {"valid": True, "orders": [8, 12, 16], "candidate_waveform_generated": False}


def main() -> int:
    try:
        print(verify(yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"fixed_pole_rational_verification_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
