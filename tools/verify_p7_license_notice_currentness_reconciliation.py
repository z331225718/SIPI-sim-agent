"""Verify the additive P7 license/NOTICE currentness reconciliation."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import tarfile
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/baselines/p7-license-notice-currentness-reconciliation.v1.yaml"
SCHEMA = "sipi.p7-license-notice-currentness-reconciliation.v1"
BUILD_SCHEMA = "sipi.p7-candidate-build-license-material-observation.v2"
NORMALIZATION_SCHEMA = "sipi.p7-compiled-license-metadata-normalization.v1"
TARGET = "x86_64-pc-windows-msvc"
BASELINE_COMMIT = "805ebb6bbaf588dec08685be4eb78a8ce2fff563"
BASELINE_TREE = "5a378052ea8fdadb8754f22d0a0150088cec6332"
HISTORICAL_COMMIT = "f49849998a9b53fcf56be4a45b2f1fa0418d2588"
HISTORICAL_TREE = "eb14221de2e742f88dcf18ec26e6790c1fb1005b"
OBSERVER_COMMIT = "02fffadab6cce468d95d404baf89d6b62a6756cc"
HISTORICAL_PACKAGE_SET = "ff34e43289a5ba721ac8f5487894d7afd64481f0e71a795ece822a1fe229e927"
BUILD_REPORT_SHA256 = "3a5da5b5ec1a64eb523eb1cd4d586156b9d326237d3615afe024078f3542bd29"
BUILD_REPORT_BYTES = 57976
NORMALIZATION_REPORT_SHA256 = "d023d4680dda293bc2df746f2f2a24b9e40978504b4acaaa5d4b0cb480e15017"
NORMALIZATION_REPORT_BYTES = 1209
OBSERVER_SHA256 = "addcee98d164d64f36f7179ebb4544f22507b129267bd368014d4910b3b9cbd6"
CURRENT_LOCK_SHA256 = "12a9656214b2c5cefc4547a83ed9b2ce57eb629e8dbb062fa1d35724a758ce21"
TOOLCHAIN_SHA256 = "512bedfbbe3c4ef614fbb901b3661f40b4adb701d26c94664e79ca765aa3d109"
LICENSE_MANIFEST_SHA256 = "a79c6da642f634a09884442c83c7f9add1ea170598f262ed83184f0e4de62fad"
EVIDENCE_SHA256 = "3ec62e0a3188830bcf0416bee995b25ac9e017c35eeead33e3e358bcaa2c0199"
NORMALIZATION_EVIDENCE_SHA256 = "45c55cd340d77d4522944423e6eeb66f7218e4eff3e5a727e2de60049523d593"
EXPECTED_COUNTS = {"total": 86, "registry": 73, "workspace": 13}
EXPECTED_CATEGORIES = {
    "declared_string_unparsed": 73,
    "license_file_declared": 0,
    "workspace_inherited_declared_unresolved": 0,
    "metadata_absent": 0,
    "conflicting_or_unbound": 13,
}
EXPECTED_GATES = {
    "historical_package_set_reconciled": True,
    "historical_declared_metadata_reconciled": True,
    "current_package_set_observed": False,
    "current_declared_metadata_observed": False,
    "current_license_file_material_observed": False,
    "current_notice_material_observed": False,
    "dependency_snapshot_ready": False,
    "dependencies_approved": False,
    "notices_approved": False,
    "first_party_approved": False,
    "release_sbom": False,
    "release_ready": False,
    "promotion_status": "blocked",
}
EXPECTED_UNRESOLVED = {
    "current_candidate_source_drift",
    "historical_build_report_bytes_missing",
    "historical_normalization_report_bytes_missing",
    "current_package_member_inventory_missing",
    "current_license_notice_material_identity_missing",
}
EXPECTED_NEXT_INPUTS = {
    "current_build_report_json_with_sha256_and_byte_length",
    "current_normalization_report_json_with_sha256_and_byte_length",
    "current_per_package_registry_lock_checksum_and_manifest_metadata",
    "current_per_package_license_file_notice_copyright_material_sha256_and_byte_length",
    "first_party_product_path_owner_scope_and_approval_input",
    "dependency_distribution_rights_and_notice_review_input",
}


class ReconciliationError(RuntimeError):
    pass


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hex(value: object, length: int = 64) -> str:
    if not isinstance(value, str) or len(value) != length or any(char not in "0123456789abcdef" for char in value):
        raise ReconciliationError("digest_invalid")
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ReconciliationError("document_unavailable") from error
    if not isinstance(value, dict):
        raise ReconciliationError("document_invalid")
    return value


def _git(*arguments: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *arguments], check=True, capture_output=True).stdout.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise ReconciliationError("git_identity_unavailable") from error


def _archive_sha256(commit: str, path: str) -> str:
    try:
        payload = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", commit, path], check=True, capture_output=True).stdout
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
            member = archive.getmember(path)
            if not member.isfile() or member.issym() or member.islnk():
                raise ReconciliationError("archived_input_invalid")
            stream = archive.extractfile(member)
            if stream is None:
                raise ReconciliationError("archived_input_invalid")
            return sha256(stream.read())
    except (OSError, subprocess.CalledProcessError, tarfile.TarError, KeyError) as error:
        raise ReconciliationError("archived_input_invalid") from error


def _safe_relative(value: object, suffix: str) -> str:
    if not isinstance(value, str) or not value.endswith(suffix) or "\\" in value or ":" in value or "\0" in value:
        raise ReconciliationError("reference_invalid")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ReconciliationError("reference_invalid")
    return value


def _assert_keys(value: object, keys: set[str], reason: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ReconciliationError(reason)
    return value


def _assert_external_reference(value: object, digest: str, size: int, reason: str) -> None:
    reference = _assert_keys(value, {"sha256", "bytes", "availability", "verification"}, reason)
    if reference != {"sha256": digest, "bytes": size, "availability": "missing", "verification": "not_run_external_bytes_unavailable"}:
        raise ReconciliationError(reason)


def _validate_historical_evidence(document: dict[str, Any]) -> None:
    historical = _assert_keys(document["historical_build"], {"evidence_ref", "evidence_sha256", "candidate", "observer_source", "external_report", "exact_build", "material_identity"}, "historical_build_invalid")
    evidence_path = ROOT / _safe_relative(historical["evidence_ref"], ".yaml")
    if sha256(evidence_path.read_bytes()) != EVIDENCE_SHA256 or historical["evidence_sha256"] != EVIDENCE_SHA256:
        raise ReconciliationError("historical_evidence_identity_invalid")
    evidence = _load_yaml(evidence_path)
    if evidence.get("schema") != "sipi.p7-candidate-build-license-material-observation-evidence.v2" or evidence.get("kind") != "external_actual_build_closure_observation_not_license_decision":
        raise ReconciliationError("historical_evidence_schema_invalid")
    candidate = _assert_keys(evidence.get("candidate"), {"commit", "tree", "cargo_lock_sha256", "toolchain_sha256"}, "historical_candidate_invalid")
    expected_candidate = {
        "commit": HISTORICAL_COMMIT,
        "tree": HISTORICAL_TREE,
        "cargo_lock_sha256": "d10679ecbb0884cc3325f9b67afaf9a8d61a9f826c262f6fefd437538df34e99",
        "toolchain_sha256": TOOLCHAIN_SHA256,
    }
    if candidate != expected_candidate or historical["candidate"] != expected_candidate:
        raise ReconciliationError("historical_candidate_binding_invalid")
    if _git("show", "-s", "--format=%T", HISTORICAL_COMMIT) != HISTORICAL_TREE or _archive_sha256(HISTORICAL_COMMIT, "Cargo.lock") != expected_candidate["cargo_lock_sha256"] or _archive_sha256(HISTORICAL_COMMIT, "rust-toolchain.toml") != TOOLCHAIN_SHA256:
        raise ReconciliationError("historical_candidate_identity_invalid")
    _assert_external_reference(historical["external_report"], BUILD_REPORT_SHA256, BUILD_REPORT_BYTES, "historical_build_report_reference_invalid")
    exact_build = _assert_keys(historical["exact_build"], {"target", "release", "locked", "offline", "fresh_builds", "package_set_sha256", "package_counts", "package_members"}, "historical_exact_build_invalid")
    if exact_build != {
        "target": TARGET,
        "release": True,
        "locked": True,
        "offline": True,
        "fresh_builds": 2,
        "package_set_sha256": HISTORICAL_PACKAGE_SET,
        "package_counts": EXPECTED_COUNTS,
        "package_members": "unavailable_external_report_bytes",
    }:
        raise ReconciliationError("historical_exact_build_binding_invalid")
    material = _assert_keys(historical["material_identity"], {"per_package_manifest_metadata", "license_file_materials", "notice_candidates"}, "historical_material_identity_invalid")
    if any(value != "unavailable_external_report_bytes" for value in material.values()):
        raise ReconciliationError("historical_material_identity_invalid")
    observer = _assert_keys(historical["observer_source"], {"commit", "tree", "sha256"}, "historical_observer_invalid")
    if observer != {"commit": OBSERVER_COMMIT, "tree": "38e48a367f00e0f767cd43c434bcd1b6242c4f38", "sha256": OBSERVER_SHA256}:
        raise ReconciliationError("historical_observer_binding_invalid")
    if _git("show", "-s", "--format=%T", OBSERVER_COMMIT) != observer["tree"] or _archive_sha256(OBSERVER_COMMIT, "tools/observe_p7_candidate_build_license_material_v2.py") != OBSERVER_SHA256:
        raise ReconciliationError("historical_observer_identity_invalid")


def _validate_normalization(document: dict[str, Any]) -> None:
    normalization = _assert_keys(document["normalization"], {"evidence_ref", "evidence_sha256", "input", "external_report", "record_count", "category_counts", "normalized_records_sha256", "unresolved_set_sha256", "material_identity"}, "normalization_invalid")
    evidence_path = ROOT / _safe_relative(normalization["evidence_ref"], ".yaml")
    if sha256(evidence_path.read_bytes()) != NORMALIZATION_EVIDENCE_SHA256 or normalization["evidence_sha256"] != NORMALIZATION_EVIDENCE_SHA256:
        raise ReconciliationError("normalization_evidence_identity_invalid")
    evidence = _load_yaml(evidence_path)
    if evidence.get("schema") != "sipi.p7-compiled-license-metadata-normalization-evidence.v1" or evidence.get("kind") != "external_structural_metadata_observation_not_license_decision":
        raise ReconciliationError("normalization_evidence_schema_invalid")
    expected_input = {"sha256": BUILD_REPORT_SHA256, "bytes": BUILD_REPORT_BYTES, "package_set_sha256": HISTORICAL_PACKAGE_SET}
    if evidence.get("input") != expected_input or normalization["input"] != expected_input:
        raise ReconciliationError("normalization_input_binding_invalid")
    _assert_external_reference(normalization["external_report"], NORMALIZATION_REPORT_SHA256, NORMALIZATION_REPORT_BYTES, "normalization_report_reference_invalid")
    if evidence.get("external_report") != {"sha256": NORMALIZATION_REPORT_SHA256, "bytes": NORMALIZATION_REPORT_BYTES}:
        raise ReconciliationError("normalization_evidence_report_binding_invalid")
    if normalization["record_count"] != 86 or evidence.get("result", {}).get("record_count") != 86:
        raise ReconciliationError("normalization_record_count_invalid")
    if normalization["category_counts"] != EXPECTED_CATEGORIES or evidence.get("result", {}).get("category_counts") != EXPECTED_CATEGORIES:
        raise ReconciliationError("normalization_category_counts_invalid")
    if normalization["normalized_records_sha256"] != "d0cb395ea32228de4131c0e5dce51aa0484f85bd689b368c2efada398e63b07c" or normalization["unresolved_set_sha256"] != "678479d6023e26b7b9eaba0c2930edaec4cba3c5b09b751c1c530df03bfec27f":
        raise ReconciliationError("normalization_digest_invalid")
    result = evidence.get("result", {})
    if result.get("normalized_records_sha256") != normalization["normalized_records_sha256"] or result.get("unresolved_set_sha256") != normalization["unresolved_set_sha256"]:
        raise ReconciliationError("normalization_digest_binding_invalid")
    if normalization["material_identity"] != "unavailable_external_report_bytes":
        raise ReconciliationError("normalization_material_identity_invalid")


def validate(document: dict[str, Any]) -> None:
    expected = {"schema", "kind", "recorded_at", "baseline", "historical_build", "normalization", "currentness", "gates", "unresolved", "next_required_external_inputs", "non_claims", "audit_ref"}
    if set(document) != expected or document.get("schema") != SCHEMA or document.get("kind") != "additive_currentness_reconciliation_not_legal_conclusion" or document.get("recorded_at") != "2026-08-21":
        raise ReconciliationError("document_schema_invalid")
    baseline = _assert_keys(document["baseline"], {"commit", "tree", "cargo_lock_sha256", "toolchain_sha256", "observer", "license_manifest"}, "baseline_invalid")
    if baseline["commit"] != BASELINE_COMMIT or baseline["tree"] != BASELINE_TREE or _git("show", "-s", "--format=%T", BASELINE_COMMIT) != BASELINE_TREE:
        raise ReconciliationError("baseline_git_identity_invalid")
    if baseline["cargo_lock_sha256"] != CURRENT_LOCK_SHA256 or _archive_sha256(BASELINE_COMMIT, "Cargo.lock") != CURRENT_LOCK_SHA256:
        raise ReconciliationError("baseline_lock_identity_invalid")
    if baseline["toolchain_sha256"] != TOOLCHAIN_SHA256 or _archive_sha256(BASELINE_COMMIT, "rust-toolchain.toml") != TOOLCHAIN_SHA256:
        raise ReconciliationError("baseline_toolchain_identity_invalid")
    observer = _assert_keys(baseline["observer"], {"path", "sha256"}, "baseline_observer_invalid")
    observer_path = _safe_relative(observer["path"], ".py")
    if observer_path != "tools/observe_p7_candidate_build_license_material_v2.py" or observer["sha256"] != OBSERVER_SHA256 or _archive_sha256(BASELINE_COMMIT, observer_path) != OBSERVER_SHA256:
        raise ReconciliationError("baseline_observer_identity_invalid")
    license_manifest = _assert_keys(baseline["license_manifest"], {"path", "sha256"}, "baseline_license_manifest_invalid")
    manifest_path = ROOT / _safe_relative(license_manifest["path"], ".yaml")
    if license_manifest["sha256"] != LICENSE_MANIFEST_SHA256 or sha256(manifest_path.read_bytes()) != LICENSE_MANIFEST_SHA256:
        raise ReconciliationError("baseline_license_manifest_identity_invalid")

    _validate_historical_evidence(document)
    _validate_normalization(document)

    currentness = _assert_keys(document["currentness"], {"state", "candidate_commit_matches_baseline", "candidate_tree_matches_baseline", "candidate_cargo_lock_matches_baseline", "candidate_toolchain_matches_baseline", "observer_source_commit_matches_baseline", "observer_byte_identity_matches_baseline", "current_build_replay", "current_package_set", "current_declared_metadata", "current_license_file_material_identity", "current_notice_material_identity"}, "currentness_invalid")
    expected_currentness = {
        "state": "historical_source_drift_and_external_bytes_missing",
        "candidate_commit_matches_baseline": False,
        "candidate_tree_matches_baseline": False,
        "candidate_cargo_lock_matches_baseline": False,
        "candidate_toolchain_matches_baseline": True,
        "observer_source_commit_matches_baseline": False,
        "observer_byte_identity_matches_baseline": True,
        "current_build_replay": "not_observed",
        "current_package_set": "unavailable",
        "current_declared_metadata": "unavailable",
        "current_license_file_material_identity": "unavailable",
        "current_notice_material_identity": "unavailable",
    }
    if currentness != expected_currentness:
        raise ReconciliationError("currentness_binding_invalid")
    if document["gates"] != EXPECTED_GATES:
        raise ReconciliationError("gates_invalid")
    unresolved = document["unresolved"]
    if not isinstance(unresolved, list) or {item.get("id") for item in unresolved if isinstance(item, dict)} != EXPECTED_UNRESOLVED or any(item.get("status") != "blocked" for item in unresolved if isinstance(item, dict)):
        raise ReconciliationError("unresolved_invalid")
    next_inputs = document["next_required_external_inputs"]
    if not isinstance(next_inputs, list) or set(next_inputs) != EXPECTED_NEXT_INPUTS:
        raise ReconciliationError("next_inputs_invalid")
    non_claims = document["non_claims"]
    required_non_claims = {"cargo_license_strings_are_not_legal_conclusions", "historical_counts_do_not_prove_current_package_members", "missing_notice_material_bytes_do_not_prove_notice_not_required", "not_an_spdx_or_cyclonedx_sbom", "not_a_dependency_or_first_party_approval", "not_a_notice_or_legal_compatibility_decision", "not_release_ready", "promotion_status_blocked"}
    if not isinstance(non_claims, list) or set(non_claims) != required_non_claims:
        raise ReconciliationError("non_claims_invalid")
    audit_ref = _safe_relative(document["audit_ref"], ".md")
    if not audit_ref.startswith("docs/baselines/audits/") or not (ROOT / audit_ref).is_file():
        raise ReconciliationError("audit_reference_invalid")


def _read_external(path: Path) -> bytes:
    resolved = path.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise ReconciliationError("external_report_required")
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
            raise ReconciliationError("external_report_invalid")
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise ReconciliationError("external_report_invalid") from error
    if before.st_size != len(raw) or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ReconciliationError("external_report_changed")
    return raw


def verify_external_pair(build_path: Path, normalization_path: Path, document: dict[str, Any]) -> None:
    build_raw = _read_external(build_path)
    if len(build_raw) != BUILD_REPORT_BYTES or sha256(build_raw) != BUILD_REPORT_SHA256:
        raise ReconciliationError("historical_build_report_identity_mismatch")
    try:
        build = json.loads(build_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReconciliationError("historical_build_report_invalid") from error
    if not isinstance(build, dict) or build.get("schema") != BUILD_SCHEMA or build.get("candidate") != document["historical_build"]["candidate"]:
        raise ReconciliationError("historical_build_report_binding_invalid")
    package_set = build.get("package_set")
    if not isinstance(package_set, dict) or package_set.get("sha256") != HISTORICAL_PACKAGE_SET or package_set.get("counts") != EXPECTED_COUNTS or not isinstance(package_set.get("packages"), list) or len(package_set["packages"]) != EXPECTED_COUNTS["total"]:
        raise ReconciliationError("historical_build_report_package_set_invalid")
    normalization_raw = _read_external(normalization_path)
    if len(normalization_raw) != NORMALIZATION_REPORT_BYTES or sha256(normalization_raw) != NORMALIZATION_REPORT_SHA256:
        raise ReconciliationError("historical_normalization_report_identity_mismatch")
    try:
        normalization = json.loads(normalization_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReconciliationError("historical_normalization_report_invalid") from error
    if not isinstance(normalization, dict) or normalization.get("schema") != NORMALIZATION_SCHEMA or normalization.get("input") != document["normalization"]["input"] or normalization.get("result", {}).get("record_count") != 86:
        raise ReconciliationError("historical_normalization_report_binding_invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-report", type=Path)
    parser.add_argument("--normalization-report", type=Path)
    arguments = parser.parse_args()
    try:
        document = _load_yaml(DOCUMENT)
        validate(document)
        if (arguments.build_report is None) != (arguments.normalization_report is None):
            raise ReconciliationError("external_report_pair_required")
        external_inputs_verified = arguments.build_report is not None
        if external_inputs_verified:
            verify_external_pair(arguments.build_report, arguments.normalization_report, document)
        print(json.dumps({"schema": SCHEMA, "valid": True, "currentness_state": document["currentness"]["state"], "external_inputs_verified": external_inputs_verified}, sort_keys=True))
        return 0
    except ReconciliationError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
