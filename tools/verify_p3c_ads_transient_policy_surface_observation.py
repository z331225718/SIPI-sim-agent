"""Fail closed on the P3C ADS transient-policy observation and its non-promotions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-ads-transient-policy-surface-observation.v1.yaml"
STATIC = ROOT / "docs" / "baselines" / "p3c-selected-four-port-static-bench.v1.yaml"
PUBLICATION = ROOT / "docs" / "baselines" / "release-capability-publication.v1.yaml"
SCHEMA = "sipi.p3c-ads-transient-policy-surface-observation.v1"
REPORT_SHA256 = "3bdbb5d01290790c3cddef353f3f224e47cfaf379905c8076ca11186be01e2c3"
RUNNER_SHA256 = "94b76e640a8ad823f6e66fc2f0aff8eb33771ca9c2a5ab14923e58b5bf1353bc"
SOURCE_SHA256 = "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"
DOCUMENTATION_SHA256S = {
    "94556c3c3a59ee30bb733e92ec795c7d15bb126820e74d57aec9276c7275b667",
    "290ae0dc3771afbbf9e14f326e5b0fc1b131272e10ca96dfbfa3c85193330bca",
    "45372e9c7c79492bf6023a4e860f05a20caf0ef5e2a083407c119909afc187bf",
    "621851d5d3bd754b898c27bccd641da3dae08954ef902f72b6609bd8f093a7e0",
}


class VerificationError(ValueError):
    pass


def tracked_hashes() -> set[str]:
    return {
        hashlib.sha256((ROOT / path.decode("utf-8")).read_bytes()).hexdigest()
        for path in __import__("subprocess").run(["git", "-C", str(ROOT), "ls-files", "-z"], check=True, capture_output=True).stdout.split(b"\0")
        if path
    }


def external_custody_hashes() -> set[str]:
    return {REPORT_SHA256, SOURCE_SHA256} | DOCUMENTATION_SHA256S


def verify(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("policy_surface_schema_invalid")
    if document.get("status") != "external_ads_transient_policy_surface_observed_product_deterministic_time_domain_policy_missing":
        raise VerificationError("policy_surface_status_invalid")
    if document.get("authority") != {"actor": "user", "decision_ref": "user-authorized-2026-08-12-p3c-ads-policy-surface-observation", "scope": "external_ads_documentation_and_generated_netlist_observation_only"}:
        raise VerificationError("policy_surface_authority_invalid")
    if document.get("external_observation") != {"custody": "external_only_hash_only", "report_path_retained": False, "report_byte_length": 2594, "report_content_sha256": REPORT_SHA256, "fresh_observations": 2, "canonical_repeatability": "identical"}:
        raise VerificationError("policy_surface_observation_binding_invalid")
    if document.get("source") != {"logical_name": "channel_gen5_highloss.s4p", "byte_length": 1834156, "sha256": SOURCE_SHA256, "asset_bytes_tracked": False}:
        raise VerificationError("policy_surface_source_binding_invalid")
    if document.get("runner") != {"logical_name": "run_p3c_external_ads_prbs9_reference.py", "sha256": RUNNER_SHA256}:
        raise VerificationError("policy_surface_runner_binding_invalid")
    expected_docs = {
        "channel_convolution": {"logical_name": "Differential_Channel_Simulator_-_Convolution.html", "byte_length": 57677, "sha256": "94556c3c3a59ee30bb733e92ec795c7d15bb126820e74d57aec9276c7275b667"},
        "simulation_controllers": {"logical_name": "Simulation_and_Optimization_Controllers.html", "byte_length": 135600, "sha256": "290ae0dc3771afbbf9e14f326e5b0fc1b131272e10ca96dfbfa3c85193330bca"},
        "transient_parameters": {"logical_name": "Transient_Simulation_Parameters.html", "byte_length": 150522, "sha256": "45372e9c7c79492bf6023a4e860f05a20caf0ef5e2a083407c119909afc187bf"},
        "transient_troubleshooting": {"logical_name": "Troubleshooting_a_Transient-Convolution_Simulation.html", "byte_length": 78496, "sha256": "621851d5d3bd754b898c27bccd641da3dae08954ef902f72b6609bd8f093a7e0"},
    }
    if document.get("documentation") != expected_docs:
        raise VerificationError("policy_surface_documentation_binding_invalid")
    expected_netlist = {"source_edge_seconds": 1.0e-16, "max_time_step_seconds": 9.765625e-13, "output_points": "all_strobe_points", "low_frequency_extrapolation": "enabled_transient_engine_adaptive_start_frequency", "approximate_linear_models": "disabled", "convolution_mode": 1, "controller_passivity_enforcement": "enabled", "snp_component_passivity_override": "not_declared", "initial_conditions": "disabled"}
    if document.get("generated_netlist") != expected_netlist:
        raise VerificationError("policy_surface_netlist_invalid")
    expected_unresolved = ["convolution_frequency_grid_and_delta_frequency_not_explicit", "maximum_frequency_not_explicit", "impulse_length_and_truncation_not_explicit", "frequency_interpolation_and_extrapolation_algorithm_not_selected", "causalization_and_passivity_handling_algorithm_not_selected", "linear_convolution_startup_history_and_output_strobe_algorithm_not_selected"]
    if document.get("unresolved_product_policy") != expected_unresolved:
        raise VerificationError("policy_surface_unresolved_policy_invalid")
    expected_admission = {"ads_policy_surface_observed": True, "product_deterministic_time_domain_policy_observed": False, "candidate_waveform_generated": False, "external_reference_binding_evaluated": False, "accepted_receiver": False, "product_runtime_invoked": False, "p4b_ami_runtime_invoked": False, "release_ledger_promoted": False}
    if document.get("admission") != expected_admission:
        raise VerificationError("policy_surface_promotion_invalid")
    if document.get("blockers") != ["product_deterministic_time_domain_policy_missing", "candidate_waveform_generation_missing", "external_reference_binding_missing", "accepted_receiver_stage_missing", "statistical_eye_contour_semantics_missing"]:
        raise VerificationError("policy_surface_blockers_invalid")
    static = yaml.safe_load(STATIC.read_text(encoding="utf-8"))
    if static.get("implementation", {}).get("time_domain_executor") != "not_implemented" or static.get("admission", {}).get("candidate_waveform_generated") is not False:
        raise VerificationError("static_bench_time_domain_promotion")
    publication = json.loads(PUBLICATION.read_text(encoding="utf-8"))
    compare = next((row for row in publication.get("rows", []) if row.get("id") == "compare"), None)
    if not isinstance(compare, dict) or "metric_profile_semantics_not_implemented" not in compare.get("blockers", []):
        raise VerificationError("release_compare_gate_drift")
    if external_custody_hashes() & tracked_hashes():
        raise VerificationError("external_custody_leak")
    return {"valid": True, "product_time_domain_policy": "missing", "candidate_waveform_generated": False, "release_promoted": False}


def main() -> int:
    try:
        print(verify(yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"policy_surface_verification_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
