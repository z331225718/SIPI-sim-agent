"""Fail-closed verifier for the P3C sealed selected-S4P intake adapter."""

from __future__ import annotations

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-sealed-selected-s4p-static-admission.v1.yaml"
MODULE = ROOT / "crates" / "sipi-p3c" / "src" / "lib.rs"
MANIFEST = ROOT / "crates" / "sipi-p3c" / "Cargo.toml"
SCHEMA = "sipi.p3c-sealed-selected-s4p-static-admission.v1"


class VerificationError(ValueError):
    pass


def verify(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("sealed_s4p_schema_invalid")
    if document.get("status") != "product_internal_sealed_selected_s4p_intake_implemented_external_custody_observation_and_stepping_blocked":
        raise VerificationError("sealed_s4p_status_invalid")
    expected_asset = {
        "logical_name": "channel_gen5_highloss.s4p", "sealed_file_name": "channel.s4p",
        "byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47",
        "port_map": ["tx_plus", "rx_plus", "tx_minus", "rx_minus"], "asset_bytes_tracked": False,
    }
    if document.get("selected_asset") != expected_asset:
        raise VerificationError("sealed_s4p_asset_invalid")
    if document.get("input_contract") != {
        "root_assumption": "caller_selected_sipi_published_root_no_hostile_concurrent_writer",
        "caller_identity": "artifact_id_and_manifest_sha256_only", "exact_sealed_files": ["channel.s4p"],
        "manifest_schema": "sipi.artifact-manifest.v1", "metadata_sidecar": "absent",
        "caller_path_url_payload_name_hash_length_port_map_or_limit_override": "prohibited",
    }:
        raise VerificationError("sealed_s4p_input_invalid")
    if document.get("verification") != {
        "artifact_primitive": "consume_exact_verified_v1", "manifest_recheck_after_payload_read": "required",
        "exact_payload_length": "required", "exact_payload_sha256": "required",
        "parser": "selected_four_port_hz_s_ri_50_v1", "static_reduction": "Hdiff=(S21-S23-S41+S43)/4",
        "parser_limits": "fixed_product_internal", "symlink_reparse_and_extra_file": "reject",
        "source_change_or_manifest_drift": "reject",
    }:
        raise VerificationError("sealed_s4p_verification_invalid")
    expected_admission = {
        "sealed_s4p_intake_implemented": True, "external_static_custody_observed": False,
        "selected_external_s4p_static_admitted": False, "real_constrained_fit_invoked": False,
        "analytic_stepping_implemented": False, "candidate_waveform_generated": False,
        "external_reference_binding_evaluated": False, "candidate_metric_acceptance_evaluated": False,
        "accepted_receiver": False, "product_runtime_invoked": False, "p4b_ami_runtime_invoked": False,
        "release_ledger_promoted": False,
    }
    if document.get("admission") != expected_admission:
        raise VerificationError("sealed_s4p_promotion_invalid")
    required_blockers = {
        "two_fresh_external_sealed_s4p_custody_observations_missing", "real_constrained_fit_invocation_on_external_s4p_missing",
        "analytic_direct_stepping_implementation_missing", "candidate_waveform_generation_missing",
        "external_reference_binding_missing", "accepted_receiver_stage_missing", "statistical_eye_contour_semantics_missing",
    }
    if not required_blockers <= set(document.get("blockers", [])):
        raise VerificationError("sealed_s4p_blocker_missing")
    module = MODULE.read_text(encoding="utf-8")
    required_source = [
        "consume_exact_verified_v1", "SELECTED_P3C_S4P_FILE_NAME_V1", "SELECTED_P3C_S4P_BYTE_LENGTH_V1",
        "SELECTED_P3C_S4P_SHA256_V1", "parse_selected_four_port_hz_s_ri_50_v1",
        "admit_selected_p3c_fixed_four_port_v1", "reduce_selected_p3c_fixed_four_port_bench_v1",
    ]
    if any(token not in module for token in required_source):
        raise VerificationError("sealed_s4p_source_drift")
    forbidden_source = ["command::new", "std::process", "ami", "dll", "fit_selected", "http", "url"]
    if any(token in module.lower() for token in forbidden_source):
        raise VerificationError("sealed_s4p_forbidden_source_surface")
    manifest = MANIFEST.read_text(encoding="utf-8")
    for dependency in ["sipi-artifacts", "sipi-channel", "sipi-touchstone"]:
        if dependency not in manifest:
            raise VerificationError("sealed_s4p_dependency_drift")
    return {"valid": True, "sealed_s4p_intake_implemented": True, "external_static_custody_observed": False}


def main() -> int:
    try:
        print(verify(yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"sealed_selected_s4p_admission_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
