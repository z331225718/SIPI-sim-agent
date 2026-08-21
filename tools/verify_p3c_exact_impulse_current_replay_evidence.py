"""Verify the blocked, hash-only T08 P3C exact impulse replay observation.

This gate is intentionally read-only.  It never opens an external S4P,
reference payload, executable, or historical report.  A valid record proves
only that the exact S4P was observed and that the replay was blocked before
the ignored Rust runner because the exact ADS payload was unavailable.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p3c-exact-impulse-current-replay-evidence.v1.yaml"
SCHEMA = "sipi.p3c-exact-impulse-current-replay-evidence.v1"
COMMIT = "805ebb6bbaf588dec08685be4eb78a8ce2fff563"
TREE = "5a378052ea8fdadb8754f22d0a0150088cec6332"
CONTRACT_PATH = "docs/baselines/p3c-exact-impulse-current-replay-preparation.v1.yaml"
CONTRACT_SHA256 = "9709f18df807381dd024d15e6979976e7b7d5ddb32aca953d43d2b8875d8bc36"
SPEC_PATH = "docs/clean-room/specs/p3c-exact-impulse-current-replay-preparation.v1.md"
SPEC_SHA256 = "bc2746a2a6c075c0ce62d21c117f99183b60b205684130e817bb3dddaaba90c0"
OBSERVER_PATH = "tools/observe_p3c_exact_impulse_current_replay_preparation.py"
OBSERVER_SHA256 = "e775c7275f0d1b94d7da8e7e11750748fdd8249b031dda682aeeabf64a3cd3f5"
S4P = {
    "logical_name": "channel_gen5_highloss.s4p",
    "byte_length": 1834156,
    "sha256": "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47",
    "custody": "external_only",
    "exact_identity_observed": True,
}
ADS = {
    "logical_name": "ads_canonical_triple_payload_le_f64.bin",
    "expected_byte_length": 1177344,
    "expected_sha256": "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726",
    "tuple_format": "little_endian_f64_time_tx_differential_rx_differential",
    "observed_column": "rx_differential",
    "samples": 49056,
    "sample_interval_bits": "3d712e0be826d695",
    "custody": "external_only",
    "exact_identity_observed": False,
    "missing_reason": "no_exact_external_bytes_available",
    "search": {
        "status": "no_exact_bytes_found",
        "scope": ["ads_workspace_data_root", "known_external_reference_and_artifact_roots"],
        "logical_name_matches": 0,
        "exact_length_matches": 0,
        "sha256_match_attempted": False,
        "bytes_reconstructed": False,
        "historical_summary_substituted": False,
        "old_report_reused": False,
    },
}
CLI = {
    "logical_name": "sipi.exe",
    "custody": "external_only",
    "clean_archive_commit": COMMIT,
    "clean_archive_build": True,
    "cargo_profile": "release",
    "cargo_locked": True,
    "cargo_offline": True,
    "target_external": True,
    "byte_length": 3975168,
    "sha256": "11c4ff6c81a4420ed95317b211d474c49ce55ab8224cf0d9e6a44efb50156c02",
    "bytes_tracked_in_repository": False,
}
EXPECTED_TOP_KEYS = {
    "schema",
    "ticket",
    "status",
    "authority",
    "baseline",
    "observer",
    "rust_runner_probe",
    "inputs",
    "replay",
    "admission",
    "blockers",
    "non_claims",
}
EXPECTED_AUTHORITY = {
    "actor": "project",
    "decision_ref": "task-t08-2026-08-21-exact-impulse-current-replay",
    "scope": "exact_selected_s4p_ads_reference_current_v2_impulse_replay_only",
}
EXPECTED_OBSERVER_INVOCATION = {
    "mode": "locked_offline_clean_archive_external_target",
    "command": "cargo test --locked --offline -p sipi-p3c --test p3c_external_ads_selected_highloss_waveform_only_runner -- --ignored p3c_external_ads_selected_highloss_waveform_only_runner_v2",
    "clean_archive_materialized": False,
    "clean_archive_bytes_retained": False,
    "external_target": True,
    "status": "rejected_before_runner",
    "rejection_stage": "external_input_preflight",
    "rejection_reason": "ads_reference_missing_exact_bytes",
    "report_written": False,
    "report_bytes_retained": False,
}
EXPECTED_RUST_RUNNER_PROBE = {
    "command": "cargo test --locked --offline -p sipi-p3c --test p3c_external_ads_selected_highloss_waveform_only_runner -- --ignored p3c_external_ads_selected_highloss_waveform_only_runner_v2",
    "ignored_test": "p3c_external_ads_selected_highloss_waveform_only_runner_v2",
    "clean_archive_materialized": True,
    "clean_archive_bytes_retained": False,
    "external_target": True,
    "status": "rejected_missing_external_reference",
    "rejection_stage": "reference_identity",
    "rejection_reason": "reference_open",
    "report_written": False,
    "report_bytes_retained": False,
}
EXPECTED_REPLAY = {
    "route": "ieee_bsd_impulse_only",
    "fresh_replay_runs": 0,
    "fresh_custody_runs": 0,
    "runner_invoked": False,
    "candidate_waveform_evaluated": False,
    "reference_waveform_evaluated": False,
    "candidate_payload_sha256": None,
    "reference_rx_payload_sha256": None,
    "strict_index_nrmse_bits": None,
    "strict_index_nrmse_limit_bits": "3f847ae147ae147b",
    "strict_index_compare_status": "blocked_missing_ads_reference",
    "blocker": "t08_external_ads_reference_exact_bytes_missing",
}
EXPECTED_ADMISSION = {
    "selected_s4p_identity_observed": True,
    "ads_reference_identity_observed": False,
    "product_cli_identity_observed": True,
    "locked_offline_release_build_observed": True,
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
EXPECTED_BLOCKERS = [
    "t08_external_ads_reference_exact_bytes_missing",
    "t08_two_fresh_replay_not_executed",
    "t08_candidate_reference_binding_not_evaluated",
    "strict_index_waveform_only_acceptance_not_evaluated",
]
EXPECTED_NON_CLAIMS = [
    "This is a structured blocked external-input observation, not current waveform evidence.",
    "The exact ADS canonical payload was not reconstructed from its hash, and no historical summary or old report was substituted.",
    "No ADS simulator was launched; no candidate or reference waveform bytes were retained.",
    "No rational fit, delay or alignment search, gain or DC fitting, polarity transform, parameter sweep, or tolerance relaxation was performed.",
    "The selected S4P identity and clean-archive release CLI build are recorded, but they do not promote the candidate or any receiver or release gate.",
]


class VerificationError(ValueError):
    """Evidence does not satisfy the fail-closed T08 contract."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hex(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and all(character in "0123456789abcdef" for character in value)


