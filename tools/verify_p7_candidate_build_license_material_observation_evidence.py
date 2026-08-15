"""Verify the hash-only, rejected P7 Cargo license-material observation."""

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
DOCUMENT = ROOT / "docs" / "baselines" / "p7-candidate-build-license-material-observation-evidence.v1.yaml"
SCHEMA = "sipi.p7-candidate-build-license-material-observation-evidence.v1"
REPORT_SCHEMA = "sipi.p7-candidate-build-license-material-observation.v1"
MAX_REPORT_BYTES = 16 * 1024
EXPECTED_GATES = {
    "selected_windows_build_package_set_observed": False,
    "license_declared_metadata_observed": False,
    "dependency_snapshot_ready": False,
    "dependencies_approved": False,
    "notices_approved": False,
    "first_party_approved": False,
    "release_sbom": False,
    "release_ready": False,
    "promotion_status": "blocked",
}
EXPECTED_NON_CLAIMS = [
    "offline_build_closure_not_observed",
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
        completed = subprocess.run(["git", "-C", str(ROOT), *arguments], check=True, capture_output=True)
        return completed.stdout.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise EvidenceError("git_identity_unavailable") from error


def _archived_sha256(commit: str, path: str) -> str:
    try:
        raw = subprocess.run(
            ["git", "-C", str(ROOT), "archive", "--format=tar", commit, path], check=True, capture_output=True
        ).stdout
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


def _safe_relative_file(value: object, *, suffix: str) -> str:
    if not isinstance(value, str) or not value.endswith(suffix) or "\\" in value or ":" in value or "\0" in value:
        raise EvidenceError("reference_invalid")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise EvidenceError("reference_invalid")
    return value


def _reference(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {"sha256", "bytes"}:
        raise EvidenceError("report_reference_invalid")
    _hex(value.get("sha256"))
    if not isinstance(value.get("bytes"), int) or value["bytes"] <= 0 or value["bytes"] > MAX_REPORT_BYTES:
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
    expected = {
        "schema", "kind", "candidate", "observer", "external_report", "result", "gates", "non_claims", "audit_ref"
    }
    if set(document) != expected or document.get("schema") != SCHEMA or document.get("kind") != "external_rejected_observation_not_license_decision":
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
    if _archived_sha256(commit, "Cargo.lock") != candidate["cargo_lock_sha256"]:
        raise EvidenceError("candidate_lock_mismatch")
    if _archived_sha256(commit, "rust-toolchain.toml") != candidate["toolchain_sha256"]:
        raise EvidenceError("candidate_toolchain_mismatch")

    observer = document.get("observer")
    expected_observer = {"source_commit", "source_tree", "path", "sha256", "clean_archive_execution", "checkout_materialization"}
    if not isinstance(observer, dict) or set(observer) != expected_observer:
        raise EvidenceError("observer_schema_invalid")
    source_commit = _hex(observer.get("source_commit"), 40)
    source_tree = _hex(observer.get("source_tree"), 40)
    path = _safe_relative_file(observer.get("path"), suffix=".py")
    _hex(observer.get("sha256"))
    if observer.get("clean_archive_execution") is not True or observer.get("checkout_materialization") != "git_worktree_detached_core_autocrlf_false":
        raise EvidenceError("observer_materialization_invalid")
    if _git_text("cat-file", "-t", source_commit) != "commit" or _git_text("rev-parse", f"{source_commit}^{{tree}}") != source_tree:
        raise EvidenceError("observer_git_identity_invalid")
    ancestry = subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, source_commit], capture_output=True, check=False)
    if ancestry.returncode != 0 or commit == source_commit:
        raise EvidenceError("candidate_observer_lineage_invalid")
    if _archived_sha256(source_commit, path) != observer["sha256"]:
        raise EvidenceError("observer_source_mismatch")

    _reference(document.get("external_report"))
    result = document.get("result")
    expected_result = {
        "status": "selected_windows_build_license_material_rejected",
        "rejection_stage": "build_closure",
        "rejection_reason": "cargo_metadata_failed",
        "fresh_builds": 2,
        "package_set_observed": False,
    }
    if result != expected_result:
        raise EvidenceError("result_invalid")
    if document.get("gates") != EXPECTED_GATES or document.get("non_claims") != EXPECTED_NON_CLAIMS:
        raise EvidenceError("blocked_gates_invalid")
    audit_ref = _safe_relative_file(document.get("audit_ref"), suffix=".md")
    if not audit_ref.startswith("docs/baselines/audits/") or not (ROOT / audit_ref).is_file():
        raise EvidenceError("audit_reference_invalid")


def _read_external(path: Path) -> bytes:
    resolved = path.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise EvidenceError("external_report_required")
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode) or before.st_size <= 0 or before.st_size > MAX_REPORT_BYTES:
            raise EvidenceError("external_report_invalid")
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise EvidenceError("external_report_invalid") from error
    if before.st_size != len(raw) or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise EvidenceError("external_report_changed_during_read")
    return raw


def verify_external_report(document: dict[str, Any], path: Path) -> None:
    reference = _reference(document["external_report"])
    raw = _read_external(path)
    if len(raw) != reference["bytes"] or sha256(raw) != reference["sha256"]:
        raise EvidenceError("external_report_identity_mismatch")
    try:
        report = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError("external_report_invalid") from error
    if not isinstance(report, dict):
        raise EvidenceError("external_report_invalid")
    expected_keys = {"schema", "status", "candidate", "build", "gates", "non_claims"}
    if set(report) != expected_keys or report.get("schema") != REPORT_SCHEMA or report.get("status") != document["result"]["status"]:
        raise EvidenceError("external_report_invalid")
    if report.get("candidate") != document["candidate"] or report.get("gates") != EXPECTED_GATES or report.get("non_claims") != EXPECTED_NON_CLAIMS:
        raise EvidenceError("external_report_binding_invalid")
    build = report.get("build")
    expected_build = {"cargo_version_sha256", "target", "release", "locked", "offline", "fresh_builds", "rejection_stage", "rejection_reason"}
    if not isinstance(build, dict) or set(build) != expected_build or not isinstance(build.get("cargo_version_sha256"), str):
        raise EvidenceError("external_report_invalid")
    _hex(build["cargo_version_sha256"])
    if {key: build[key] for key in expected_build if key != "cargo_version_sha256"} != {
        "target": "x86_64-pc-windows-msvc", "release": True, "locked": True, "offline": True,
        "fresh_builds": 2, "rejection_stage": "build_closure", "rejection_reason": "cargo_metadata_failed",
    }:
        raise EvidenceError("external_report_binding_invalid")


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
