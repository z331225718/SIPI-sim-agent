"""Verify the dedicated current P7 actual-build observation record.

This verifier is intentionally independent of the historical v2 verifier.  A
current clean-archive observation may identify the candidate itself as the
observer; that exception belongs to this schema only.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs" / "baselines" / "p7-current-candidate-build-license-material-observation-evidence.v1.yaml"
SCHEMA = "sipi.p7-current-candidate-build-license-material-observation-evidence.v1"
REPORT_SCHEMA = "sipi.p7-candidate-build-license-material-observation.v2"
MAX_REPORT_BYTES = 128 * 1024
EXPECTED_GATES = {
    "selected_windows_build_package_set_observed": True,
    "license_declared_metadata_observed": True,
    "dependency_snapshot_ready": False,
    "dependencies_approved": False,
    "notices_approved": False,
    "first_party_approved": False,
    "release_sbom": False,
    "release_ready": False,
    "promotion_status": "blocked",
}
EXPECTED_NON_CLAIMS = [
    "license_concluded_NOASSERTION",
    "notice_requirement_not_evaluated",
    "not_a_complete_cargo_lock_snapshot",
    "not_an_spdx_or_cyclonedx_sbom",
    "not_a_notice_or_legal_compatibility_decision",
    "not_a_first_party_promotion_or_release_approval",
]


class EvidenceError(RuntimeError):
    pass


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hex(value: object, length: int = 64) -> str:
    if not isinstance(value, str) or len(value) != length or any(char not in "0123456789abcdef" for char in value):
        raise EvidenceError("invalid_digest")
    return value


def _git_text(*arguments: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *arguments], check=True, capture_output=True).stdout.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise EvidenceError("git_identity_unavailable") from error


def _archive_sha256(commit: str, path: str) -> str:
    try:
        raw = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", commit, path], check=True, capture_output=True).stdout
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            member = archive.getmember(path)
            if not member.isfile() or member.issym() or member.islnk():
                raise EvidenceError("archived_input_invalid")
            stream = archive.extractfile(member)
            if stream is None:
                raise EvidenceError("archived_input_invalid")
            return sha256(stream.read())
    except (OSError, subprocess.CalledProcessError, tarfile.TarError, KeyError) as error:
        if isinstance(error, EvidenceError):
            raise
        raise EvidenceError("archived_input_invalid") from error


def _safe_relative(value: object, suffix: str) -> str:
    if not isinstance(value, str) or not value.endswith(suffix) or "\\" in value or ":" in value or "\0" in value:
        raise EvidenceError("reference_invalid")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise EvidenceError("reference_invalid")
    return value


def _reference(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {"sha256", "bytes"}:
        raise EvidenceError("report_reference_invalid")
    _hex(value.get("sha256"))
    if not isinstance(value.get("bytes"), int) or not 0 < value["bytes"] <= MAX_REPORT_BYTES:
        raise EvidenceError("report_reference_invalid")
    return value


def _load_document() -> dict[str, Any]:
    try:
        value = yaml.safe_load(DOCUMENT.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise EvidenceError("document_unavailable") from error
    if not isinstance(value, dict):
        raise EvidenceError("document_invalid")
    return value


def validate(document: dict[str, Any]) -> None:
    expected = {"schema", "kind", "candidate", "observer", "historical_predecessor", "external_report", "result", "gates", "non_claims", "audit_ref"}
    if set(document) != expected or document.get("schema") != SCHEMA or document.get("kind") != "current_external_actual_build_closure_observation_not_license_decision":
        raise EvidenceError("document_schema_invalid")
    candidate = document.get("candidate")
    if not isinstance(candidate, dict) or set(candidate) != {"commit", "tree", "cargo_lock_sha256", "toolchain_sha256"}:
        raise EvidenceError("candidate_schema_invalid")
    commit = _hex(candidate.get("commit"), 40)
    tree = _hex(candidate.get("tree"), 40)
    _hex(candidate.get("cargo_lock_sha256"))
    _hex(candidate.get("toolchain_sha256"))
    if _git_text("cat-file", "-t", commit) != "commit" or _git_text("rev-parse", f"{commit}^{{tree}}") != tree:
        raise EvidenceError("candidate_git_identity_invalid")
    if _archive_sha256(commit, "Cargo.lock") != candidate["cargo_lock_sha256"] or _archive_sha256(commit, "rust-toolchain.toml") != candidate["toolchain_sha256"]:
        raise EvidenceError("candidate_input_mismatch")

    observer = document.get("observer")
    required_observer = {"source_commit", "source_tree", "path", "sha256", "clean_archive_execution", "checkout_materialization"}
    if not isinstance(observer, dict) or set(observer) != required_observer:
        raise EvidenceError("observer_schema_invalid")
    source_commit = _hex(observer.get("source_commit"), 40)
    source_tree = _hex(observer.get("source_tree"), 40)
    path = _safe_relative(observer.get("path"), ".py")
    _hex(observer.get("sha256"))
    if observer.get("clean_archive_execution") is not True or observer.get("checkout_materialization") != "git_worktree_detached_core_autocrlf_false":
        raise EvidenceError("observer_materialization_invalid")
    if source_commit != commit or source_tree != tree:
        raise EvidenceError("current_observer_binding_invalid")
    if _git_text("cat-file", "-t", source_commit) != "commit" or _git_text("rev-parse", f"{source_commit}^{{tree}}") != source_tree:
        raise EvidenceError("observer_git_identity_invalid")
    if _archive_sha256(source_commit, path) != observer["sha256"]:
        raise EvidenceError("observer_input_mismatch")

    predecessor = document.get("historical_predecessor")
    if not isinstance(predecessor, dict) or set(predecessor) != {"path", "sha256", "status"}:
        raise EvidenceError("historical_predecessor_invalid")
    predecessor_path = _safe_relative(predecessor.get("path"), ".yaml")
    _hex(predecessor.get("sha256"))
    try:
        predecessor_hash = sha256((ROOT / predecessor_path).read_bytes())
    except OSError as error:
        raise EvidenceError("historical_predecessor_invalid") from error
    if predecessor.get("status") != "historical_metadata_superset_rejected_not_actual_build_closure" or predecessor_hash != predecessor["sha256"]:
        raise EvidenceError("historical_predecessor_invalid")

    _reference(document.get("external_report"))
    result = document.get("result")
    if not isinstance(result, dict) or set(result) != {"status", "fresh_builds", "package_set_sha256", "package_counts"}:
        raise EvidenceError("result_invalid")
    if result.get("status") != "selected_windows_build_license_material_observed_not_concluded" or result.get("fresh_builds") != 2:
        raise EvidenceError("result_invalid")
    _hex(result.get("package_set_sha256"))
    if result.get("package_counts") != {"total": 86, "registry": 73, "workspace": 13}:
        raise EvidenceError("result_invalid")
    if document.get("gates") != EXPECTED_GATES or document.get("non_claims") != EXPECTED_NON_CLAIMS:
        raise EvidenceError("blocked_gates_invalid")
    audit_ref = _safe_relative(document.get("audit_ref"), ".md")
    if not audit_ref.startswith("docs/baselines/audits/") or not (ROOT / audit_ref).is_file():
        raise EvidenceError("audit_reference_invalid")


def _read_external(path: Path) -> bytes:
    resolved = path.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise EvidenceError("external_report_required")
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode) or not 0 < before.st_size <= MAX_REPORT_BYTES:
            raise EvidenceError("external_report_invalid")
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise EvidenceError("external_report_invalid") from error
    if before.st_size != len(raw) or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise EvidenceError("external_report_changed_during_read")
    return raw


def _validate_material(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {"path", "sha256", "bytes"}:
        raise EvidenceError("package_license_material_invalid")
    path = value.get("path")
    if not isinstance(path, str) or not path or "\\" in path or ":" in path or "\0" in path or any(part in {"", ".", ".."} for part in path.split("/") ):
        raise EvidenceError("package_license_material_invalid")
    _hex(value.get("sha256"))
    if not isinstance(value.get("bytes"), int) or value["bytes"] < 0:
        raise EvidenceError("package_license_material_invalid")


def _validate_package(value: object) -> str:
    if not isinstance(value, dict) or not isinstance(value.get("kind"), str):
        raise EvidenceError("package_schema_invalid")
    kind = value["kind"]
    if kind == "registry":
        expected = {"identity", "kind", "name", "version", "cargo_lock_checksum", "manifest_sha256", "literal_license", "literal_license_file", "license_materials", "license_concluded", "notice_requirement"}
        if set(value) != expected:
            raise EvidenceError("registry_package_schema_invalid")
        if not all(isinstance(value.get(field), str) and value[field] for field in ("identity", "name", "version")):
            raise EvidenceError("registry_package_schema_invalid")
        checksum = _hex(value.get("cargo_lock_checksum"))
        _hex(value.get("manifest_sha256"))
        if value["identity"] != f"registry:{value['name']}@{value['version']}#{checksum}":
            raise EvidenceError("registry_package_identity_invalid")
    elif kind == "workspace":
        expected = {"identity", "kind", "name", "version", "version_source", "manifest_path", "manifest_sha256", "literal_license", "literal_license_file", "boundary_class", "license_materials", "license_concluded", "notice_requirement"}
        if set(value) != expected:
            raise EvidenceError("workspace_package_schema_invalid")
        if not all(isinstance(value.get(field), str) and value[field] for field in ("identity", "name", "version", "version_source")):
            raise EvidenceError("workspace_package_schema_invalid")
        manifest_path = value.get("manifest_path")
        if not isinstance(manifest_path, str) or not manifest_path.endswith("Cargo.toml") or "\\" in manifest_path or ":" in manifest_path or "\0" in manifest_path or any(part in {"", ".", ".."} for part in manifest_path.split("/")):
            raise EvidenceError("workspace_package_schema_invalid")
        manifest_sha = _hex(value.get("manifest_sha256"))
        if value["identity"] != f"workspace:{value['name']}@{value['version']}#{manifest_sha}":
            raise EvidenceError("workspace_package_identity_invalid")
        boundary = value.get("boundary_class")
        if not isinstance(boundary, dict) or set(boundary) != {"rule", "class", "license", "provenance", "distribution"} or not all(isinstance(item, str) and item for item in boundary.values()):
            raise EvidenceError("workspace_boundary_class_invalid")
    else:
        raise EvidenceError("package_kind_invalid")
    for field in ("literal_license", "literal_license_file"):
        if value[field] is not None and (not isinstance(value[field], str) or not value[field]):
            raise EvidenceError("package_literal_license_invalid")
    if value["license_materials"] is None or not isinstance(value["license_materials"], list):
        raise EvidenceError("package_license_materials_invalid")
    for material in value["license_materials"]:
        _validate_material(material)
    if value["license_concluded"] != "NOASSERTION" or value["notice_requirement"] != "not_evaluated":
        raise EvidenceError("package_conclusion_invalid")
    if kind == "workspace" and value["license_materials"] != []:
        raise EvidenceError("workspace_license_materials_invalid")
    return kind


def verify_external_report(document: dict[str, Any], path: Path) -> None:
    reference = _reference(document["external_report"])
    raw = _read_external(path)
    if len(raw) != reference["bytes"] or sha256(raw) != reference["sha256"]:
        raise EvidenceError("external_report_identity_mismatch")
    try:
        report = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError("external_report_invalid") from error
    expected_keys = {"schema", "status", "candidate", "build", "package_set", "gates", "non_claims"}
    if not isinstance(report, dict) or set(report) != expected_keys or report.get("schema") != REPORT_SCHEMA:
        raise EvidenceError("external_report_invalid")
    if report.get("status") != document["result"]["status"] or report.get("candidate") != document["candidate"]:
        raise EvidenceError("external_report_binding_invalid")
    if report.get("gates") != EXPECTED_GATES or report.get("non_claims") != EXPECTED_NON_CLAIMS:
        raise EvidenceError("external_report_binding_invalid")
    build = report.get("build")
    if not isinstance(build, dict) or set(build) != {"cargo_version_sha256", "target", "release", "locked", "offline", "fresh_builds"}:
        raise EvidenceError("external_report_invalid")
    _hex(build.get("cargo_version_sha256"))
    expected_build = {"target": "x86_64-pc-windows-msvc", "release": True, "locked": True, "offline": True, "fresh_builds": 2}
    if {key: build[key] for key in build if key != "cargo_version_sha256"} != expected_build:
        raise EvidenceError("external_report_binding_invalid")
    package_set = report.get("package_set")
    if not isinstance(package_set, dict) or set(package_set) != {"sha256", "counts", "build_a_stderr_sha256", "build_b_stderr_sha256", "packages"}:
        raise EvidenceError("external_report_invalid")
    _hex(package_set.get("sha256")); _hex(package_set.get("build_a_stderr_sha256")); _hex(package_set.get("build_b_stderr_sha256"))
    if package_set.get("sha256") != document["result"]["package_set_sha256"] or package_set.get("counts") != document["result"]["package_counts"]:
        raise EvidenceError("external_report_binding_invalid")
    packages = package_set.get("packages")
    if not isinstance(packages, list) or len(packages) != package_set["counts"]["total"]:
        raise EvidenceError("external_report_invalid")
    kinds = [_validate_package(item) for item in packages]
    if len(set(item["identity"] for item in packages)) != len(packages):
        raise EvidenceError("package_identity_duplicate")
    counts = {"total": len(packages), "registry": kinds.count("registry"), "workspace": kinds.count("workspace")}
    if counts != package_set["counts"] or counts != {"total": 86, "registry": 73, "workspace": 13}:
        raise EvidenceError("package_counts_invalid")
    canonical = json.dumps(packages, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if sha256(canonical) != package_set["sha256"]:
        raise EvidenceError("package_set_digest_invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    try:
        document = _load_document()
        validate(document)
        if arguments.report is not None:
            verify_external_report(document, arguments.report)
        print(json.dumps({"schema": SCHEMA, "valid": True, "external_report_verified": arguments.report is not None}, sort_keys=True))
        return 0
    except EvidenceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
