"""Verify the bounded P3C selected-S4P external custody observation charter."""

from __future__ import annotations

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-selected-s4p-external-static-custody-observation-contract.v1.yaml"
RUNNER = ROOT / "crates" / "sipi-p3c" / "tests" / "p3c_sealed_s4p_external_runner.rs"
OBSERVER = ROOT / "tools" / "observe_p3c_sealed_selected_s4p_custody.py"
SCHEMA = "sipi.p3c-selected-s4p-external-static-custody-observation-contract.v1"


class VerificationError(ValueError):
    pass


def verify(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VerificationError("custody_contract_schema_invalid")
    if document.get("status") != "external_only_two_fresh_custody_observation_authorized_pending":
        raise VerificationError("custody_contract_status_invalid")
    if document.get("selected_asset") != {
        "logical_name": "channel_gen5_highloss.s4p", "byte_length": 1834156,
        "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47",
        "asset_bytes_tracked": False,
    }:
        raise VerificationError("custody_contract_asset_invalid")
    if document.get("execution") != {
        "custody": "external_only", "clean_git_archive": "required",
        "runner": "p3c_sealed_s4p_external_runner", "fresh_temporary_artifact_roots": 2,
        "artifact_id_reuse_between_runs": "prohibited", "source_identity_checks": "before_stage_after_equal",
        "sealed_file": "channel.s4p", "required_product_api": "admit_selected_p3c_sealed_s4p_v1",
        "report_path": "external_only_hash_and_aggregate_facts",
        "no_hostile_concurrent_writer_assumption": "required", "cleanup_failure": "reject",
    }:
        raise VerificationError("custody_contract_execution_invalid")
    expected_admission = {
        "custody_observation_harness_implemented": True, "external_static_custody_observed": False,
        "selected_external_s4p_static_admitted": False, "real_constrained_fit_invoked": False,
        "analytic_stepping_implemented": False, "candidate_waveform_generated": False,
        "external_reference_binding_evaluated": False, "candidate_metric_acceptance_evaluated": False,
        "accepted_receiver": False, "product_runtime_invoked": False, "p4b_ami_runtime_invoked": False,
        "release_ledger_promoted": False,
    }
    if document.get("admission") != expected_admission:
        raise VerificationError("custody_contract_promotion_invalid")
    blockers = set(document.get("blockers", []))
    if "two_fresh_external_sealed_s4p_custody_observations_missing" not in blockers or any(
        document["admission"][key] for key in ("real_constrained_fit_invoked", "analytic_stepping_implemented", "candidate_waveform_generated")
    ):
        raise VerificationError("custody_contract_blocker_invalid")
    runner = RUNNER.read_text(encoding="utf-8")
    observer = OBSERVER.read_text(encoding="utf-8")
    required_runner = [
        "#[ignore", "source_identity(source)?", "stage_reader(SELECTED_P3C_S4P_FILE_NAME_V1",
        "admit_selected_p3c_sealed_s4p_v1", "fs::remove_dir_all", "first.manifest_sha256 == second.manifest_sha256",
    ]
    required_observer = [
        "git", "archive", "clean_archive", "--locked", "--offline", "parse_runner_report",
        "report_must_be_outside_worktree", "\"fresh_custody_runs\"",
    ]
    if any(token not in runner for token in required_runner) or any(token not in observer for token in required_observer):
        raise VerificationError("custody_contract_source_drift")
    forbidden_runner = ["CircuitSimulator", "GetWave", "fit_selected", "run_netlist", "Command::new"]
    if any(token in runner.lower() for token in forbidden_runner):
        raise VerificationError("custody_contract_forbidden_surface")
    return {"valid": True, "custody_observation_harness_implemented": True, "external_static_custody_observed": False}


def main() -> int:
    try:
        print(verify(yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"selected_s4p_custody_contract_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
