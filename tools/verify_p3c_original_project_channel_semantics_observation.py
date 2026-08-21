"""Verify the hash-only original-project P3C channel-semantics observation."""

from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-original-project-channel-semantics-observation.v1.yaml"
SCHEMA = "sipi.p3c.original-project-channel-semantics-observation.v1"
SIPI_COMMIT = "74ef3870a1738f58fc2694ca989a39dc290b9339"
SIPI_TREE = "bd1d8e6948b828509cffac598529615c4f7f9f4c"
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def _expect(value: object, expected: object, reason: str) -> None:
    if value != expected:
        raise VerificationError(reason)


def _keys(value: object, expected: set[str], reason: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise VerificationError(reason)
    return value


def _hash(value: object, reason: str = "hash_invalid") -> None:
    if not isinstance(value, str) or len(value) != 64 or set(value) - HEX:
        raise VerificationError(reason)


def _git_hash(value: object, reason: str = "git_hash_invalid") -> None:
    if not isinstance(value, str) or len(value) != 40 or set(value) - HEX:
        raise VerificationError(reason)


def _hashes(value: object, reason: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise VerificationError(reason)
    for item in value.values():
        _hash(item, reason)
    return value


def _archive_hash(path: str) -> str:
    result = subprocess.run(
        ["git", "archive", "--format=tar", SIPI_COMMIT, "--", path],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise VerificationError("sipi_source_archive_failed")
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        if len(members) != 1 or members[0].name != path:
            raise VerificationError("sipi_source_archive_inventory")
        payload = archive.extractfile(members[0])
        if payload is None:
            raise VerificationError("sipi_source_archive_payload")
        return hashlib.sha256(payload.read()).hexdigest()


def _verify_sipi_identity(document: dict[str, object]) -> None:
    current = document["current_product"]
    assert isinstance(current, dict)
    _expect(current["clean_archive_commit"], SIPI_COMMIT, "sipi_commit")
    _expect(current["clean_archive_tree"], SIPI_TREE, "sipi_tree")
    tree = subprocess.run(
        ["git", "rev-parse", f"{SIPI_COMMIT}^{{tree}}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if tree.returncode or tree.stdout.strip() != SIPI_TREE:
        raise VerificationError("sipi_tree_drift")
    inventory = current["source_inventory"]
    assert isinstance(inventory, dict)
    for path, expected in inventory.items():
        if _archive_hash(path) != expected:
            raise VerificationError(f"sipi_source_hash:{path}")


def verify_document(document: object) -> dict[str, object]:
    top = _keys(
        document,
        {
            "schema",
            "status",
            "authority",
            "current_product",
            "external_ads",
            "external_pybert",
            "comparison",
            "policy",
            "admission",
            "blockers",
            "non_claims",
        },
        "top_level_shape",
    )
    _expect(top["schema"], SCHEMA, "schema")
    _expect(
        top["status"],
        "original_project_semantics_observed_source_phase_bound_waveform_cause_unresolved",
        "status",
    )
    _expect(
        top["authority"],
        {
            "actor": "project",
            "decision_ref": "task-t08-2026-08-21-original-project-channel-semantics-observation",
            "scope": "retained_original_ads_and_pybert_read_only_semantics_observation",
        },
        "authority",
    )

    current = _keys(top["current_product"], {"clean_archive_commit", "clean_archive_tree", "source_inventory", "source_policy"}, "current_shape")
    _hashes(current["source_inventory"], "current_inventory_hash")
    _expect(
        current["source_inventory"],
        {
            "crates/sipi-p3c/src/prbs9_impulse_candidate_v2.rs": "ec3ee799f5d42988d0b78ba02c5ea29ea766c8179622659be711ac02f3991ad9",
            "crates/sipi-ieee-com-sparam/src/interp_sparam_v1.rs": "26e3918bcbee01c0ec54430831d24d6ed904b1c11576715f3a23c6e15f124918",
            "crates/sipi-ieee-com-sparam/src/s21_to_causal_v1.rs": "5233a6ade2a4fd33678fd0fb94bf6c278848cc2e67cd43f6b846c487e11586cc",
            "crates/sipi-ieee-com-sparam/src/s21_to_truncated_v1.rs": "160a1fc3b65f250cfa1fc86c50951878bc708a7660f8d6ad0fe3682690986c4b",
            "crates/sipi-channel/src/p3c_fixed_four_port_bench_v1.rs": "c546fa998eeb5ff3163521cd3cdd422a1caffc458c584fbf705a97b13210d008",
            "crates/sipi-compare/src/selected_highloss_prbs9_waveform_only_v3.rs": "df4fdd75531562b952ef56d85057507edd516be13c31565358ef4084155cb0e5",
        },
        "current_inventory",
    )
    _expect(
        current["source_policy"],
        {
            "seed_hex": "0x1a5",
            "samples_per_ui": 32,
            "phase_zero": "prior_symbol",
            "phases_one_through_31": "current_symbol",
            "boundary_policy": "finite_edge_right_continuous_v2",
            "source_policy_changed_by_observation": False,
        },
        "source_policy",
    )

    ads = _keys(top["external_ads"], {"custody", "selected_s4p", "manifest", "dataset", "netlist", "canonical_payload", "dsdump_observation", "workspace_controller_log"}, "ads_shape")
    _expect(ads["custody"], "external_only_retained_original_ads", "ads_custody")
    _expect(
        ads["selected_s4p"],
        {"logical_name": "channel_gen5_highloss.s4p", "byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"},
        "ads_s4p",
    )
    _expect(
        ads["manifest"],
        {"logical_name": "manifest.json", "byte_length": 2479, "sha256": "37930afa7f151cd6ca317f17ebb544dfb9c5a56a4a4c455b35f0114dc4fb94f9", "schema": "sipi.p3c-external-ads-prbs9-reference-run.v1", "runtime_invoked": True, "product_runtime": False, "p4b_ami_runtime": False},
        "ads_manifest",
    )
    _expect(
        ads["dataset"],
        {"logical_name": "p3c_prbs9.ds", "byte_length": 7107072, "sha256": "1375d8beec33b2688cf4ab305a6a472b9ae0260960b2128e199b760979d12310"},
        "ads_dataset",
    )
    _expect(
        ads["netlist"],
        {"logical_name": "p3c_prbs9_ideal_load.ckt", "declared_byte_length": 5246, "declared_sha256": "2784e9e8d42c7ecdc3459b79a5f9cd79cc86131f839c86b1658e8d40b1d9aaf9", "retained_byte_length": 5254, "retained_sha256": "c6d3df30e2f23dd9181426b2d834bab4cb5990d19a1e48a2b968eb9e79369765", "line_ending_difference_only": True, "mode": 2, "register_length": 9, "seed_hex": "0x1a5", "bit_rate_hz": 32000000000.0, "rise_time_seconds": 1.0e-16, "fall_time_seconds": 1.0e-16, "max_time_step_seconds": 9.765625e-13, "imp_lfe_on": True, "imp_mode": 1, "imp_enforce_passivity": True, "output_all_points": True},
        "ads_netlist",
    )
    _expect(
        ads["canonical_payload"],
        {"logical_name": "canonical_waveform_le_f64.bin", "byte_length": 1177344, "sha256": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726", "tuple_format": "little_endian_f64_time_tx_differential_rx_differential", "observed_column": "rx_differential", "sample_count": 49056, "sample_interval_bits": "3d712e0be826d695", "endpoint_policy": "ads_inclusive_endpoint_excluded_from_canonical_half_open_payload"},
        "ads_payload",
    )
    _expect(
        ads["dsdump_observation"],
        {"source_dataset_sha256": "1375d8beec33b2688cf4ab305a6a472b9ae0260960b2128e199b760979d12310", "vectorset": "TRAN.TRAN", "point_count_inclusive": 49057, "sample_interval_bits": "3d712e0be826d695", "samples_per_ui": 32, "source_edge_floor_seconds": 1.0e-16, "first_symbols_bits": "1101", "first_ui_last_sample_index": 31, "first_phase_zero_boundary_index": 32, "first_observed_phase_one_transition_index": 65, "third_period_start_index": 32704, "third_observed_phase_one_transition_index": 32705, "phase_zero_owns_prior_symbol": True, "phase_one_through_31_own_current_symbol": True, "source_fact_is_not_channel_solver_parity": True},
        "ads_dsdump",
    )
    _expect(
        ads["workspace_controller_log"],
        {"logical_name": "netlist.log", "byte_length": 7858, "sha256": "676838f9bff5f92cd0e645da7db20b3adf3399cab015300d1d3b34e8098f3983", "touchstone_interp_mode": "linear", "touchstone_extrap_mode": "constant", "channel_sim_type": "Statistical", "tolerance_mode": 1, "enforce_passivity": True, "max_impulse_length": 1000, "number_time_points_per_ui": 32, "status_level": 2, "anti_aliasing_window": 1, "imp_lfe_on": True, "imp_cache": True, "tx_use_controller_sample_rate": True, "rx_use_controller_sample_rate": True, "rx_wave_capture_delay": 1000, "rx_wave_capture_count": 2047, "rx_wave_capture_mode": 2, "log_is_controller_observation_not_p3c_acceptance": True},
        "ads_controller_log",
    )

    pybert = _keys(top["external_pybert"], {"custody", "commit", "tree", "source_inventory", "semantics"}, "pybert_shape")
    _expect(pybert["custody"], "external_read_only_source_repository", "pybert_custody")
    _expect(pybert["commit"], "5bf6d7ea0ace261891aaeb611ffc1c267e160afe", "pybert_commit")
    _expect(pybert["tree"], "5faef6bdb341d444ad65d82a11c0018b15805e24", "pybert_tree")
    _expect(
        pybert["source_inventory"],
        {"src/pybert/models/bert.py": "145cb77bd1c864a41c307e76581beb19c6de7ec1a5764cada9df82882bbf4d10", "src/pybert/pybert.py": "a2fdd33db845db09155e323a26465688d759e77ed2bcc4a23cb7a5298d5457dd", "src/pybert/utility/sparam.py": "a14b65364f124a807c0efd3f0c73d7dc54bb750598edcf26996c588054e3011d", "src/pybert/utility/sigproc.py": "394c8ffebf5ae2c352ab16c0155a1241b84089f6bd8bbb40fc7ce1d73e0758ad", "docs/RUST_SIMULATION_ENGINE_MIGRATION.md": "e7036c0b71b0ea34bbe0bdc6634590f963b7917d9cf7814bcaf0ff195abc3f86"},
        "pybert_inventory",
    )
    _expect(
        pybert["semantics"],
        {"channel_response_stage": "calc_chnl_h_then_causal_linear_convolve_preserving_leading_zeros", "touchstone_four_port": "mixed_mode_sdd21_conversion", "touchstone_interpolation": "polar_interpolation_with_extrapolation_policy", "terminations": "frequency_dependent_source_and_load_impedance_then_voltage_normalization", "inverse_transform": "irfft_then_cubic_resample_from_t_irfft_to_system_t", "impulse_scaling": "system_dt_over_irfft_dt", "impulse_trimming": "20_to_100_ui_front_porch_kept_energy_0.999", "delay_semantics": "peak_index_diagnostic_only", "output_strobe_semantics": "no_explicit_ads_controller_strobe_in_native_channel_stage"},
        "pybert_semantics",
    )

    comparison = _keys(top["comparison"], {"current_strict_replay", "source_only_basis", "conclusion"}, "comparison_shape")
    _expect(comparison["current_strict_replay"], {"source_sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47", "canonical_payload_sha256": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726", "compared_period": "third", "start_index": 32704, "sample_count": 16352, "nrmse_bits": "3f9dd184cd51df98", "nrmse_decimal": 0.02911956313297956, "fixed_limit_decimal": 0.01, "within_limit": False, "report_sha256": "09ec29941fbddd9c6724e40e9603a877dc382aa010fbfe9445d2f23ea05ccf4f"}, "current_replay")
    _expect(comparison["source_only_basis"], {"report_sha256": "566a60e654b9f9b1d22fc8a998b587a53209e0076845b153c8866138006ec1a5", "third_period_interior_sample_count": 15841, "third_period_interior_nrmse_bits": "0000000000000000", "third_period_boundary_sample_count": 511, "third_period_boundary_nrmse_bits": "3ea0773eea805ee1", "fixed_mapping": "ads_loaded_differential_equals_0.5_times_product_finite_edge_projection_v2"}, "source_only_basis")
    _expect(comparison["conclusion"], {"source_only_interior_matches_selected_projection_while_full_chain_mismatch_remains": True, "basis": "source_only_interior_is_bitwise_exact_while_full_channel_third_period_remains_0.02911956313297956", "ads_interpolation_causality_delay_trimming_differ_from_current_policy": True, "migration_authorized": False, "waveform_root_cause_identified": False}, "conclusion")

    _expect(top["policy"], {"same_index_compare_required": True, "alignment": "prohibited", "delay_sweep": "prohibited", "gain_fit": "prohibited", "dc_removal": "prohibited", "polarity_flip": "prohibited", "resampling": "prohibited", "rational_fit": "prohibited", "parameter_scan": "prohibited", "tolerance_relaxation": "prohibited"}, "policy")
    _expect(top["admission"], {"retained_ads_identity_bound": True, "dsdump_phase_fact_bound": True, "ads_controller_log_bound": True, "pybert_commit_tree_source_hashes_bound": True, "source_policy_test_only_updated": True, "current_waveform_accepted": False, "causal_fir_admitted": False, "receiver_accepted": False, "release_promoted": False}, "admission")
    _expect(top["blockers"], ["current_strict_same_index_nrmse_exceeds_fixed_one_percent_limit", "ads_interpolation_causality_delay_and_trimming_contract_not_authorized_for_migration", "exact_waveform_root_cause_unresolved"], "blockers")
    _expect(top["non_claims"], ["This observation does not claim ADS solver parity or receiver acceptance.", "The source-only interior match and remaining full-chain mismatch do not identify or exclude any root cause.", "PyBERT semantics are forensic references only; no PyBERT code or algorithm was copied into SIPI.", "No alignment, delay search, gain or DC fit, polarity transform, resampling, rational fit, parameter scan, or tolerance relaxation was performed.", "No ADS payload, dataset, S4P, absolute path, or waveform array is tracked in the repository."], "non_claims")

    for value in (ads["selected_s4p"]["sha256"], ads["manifest"]["sha256"], ads["dataset"]["sha256"], ads["netlist"]["declared_sha256"], ads["netlist"]["retained_sha256"], ads["canonical_payload"]["sha256"], ads["workspace_controller_log"]["sha256"], *pybert["source_inventory"].values()):
        _hash(value)
    _git_hash(pybert["commit"])
    _git_hash(pybert["tree"])
    if any(token in str(document).lower() for token in ("file://", "http://", "https://", "c:\\", "c:/", "%temp%", "waveform: [", "samples: [")):
        raise VerificationError("evidence_leak")
    return {"valid": True, "source_phase_bound": True, "current_waveform_accepted": False}


def verify() -> dict[str, object]:
    document = yaml.safe_load(PATH.read_text(encoding="utf-8"))
    result = verify_document(document)
    _verify_sipi_identity(document)
    return result


if __name__ == "__main__":
    try:
        print(verify())
    except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_original_project_channel_semantics_observation_failed:{error}", file=sys.stderr)
        raise SystemExit(1)
