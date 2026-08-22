"""Verify the lane-local Agent-COM COM-03 direct-port boundary."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import yaml

from run_com_03_direct_oracle import git_archive_sha256, git_blob_sha256, scenario_documents, scenario_set_sha256


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/baselines/com-03-direct-port.v1.yaml"
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
REQUIRED_PATHS = {
    "src/agent_com/reporting.py": {
        "git_blob_sha1": "efbb14dda4d656a71e6915f5c5026b719e22d141",
        "bytes": 82620,
        "content_sha256": "14c4e4f0e5e51ee6fe76343ef133a565b8c922a0794acfe6c36ac3c7bbc1a0e1",
    },
    "src/agent_com/cli.py": {
        "git_blob_sha1": "7964d84bd52d60731bbf56ab9847bf4c190eacf9",
        "bytes": 15589,
        "content_sha256": "3ca1d26c097abaaa6197682a2c095dc2bc9d5810177429662a40463096fb51ca",
    },
    "schemas/result-v1.schema.json": {
        "git_blob_sha1": "9655622a259c4230d627ca2d2f7503d9bdec31f7",
        "bytes": 1968,
        "content_sha256": "00ace60e6d31fd37c4944681fa7fbfa390c763a69a3b42543a4b741bb4a8a247",
    },
}
SCENARIOS = {
    "identical",
    "schema_version_true_equals_one",
    "schema_version_float_equals_one",
    "provenance_empty_sequence",
    "provenance_pair_sequence_metadata_ignored",
    "non_comparable_metadata_ignored",
    "numeric_within_absolute_atol",
    "numeric_and_nested_mismatch",
    "object_key_mismatch",
    "array_length_mismatch",
    "scalar_string_mismatch",
    "invalid_schema_version",
    "missing_required_key",
    "invalid_profile",
    "empty_cases",
    "non_contiguous_case_index",
    "negative_signal",
    "non_integer_cursor",
    "invalid_eye_width_shape",
    "malformed_json",
    "negative_atol",
    "missing_golden",
    "missing_result",
}


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_candidate_binding(
    candidate: Any, *, candidate_root: Path | None, rust_binary: Path | None
) -> None:
    require(isinstance(candidate, dict), "candidate binding missing")
    status = candidate.get("status")
    if status == "unbound_observation":
        require(
            candidate == {
                "status": "unbound_observation",
                "reason": "preparation_worktree_is_not_an_immutable_candidate",
            },
            "unbound candidate observation drift",
        )
        return
    require(status == "immutable_candidate_bound", "candidate binding status drift")
    require(candidate_root is not None and candidate_root.is_dir(), "bound candidate root is required")
    require(rust_binary is not None and rust_binary.is_file(), "bound Rust binary is required")
    commit = str(candidate.get("commit"))
    require(git(candidate_root, "rev-parse", "HEAD") == commit, "candidate commit binding drift")
    require(
        git(candidate_root, "rev-parse", f"{commit}^{{tree}}") == candidate.get("tree"),
        "candidate tree binding drift",
    )
    require(
        git_archive_sha256(candidate_root, commit, "crates/sipi-agent-com-direct")
        == candidate.get("direct_crate_inventory_sha256"),
        "direct crate inventory drift",
    )
    require(
        git_blob_sha256(candidate_root, commit, "crates/sipi-agent-com-direct/Cargo.lock")
        == candidate.get("cargo_lock_sha256"),
        "Cargo.lock binding drift",
    )
    require(candidate.get("toolchain"), "candidate toolchain binding missing")
    require(
        candidate.get("cargo_build") == "clean_git_archive_with_independent_cargo_target_dir",
        "candidate build provenance missing",
    )
    require(sha256(rust_binary) == candidate.get("binary_sha256"), "Rust binary binding drift")


def require_no_absolute_temp_paths(text: str) -> None:
    require(
        not re.search(r"(?:[A-Za-z]:[\\/]|/)(?:[^\n\r ]*[\\/])?(?:Users|user|tmp|Temp|var)[\\/]", text),
        "oracle report contains an absolute user or temporary path",
    )


def git(root: Path, *args: str, raw: bool = False) -> bytes | str:
    try:
        output = subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError) as error:
        raise VerificationError(f"git command failed: {error}") from error
    return output if raw else output.decode("ascii").strip()


def source_observation(root: Path, path: str) -> dict[str, Any]:
    ref = f"{UPSTREAM_COMMIT}:{path}"
    content = bytes(git(root, "cat-file", "blob", ref, raw=True))
    return {
        "git_blob_sha1": str(git(root, "rev-parse", ref)),
        "bytes": int(str(git(root, "cat-file", "-s", ref))),
        "content_sha256": hashlib.sha256(content).hexdigest(),
    }


def verify(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    agent_com_root: Path | None = None,
    candidate_root: Path | None = None,
    rust_binary: Path | None = None,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    try:
        document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise VerificationError(f"cannot read manifest: {error}") from error
    require(isinstance(document, dict), "manifest must be a mapping")
    require(document.get("schema") == "sipi.com-03-direct-port.v1", "schema drift")
    require(document.get("status") == "direct_port_scoped_corpus_unbound_observation_open", "status overclaim or drift")
    scope = document.get("scope")
    require(isinstance(scope, dict), "scope missing")
    require(scope.get("work_item") == "COM-03", "work item drift")
    require(scope.get("product_capability_promoted") is False, "product capability overclaim")
    require(scope.get("global_migration_row_closed") is False, "global row overclaim")

    source = document.get("source")
    require(isinstance(source, dict), "source missing")
    require(source.get("commit") == UPSTREAM_COMMIT, "upstream commit drift")
    require(source.get("tree") == UPSTREAM_TREE, "upstream tree drift")
    require(source.get("declared_license") == "MIT", "upstream license drift")
    paths = source.get("source_paths")
    require(isinstance(paths, list), "source path map missing")
    by_path = {item.get("path"): item for item in paths if isinstance(item, dict)}
    require(set(by_path) == set(REQUIRED_PATHS), "source path set drift")
    for path, expected in REQUIRED_PATHS.items():
        item = by_path[path]
        require(item.get("license") == "MIT", f"MIT license missing for {path}")
        for key, value in expected.items():
            require(item.get(key) == value, f"source binding drift for {path}: {key}")
    if agent_com_root is not None:
        require(agent_com_root.is_dir(), "Agent-COM root is not a directory")
        require(str(git(agent_com_root, "rev-parse", "HEAD")) == UPSTREAM_COMMIT, "Agent-COM commit unavailable")
        require(str(git(agent_com_root, "rev-parse", f"{UPSTREAM_COMMIT}^{{tree}}")) == UPSTREAM_TREE, "Agent-COM tree drift")
        for path, expected in REQUIRED_PATHS.items():
            require(source_observation(agent_com_root, path) == expected, f"Git object drift for {path}")
        require(
            source.get("archive_inventory_sha256")
            == git_archive_sha256(agent_com_root, UPSTREAM_COMMIT),
            "upstream archive inventory drift",
        )

    implementation = document.get("implementation")
    require(isinstance(implementation, dict), "implementation missing")
    crate = repo_root / str(implementation.get("crate"))
    require(crate.is_dir(), "direct-port crate missing")
    cargo = crate / "Cargo.toml"
    lib = crate / "src/lib.rs"
    binary = crate / "src/bin/compare.rs"
    require(cargo.is_file() and lib.is_file() and binary.is_file(), "direct-port source files missing")
    cargo_document = tomllib.loads(cargo.read_text(encoding="utf-8"))
    require(cargo_document.get("package", {}).get("name") == "sipi-agent-com-direct", "crate name drift")
    require("workspace" in cargo_document, "lane-local standalone workspace boundary missing")
    require(cargo_document.get("package", {}).get("license") == "MIT", "direct-port license drift")
    lib_text = lib.read_text(encoding="utf-8")
    binary_text = binary.read_text(encoding="utf-8")
    for marker in (
        "validate_result_json_v1",
        "compare_result_json_v1",
        "DEFAULT_ATOL_V1",
        "MISMATCH_EXIT_CODE_V1",
        "remove(\"timings_s\")",
        "provenance.remove(\"platform\")",
        "provenance.remove(\"python_version\")",
        "keys differ",
        "list lengths differ",
        "optimization_cursor",
        "EW_UI shape must equal L-1",
    ):
        require(marker in lib_text, f"implementation marker missing: {marker}")
    require("compare_result_paths_v1" in binary_text and "ExitCode" in binary_text, "CLI boundary missing")
    for filename in ("SOURCE-MAP.md", "NOTICE-AGENT-COM-MIT.md"):
        require((crate / filename).is_file(), f"license/provenance file missing: {filename}")
    notice = (crate / "NOTICE-AGENT-COM-MIT.md").read_text(encoding="utf-8")
    require("MIT License" in notice and "Copyright (c) 2026 z331225718" in notice, "MIT attribution missing")

    contract = document.get("contract")
    require(isinstance(contract, dict), "contract missing")
    require(contract.get("default_atol") == 1.0e-12, "default tolerance drift")
    require(contract.get("relative_tolerance") == 0.0, "relative tolerance drift")
    require(contract.get("exit_codes") == {"matched": 0, "mismatch": 3, "malformed_json": 2, "invalid_schema": 3, "negative_atol": 3, "io_error": 1}, "exit map drift")

    oracle = document.get("oracle")
    require(isinstance(oracle, dict), "oracle evidence missing")
    require(oracle.get("scenario_count") == len(SCENARIOS), "scenario count drift")
    require(oracle.get("all_cli_contracts_match") is True, "oracle contract not green")
    require(oracle.get("stderr_diagnostic_text") == "not_frozen_contract", "stderr contract policy drift")
    expected_candidate_status = oracle.get("candidate_binding_status")
    require(
        expected_candidate_status in {"unbound_observation", "immutable_candidate_bound"},
        "candidate status drift",
    )
    require(
        oracle.get("bound_mode") == "clean_git_archive_with_independent_cargo_target_dir",
        "bound execution policy drift",
    )
    require(oracle.get("report_path_policy") == "redacted", "report path policy drift")
    require(oracle.get("diagnostic_policy") == "stable_categories_only", "diagnostic policy drift")
    expected_scenario_digest = scenario_set_sha256(scenario_documents())
    require(oracle.get("scenario_set_sha256") == expected_scenario_digest, "manifest scenario-set digest drift")
    expected_archive_digest = oracle.get("upstream_archive_inventory_sha256")
    require(isinstance(expected_archive_digest, str) and len(expected_archive_digest) == 64, "manifest archive digest missing")
    if agent_com_root is not None:
        require(
            expected_archive_digest == git_archive_sha256(agent_com_root, UPSTREAM_COMMIT),
            "manifest archive inventory drift",
        )
    reports = []
    for invocation in oracle.get("invocations", []):
        require(isinstance(invocation, dict), "oracle invocation malformed")
        path = repo_root / invocation["report"]
        require(path.is_file(), f"oracle report missing: {path}")
        require(sha256(path) == invocation.get("sha256"), f"oracle report hash drift: {path}")
        report_text = path.read_text(encoding="utf-8")
        require_no_absolute_temp_paths(report_text)
        report = yaml.safe_load(report_text) if path.suffix in {".yaml", ".yml"} else __import__("json").loads(report_text)
        require(report.get("source", {}).get("commit") == UPSTREAM_COMMIT, "oracle report commit drift")
        require(report.get("source", {}).get("tree") == UPSTREAM_TREE, "oracle report tree drift")
        require(
            report.get("source", {}).get("archive_inventory_sha256") == expected_archive_digest,
            "oracle archive inventory drift",
        )
        require(report.get("scenario_set_sha256") == expected_scenario_digest, "scenario-set digest drift")
        require(report.get("candidate", {}).get("status") == expected_candidate_status, "candidate status mismatch")
        expected_binary_mode = (
            "unbound_external_binary"
            if expected_candidate_status == "unbound_observation"
            else "candidate_archive_build"
        )
        require(report.get("rust_binary") == {"mode": expected_binary_mode}, "binary provenance disclosure drift")
        verify_candidate_binding(report.get("candidate"), candidate_root=candidate_root, rust_binary=rust_binary)
        require(report.get("scenario_count") == len(SCENARIOS), "oracle report scenario count drift")
        require(report.get("all_cli_contracts_match") is True, "oracle report contract not green")
        scenario_ids = {item.get("id") for item in report.get("scenarios", [])}
        require(scenario_ids == SCENARIOS, "oracle scenario matrix drift")
        require(all(item.get("cli_contract_match") is True for item in report["scenarios"]), "Rust/oracle CLI contract mismatch")
        reports.append(report)
    require(len(reports) == 2, "two fresh oracle reports are required")

    aggregate_path = repo_root / oracle.get("aggregate_report")
    require(aggregate_path.is_file(), "oracle aggregate report missing")
    require(sha256(aggregate_path) == oracle.get("aggregate_sha256"), "oracle aggregate hash drift")
    aggregate_text = aggregate_path.read_text(encoding="utf-8")
    require_no_absolute_temp_paths(aggregate_text)
    aggregate = __import__("json").loads(aggregate_text)
    require(aggregate.get("candidate", {}).get("status") == expected_candidate_status, "aggregate candidate status mismatch")
    require(aggregate.get("scenario_set_sha256") == expected_scenario_digest, "aggregate scenario-set digest drift")
    require(aggregate.get("fresh_runs") == 2, "aggregate fresh-run count drift")
    require(aggregate.get("scenario_count") == len(SCENARIOS), "aggregate scenario count drift")
    require(aggregate.get("scenario_outcomes_identical") is True, "aggregate outcome identity missing")
    require(aggregate.get("all_cli_contracts_match") is True, "aggregate contract not green")
    require(aggregate.get("stderr_is_not_a_frozen_contract") is True, "aggregate stderr policy drift")

    non_claims = set(document.get("non_claims", []))
    for claim in (
        "no_product_capability_promotion",
        "no_global_migration_row_close",
        "no_external_runtime_source_attestation",
        "no_workbook_or_run_or_public_api_implementation",
        "no_golden_or_result_payloads_vendored",
        "no_numeric_com_metric_acceptance",
        "no_release_readiness",
        "no_full_argparse_or_all_dict_conversion_branch_matrix",
        "no_immutable_candidate_binding",
    ):
        require(claim in non_claims, f"non-claim missing: {claim}")
    return {"schema": document["schema"], "status": document["status"], "source_paths": len(paths), "fresh_runs": 2, "scenario_count": len(SCENARIOS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--agent-com-root", type=Path)
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--rust-binary", type=Path)
    args = parser.parse_args()
    try:
        print(
            verify(
                args.manifest,
                agent_com_root=args.agent_com_root,
                candidate_root=args.candidate_root,
                rust_binary=args.rust_binary,
            )
        )
    except VerificationError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
