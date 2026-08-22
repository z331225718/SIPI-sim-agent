"""Fail-closed verifier for the Agent-COM upstream process adapter evidence."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/baselines/com-upstream-adapter.v1.yaml"
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
SCHEMA = "sipi.com-upstream-adapter.v1"
REQUIRED_WORKFLOWS = {"COM-01", "COM-02", "COM-03", "COM-04"}
REQUIRED_OPERATIONS = {"config_validate", "run", "compare", "public_workflow"}
REQUIRED_CATEGORIES = {"implemented", "report_only", "unimplemented", "obsolete", "unverified"}


class VerificationError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _git(root: Path, *args: str, raw: bool = False) -> bytes | str:
    try:
        output = subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError) as error:
        raise VerificationError(f"git command failed for {root}: {error}") from error
    return output if raw else output.decode("ascii").strip()


def _source_observation(root: Path, path: str) -> dict[str, Any]:
    ref = f"{UPSTREAM_COMMIT}:{path}"
    oid = str(_git(root, "rev-parse", ref))
    size = int(str(_git(root, "cat-file", "-s", ref)))
    content = bytes(_git(root, "cat-file", "blob", ref, raw=True))
    return {
        "path": path,
        "blob_oid_sha1": oid,
        "bytes": size,
        "content_sha256": hashlib.sha256(content).hexdigest(),
    }


def verify(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    agent_com_root: Path | None = None,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    try:
        document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise VerificationError(f"cannot read manifest: {error}") from error
    _require(isinstance(document, dict), "manifest must be a mapping")
    _require(document.get("schema") == SCHEMA, "schema mismatch")
    _require(document.get("status") == "adapter_implemented_parity_pending", "status must remain parity-pending")

    upstream = document.get("upstream")
    _require(isinstance(upstream, dict), "upstream binding missing")
    _require(upstream.get("commit") == UPSTREAM_COMMIT, "upstream commit drift")
    _require(upstream.get("tree") == UPSTREAM_TREE, "upstream tree drift")
    _require(upstream.get("repository") == "https://github.com/z331225718/agent-com.git", "upstream repository drift")
    _require(upstream.get("declared_license") == "MIT", "upstream root license drift")
    _require(upstream.get("license_scope") == "source_only_pending_per_path_review", "license scope overclaims")

    adapter = document.get("adapter")
    _require(isinstance(adapter, dict), "adapter binding missing")
    _require(adapter.get("crate") == "crates/sipi-agent-com-adapter", "adapter crate drift")
    _require(adapter.get("schema") == "sipi.agent-com.process-adapter.v1", "adapter schema drift")
    _require(set(adapter.get("operations", [])) == REQUIRED_OPERATIONS, "adapter operation set drift")
    _require(adapter.get("public_workflow_sequence") == ["load_config", "run_com", "write_artifacts"], "public API sequence missing")
    _require(adapter.get("backend_mode") == "process_external_no_shell", "adapter is not strict process-external")
    containment = adapter.get("windows_process_containment")
    _require(isinstance(containment, dict), "Windows process containment contract missing")
    _require(containment.get("dependency") == "process-wrap", "Windows containment dependency drift")
    _require(containment.get("version") == "9.1.0", "process-wrap version drift")
    _require(containment.get("registry_checksum") == "2e842efad9119158434d193c6682e2ebee4b44d6ad801d7b349623b3f57cdf55", "process-wrap checksum drift")
    _require(containment.get("declared_license") == "MIT OR Apache-2.0", "process-wrap license drift")
    _require(containment.get("features") == ["std", "job-object"], "process-wrap feature drift")
    _require(containment.get("spawn") == "suspended_before_job_assignment_then_resumed", "Windows suspended-spawn contract drift")
    _require(containment.get("setup_failure") == "suspended_child_direct_kill_guard_fail_closed", "Windows Job Object setup is not fail-closed")
    _require(containment.get("termination") == "job_object_kill_for_timeout_cancel_output_and_normal_drain", "Windows Job Object termination contract drift")
    _require(containment.get("drain") == "bounded_job_wait_and_pipe_join", "Windows Job Object drain contract drift")
    _require(containment.get("non_windows") == "bounded_direct_child_only", "non-Windows containment scope drift")
    working_directory = adapter.get("working_directory")
    _require(isinstance(working_directory, dict), "working-directory contract missing")
    _require(working_directory.get("ownership") == "caller_owned", "working-directory ownership drift")
    _require(working_directory.get("validation") == "canonical_existing_directory_symlink_junction_fail_closed", "working-directory validation drift")
    _require(working_directory.get("process_current_dir") == "enforced", "process current_dir is not enforced")
    _require(working_directory.get("relative_request_paths") == "resolved_against_working_directory_before_transport", "relative request path policy drift")
    _require(working_directory.get("relative_artifact_paths") == "resolved_against_working_directory_before_containment", "relative artifact path policy drift")
    _require(
        adapter.get("designated_output_boundary")
        == {
            "output_dir": "caller_selected_runtime_root",
            "log_file_and_progress_jsonl": "must_be_descendants_of_output_dir",
            "filesystem_sandbox": False,
            "hostile_writer_custody": "not_claimed",
            "freshness": "not_claimed_overwrite_semantics_remain_upstream_owned",
            "cpu_memory_and_process_count_isolation": "not_claimed",
        },
        "designated output boundary drift",
    )
    profile_admission = adapter.get("public_workflow_profile_admission")
    _require(isinstance(profile_admission, dict), "public workflow profile admission missing")
    _require(profile_admission.get("omitted") == "pass_none_to_upstream_load_config", "public workflow default ownership drift")
    _require(profile_admission.get("named_preset") == "explicit_from_name", "named profile admission drift")
    _require(profile_admission.get("custom") == "explicit_reader_required", "custom profile reader admission drift")
    _require(profile_admission.get("empty_profile_spec") == "rejected", "empty profile admission drift")
    _require(adapter.get("defaults") == "upstream_owned_omitted_when_not_explicit", "default ownership drift")
    _require(adapter.get("numerical_policy") == "upstream_owned_no_rewrite", "numerical rewrite claim")
    _require(adapter.get("fallback") == "forbidden", "fallback policy drift")
    bounded = adapter.get("bounded_io")
    _require(isinstance(bounded, dict), "bounded I/O declaration missing")
    _require(all(bounded.get(field) == "enforced" for field in ("stdout", "stderr", "wall_time")), "bounded I/O is incomplete")
    _require(bounded.get("artifact_bytes") == "enforced_without_reading_artifact_payloads", "artifact bound missing")
    _require(bounded.get("stdin") == "enforced_for_public_bridge", "public bridge stdin bound missing")
    _require(bounded.get("cancellation") == "caller_owned_token", "cancellation contract drift")
    _require(bounded.get("argv_bytes") == "enforced_including_executable_fixed_args_and_final_command_args", "argv bound missing")
    _require(bounded.get("secondary_reap_deadline") == "enforced", "secondary reap deadline missing")
    _require(bounded.get("reader_and_stdin_join") == "bounded_secondary_deadline", "reader/stdin join is unbounded")
    _require(bounded.get("windows_termination") == "process_wrap_job_object_kill_and_bounded_drain", "bounded Windows process-tree termination policy drift")
    _require(bounded.get("output_root_and_ancestors") == "symlink_junction_fail_closed", "output-root link policy missing")
    _require(bounded.get("artifact_entries") == "regular_files_or_directories_only_with_hard_count_limit", "artifact entry policy missing")

    bindings = document.get("source_bindings")
    _require(isinstance(bindings, list) and len(bindings) >= 10, "source binding set incomplete")
    expected_by_path = {entry.get("path"): entry for entry in bindings if isinstance(entry, dict)}
    for path in ("src/agent_com/cli.py", "src/agent_com/__init__.py", "src/agent_com/api.py", "src/agent_com/reporting.py", "src/agent_com/config/consumption.py", "CONFIG_CONSUMPTION_AUDIT.md"):
        _require(path in expected_by_path, f"missing source binding: {path}")
    if agent_com_root is not None:
        _require(agent_com_root.is_dir(), "agent-com root is not a directory")
        _require(str(_git(agent_com_root, "rev-parse", UPSTREAM_COMMIT)) == UPSTREAM_COMMIT, "pinned commit is not present")
        _require(str(_git(agent_com_root, "rev-parse", f"{UPSTREAM_COMMIT}^{{tree}}")) == UPSTREAM_TREE, "pinned tree mismatch")
        for path, expected in expected_by_path.items():
            observed = _source_observation(agent_com_root, path)
            for key in ("blob_oid_sha1", "bytes", "content_sha256"):
                _require(observed[key] == expected.get(key), f"source binding drift for {path}: {key}")

    crate = repo_root / "crates/sipi-agent-com-adapter"
    lib = crate / "src/lib.rs"
    cargo = crate / "Cargo.toml"
    _require(cargo.is_file() and lib.is_file(), "adapter crate files missing")
    cargo_text = cargo.read_text(encoding="utf-8")
    cargo_document = tomllib.loads(cargo_text)
    lib_text = lib.read_text(encoding="utf-8")
    _require('name = "sipi-agent-com-adapter"' in cargo_text, "adapter package name missing")
    windows_dependencies = cargo_document.get("target", {}).get("cfg(windows)", {}).get("dependencies", {})
    process_wrap = windows_dependencies.get("process-wrap")
    _require(isinstance(process_wrap, dict), "target-Windows process-wrap dependency missing")
    _require(process_wrap.get("version") == "=9.1.0", "Cargo process-wrap version drift")
    _require(process_wrap.get("default-features") is False, "process-wrap default features must remain disabled")
    _require(process_wrap.get("features") == ["std", "job-object"], "Cargo process-wrap feature drift")
    _require(cargo_document.get("features") == {"test-support": []}, "test-support feature boundary drift")
    fake_bins = [target for target in cargo_document.get("bin", []) if target.get("name") == "fake-com-backend"]
    _require(
        len(fake_bins) == 1 and fake_bins[0].get("required-features") == ["test-support"],
        "fake COM backend is not feature-isolated",
    )
    lock_document = tomllib.loads((repo_root / "Cargo.lock").read_text(encoding="utf-8"))
    locked_process_wrap = [package for package in lock_document.get("package", []) if package.get("name") == "process-wrap"]
    _require(len(locked_process_wrap) == 1, "Cargo.lock process-wrap package missing or ambiguous")
    _require(locked_process_wrap[0].get("version") == "9.1.0", "Cargo.lock process-wrap version drift")
    _require(locked_process_wrap[0].get("checksum") == containment["registry_checksum"], "Cargo.lock process-wrap checksum drift")
    for marker in (UPSTREAM_COMMIT, "process-external", "load_config", "run_com", "write_artifacts", "working_directory", "current_dir", "validate_working_directory", "resolve_request_path", "resolve_designated_output_path", "max_artifact_bytes", "max_artifact_entries", "CancellationToken", "CommandWrap", "JobObject", "FailClosedJobSetup", "KillSuspendedOnDrop", "PreserveJobCompletionPoll", "terminate_process_tree", "wait_child_bounded", "SECONDARY_REAP_TIMEOUT", "validate_final_argv", "reject_link_ancestors", "is_link_or_reparse"):
        _require(marker in lib_text, f"adapter implementation marker missing: {marker}")
    _require(
        ".wrap(FailClosedJobSetup)\n        .wrap(JobObject)\n        .wrap(PreserveJobCompletionPoll)" in lib_text,
        "Windows fail-closed/job/poll wrapper order drift",
    )
    _require("taskkill" not in lib_text.lower(), "Windows containment regressed to taskkill")
    _require('reader or "r480"' not in lib_text, "public workflow bridge silently defaults custom reader")
    _require("profile = BehaviorProfile.r480()" not in lib_text, "public workflow bridge silently defaults empty profile")
    _require(not any(path.suffix.lower() in {".xlsx", ".xlsm", ".mat", ".npz", ".s4p", ".s2p"} for path in crate.rglob("*")), "external asset bytes appear inside adapter crate")

    workflows = document.get("workflows")
    _require(isinstance(workflows, list), "workflow inventory missing")
    by_id = {entry.get("id"): entry for entry in workflows if isinstance(entry, dict)}
    _require(set(by_id) == REQUIRED_WORKFLOWS, "workflow set drift")
    for workflow_id, workflow in by_id.items():
        _require(workflow.get("status") == "adapter_implemented_parity_pending", f"{workflow_id} status overclaims")
        _require(isinstance(workflow.get("reachable_modules"), list) and workflow["reachable_modules"], f"{workflow_id} reachable inventory missing")
        _require(isinstance(workflow.get("input_assets"), list) and workflow["input_assets"], f"{workflow_id} input asset boundary missing")
        _require("matlab_runtime" in workflow, f"{workflow_id} MATLAB boundary missing")
        if workflow_id in {"COM-01", "COM-02", "COM-04"}:
            _require("golden_result" in workflow, f"{workflow_id} golden boundary missing")

    consumption = document.get("consumption_audit")
    _require(isinstance(consumption, dict), "consumption audit missing")
    _require(set(consumption.get("categories", [])) == REQUIRED_CATEGORIES, "consumption categories drift")
    _require(consumption.get("observed_summary") == {"implemented": 196, "report_only": 26, "unimplemented": 1, "obsolete": 15, "unverified": 0}, "consumption summary drift")
    _require(consumption.get("unimplemented_fields") == ["Do_White_Noise"], "unimplemented-field claim drift")
    _require(consumption.get("runtime_reads_are_not_parity") is True, "runtime-read overclaim")
    required_nonclaims = {
        "no_filesystem_sandbox_or_hostile_writer_custody",
        "no_cpu_memory_or_process_count_isolation",
        "no_runtime_source_attestation",
        "designated_outputs_only_no_general_write_containment",
        "no_freshness_claim_for_com_overwrite_workflows",
    }
    _require(
        required_nonclaims <= set(document.get("non_claims", [])),
        "runtime or containment non-claim missing",
    )

    non_claims = set(document.get("non_claims", []))
    for claim in ("no_rust_parity_acceptance", "no_matlab_oracle_generation", "no_workbook_bytes_or_golden_bytes_vendored", "no_license_conclusion_for_matlab_data_workbook_or_golden_assets", "no_default_or_numeric_or_alignment_or_tolerance_rewrite", "no_silent_fallback", "no_release_readiness"):
        _require(claim in non_claims, f"non-claim missing: {claim}")
    return {
        "schema": SCHEMA,
        "status": document["status"],
        "source_bindings": len(bindings),
        "workflows": sorted(by_id),
        "agent_com_verified": agent_com_root is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--agent-com-root", type=Path)
    args = parser.parse_args()
    try:
        print(verify(args.manifest, agent_com_root=args.agent_com_root))
    except VerificationError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
