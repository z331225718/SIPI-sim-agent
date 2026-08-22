"""Verify the pinned PyBERT workflow inventory and bounded adapter slice."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/baselines/pb-upstream-workflow-inventory.v1.yaml"
CONTRACT = ROOT / "docs/baselines/pb-upstream-adapter-contract.v1.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-08-22-pb-upstream-first-migration.md"
ADAPTER = ROOT / "crates/sipi-pybert-adapter/src/lib.rs"
PROCESS_TEST = ROOT / "crates/sipi-pybert-adapter/tests/process.rs"
CARGO_MANIFEST = ROOT / "crates/sipi-pybert-adapter/Cargo.toml"

SCHEMA = "sipi.pb-upstream-workflow-inventory.v1"
CONTRACT_SCHEMA = "sipi.pb-upstream-adapter-contract.v1"
COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
CLI_PATH = "src/pybert/cli.py"
CLI_BLOB = "4c1116007d31bcebf8db3252363eed7774c7b349"
CLI_SHA256 = "3826b0c156166e6f04b0e9997ce64a53a53867db6d89143b7c582ca2cf4337c9"
WORKFLOW_IDS = ("PB-01", "PB-02", "PB-03", "PB-04", "PB-05")
COMMANDS = ("sim", "sim-native", "sim-rust", "sim-auto", "sim-compare")


class WorkflowVerificationError(RuntimeError):
    """Raised when the migration slice is not bound to its stated contract."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise WorkflowVerificationError(reason)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise WorkflowVerificationError(f"document_invalid:{path.name}") from error
    _require(isinstance(value, dict), f"document_not_mapping:{path.name}")
    return value


