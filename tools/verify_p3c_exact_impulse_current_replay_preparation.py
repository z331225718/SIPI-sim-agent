"""Verify the P3C exact-impulse current replay preparation contract."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p3c-exact-impulse-current-replay-preparation.v1.yaml"
SPEC = ROOT / "docs/clean-room/specs/p3c-exact-impulse-current-replay-preparation.v1.md"
OBSERVER = ROOT / "tools/observe_p3c_exact_impulse_current_replay_preparation.py"
RUNNER = ROOT / "crates/sipi-p3c/tests/p3c_external_ads_selected_highloss_waveform_only_runner.rs"
SCHEMA = "sipi.p3c-exact-impulse-current-replay-preparation.v1"
COMMIT = "805ebb6bbaf588dec08685be4eb78a8ce2fff563"
TREE = "5a378052ea8fdadb8754f22d0a0150088cec6332"
S4P = {"logical_name": "channel_gen5_highloss.s4p", "byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47", "custody": "external_only", "bytes_tracked_in_repository": False}
ADS = {"logical_name": "ads_canonical_triple_payload_le_f64.bin", "byte_length": 1177344, "sha256": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726", "tuple_format": "little_endian_f64_time_tx_differential_rx_differential", "observed_column": "rx_differential", "samples": 49056, "sample_interval_bits": "3d712e0be826d695", "custody": "external_only", "bytes_tracked_in_repository": False}
RUNNER_RELATIVE = "crates/sipi-p3c/tests/p3c_external_ads_selected_highloss_waveform_only_runner.rs"
RUNNER_TEST = "p3c_external_ads_selected_highloss_waveform_only_runner_v2"
EXPECTED_INVENTORY_PATHS = {
    "Cargo.lock",
    "Cargo.toml",
    "rust-toolchain.toml",
    "crates/sipi-artifacts/Cargo.toml",
    "crates/sipi-artifacts/src/lib.rs",
    "crates/sipi-channel/Cargo.toml",
    "crates/sipi-channel/src/lib.rs",
    "crates/sipi-channel/src/p3c_fixed_four_port_bench_v1.rs",
    "crates/sipi-contracts/Cargo.toml",
    "crates/sipi-contracts/src/lib.rs",
    "crates/sipi-ieee-com-sparam/Cargo.toml",
    "crates/sipi-ieee-com-sparam/NOTICE-IEEE-802-COM.md",
    "crates/sipi-ieee-com-sparam/SOURCE-MAP.md",
    "crates/sipi-ieee-com-sparam/src/lib.rs",
    "crates/sipi-ieee-com-sparam/src/interp_sparam_v1.rs",
    "crates/sipi-ieee-com-sparam/src/s21_to_raw_periodic_v1.rs",
    "crates/sipi-ieee-com-sparam/src/s21_to_causal_v1.rs",
    "crates/sipi-ieee-com-sparam/src/s21_to_truncated_v1.rs",
    "crates/sipi-link/Cargo.toml",
    "crates/sipi-link/src/lib.rs",
    "crates/sipi-p3c/Cargo.toml",
    "crates/sipi-p3c/src/lib.rs",
    "crates/sipi-p3c/src/prbs9_impulse_candidate_v1.rs",
    "crates/sipi-p3c/src/prbs9_impulse_candidate_v2.rs",
    RUNNER_RELATIVE,
    "crates/sipi-compare/Cargo.toml",
    "crates/sipi-compare/src/lib.rs",
    "crates/sipi-compare/src/selected_highloss_prbs9_waveform_only_v3.rs",
    "crates/sipi-touchstone/Cargo.toml",
    "crates/sipi-touchstone/src/lib.rs",
    "crates/sipi-touchstone/src/selected_four_port_v1.rs",
    "crates/sipi-types/Cargo.toml",
    "crates/sipi-types/src/lib.rs",
}


class VerificationError(ValueError):
    pass


def _safe_extract(data: bytes, destination: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        members = archive.getmembers()
        for member in members:
            name = Path(member.name)
            if name.is_absolute() or ".." in name.parts or member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                raise VerificationError("archive_member_invalid")
        archive.extractall(destination)


def _archive_inventory(paths: set[str]) -> dict[str, str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=tar", COMMIT, "--", *sorted(paths)],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise VerificationError("clean_archive_unavailable")
    with tempfile.TemporaryDirectory(prefix="sipi-p3c-contract-") as temporary:
        destination = Path(temporary)
        _safe_extract(result.stdout, destination)
        inventory: dict[str, str] = {}
        for path in paths:
            payload = destination / Path(path)
            if not payload.is_file():
                raise VerificationError("clean_archive_path_missing")
            inventory[path] = hashlib.sha256(payload.read_bytes()).hexdigest()
        return inventory


def _hex(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and all(character in "0123456789abcdef" for character in value)


def verify(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("schema")
    if document.get("status") != "external_only_two_fresh_current_replay_preparation_pending":
        raise VerificationError("status")
    if document.get("baseline") != {
        "commit": COMMIT,
        "tree": TREE,
        "historical_evidence_currentness": "external_replay_required",
        "historical_records_rewritten": False,
    }:
        raise VerificationError("baseline")
    if document.get("selected_inputs", {}).get("s4p") != S4P:
        raise VerificationError("s4p_input")
    if document.get("selected_inputs", {}).get("ads_reference") != ADS:
        raise VerificationError("ads_reference_input")
    if document.get("selected_inputs", {}).get("product_cli") != {
        "custody": "external_only",
        "identity": "t08_supplied_executable_sha256_required",
        "bytes_tracked_in_repository": False,
    }:
        raise VerificationError("product_cli_input")
    if document.get("clean_archive") != {
        "commit": COMMIT,
        "tree": TREE,
        "materialization": "git_archive_only",
        "archive_bytes_retained": False,
        "worktree_execution": "prohibited",
    }:
        raise VerificationError("clean_archive")
    if document.get("runner") != {
        "observer": "tools/observe_p3c_exact_impulse_current_replay_preparation.py",
        "existing_ignored_test": RUNNER_RELATIVE,
        "test_name": "p3c_external_ads_selected_highloss_waveform_only_runner_v2",
        "test_mode": "ignored_external_only",
        "cargo_command": "cargo test --locked --offline -p sipi-p3c --test p3c_external_ads_selected_highloss_waveform_only_runner -- --ignored p3c_external_ads_selected_highloss_waveform_only_runner_v2",
        "source_inventory": "clean_archive_product_paths_below",
        "ads_runtime_invoked": False,
        "ads_reference_read_only": True,
        "candidate_reference_bytes_retained": False,
    }:
        raise VerificationError("runner_contract")
    custody = document.get("custody")
    if custody != {
        "fresh_replay_runs": 2,
        "fresh_custody_runs": 2,
        "fresh_artifact_roots_per_run": 2,
        "artifact_id_reuse": "prohibited",
        "source_identity_checks": "before_stage_after_equal",
        "reference_identity_checks": "before_read_after_read_equal",
        "distinct_manifest_identities": "required",
        "equal_canonical_facts": "required",
        "cleanup": "complete_required",
        "cleanup_failure": "reject",
    }:
        raise VerificationError("custody_contract")
    impulse = document.get("impulse_chain")
    expected_stages = [
        "sealed_selected_s4p_admission_v2",
        "ieee_bsd_interpolation_v1",
        "ieee_bsd_raw_periodic_internal_to_bounded_causality_v1",
        "ieee_bsd_bounded_causality_v1",
        "ieee_bsd_truncation_v1",
        "prbs9_finite_edge_v2_direct_full_linear_convolution",
        "strict_index_waveform_only_compare_v3",
    ]
    if not isinstance(impulse, dict) or impulse.get("route") != "ieee_bsd_impulse_only" or impulse.get("stages") != expected_stages or impulse.get("s_parameter_fit") != "prohibited" or impulse.get("rational_fit") != "prohibited" or impulse.get("alternative_solver") != "prohibited":
        raise VerificationError("impulse_route")
    candidate = impulse.get("current_candidate")
    if candidate != {
        "api": "generate_selected_p3c_prbs9_impulse_candidate_v2",
        "module": "crates/sipi-p3c/src/prbs9_impulse_candidate_v2.rs",
        "source_policy": "finite_edge_boundary_pretransition_phase1_new_level",
        "source_amplitude_volts_differential": [-1.0, 1.0],
        "sample_zero": "first_symbol_current",
        "ui_boundary_phase_0": "prior_symbol",
        "ui_boundary_phases_1_through_31": "current_symbol",
        "samples_per_ui": 32,
        "periods": 3,
        "warmup_periods": 2,
        "sample_interval_bits": "3d712e0be826d695",
        "period_sha256": "4437fb3beb2fa1ca99b4177673c53fc20089ac9cf68b1adaa1e0fad14d742127",
        "v1_runtime_selector": "prohibited",
    }:
        raise VerificationError("current_candidate_policy")
    strict = impulse.get("strict_index_compare")
    if strict != {
        "contract_schema": "sipi.p3c-selected-highloss-prbs9-waveform-only-contract.v3",
        "contract_sha256": "db0d9a663b311105be329d79060f05a5179f40fd7eccf448faf85d45b73da64a",
        "compared_period": "third",
        "start_index": 32704,
        "sample_count": 16352,
        "same_index": "required",
        "same_seed": "required",
        "alignment": "prohibited",
        "delay_sweep": "prohibited",
        "gain_fit": "prohibited",
        "dc_removal": "prohibited",
        "polarity_flip": "prohibited",
        "resampling": "prohibited",
        "phase_or_fold_search": "prohibited",
        "output_strobe_sweep": "prohibited",
        "causality_parameter_sweep": "prohibited",
        "passivity_parameter_sweep": "prohibited",
        "truncation_parameter_sweep": "prohibited",
        "nrmse_parameter_sweep": "prohibited",
        "relative_rms_limit": 0.01,
    }:
        raise VerificationError("strict_index_policy")
    report = document.get("report")
    if report != {
        "custody": "external_only",
        "format": "hash_only_json",
        "path": "outside_worktree_required",
        "retained_in_repository": False,
        "includes": ["clean_archive_identity", "source_identity", "reference_identity", "cli_sha256", "manifest_sha256s", "candidate_payload_sha256", "strict_index_metric_bits", "stage_qualified_rejection"],
        "excludes": ["s4p_bytes", "ads_reference_bytes", "candidate_bytes", "waveform_arrays", "absolute_paths"],
        "status_if_strict_compare_fails": "prepared_observed_not_accepted",
        "status_if_any_stage_fails": "rejected_with_stage_and_reason",
    }:
        raise VerificationError("report_policy")
    expected_admission = {
        "preparation_contract_verified": True,
        "external_replay_executed": False,
        "current_candidate_waveform_evaluated": False,
        "current_reference_binding_evaluated": False,
        "strict_index_compare_accepted": False,
        "causal_fir_admitted": False,
        "accepted_receiver": False,
        "p4b_ami_runtime_invoked": False,
        "p5_reference_evaluated": False,
        "release_ledger_promoted": False,
    }
    if document.get("admission") != expected_admission:
        raise VerificationError("admission")
    blockers = set(document.get("blockers", []))
    required_blockers = {
        "t08_two_fresh_external_replay_not_executed",
        "t08_external_s4p_input_missing_from_workspace",
        "t08_external_ads_reference_input_missing_from_workspace",
        "t08_external_product_cli_identity_missing",
        "current_replay_report_not_retained_as_evidence",
        "strict_index_waveform_only_acceptance_requires_owner_gate_after_replay",
    }
    if not required_blockers.issubset(blockers):
        raise VerificationError("blockers")
    inventory = document.get("product_source_inventory")
    if not isinstance(inventory, dict) or set(inventory) != EXPECTED_INVENTORY_PATHS or any(not _hex(value) for value in inventory.values()):
        raise VerificationError("source_inventory_shape")
    if inventory != _archive_inventory(EXPECTED_INVENTORY_PATHS):
        raise VerificationError("source_inventory_drift")
    observer = OBSERVER.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    spec = SPEC.read_text(encoding="utf-8")
    for source, required, forbidden, name in (
        (
            observer,
            ["git", "archive", "--locked", "--offline", "--ignored", RUNNER_TEST, "TemporaryDirectory", "cleanup", "SIPI_P3C_ADS_REFERENCE_CANONICAL_PAYLOAD"],
            ["CircuitSimulator", "run_netlist", "ADS_PYTHON", "dsdump", "ImpMaxFreq", "--include-ignored"],
            "observer",
        ),
        (
            runner,
            ["#[ignore", "generate_selected_p3c_prbs9_impulse_candidate_v2", "admit_selected_p3c_sealed_s4p_v2", "fresh_root", "remove_dir_all", "within_selected_waveform_only_profile"],
            ["CircuitSimulator", "run_netlist", "ADS_PYTHON", "dsdump", "fit_selected", "rational"],
            "runner",
        ),
    ):
        if any(token not in source for token in required):
            raise VerificationError(f"{name}_source_shape")
        if any(token.lower() in source.lower() for token in forbidden):
            raise VerificationError(f"{name}_forbidden_surface")
    if any(token in spec for token in ("run_netlist", "CircuitSimulator")):
        raise VerificationError("spec_forbidden_surface")
    return {"valid": True, "current_replay_preparation": True, "external_replay_executed": False, "release_admitted": False}


def main() -> int:
    try:
        print(verify(yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"exact_impulse_current_replay_preparation_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
