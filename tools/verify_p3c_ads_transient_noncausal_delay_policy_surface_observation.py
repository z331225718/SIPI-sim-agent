"""Fail closed on the selected ADS transient noncausal-delay observation."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-ads-transient-noncausal-delay-policy-surface-observation-evidence.v1.yaml"
SCHEMA = "sipi.p3c-ads-transient-noncausal-delay-policy-surface-observation-evidence.v1"
COMMIT = "418a1908019428f43f34530f1801e3ca15f79ac0"
TREE = "8916cb56e8a41dd7da137090bd16b32e366900d9"
EXTERNAL_HASHES = {"8ae52a7220beb88d0102ed2fdd5c0edb12b8125260326ef97949db0b792b35d1", "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47", "621851d5d3bd754b898c27bccd641da3dae08954ef902f72b6609bd8f093a7e0"}
ARCHIVED_HASHES = {
    "tools/observe_p3c_ads_transient_noncausal_delay_policy_fresh.py": "9c2631286d18d44c6a3e210333470f55b112c4b287ac7d18e9cdcdae617b5077",
    "tools/observe_p3c_ads_transient_noncausal_delay_policy.py": "892a93407ed58a5c07c133d5029a76969ede768bc091ac140cdf2e82868752cd",
    "tools/run_p3c_external_ads_fixed_pulse_operator.py": "806147101f559a865c14cc89290ad596d4dce91aad8048d35f33a8f97654d360",
    "docs/baselines/p3c-ieee-bsd-inline-causality-direct-port.v1.yaml": "bda815e60696a7108558d8403398eb6d5dcc39cf3b5ec5eff29149ce0bf13fcd",
}


class VerificationError(ValueError):
    pass


def archived_hash(path: str) -> str:
    result = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", COMMIT, path], check=True, capture_output=True)
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        files = [member for member in archive.getmembers() if member.isfile()]
        if len(files) != 1 or files[0].name != path:
            raise VerificationError("clean_archive_inventory_shape_invalid")
        payload = archive.extractfile(files[0])
        if payload is None:
            raise VerificationError("clean_archive_inventory_payload_missing")
        return hashlib.sha256(payload.read()).hexdigest()


def tracked_hashes() -> set[str]:
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], check=True, capture_output=True).stdout.split(b"\0")
    return {hashlib.sha256((ROOT / path.decode("utf-8")).read_bytes()).hexdigest() for path in files if path}


def expected() -> dict[str, object]:
    return {
        "schema": SCHEMA, "status": "external_ads_transient_noncausal_delay_policy_surface_observed_no_selected_run_action_claim",
        "authority": {"actor": "user", "decision_ref": "user-delegated-owner-discretion-2026-08-15", "scope": "one_read_only_ads_transient_noncausal_delay_policy_surface_observation_only"},
        "predecessors": {"charter": "docs/baselines/p3c-ads-transient-noncausal-delay-policy-surface-charter.v1.yaml", "fresh_custody_spec": "docs/clean-room/specs/p3c-ads-transient-noncausal-delay-fresh-custody.v1.md"},
        "external_observation": {
            "schema": "sipi.p3c-ads-transient-noncausal-delay-policy-fresh-observation.v1", "custody": "external_only_hash_only", "result_path_retained": False, "result_byte_length": 1950, "result_content_sha256": "8ae52a7220beb88d0102ed2fdd5c0edb12b8125260326ef97949db0b792b35d1", "clean_archive_commit": COMMIT, "clean_archive_tree": TREE, "fresh_observations": 2, "canonical_repeatability": "identical", "cleanup_status": "complete",
            "source": {"logical_name": "channel_gen5_highloss.s4p", "byte_length": 1834156, "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"},
            "ads_document": {"logical_name": "Troubleshooting_a_Transient-Convolution_Simulation.html", "byte_length": 78496, "sha256": "621851d5d3bd754b898c27bccd641da3dae08954ef902f72b6609bd8f093a7e0"},
            "tool_inventory": {"fresh_custody_harness": ARCHIVED_HASHES["tools/observe_p3c_ads_transient_noncausal_delay_policy_fresh.py"], "child_observer": ARCHIVED_HASHES["tools/observe_p3c_ads_transient_noncausal_delay_policy.py"], "fixed_pwl_runner": ARCHIVED_HASHES["tools/run_p3c_external_ads_fixed_pulse_operator.py"], "product_no_delay_contract": ARCHIVED_HASHES["docs/baselines/p3c-ieee-bsd-inline-causality-direct-port.v1.yaml"]},
            "fixed_pwl_netlist": {"sha256": "5a9e7f1b0f969220832e2baa776640bc76ef5183ac8bf63e5a94b7a488cb1a82", "imp_max_freq_hz": 40_000_000_000.0, "imp_delta_freq_hz": 39_062_500.0, "imp_mode": 1, "imp_noncausal_length": "not_declared"},
            "documented_policy": {"controller_introduces_delay_to_force_causality": True, "imp_noncausal_length_default": 32, "timestep_relation": "documentation_states_timestep_set_by_default_imp_max_freq"},
            "product_no_delay_contract": {"delay_extraction_implemented": False, "caller_delay_or_alignment_override": "prohibited"},
        },
        "independent_audit": {"reviewer": "Orca_reused_OpenCode_terminal", "terminal": "term_2de7cb74-b803-4e20-bb5b-4803777c24f8", "status": "pending_platform_payment_required", "result": "not_run", "report": None},
        "admission": {"ads_transient_noncausal_delay_policy_surface_documented": True, "selected_netlist_implicit_noncausal_length_surface_observed": True, "product_no_delay_contract_bound": True, "selected_run_delay_action_observed": False, "delay_seconds_derived": False, "ads_algorithm_reproduced": False, "alignment_authorized": False, "candidate_waveform_accepted": False, "release_ledger_promoted": False},
        "blockers": ["selected_run_delay_action_not_observable_from_document_and_netlist_only", "exact_delay_seconds_not_authorized_or_observed", "documented_delay_policy_not_algorithm_attribution", "waveform_mismatch_cause_not_identified"],
        "non_claims": ["The documentation policy surface does not prove that this selected ADS run introduced a delay.", "No delay duration, ADS algorithm, alignment authorization, candidate acceptance, receiver, P4B, P5, or release result is derived.", "No ADS document, S4P, netlist, external result, waveform, dataset, or absolute path is retained in the repository."],
    }


def verify(document: object) -> dict[str, object]:
    if document != expected():
        raise VerificationError("noncausal_delay_policy_surface_evidence_invalid")
    if subprocess.run(["git", "-C", str(ROOT), "rev-parse", f"{COMMIT}^{{tree}}"], check=True, capture_output=True, text=True).stdout.strip() != TREE:
        raise VerificationError("clean_archive_tree_drift")
    if any(archived_hash(path) != digest for path, digest in ARCHIVED_HASHES.items()):
        raise VerificationError("clean_archive_inventory_drift")
    if EXTERNAL_HASHES & tracked_hashes():
        raise VerificationError("external_custody_leak")
    return {"valid": True, "selected_run_delay_action_observed": False, "delay_seconds_derived": False, "candidate_waveform_accepted": False}


if __name__ == "__main__":
    try:
        print(json.dumps(verify(yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))), sort_keys=True))
    except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError, yaml.YAMLError) as error:
        print(f"noncausal_delay_policy_surface_verification_failed:{error}", file=sys.stderr)
        raise SystemExit(1)