def _safe_relative(value: object) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise VerificationError("absolute_or_parent_path")
    return Path(value)


def _git_tree(root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", f"{COMMIT}^{{tree}}"],
        capture_output=True,
        check=False,
        text=True,
        encoding="ascii",
    )
    if completed.returncode != 0:
        raise VerificationError("baseline_commit_missing")
    return completed.stdout.strip()


def _check_hash_binding(binding: object, expected_path: str, expected_hash: str, root: Path) -> None:
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise VerificationError("hash_binding_shape")
    if binding["path"] != expected_path or binding["sha256"] != expected_hash:
        raise VerificationError("hash_binding_identity")
    path = root / _safe_relative(binding["path"])
    if not path.is_file() or _sha256(path) != expected_hash:
        raise VerificationError("hash_binding_drift")


def verify(document: object, root: Path = ROOT) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != EXPECTED_TOP_KEYS:
        raise VerificationError("top_level_shape")
    if document["schema"] != SCHEMA or document["ticket"] != "T08" or document["status"] != "external_only_two_fresh_current_replay_blocked_missing_ads_reference":
        raise VerificationError("record_identity")
    if document["authority"] != EXPECTED_AUTHORITY:
        raise VerificationError("authority")
    baseline = document["baseline"]
    if not isinstance(baseline, dict) or set(baseline) != {"commit", "tree", "preparation_contract", "preparation_spec"}:
        raise VerificationError("baseline_shape")
    if baseline["commit"] != COMMIT or baseline["tree"] != TREE or _git_tree(root) != TREE:
        raise VerificationError("baseline_identity")
    _check_hash_binding(baseline["preparation_contract"], CONTRACT_PATH, CONTRACT_SHA256, root)
    _check_hash_binding(baseline["preparation_spec"], SPEC_PATH, SPEC_SHA256, root)

    observer = document["observer"]
    if not isinstance(observer, dict) or set(observer) != {"path", "sha256", "invocation"}:
        raise VerificationError("observer_shape")
    if observer["path"] != OBSERVER_PATH or observer["sha256"] != OBSERVER_SHA256:
        raise VerificationError("observer_identity")
    observer_path = root / _safe_relative(observer["path"])
    if not observer_path.is_file() or _sha256(observer_path) != OBSERVER_SHA256:
        raise VerificationError("observer_drift")
    if observer["invocation"] != EXPECTED_OBSERVER_INVOCATION:
        raise VerificationError("observer_invocation")

    if document["rust_runner_probe"] != EXPECTED_RUST_RUNNER_PROBE:
        raise VerificationError("rust_runner_probe")

    inputs = document["inputs"]
    if not isinstance(inputs, dict) or set(inputs) != {"selected_s4p", "ads_reference", "product_cli"}:
        raise VerificationError("inputs_shape")
    if inputs["selected_s4p"] != S4P or inputs["ads_reference"] != ADS or inputs["product_cli"] != CLI:
        raise VerificationError("input_identity")
    if not _hex(CLI["sha256"]) or CLI["byte_length"] <= 0:
        raise VerificationError("cli_digest")

    if document["replay"] != EXPECTED_REPLAY:
        raise VerificationError("replay_blocked_state")
    if document["admission"] != EXPECTED_ADMISSION:
        raise VerificationError("admission_fail_closed")
    if document["blockers"] != EXPECTED_BLOCKERS:
        raise VerificationError("blockers")
    if document["non_claims"] != EXPECTED_NON_CLAIMS:
        raise VerificationError("non_claims")

    serialized = json.dumps(document, sort_keys=True, separators=(",", ":"))
    if any(token in serialized for token in ("file://", "http://", "https://", "C:/", "C:\\\\", "samples:[", "waveform:[")):
        raise VerificationError("path_or_payload_leak")
    return {
        "valid": True,
        "ticket": "T08",
        "status": document["status"],
        "external_replay_executed": False,
        "ads_reference_available": False,
        "release_admitted": False,
    }


def main() -> int:
    try:
        document = yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        print(json.dumps(verify(document), sort_keys=True))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"exact_impulse_current_replay_evidence_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
