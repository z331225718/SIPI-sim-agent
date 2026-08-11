"""Verify hash-only external CLI evidence for the selected matched-S21 profile."""

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
from verify_channel_s2p_matched_external_compare_evidence import verify_document as verify_core_evidence


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.channel.s2p-matched.cli-external-compare-evidence.v1"
REPORT_SCHEMA = "sipi.channel.required-profile-cli-compare.v1"
PROFILE_ID = "channel-s2p-channel-16ghz-3db-v1"
CONTRACT = ROOT / "docs" / "baselines" / "channel-s2p-matched-acceptance.v1.yaml"
CORE_EVIDENCE = ROOT / "docs" / "baselines" / "channel-s2p-matched-external-compare-evidence.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "channel-s2p-matched-cli-external-compare-evidence.v1.yaml"
COMPARATOR = ROOT / "tools" / "compare_channel_s2p_matched_cli.py"
TREE_PATHS = {
    "sipi-cli": "crates/sipi-cli",
    "sipi-contracts": "crates/sipi-contracts",
    "sipi-touchstone": "crates/sipi-touchstone",
    "sipi-channel": "crates/sipi-channel",
    "sipi-types": "crates/sipi-types",
}
NON_CLAIMS = [
    "This gate accepts only the selected external S2P text through the bounded CLI path.",
    "Ordinary caller input remains unattested at runtime because the CLI has no external asset identity.",
    "It does not establish general Touchstone, reflection, Link/eye/BER, artifact, or release behavior.",
]


class EvidenceError(RuntimeError):
    pass


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _sha1(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


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
    value = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "blob", f"{revision}:{path}"],
        check=True,
        capture_output=True,
    ).stdout
    return hashlib.sha256(value).hexdigest()


