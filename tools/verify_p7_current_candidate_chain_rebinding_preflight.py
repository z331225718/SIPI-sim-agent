"""Verify the hash-only rejected P7 current-candidate rebinding preflight."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs" / "baselines" / "p7-current-candidate-chain-rebinding-preflight.v1.yaml"
SCHEMA = "sipi.p7-current-candidate-chain-rebinding-preflight.v1"
TWIN_SCHEMA = "sipi.p7-windows-twin-build-report.v1"
REQUIRED_BLOCKERS = {
    "license_notice_pending",
    "fresh_machine_evidence_missing",
    "uncertified_domain_profiles",
    "current_candidate_p7_chain_not_admitted",
}
EXPECTED_LAYOUT_STDOUT = b'{"schema":"sipi.release-layout-report.v1","status":"rejected","reason":"pe_rejected"}\n'


class PreflightError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hex(value: object, length: int = 64) -> str:
    if not isinstance(value, str) or len(value) != length or any(character not in "0123456789abcdef" for character in value):
        raise PreflightError("invalid_digest")
    return value


def _load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        document = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PreflightError("invalid_json") from error
    if not isinstance(document, dict):
        raise PreflightError("invalid_json")
    return document, payload


def _git_text(*arguments: str) -> str:
    try:
        completed = subprocess.run(["git", "-C", str(ROOT), *arguments], check=True, capture_output=True)
        return completed.stdout.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise PreflightError("git_object_unavailable") from error


def _git_archived_member_sha256(commit: str, path: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "archive", "--format=tar", commit, path],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise PreflightError("candidate_input_unavailable") from error
    try:
        with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as bundle:
            member = bundle.getmember(path)
            if not member.isfile() or member.issym() or member.islnk():
                raise PreflightError("candidate_input_unavailable")
            stream = bundle.extractfile(member)
            if stream is None:
                raise PreflightError("candidate_input_unavailable")
            return sha256_bytes(stream.read())
    except (tarfile.TarError, KeyError) as error:
        raise PreflightError("candidate_input_unavailable") from error


def _external(path: Path) -> bool:
    resolved = path.resolve()
    return resolved != ROOT and ROOT not in resolved.parents


def validate(document: dict[str, Any]) -> None:
    expected = {
        "schema", "kind", "candidate_source_commit", "candidate_tree", "candidate_cargo_lock_sha256",
        "candidate_toolchain_sha256", "twin_build", "static_layout", "downstream", "global_blockers",
        "promotion_status", "release_candidate", "non_claims",
    }
    if set(document) != expected or document.get("schema") != SCHEMA or document.get("kind") != "historical_rejected_preflight_not_release":
        raise PreflightError("document_schema_invalid")
    commit = _hex(document.get("candidate_source_commit"), 40)
    tree = _hex(document.get("candidate_tree"), 40)
    for field in ("candidate_cargo_lock_sha256", "candidate_toolchain_sha256"):
        _hex(document.get(field))
    if _git_text("cat-file", "-t", commit) != "commit" or _git_text("rev-parse", f"{commit}^{{tree}}") != tree:
        raise PreflightError("candidate_git_identity_invalid")
    if _git_archived_member_sha256(commit, "Cargo.lock") != document["candidate_cargo_lock_sha256"]:
        raise PreflightError("candidate_lock_mismatch")
    if _git_archived_member_sha256(commit, "rust-toolchain.toml") != document["candidate_toolchain_sha256"]:
        raise PreflightError("candidate_toolchain_mismatch")

    twin = document.get("twin_build")
    if not isinstance(twin, dict) or set(twin) != {"status", "report_sha256", "binary_sha256", "binary_bytes"}:
        raise PreflightError("twin_schema_invalid")
    if twin.get("status") != "identical" or not isinstance(twin.get("binary_bytes"), int) or twin["binary_bytes"] <= 0:
        raise PreflightError("twin_status_invalid")
    for field in ("report_sha256", "binary_sha256"):
        _hex(twin.get(field))

    layout = document.get("static_layout")
    expected_layout = {"policy_sha256", "stage_executable_sha256", "exit_code", "stdout_sha256", "stdout_bytes", "result", "report_retained"}
    if not isinstance(layout, dict) or set(layout) != expected_layout:
        raise PreflightError("layout_schema_invalid")
    for field in ("policy_sha256", "stage_executable_sha256", "stdout_sha256"):
        _hex(layout.get(field))
    if (
        layout.get("stage_executable_sha256") != twin["binary_sha256"]
        or layout.get("exit_code") != 2
        or layout.get("stdout_sha256") != sha256_bytes(EXPECTED_LAYOUT_STDOUT)
        or layout.get("stdout_bytes") != len(EXPECTED_LAYOUT_STDOUT)
        or layout.get("result") != "rejected_pe_rejected"
        or layout.get("report_retained") is not False
    ):
        raise PreflightError("layout_rejection_invalid")

    downstream = document.get("downstream")
    expected_downstream = {
        "composition_invoked", "archive_invoked", "install_invoked", "performance_observation_invoked",
        "candidate_evaluation_invoked", "reason",
    }
    if (
        not isinstance(downstream, dict)
        or set(downstream) != expected_downstream
        or any(downstream[key] is not False for key in expected_downstream if key != "reason")
        or downstream.get("reason") != "static_layout_preflight_rejected"
    ):
        raise PreflightError("downstream_gate_invalid")
    blockers = document.get("global_blockers")
    if not isinstance(blockers, list) or len(blockers) != len(set(blockers)) or set(blockers) != REQUIRED_BLOCKERS:
        raise PreflightError("global_blockers_invalid")
    non_claims = document.get("non_claims")
    if not isinstance(non_claims, list) or not non_claims or len(non_claims) != len(set(non_claims)) or any(not isinstance(value, str) or not value for value in non_claims):
        raise PreflightError("non_claims_invalid")
    if document.get("promotion_status") != "blocked" or document.get("release_candidate") is not False:
        raise PreflightError("promotion_state_invalid")


def _read_regular_external(path: Path, reason: str) -> bytes:
    if not _external(path) or not path.is_file() or path.is_symlink():
        raise PreflightError(reason)
    try:
        return path.read_bytes()
    except OSError as error:
        raise PreflightError(reason) from error


def verify_external_observation(
    document: dict[str, Any],
    twin_path: Path,
    layout_stdout_path: Path,
    layout_policy_path: Path,
    stage_executable_path: Path,
) -> None:
    if not all(_external(path) for path in (twin_path, layout_stdout_path, layout_policy_path, stage_executable_path)):
        raise PreflightError("external_evidence_required")
    twin, raw = _load_json(twin_path)
    expected_twin = document["twin_build"]
    if sha256_bytes(raw) != expected_twin["report_sha256"]:
        raise PreflightError("twin_digest_mismatch")
    expected_keys = {"schema", "status", "commit", "tree", "lock_sha256", "toolchain_sha256", "rustflags_sha256", "target", "build_a", "build_b", "comparison", "limitations"}
    if set(twin) != expected_keys or twin.get("schema") != TWIN_SCHEMA or twin.get("status") != "identical":
        raise PreflightError("twin_report_invalid")
    if (
        twin.get("commit") != document["candidate_source_commit"]
        or twin.get("tree") != document["candidate_tree"]
        or twin.get("lock_sha256") != document["candidate_cargo_lock_sha256"]
        or twin.get("toolchain_sha256") != document["candidate_toolchain_sha256"]
        or twin.get("comparison") != {"size_match": True, "digest_match": True}
    ):
        raise PreflightError("twin_identity_mismatch")
    for key in ("build_a", "build_b"):
        build = twin.get(key)
        if not isinstance(build, dict) or build.get("binary_sha256") != expected_twin["binary_sha256"] or build.get("binary_bytes") != expected_twin["binary_bytes"]:
            raise PreflightError("twin_binary_mismatch")
    layout_stdout = _read_regular_external(layout_stdout_path, "layout_stdout_unavailable")
    layout = document["static_layout"]
    if layout_stdout != EXPECTED_LAYOUT_STDOUT or sha256_bytes(layout_stdout) != layout["stdout_sha256"]:
        raise PreflightError("layout_stdout_mismatch")
    if sha256_bytes(_read_regular_external(layout_policy_path, "layout_policy_unavailable")) != layout["policy_sha256"]:
        raise PreflightError("layout_policy_mismatch")
    stage = _read_regular_external(stage_executable_path, "stage_executable_unavailable")
    if (
        sha256_bytes(stage) != layout["stage_executable_sha256"]
        or len(stage) != expected_twin["binary_bytes"]
    ):
        raise PreflightError("stage_executable_mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document", type=Path, default=DOCUMENT)
    parser.add_argument("--twin-report", type=Path)
    parser.add_argument("--layout-stdout", type=Path)
    parser.add_argument("--layout-policy", type=Path)
    parser.add_argument("--stage-executable", type=Path)
    arguments = parser.parse_args()
    try:
        document, raw = _load_json(arguments.document)
        validate(document)
        external = (arguments.twin_report, arguments.layout_stdout, arguments.layout_policy, arguments.stage_executable)
        if any(value is None for value in external) and any(value is not None for value in external):
            raise PreflightError("paired_external_evidence_required")
        if arguments.twin_report is not None:
            verify_external_observation(document, arguments.twin_report, arguments.layout_stdout, arguments.layout_policy, arguments.stage_executable)
        print(json.dumps({"schema": SCHEMA, "valid": True, "document_sha256": sha256_bytes(raw)}, sort_keys=True))
        return 0
    except PreflightError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
