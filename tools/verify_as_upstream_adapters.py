"""Verify the AS-01..AS-06 Agent-Spice external adapter evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "baselines" / "as-upstream-adapter-contracts.v1.yaml"
EXPECTED_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
EXPECTED_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
EXPECTED_SOURCE_INDEX_SHA256 = "0d1f2cc0ad66d457c7f40eb6ead0fed40373f2f4c5690345fbfb9cb708dc461d"
EXPECTED_COMMANDS = {
    "AS-01": ("fit-sparam", "FitSparamRequest"),
    "AS-02": ("fit-sparam-cascade", "FitSparamCascadeRequest"),
    "AS-03": ("fit-yparam", "FitYparamRequest"),
    "AS-04": ("tune-yparam-tran", "TuneYparamTranRequest"),
    "AS-05": ("run-hspice", "RunHspiceRequest"),
    "AS-06": ("run-rfm", "RunRfmRequest"),
}
REQUIRED_ADAPTER_MARKERS = (
    "UPSTREAM_COMMIT",
    "OutputLimitExceeded",
    "CancellationToken",
    "capture_artifacts",
    "validate_output_admission",
    "validate_required_artifacts",
    "RequiredArtifactMissing",
    "terminate_process_tree",
    "recv_timeout",
    "ReaderDrainTimedOut",
    "symlink_metadata",
    "reap_child_until",
    "CommandWrap",
    "JobObject",
    "FailClosedJobSetup",
    "KillSuspendedOnDrop",
    "ProcessIsolationFailed",
    "ProcessTerminationFailed",
    "process-wrap",
    "artifact_max_depth",
    "artifact_directories",
    "artifact_path_bytes",
    "argv_bytes",
    "artifact_manifest_sha256",
    "runtime_source_authenticated",
    "caller_supplied_unverified",
    "is_windows_reparse_point",
    "read_failed",
    "no_upstream_cli_default",
)
REQUIRED_TEST_MARKERS = (
    "fit_sparam_missing_required_output_is_rejected",
    "fit_sparam_required_output_is_accepted",
    "fit_sparam_cascade_missing_required_output_is_rejected",
    "fit_sparam_cascade_required_output_is_accepted",
    "fit_yparam_missing_required_output_is_rejected",
    "fit_yparam_required_output_is_accepted",
    "tune_yparam_tran_missing_required_output_is_rejected",
    "tune_yparam_tran_required_output_is_accepted",
    "run_hspice_missing_required_output_is_rejected",
    "run_hspice_required_output_is_accepted",
    "run_rfm_missing_required_output_is_rejected",
    "run_rfm_required_output_is_accepted",
    "parent_exit_kills_job_before_reader_drain",
    "output_overflow_kills_descendant_job",
    "execute_revalidates_public_run_request_backend_state",
    "artifact-empty-directory-path-limit",
    "preexisting_required_output_is_rejected_before_spawn",
    "cancellation_terminates_descendant_job",
    "clean_parent_exit_terminates_detached_descendant_job",
    "nested_artifact_junction_is_rejected",
)


def _test_support_manifest_blockers(cargo: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    features = cargo.get("features")
    if not isinstance(features, dict) or features.get("test-support") != []:
        blockers.append("test-support feature missing or non-empty")
    elif "test-support" in features.get("default", []):
        blockers.append("test-support feature must not be enabled by default")

    expected_targets = (
        (
            "bin",
            "sipi-agent-spice-fake-interpreter",
            "tests/fake_interpreter.rs",
        ),
        ("test", "adapter", "tests/adapter.rs"),
    )
    for kind, name, path in expected_targets:
        targets = cargo.get(kind)
        matches = (
            [
                target
                for target in targets
                if isinstance(target, dict)
                and (target.get("name") == name or target.get("path") == path)
            ]
            if isinstance(targets, list)
            else []
        )
        if len(matches) != 1 or matches[0].get("path") != path:
            blockers.append(f"test-support {kind} target identity drift: {name}")
        elif matches[0].get("required-features") != ["test-support"]:
            blockers.append(f"test-support {kind} target is not feature-gated: {name}")
    return blockers


def _git(source: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_blob(source: Path, commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(source), "cat-file", "blob", f"{commit}:{path}"],
        check=True,
        capture_output=True,
    )
    return result.stdout


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_lower_hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def verify(
    document: dict[str, Any], source: Path | None = None, root: Path = ROOT
) -> dict[str, Any]:
    blockers: list[str] = []
    if document.get("schema") != "sipi.as-upstream-adapter-contracts.v1":
        blockers.append("schema mismatch")
    source_data = document.get("source")
    index = document.get("source_file_index")
    commands = document.get("commands")
    adapter = document.get("adapter")
    if not all(isinstance(value, dict) for value in (source_data, index, adapter)) or not isinstance(commands, list):
        return {"ready": False, "blockers": blockers + ["source, adapter, index, and commands are required"]}

    if source_data.get("repository") != "agent-spice":
        blockers.append("source repository mismatch")
    if source_data.get("commit") != EXPECTED_COMMIT:
        blockers.append("source commit is not the pinned Agent-Spice object")
    if source_data.get("tree") != EXPECTED_TREE:
        blockers.append("source tree is not the pinned Agent-Spice tree")
    if source_data.get("module") != "agent_spice.cli":
        blockers.append("source module mismatch")
    source_index_sha256 = _sha256(
        json.dumps(index, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    if source_index_sha256 != EXPECTED_SOURCE_INDEX_SHA256:
        blockers.append("source file index identity drift")
    if adapter.get("launcher") != ["-m", "agent_spice.cli"]:
        blockers.append("production launcher prefix drift")
    if adapter.get("launcher_policy") != "production_default_with_explicit_test_override":
        blockers.append("launcher override scope drift")
    if adapter.get("argument_policy") != "caller_supplied_arguments_are_passed_through_without_rewrite":
        blockers.append("argument policy drift")
    if adapter.get("fallback_policy") != "no_silent_fallback_or_backend_substitution":
        blockers.append("fallback policy drift")
    output_admission = adapter.get("output_admission")
    if not isinstance(output_admission, dict):
        blockers.append("output admission policy missing")
    else:
        required_outputs = output_admission.get("required_explicit_outputs")
        expected_outputs = {
            "AS-01": ["--output"],
            "AS-02": ["--output-root"],
            "AS-03": ["--output"],
            "AS-04": ["--output-rfm", "--work-dir"],
            "AS-05": ["--output-root"],
            "AS-06": ["--output-root"],
        }
        if required_outputs != expected_outputs:
            blockers.append("output admission required paths drift")
        if output_admission.get("missing_default_output_paths") != "rejected":
            blockers.append("default output admission is not fail-closed")
        if output_admission.get("optional_output_paths_are_also_checked") is not True:
            blockers.append("optional output paths are not checked")
        if output_admission.get("output_symlink_target") != "rejected_even_when_dangling":
            blockers.append("dangling output symlink policy drift")
        if output_admission.get("symlink_parent") != "canonicalized_and_must_remain_inside_root":
            blockers.append("symlink parent containment policy drift")
        if output_admission.get("target_preexistence") != "rejected_before_spawn":
            blockers.append("preexisting output target policy drift")
    expected_required_artifacts = {
        "AS-01": {"--output": "file"},
        "AS-02": {"--output-root": "directory"},
        "AS-03": {"--output": "file"},
        "AS-04": {"--output-rfm": "file", "--work-dir": "directory"},
        "AS-05": {"--output-root": "directory"},
        "AS-06": {"--output-root": "directory"},
    }
    required_artifacts = adapter.get("post_success_required_artifacts")
    if not isinstance(required_artifacts, dict):
        blockers.append("post-success required artifact contract missing")
    else:
        observed_required_artifacts = {
            key: value for key, value in required_artifacts.items() if key.startswith("AS-")
        }
        if observed_required_artifacts != expected_required_artifacts:
            blockers.append("post-success required artifact mapping drift")
        if required_artifacts.get("failure_code") != "required_artifact_missing":
            blockers.append("required artifact failure code drift")
        if required_artifacts.get("enforcement") != "targeted_path_not_whole_root_inference":
            blockers.append("required artifact enforcement drift")
    process_tree = adapter.get("process_tree_termination")
    windows_job = process_tree.get("windows") if isinstance(process_tree, dict) else None
    if not isinstance(windows_job, dict) or windows_job != {
        "crate": "process-wrap",
        "version": "9.1.0",
        "features": ["std", "job-object"],
        "license": "MIT OR Apache-2.0",
        "lifecycle": "child_created_suspended_then_assigned_to_job_before_resume",
        "termination": "job_object_start_kill_covers_descendants_after_parent_exit",
        "normal_exit_cleanup": "retained_job_is_terminated_before_result_publication",
        "setup_failure": "process_isolation_failed_and_suspended_child_kill_attempted_without_raw_fallback",
    }:
        blockers.append("windows process-tree termination policy drift")
    if (
        not isinstance(process_tree, dict)
        or process_tree.get("non_windows") != "direct_child_kill_only_no_process_tree_claim"
    ):
        blockers.append("non-Windows process termination claim drift")
    provenance = adapter.get("provenance")
    if not isinstance(provenance, dict) or (
        provenance.get("runtime_source_authenticated") is not False
        or provenance.get("runtime_identity") != "caller_supplied_unverified"
        or provenance.get("source_identity")
        != "declared_migration_authority_not_authenticated_runtime_package"
    ):
        blockers.append("runtime source authentication nonclaim drift")
    process_limits = adapter.get("process_limits")
    if not isinstance(process_limits, dict) or any(
        process_limits.get(key) is None
        for key in (
            "reader_drain_time",
            "argv_bytes",
            "artifact_directories",
            "artifact_max_depth",
            "artifact_path_bytes",
        )
    ):
        blockers.append("secondary reader and artifact structure budgets missing")

    if source is not None:
        try:
            if _git(source, "rev-parse", "--verify", f"{EXPECTED_COMMIT}^{{commit}}") != EXPECTED_COMMIT:
                blockers.append("source commit does not resolve exactly")
            if _git(source, "rev-parse", f"{EXPECTED_COMMIT}^{{tree}}") != EXPECTED_TREE:
                blockers.append("source tree does not resolve exactly")
        except (OSError, subprocess.CalledProcessError) as error:
            blockers.append(f"source git unavailable: {error}")

    for key, entry in index.items():
        if not isinstance(entry, dict):
            blockers.append(f"source index entry malformed: {key}")
            continue
        path = entry.get("path")
        oid = entry.get("blob_oid")
        expected_hash = entry.get("sha256")
        if not isinstance(path, str) or not path or not _is_lower_hex(oid, 40) or not _is_lower_hex(expected_hash, 64):
            blockers.append(f"source index identity incomplete: {key}")
            continue
        if Path(path).is_absolute() or ".." in Path(path).parts:
            blockers.append(f"source path is not relative: {path}")
            continue
        if source is not None:
            try:
                actual_oid = _git(source, "rev-parse", f"{EXPECTED_COMMIT}:{path}")
                actual_hash = _sha256(_git_blob(source, EXPECTED_COMMIT, path))
            except (OSError, subprocess.CalledProcessError) as error:
                blockers.append(f"source blob unavailable: {path}: {error}")
                continue
            if actual_oid != oid:
                blockers.append(f"source blob oid mismatch: {path}")
            if actual_hash != expected_hash:
                blockers.append(f"source blob sha256 mismatch: {path}")

    rows: dict[str, dict[str, Any]] = {}
    for row in commands:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            blockers.append("malformed command row")
            continue
        row_id = row["id"]
        if row_id in rows:
            blockers.append(f"duplicate command row: {row_id}")
        rows[row_id] = row
        expected = EXPECTED_COMMANDS.get(row_id)
        if expected is None:
            blockers.append(f"unknown command row: {row_id}")
            continue
        if (row.get("cli"), row.get("request_type")) != expected:
            blockers.append(f"command identity mismatch: {row_id}")
        source_paths = row.get("source_paths")
        if not isinstance(source_paths, list) or not source_paths:
            blockers.append(f"source path mapping missing: {row_id}")
        elif any(path_key not in index for path_key in source_paths):
            blockers.append(f"source path mapping references unknown key: {row_id}")
        if not isinstance(row.get("branches"), list) or not row["branches"]:
            blockers.append(f"reachable branch inventory missing: {row_id}")
        if not isinstance(row.get("options"), list):
            blockers.append(f"direct option inventory missing: {row_id}")
        if row_id in {"AS-05", "AS-06"} and not row.get("explicit_backend_values"):
            blockers.append(f"backend value inventory missing: {row_id}")
        for field in ("dependencies", "assets", "upstream_error_surface"):
            if not isinstance(row.get(field), list) or not row[field]:
                blockers.append(f"{field} inventory missing: {row_id}")
        if row.get("adapter_status") not in {
            "implemented_transport_only",
            "implemented_transport_with_explicit_backend",
        }:
            blockers.append(f"adapter status is not implemented: {row_id}")
        if row.get("parity_status") == "accepted":
            blockers.append(f"adapter evidence cannot claim parity: {row_id}")

    if set(rows) != set(EXPECTED_COMMANDS):
        blockers.append("six AS command rows are not an exact set")

    crate = root / "crates" / "sipi-agent-spice-adapter"
    required_files = (
        crate / "Cargo.toml",
        crate / "src" / "lib.rs",
        crate / "tests" / "adapter.rs",
        crate / "tests" / "fake_interpreter.rs",
    )
    for path in required_files:
        if not path.is_file():
            blockers.append(f"adapter file missing: {path.relative_to(root)}")
    try:
        source_text = (crate / "src" / "lib.rs").read_text(encoding="utf-8")
        cargo_text = (crate / "Cargo.toml").read_text(encoding="utf-8")
        tests_text = (crate / "tests" / "adapter.rs").read_text(encoding="utf-8")
    except OSError as error:
        blockers.append(f"adapter source unreadable: {error}")
        source_text = ""
        cargo_text = ""
        tests_text = ""
    for marker in REQUIRED_ADAPTER_MARKERS:
        if marker not in source_text and marker not in cargo_text:
            blockers.append(f"adapter safety marker missing: {marker}")
    for forbidden in ("to_string_lossy", "from_utf8_lossy"):
        if forbidden in source_text:
            blockers.append(f"adapter uses lossy path/invocation encoding: {forbidden}")
    for marker in REQUIRED_TEST_MARKERS:
        if marker not in tests_text:
            blockers.append(f"adapter focused test marker missing: {marker}")
    try:
        cargo_document = tomllib.loads(cargo_text)
    except tomllib.TOMLDecodeError as error:
        blockers.append(f"adapter Cargo manifest malformed: {error}")
        cargo_document = {}
    blockers.extend(_test_support_manifest_blockers(cargo_document))
    process_wrap = (
        cargo_document.get("target", {})
        .get("cfg(windows)", {})
        .get("dependencies", {})
        .get("process-wrap")
    )
    if process_wrap != {
        "version": "=9.1.0",
        "default-features": False,
        "features": ["std", "job-object"],
    }:
        blockers.append("Windows process-wrap dependency drift")
    if "sipi-cli" in cargo_text or "sipi-com" in cargo_text:
        blockers.append("adapter crate unexpectedly depends on product command crates")

    verification = document.get("verification")
    if not isinstance(verification, dict) or (
        verification.get("repository_contract_gate")
        != "does_not_require_external_source_worktree"
        or verification.get("exact_source_git_objects")
        != "checked_only_when_source_is_explicitly_supplied"
    ):
        blockers.append("portable source verification policy drift")

    audit = document.get("audit")
    if not isinstance(audit, dict):
        blockers.append("audit identity missing")
    else:
        audit_path = audit.get("path")
        audit_hash = audit.get("sha256")
        if not isinstance(audit_path, str) or not isinstance(audit_hash, str):
            blockers.append("audit identity incomplete")
        else:
            path = root / audit_path
            if not _within(path, root) or not path.is_file():
                blockers.append("audit path unavailable")
            elif _sha256(path.read_bytes()) != audit_hash.lower():
                blockers.append("audit sha256 mismatch")

    return {
        "ready": not blockers,
        "blockers": blockers,
        "source_commit": source_data.get("commit"),
        "source_tree": source_data.get("tree"),
        "command_count": len(rows),
        "source_file_count": len(index),
        "source_git_objects_checked": source is not None,
        "crate": str(crate),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    args = parser.parse_args()
    try:
        document = yaml.safe_load(args.contract.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        print(json.dumps({"ready": False, "blockers": [f"contract unreadable: {error}"]}, indent=2))
        return 2
    source = None if args.source is None else args.source.resolve()
    report = verify(document, source, ROOT)
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