def _load_report(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError("external_report_invalid") from error
    if not isinstance(value, dict):
        raise EvidenceError("external_report_invalid")
    return value


def _validate_comparison(value: object, policy: dict[str, Any], require_passed: bool) -> None:
    keys = {
        "passed", "max_absolute_error", "max_relative_error", "max_normalized_error_ratio",
        "allowed_error_at_worst_index", "worst_index", "absolute_tolerance", "relative_tolerance",
    }
    if not _exact(value, keys) or (require_passed and value["passed"] is not True):
        raise EvidenceError("comparison_invalid")
    if not all(_finite(value[key]) for key in keys - {"passed", "worst_index"}):
        raise EvidenceError("comparison_invalid")
    if not isinstance(value["worst_index"], int) or not 0 <= value["worst_index"] < 400:
        raise EvidenceError("comparison_invalid")
    accepted = policy["acceptance"]["kernel_compare"]
    if (
        value["absolute_tolerance"] != accepted["absolute_tolerance_v_per_v"]
        or value["relative_tolerance"] != accepted["relative_tolerance"]
        or value["max_normalized_error_ratio"] > 1.0
        or value["max_absolute_error"] > value["allowed_error_at_worst_index"]
    ):
        raise EvidenceError("comparison_invalid")


def _validate_report_binding(evidence: dict[str, Any], report: dict[str, Any], policy: dict[str, Any]) -> None:
    keys = {
        "schema", "profile_id", "status", "accepted", "policy_sha256", "source", "environment",
        "observer", "request", "product", "response", "comparison", "non_claims",
    }
    if not _exact(report, keys) or report["schema"] != REPORT_SCHEMA or report["profile_id"] != PROFILE_ID:
        raise EvidenceError("external_report_schema_invalid")
    if report["status"] != "passed" or report["accepted"] is not True or report["non_claims"] != NON_CLAIMS:
        raise EvidenceError("external_report_not_accepted")
    if report["policy_sha256"] != evidence["contract"]["sha256"] or report["source"] != evidence["source"]:
        raise EvidenceError("external_report_contract_binding_mismatch")
    if report["environment"] != evidence["environment"]:
        raise EvidenceError("external_report_environment_mismatch")
    if report["observer"] != evidence["observer"]:
        raise EvidenceError("external_report_observer_mismatch")
    if report["request"] != evidence["request"]:
        raise EvidenceError("external_report_request_mismatch")
    product = report["product"]
    expected_product = {
        key: evidence["product"][key]
        for key in (
            "source_commit", "source_tree", "cargo_lock_sha256", "executable",
            "executable_sha256", "executable_bytes", "cli_kernel_sha256_f64le",
        )
    }
    expected_product["cargo_version"] = product.get("cargo_version")
    if not isinstance(product.get("cargo_version"), str) or not product["cargo_version"] or product != expected_product:
        raise EvidenceError("external_report_product_mismatch")
    if report["response"] != evidence["response"]:
        raise EvidenceError("external_report_response_mismatch")
    _validate_comparison(report["comparison"], policy, True)
    if report["comparison"] != evidence["comparison"] | {"passed": True}:
        raise EvidenceError("external_report_comparison_mismatch")


def verify_document(document: object, report_path: Path | None = None, source_root: Path | None = None) -> dict[str, Any]:
    keys = {
        "schema", "status", "profile_id", "contract", "core_evidence", "comparator",
        "external_report", "source", "environment", "observer", "request", "product",
        "response", "comparison", "non_claims",
    }
    if not _exact(document, keys) or document["schema"] != SCHEMA:
        raise EvidenceError("evidence_schema_invalid")
    if document["status"] != "accepted" or document["profile_id"] != PROFILE_ID or document["non_claims"] != NON_CLAIMS:
        raise EvidenceError("evidence_status_invalid")
    contract = document["contract"]
    if not _exact(contract, {"schema", "sha256"}) or contract["schema"] != "sipi.channel.s2p-matched-acceptance.v1" or contract["sha256"] != _sha256_file(CONTRACT):
        raise EvidenceError("evidence_contract_invalid")
    policy = _load(CONTRACT)
    if source_root is not None and not verify_policy(policy, source_root)["valid"]:
        raise EvidenceError("evidence_policy_invalid")
    core = document["core_evidence"]
    if not _exact(core, {"schema", "sha256"}) or core["schema"] != "sipi.channel.s2p-matched.external-compare-evidence.v1" or core["sha256"] != _sha256_file(CORE_EVIDENCE):
        raise EvidenceError("evidence_core_invalid")
    if not verify_core_evidence(_load(CORE_EVIDENCE), source_root=source_root)["valid"]:
        raise EvidenceError("evidence_core_invalid")
    comparator = document["comparator"]
    if not _exact(comparator, {"path", "sha256"}) or comparator["path"] != "tools/compare_channel_s2p_matched_cli.py" or comparator["sha256"] != _sha256_file(COMPARATOR):
        raise EvidenceError("evidence_comparator_invalid")
    source_keys = {"canonical_origin", "commit", "tree", "path", "git_blob", "content_sha256", "redistribution"}
    expected_source = {key: policy["source"][key] for key in source_keys}
    if document["source"] != expected_source:
        raise EvidenceError("evidence_source_mismatch")
    if document["environment"] != {"platform": "windows-x86_64", "environment_hash": document["environment"].get("environment_hash")} or not _sha256(document["environment"]["environment_hash"]):
        raise EvidenceError("evidence_environment_invalid")
    observer = document["observer"]
    if not _exact(observer, {"implementation", "fresh_runs", "kernel_sha256_f64le", "fft_length", "sample_interval_seconds"}) or observer["implementation"] != "standard_dft_observer_v1" or observer["fresh_runs"] != 2 or not _sha256(observer["kernel_sha256_f64le"]) or observer["fft_length"] != 400 or observer["sample_interval_seconds"] != policy["acceptance"]["dft"]["sample_interval_seconds"]:
        raise EvidenceError("evidence_observer_invalid")
    request = document["request"]
    if not _exact(request, {"schema", "sha256", "source_byte_length", "source_sha256"}) or request["schema"] != "sipi.channel.matched-two-port-kernel-run-request.v1" or not _sha256(request["sha256"]) or not isinstance(request["source_byte_length"], int) or request["source_byte_length"] <= 0 or request["source_sha256"] != expected_source["content_sha256"]:
        raise EvidenceError("evidence_request_invalid")
    product = document["product"]
    product_keys = {"source_commit", "source_tree", "source_trees", "cargo_lock_blob", "cargo_lock_sha256", "executable", "executable_sha256", "executable_bytes", "cli_kernel_sha256_f64le"}
    if not _exact(product, product_keys) or not _sha1(product["source_commit"]) or not _sha1(product["source_tree"]) or not _exact(product["source_trees"], set(TREE_PATHS)) or not _sha1(product["cargo_lock_blob"]) or not _sha256(product["cargo_lock_sha256"]) or product["executable"] != "sipi.exe" or not _sha256(product["executable_sha256"]) or not isinstance(product["executable_bytes"], int) or product["executable_bytes"] <= 0 or not _sha256(product["cli_kernel_sha256_f64le"]):
        raise EvidenceError("evidence_product_invalid")
    try:
        if _git_tree(product["source_commit"]) != product["source_tree"]:
            raise EvidenceError("evidence_product_source_drift")
        for name, path in TREE_PATHS.items():
            if not _sha1(product["source_trees"][name]) or _git_object(product["source_commit"], path) != product["source_trees"][name] or _git_object("HEAD", path) != product["source_trees"][name]:
                raise EvidenceError("evidence_product_source_drift")
        if _git_object(product["source_commit"], "Cargo.lock") != product["cargo_lock_blob"] or _git_object("HEAD", "Cargo.lock") != product["cargo_lock_blob"] or _git_blob_sha256(product["source_commit"], "Cargo.lock") != product["cargo_lock_sha256"]:
            raise EvidenceError("evidence_product_source_drift")
    except subprocess.CalledProcessError as error:
        raise EvidenceError("evidence_product_source_drift") from error
    response = document["response"]
    expected_response = {
        "schema": "sipi.channel.matched-two-port-kernel-run-result.v1",
        "stdout_sha256": response.get("stdout_sha256"),
        "command": "channel",
        "status": "ok",
        "diagnostic_count": 0,
        "evaluation_scope": "matched_s21_periodic_kernel_only",
        "external_profile_acceptance": "caller_input_unattested",
    }
    if response != expected_response or not _sha256(response["stdout_sha256"]):
        raise EvidenceError("evidence_response_invalid")
    _validate_comparison(document["comparison"] | {"passed": True}, policy, True)
    report = document["external_report"]
    if not _exact(report, {"schema", "sha256", "custody"}) or report["schema"] != REPORT_SCHEMA or not _sha256(report["sha256"]) or report["custody"] != "operator_external_only":
        raise EvidenceError("evidence_report_invalid")
    if report_path is not None:
        if _sha256_file(report_path) != report["sha256"]:
            raise EvidenceError("external_report_hash_mismatch")
        _validate_report_binding(document, _load_report(report_path), policy)
    return {"schema": SCHEMA, "valid": True, "profile_id": PROFILE_ID, "report_bound": report_path is not None, "evidence_level": "fresh_report_bound" if report_path is not None else "hash_only_attestation"}


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
