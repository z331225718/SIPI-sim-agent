"""Verify hash-only external evidence for the selected matched-S21 kernel."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

from verify_channel_s2p_matched_acceptance import _load, verify_document as verify_policy


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.channel.s2p-matched.external-compare-evidence.v1"
REPORT_SCHEMA = "sipi.channel.required-profile-compare.v1"
PROFILE_ID = "channel-s2p-channel-16ghz-3db-v1"
CONTRACT = ROOT / "docs" / "baselines" / "channel-s2p-matched-acceptance.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "channel-s2p-matched-external-compare-evidence.v1.yaml"
COMPARATOR = ROOT / "tools" / "compare_channel_s2p_matched.py"
REPORT_NON_CLAIMS = [
    "This gate compares only the frozen matched-S21 discrete V/V kernel.",
    "It does not establish public Touchstone support, reflection handling, Link/eye/BER parity, or a default route.",
    "The report retains hashes and metrics only; it retains no external asset or kernel array.",
]


class EvidenceError(RuntimeError):
    pass


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _sha1(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_object(revision: str, path: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", f"{revision}:{path}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_tree(revision: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", f"{revision}^{{tree}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_blob_sha256(revision: str, path: str) -> str:
    payload = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "blob", f"{revision}:{path}"],
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(payload).hexdigest()


def _load_report(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError("external_report_invalid") from error
    if not isinstance(value, dict):
        raise EvidenceError("external_report_invalid")
    return value


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _validate_report_binding(evidence: dict[str, Any], report: dict[str, Any]) -> None:
    expected_keys = {
        "schema", "profile_id", "status", "accepted", "policy_sha256", "source",
        "environment", "observer", "product_input", "product", "comparison", "non_claims",
    }
    if set(report) != expected_keys or report["schema"] != REPORT_SCHEMA or report["profile_id"] != PROFILE_ID:
        raise EvidenceError("external_report_schema_invalid")
    if report["status"] != "passed" or report["accepted"] is not True:
        raise EvidenceError("external_report_not_accepted")
    if report["non_claims"] != REPORT_NON_CLAIMS:
        raise EvidenceError("external_report_non_claims_mismatch")
    if report["policy_sha256"] != evidence["contract"]["sha256"] or report["source"] != evidence["source"]:
        raise EvidenceError("external_report_contract_binding_mismatch")
    expected_environment = {"platform": "windows-x86_64", "environment_hash": evidence["observer"]["environment_hash"]}
    if report["environment"] != expected_environment:
        raise EvidenceError("external_report_environment_mismatch")
    observer = report["observer"]
    if not _exact(observer, {"implementation", "fresh_run_kernel_sha256_f64le", "fft_length", "sample_interval_seconds"}) or observer["implementation"] != evidence["observer"]["implementation"] or observer["fresh_run_kernel_sha256_f64le"] != evidence["observer"]["kernel_sha256_f64le"] or observer["fft_length"] != evidence["observer"]["fft_length"] or observer["sample_interval_seconds"] != evidence["observer"]["sample_interval_seconds"]:
        raise EvidenceError("external_report_observer_mismatch")
    if report["product_input"] != evidence["product"]["product_input"]:
        raise EvidenceError("external_report_product_input_mismatch")
    product = report["product"]
    product_keys = {"cargo_lock_sha256", "cargo_version", "fft_length", "kernel_sha256_f64le", "runner", "runner_bytes", "runner_sha256", "sample_interval_seconds", "source_commit", "source_tree"}
    if not _exact(product, product_keys) or product["runner"] != "sipi-channel-kernel-runner" or not isinstance(product["cargo_version"], str) or not product["cargo_version"] or product["source_commit"] != evidence["product"]["source_commit"] or product["source_tree"] != evidence["product"]["source_tree"] or product["cargo_lock_sha256"] != evidence["product"]["cargo_lock_sha256"] or product["runner_sha256"] != evidence["product"]["runner_sha256"] or product["runner_bytes"] != evidence["product"]["runner_bytes"] or product["kernel_sha256_f64le"] != evidence["product"]["kernel_sha256_f64le"] or product["fft_length"] != evidence["product"]["fft_length"] or product["sample_interval_seconds"] != evidence["product"]["sample_interval_seconds"]:
        raise EvidenceError("external_report_product_mismatch")
    comparison = report["comparison"]
    expected_comparison = evidence["comparison"] | {"passed": True}
    if not _exact(comparison, set(expected_comparison)) or comparison != expected_comparison:
        raise EvidenceError("external_report_comparison_mismatch")


def verify_document(document: object, report_path: Path | None = None, source_root: Path | None = None) -> dict[str, Any]:
    required = {"schema", "status", "profile_id", "contract", "comparator", "external_report", "source", "observer", "product", "comparison", "non_claims"}
    if not _exact(document, required) or document["schema"] != SCHEMA:
        raise EvidenceError("evidence_schema_invalid")
    if document["status"] != "accepted" or document["profile_id"] != PROFILE_ID:
        raise EvidenceError("evidence_status_invalid")
    comparator = document["comparator"]
    if not _exact(comparator, {"path", "sha256"}) or comparator["path"] != "tools/compare_channel_s2p_matched.py" or not _sha256(comparator["sha256"]) or _sha256_file(COMPARATOR) != comparator["sha256"]:
        raise EvidenceError("evidence_comparator_invalid")
    contract = document["contract"]
    if not _exact(contract, {"schema", "sha256"}) or contract["schema"] != "sipi.channel.s2p-matched-acceptance.v1" or not _sha256(contract["sha256"]) or _sha256_file(CONTRACT) != contract["sha256"]:
        raise EvidenceError("evidence_contract_invalid")
    acceptance = _load(CONTRACT)
    source_keys = {"canonical_origin", "commit", "tree", "path", "git_blob", "content_sha256", "redistribution"}
    expected_source = {key: acceptance["source"][key] for key in source_keys}
    if document["source"] != expected_source:
        raise EvidenceError("evidence_source_mismatch")
    if source_root is not None:
        result = verify_policy(acceptance, source_root)
        if not result["valid"]:
            raise EvidenceError("external_source_policy_invalid")
    external_report = document["external_report"]
    if not _exact(external_report, {"schema", "sha256", "custody"}) or external_report["schema"] != REPORT_SCHEMA or not _sha256(external_report["sha256"]) or external_report["custody"] != "operator_external_only":
        raise EvidenceError("evidence_report_invalid")
    observer = document["observer"]
    if not _exact(observer, {"implementation", "fresh_runs", "kernel_sha256_f64le", "fft_length", "sample_interval_seconds", "environment_hash"}) or observer["implementation"] != "standard_dft_observer_v1" or observer["fresh_runs"] != 2 or not _sha256(observer["kernel_sha256_f64le"]) or observer["fft_length"] != 400 or observer["sample_interval_seconds"] != acceptance["acceptance"]["dft"]["sample_interval_seconds"] or not _sha256(observer["environment_hash"]):
        raise EvidenceError("evidence_observer_invalid")
    product = document["product"]
    tree_paths = {"sipi-channel": "crates/sipi-channel", "sipi-types": "crates/sipi-types"}
    product_keys = {"source_commit", "source_tree", "source_trees", "cargo_lock_blob", "cargo_lock_sha256", "runner_sha256", "runner_bytes", "product_input", "kernel_sha256_f64le", "fft_length", "sample_interval_seconds"}
    if not _exact(product, product_keys) or not _sha1(product["source_commit"]) or not _sha1(product["source_tree"]) or not _exact(product["source_trees"], set(tree_paths)) or not _sha1(product["cargo_lock_blob"]) or not _sha256(product["cargo_lock_sha256"]) or not _sha256(product["runner_sha256"]) or not isinstance(product["runner_bytes"], int) or product["runner_bytes"] <= 0 or not _sha256(product["kernel_sha256_f64le"]) or product["fft_length"] != 400 or product["sample_interval_seconds"] != acceptance["acceptance"]["dft"]["sample_interval_seconds"]:
        raise EvidenceError("evidence_product_invalid")
    expected_input_keys = {"schema", "sha256", "one_sided_sample_count", "frequency_step_hz", "reference_impedance_ohm"}
    if not _exact(product["product_input"], expected_input_keys) or product["product_input"]["schema"] != "sipi.channel.matched-spectrum-binary.v1" or not _sha256(product["product_input"]["sha256"]) or product["product_input"]["one_sided_sample_count"] != 201 or product["product_input"]["frequency_step_hz"] != 100000000.0 or product["product_input"]["reference_impedance_ohm"] != 50.0:
        raise EvidenceError("evidence_product_input_invalid")
    try:
        if _git_tree(product["source_commit"]) != product["source_tree"]:
            raise EvidenceError("evidence_product_source_drift")
        for name, path in tree_paths.items():
            if not _sha1(product["source_trees"][name]) or _git_object(product["source_commit"], path) != product["source_trees"][name] or _git_object("HEAD", path) != product["source_trees"][name]:
                raise EvidenceError("evidence_product_source_drift")
        if _git_object(product["source_commit"], "Cargo.lock") != product["cargo_lock_blob"] or _git_object("HEAD", "Cargo.lock") != product["cargo_lock_blob"] or _git_blob_sha256(product["source_commit"], "Cargo.lock") != product["cargo_lock_sha256"]:
            raise EvidenceError("evidence_product_source_drift")
    except subprocess.CalledProcessError as error:
        raise EvidenceError("evidence_product_source_drift") from error
    comparison = document["comparison"]
    expected_tolerances = acceptance["acceptance"]["kernel_compare"]
    if not _exact(comparison, {"absolute_tolerance", "relative_tolerance", "max_absolute_error", "max_relative_error", "max_normalized_error_ratio", "allowed_error_at_worst_index", "worst_index"}) or not all(_finite(comparison[key]) for key in ("absolute_tolerance", "relative_tolerance", "max_absolute_error", "max_relative_error", "max_normalized_error_ratio", "allowed_error_at_worst_index")) or not isinstance(comparison["worst_index"], int) or comparison["worst_index"] < 0 or comparison["worst_index"] >= 400 or comparison["absolute_tolerance"] != expected_tolerances["absolute_tolerance_v_per_v"] or comparison["relative_tolerance"] != expected_tolerances["relative_tolerance"] or comparison["max_normalized_error_ratio"] > 1.0 or comparison["allowed_error_at_worst_index"] < comparison["absolute_tolerance"] or comparison["max_absolute_error"] > comparison["allowed_error_at_worst_index"]:
        raise EvidenceError("evidence_comparison_invalid")
    if not isinstance(document["non_claims"], list) or not document["non_claims"] or any(not isinstance(item, str) or not item for item in document["non_claims"]):
        raise EvidenceError("evidence_non_claims_invalid")
    if report_path is not None:
        if _sha256_file(report_path) != external_report["sha256"]:
            raise EvidenceError("external_report_hash_mismatch")
        _validate_report_binding(document, _load_report(report_path))
    return {
        "schema": SCHEMA,
        "valid": True,
        "profile_id": PROFILE_ID,
        "report_bound": report_path is not None,
        "evidence_level": "fresh_report_bound" if report_path is not None else "hash_only_attestation",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--source-root", type=Path)
    arguments = parser.parse_args()
    try:
        result = verify_document(_load(arguments.evidence), arguments.report, arguments.source_root)
    except (EvidenceError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