def _git(root: Path, *args: str, binary: bool = False) -> str | bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        timeout=60,
    )
    _require(completed.returncode == 0, f"git_object_unavailable:{args[-1]}")
    if binary:
        return completed.stdout
    return completed.stdout.decode("utf-8", errors="strict").strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_test_support_manifest(cargo: dict[str, Any]) -> None:
    features = cargo.get("features")
    _require(
        isinstance(features, dict) and features.get("test-support") == [],
        "test_support_feature_invalid",
    )
    _require(
        "test-support" not in features.get("default", []),
        "test_support_enabled_by_default",
    )
    expected_targets = (
        ("bin", "pb_fake_pybert", "src/bin/pb_fake_pybert.rs"),
        ("test", "process", "tests/process.rs"),
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
        _require(
            len(matches) == 1 and matches[0].get("path") == path,
            f"test_support_target_identity_invalid:{kind}:{name}",
        )
        _require(
            matches[0].get("required-features") == ["test-support"],
            f"test_support_target_gate_invalid:{kind}:{name}",
        )


def validate_adapter_process_source(adapter_text: str) -> None:
    normalized = " ".join(adapter_text.split())
    _require(
        ".wrap(FailClosedJobSetup) .wrap(JobObject) .wrap(KillJobOnDropSetup) .wrap(PreserveParentCompletionPoll)"
        in normalized,
        "windows_job_wrapper_order_invalid",
    )
    _require(
        "validate_required_regular_artifacts(&records, workflow)?; Ok(records)"
        in normalized,
        "minimum_artifact_validation_not_bound_to_inventory",
    )


def validate_documents(
    inventory: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    inventory = _load(INVENTORY) if inventory is None else inventory
    contract = _load(CONTRACT) if contract is None else contract
    _require(inventory.get("schema") == SCHEMA, "inventory_schema_invalid")
    _require(
        inventory.get("status") == "observed_pinned_source_process_adapter_only",
        "inventory_status_invalid",
    )
    source = inventory.get("source")
    _require(
        isinstance(source, dict)
        and source.get("commit") == COMMIT
        and source.get("tree") == TREE
        and source.get("cli_path") == CLI_PATH
        and source.get("cli_blob_oid_sha1") == CLI_BLOB
        and source.get("cli_content_sha256") == CLI_SHA256
        and source.get("license") == "BSD-3-Clause"
        and source.get("license_path") == "LICENSE"
        and source.get("license_blob_oid_sha1") == "64d198ba43675ede5fbdef1ec918a63954951640"
        and isinstance(source.get("source_objects"), dict)
        and len(source["source_objects"]) == 25
        and source.get("source_bytes_in_repository") is False,
        "source_binding_invalid",
    )
    adapter = inventory.get("adapter")
    _require(
        isinstance(adapter, dict)
        and adapter.get("mode") == "process_external"
        and adapter.get("numerical_code_copied") is False
        and adapter.get("fallback_policy") == "upstream_decision_must_be_reported"
        and adapter.get("alignment_policy") == "no_adapter_alignment_or_resampling"
        and adapter.get("tolerance_policy") == "no_adapter_tolerance_or_acceptance_decision"
        and adapter.get("artifact_policy")
        == "fresh_target_then_pinned_minimum_regular_outputs_and_bounded_recursive_inventory_sha256_no_links"
        and adapter.get("cancellation_policy")
        == "caller_cancel_marker_or_deadline_kills_windows_job_or_nonwindows_direct_child",
        "adapter_boundary_invalid",
    )
    workflows = inventory.get("workflows")
    _require(isinstance(workflows, list), "workflows_invalid")
    by_id = {item.get("id"): item for item in workflows if isinstance(item, dict)}
    _require(tuple(by_id) == WORKFLOW_IDS, "workflow_id_set_invalid")
    for item_id, command in zip(WORKFLOW_IDS, COMMANDS):
        item = by_id[item_id]
        _require(item.get("public_command") == command, f"workflow_command_invalid:{item_id}")
        _require(item.get("adapter_status") in {"implemented_transport_only", "implemented_transport_and_selection_report"}, f"workflow_adapter_status_invalid:{item_id}")
        _require(item.get("parity_status") == "not_evaluated", f"workflow_parity_promoted:{item_id}")
        _require(isinstance(item.get("reachable_numeric_surface"), dict), f"reachable_inventory_missing:{item_id}")
        for branch in ("channel", "tx", "rx", "equalization", "jitter", "eye_ber", "result"):
            _require(item["reachable_numeric_surface"].get(branch), f"reachable_branch_missing:{item_id}:{branch}")
    _require(
        inventory.get("operational_tracks_not_first_numeric_completion")
        == ["web_fastapi", "redis_worker", "desktop_gui", "notebook_and_storage"],
        "operational_tracks_invalid",
    )

    _require(contract.get("schema") == CONTRACT_SCHEMA, "contract_schema_invalid")
    _require(contract.get("status") == "implemented_candidate_transport_contract", "contract_status_invalid")
    _require(contract.get("workflow_ids") == list(WORKFLOW_IDS), "contract_workflow_set_invalid")
    license_boundary = contract.get("license_boundary")
    _require(
        isinstance(license_boundary, dict)
        and license_boundary.get("adapter_spdx") == "MIT"
        and license_boundary.get("external_pybert_spdx") == "BSD-3-Clause"
        and license_boundary.get("source_copied_into_adapter") is False
        and license_boundary.get("external_runtime") is True
        and license_boundary.get("source_audit_path")
        == "docs/baselines/audits/2026-08-22-pb-upstream-first-migration.md"
        and license_boundary.get("source_audit_sha256") == _sha256(AUDIT),
        "license_boundary_invalid",
    )
    _require(
        contract.get("runtime_identity")
        == {
            "contract_source_only": True,
            "launcher": "caller_supplied",
            "attestation": "not_performed",
            "runtime_source_authenticated": False,
        },
        "runtime_identity_claim_invalid",
    )
    termination = contract.get("process_termination")
    _require(
        isinstance(termination, dict)
        and termination.get("windows_process_tree") == "process_wrap_9_1_job_object"
        and termination.get("windows_suspended_before_job_assignment") is True
        and termination.get("windows_job_setup_failure")
        == "fail_closed_and_kill_suspended_child"
        and termination.get("windows_job_raii_guard_after_assignment") is True
        and termination.get("windows_termination") == "terminate_job_object"
        and termination.get(
            "windows_parent_exit_descendants_terminated_before_stream_drain"
        )
        is True
        and termination.get("non_windows_process")
        == "direct_child_kill_no_tree_claim"
        and termination.get("stream_drain_deadline_required") is True,
        "contract_process_termination_invalid",
    )
    windows_dependencies = contract.get("windows_dependencies")
    process_wrap = (
        windows_dependencies.get("process_wrap")
        if isinstance(windows_dependencies, dict)
        else None
    )
    _require(
        isinstance(process_wrap, dict)
        and process_wrap.get("version") == "9.1.0"
        and process_wrap.get("features") == ["std", "job-object"]
        and process_wrap.get("license") == "MIT OR Apache-2.0"
        and process_wrap.get("target_only") == "windows",
        "contract_windows_dependency_invalid",
    )
    working_directory = contract.get("working_directory")
    _require(
        isinstance(working_directory, dict)
        and working_directory.get("caller_owned") is True
        and working_directory.get("required") is True
        and working_directory.get("existing_directory") is True
        and working_directory.get("symlink_or_junction_rejected") is True
        and working_directory.get("canonicalized_before_spawn") is True
        and working_directory.get("child_current_dir") is True
        and working_directory.get("relative_paths_resolve_from")
        == "canonical_working_directory",
        "contract_working_directory_invalid",
    )
    bounds = contract.get("request_bounds")
    _require(
        isinstance(bounds, dict)
        and bounds.get("max_request_bytes") == 65536
        and bounds.get("max_stdout_bytes") == 1048576
        and bounds.get("max_stderr_bytes") == 1048576
        and bounds.get("max_artifact_files") == 4096
        and bounds.get("max_artifact_directories") == 4096
        and bounds.get("max_artifact_bytes") == 536870912
        and bounds.get("max_artifact_depth") == 64
        and bounds.get("stream_drain_timeout_seconds") == 1
        and bounds.get("cancellation") == "explicit_caller_marker",
        "contract_bounds_invalid",
    )
    commands = contract.get("command_rules")
    _require(
        isinstance(commands, dict)
        and commands.get("exact_subcommands") == list(COMMANDS)
        and commands.get("sim_native_requires_output_dir") is True
        and commands.get("sim_rust_auto_compare_require_output_dir") is True,
        "contract_command_rules_invalid",
    )
    backend = contract.get("backend_rules")
    _require(
        isinstance(backend, dict)
        and backend.get("sim_auto_requires_diagnostics_engine_selection_on_success") is True
        and backend.get("sim_auto_records_requested_selected_fallback_reason_and_parity_gate") is True
        and backend.get("sim_compare_does_not_convert_candidate_error_to_success") is True,
        "contract_backend_rules_invalid",
    )
    artifacts = contract.get("artifact_rules")
    minimum_artifacts = (
        artifacts.get("minimum_regular_artifacts")
        if isinstance(artifacts, dict)
        else None
    )
    _require(
        isinstance(artifacts, dict)
        and artifacts.get("output_target_must_exist_after_success") is True
        and artifacts.get("nested_symlink_or_junction_rejected") is True
        and artifacts.get("canonical_file_must_remain_under_output_root") is True
        and artifacts.get("output_target_must_be_absent_before_spawn") is True
        and artifacts.get("preexisting_artifacts_never_count_as_current_run_output")
        is True
        and artifacts.get("concurrent_hostile_writer_custody") == "not_claimed"
        and artifacts.get("sim_result_file_required_after_success") is True
        and artifacts.get("required_directory_target_must_exist") is True
        and minimum_artifacts
        == {
            "PB-01": ["resolved_pybert_data_file"],
            "PB-02": ["meta.json", "arrays.npz"],
            "PB-03": ["meta.json", "arrays.npz"],
            "PB-04": ["meta.json", "arrays.npz"],
            "PB-05": ["meta.json", "arrays.npz"],
        }
        and artifacts.get("unrelated_files_do_not_substitute_for_minimum") is True
        and artifacts.get("sim_default_result_path_bound") is True
        and artifacts.get("numeric_payload_is_not_decoded") is True,
        "contract_artifact_rules_invalid",
    )
    for path in (AUDIT, ADAPTER, PROCESS_TEST, CARGO_MANIFEST):
        _require(path.is_file(), f"required_file_missing:{path.relative_to(root)}")
    adapter_text = ADAPTER.read_text(encoding="utf-8")
    for token in (
        "pub fn run(",
        "pub fn command_manifest(",
        "pub struct BackendSelection",
        "fn read_bounded",
        "fn selected_auto_backend",
        "fn kill_process_tree",
        "CommandWrap",
        "JobObject",
        "FailClosedJobSetup",
        "KillSuspendedOnDrop",
        "KillJobOnDropSetup",
        "KillJobOnDrop",
        "PreserveParentCompletionPoll",
        "spawn_managed",
        ".start_kill()",
        "ProcessIsolation",
        "pub working_directory: PathBuf",
        "validate_working_directory",
        ".current_dir(&working_directory)",
        "resolve_output_target",
        "WorkingDirectorySymlink",
        "stream_drain_timeout",
        "validate_existing_ancestors",
        "InvalidPathEncoding",
        "InvalidStatisticalTimePoints",
        "OutputLimitExceeded",
        "MissingAutoSelection",
        "OutputTargetAlreadyExists",
        "max_artifact_files",
        "max_artifact_directories",
        "RequiredArtifactMissing",
        "validate_required_regular_artifacts",
        "artifact.relative_path == *name",
        '"meta.json", "arrays.npz"',
        "canonical_path.starts_with(&canonical_root)",
        "metadata.file_type().is_symlink() || is_junction(&metadata)",
        "checked_add(self.timeout)",
        "cancel_file",
    ):
        _require(token in adapter_text, f"adapter_contract_token_missing:{token}")
    _require("to_string_lossy" not in adapter_text, "lossy_path_conversion_present")
    _require(".recv(" not in adapter_text, "unbounded_stream_receive_present")
    _require("taskkill.exe" not in adapter_text, "pid_based_tree_kill_present")
    validate_adapter_process_source(adapter_text)
    cargo_text = CARGO_MANIFEST.read_text(encoding="utf-8")
    try:
        cargo = tomllib.loads(cargo_text)
    except tomllib.TOMLDecodeError as error:
        raise WorkflowVerificationError("adapter_manifest_invalid") from error
    validate_test_support_manifest(cargo)
    target_dependencies = (
        cargo.get("target", {})
        .get("cfg(windows)", {})
        .get("dependencies", {})
    )
    process_wrap_dependency = target_dependencies.get("process-wrap")
    _require(
        "process-wrap" not in cargo.get("dependencies", {})
        and isinstance(process_wrap_dependency, dict)
        and process_wrap_dependency.get("version") == "=9.1.0"
        and process_wrap_dependency.get("default-features") is False
        and process_wrap_dependency.get("features") == ["std", "job-object"],
        "windows_process_wrap_dependency_missing",
    )
    process_text = PROCESS_TEST.read_text(encoding="utf-8")
    for token in (
        "sim_auto_reports_actual_selected_backend",
        "stdout_limit_fails_closed",
        "timeout_kills_child",
        "auto_without_selection",
        "sim_result_target_missing",
        "relative_paths_use_caller_working_directory",
        "working_directory_must_be_a_real_non_symlink_directory",
        "required_output_target_missing",
        "preexisting_output_targets_fail_closed_before_spawn",
        "artifact_directory_bound",
        "nested_junction_artifact_is_rejected_before_escape_inventory",
        "empty_or_unrelated_output_directory_fails_closed",
        "every_directory_workflow_requires_meta_and_arrays",
        "exited_parent_descendant_is_terminated_by_job_object",
        "descendant PID",
        "deadline_overflow_is_rejected_before_spawn",
    ):
        _require(token in process_text, f"process_test_missing:{token}")
    return {
        "valid": True,
        "workflows": len(workflows),
        "commands": list(COMMANDS),
        "parity": "not_evaluated",
        "source_git_objects_checked": False,
    }


def verify_source(root: Path, pybert_root: Path) -> dict[str, Any]:
    _require(pybert_root.is_dir(), "source_root_missing")
    _require(_git(pybert_root, "rev-parse", COMMIT) == COMMIT, "source_commit_unavailable")
    _require(_git(pybert_root, "rev-parse", f"{COMMIT}^{{tree}}") == TREE, "source_tree_drift")
    _require(_git(pybert_root, "rev-parse", f"{COMMIT}:{CLI_PATH}") == CLI_BLOB, "source_cli_blob_drift")
    payload = _git(pybert_root, "show", f"{COMMIT}:{CLI_PATH}", binary=True)
    _require(hashlib.sha256(payload).hexdigest() == CLI_SHA256, "source_cli_content_drift")
    inventory = _load(root / INVENTORY.relative_to(ROOT))
    objects = inventory["source"]
    for path, blob in objects["source_objects"].items():
        _require(
            _git(pybert_root, "rev-parse", f"{COMMIT}:{path}") == blob,
            f"source_object_drift:{path}",
        )
    _require(
        _git(pybert_root, "rev-parse", f"{COMMIT}:LICENSE")
        == objects["license_blob_oid_sha1"],
        "source_license_blob_drift",
    )
    return {
        "valid": True,
        "commit": objects["commit"],
        "tree": objects["tree"],
        "cli_blob_oid_sha1": objects["cli_blob_oid_sha1"],
        "cli_sha256": objects["cli_content_sha256"],
    }


def verify(root: Path = ROOT, pybert_root: Path | None = None) -> dict[str, Any]:
    result = validate_documents(root=root)
    if pybert_root is not None:
        result["source"] = verify_source(root, pybert_root)
        result["source_git_objects_checked"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--pybert-root", type=Path)
    arguments = parser.parse_args()
    try:
        print(json.dumps(verify(arguments.root, arguments.pybert_root), sort_keys=True))
        return 0
    except (OSError, WorkflowVerificationError) as error:
        print(json.dumps({"valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
