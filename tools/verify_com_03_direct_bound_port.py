"""Verify additive COM-03 immutable-candidate evidence without closing governance."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from run_com_03_direct_oracle import (
    BOUND_SCHEMA,
    bound_candidate_binary,
    git,
    git_archive_sha256,
    git_blob_sha256,
    scenario_documents,
    scenario_set_sha256,
)
from verify_com_03_direct_port import REQUIRED_PATHS, SCENARIOS, VerificationError, source_observation


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/baselines/com-03-direct-port-bound.v2.yaml"
AGGREGATE_SCHEMA = "sipi.com-03-direct-port-oracle-aggregate.v2"
CANDIDATE_COMMIT = "81d19e7fab6621f57890cf6ac6a72bd64fc56b9a"
CANDIDATE_TREE = "a950a66b15f0349b3bda72fc0ef022cdb931f07a"
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_repo_relative_file(repo_root: Path, reference: Any, label: str) -> Path:
    require(isinstance(reference, str) and reference, f"{label} path missing")
    relative = Path(reference)
    require(not relative.is_absolute() and not relative.anchor, f"{label} path must be repo-relative")
    require(".." not in relative.parts, f"{label} path escapes repository")
    root = repo_root.resolve()
    resolved = (root / relative).resolve()
    require(resolved != root and root in resolved.parents, f"{label} path escapes repository")
    require(resolved.is_file(), f"{label} file missing")
    return resolved


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def require_no_local_paths(text: str) -> None:
    require(
        not re.search(r"(?:[A-Za-z]:[\\/]|/)(?:[^\n\r ]*[\\/])?(?:Users|user|tmp|Temp|var)[\\/]", text),
        "bound evidence contains a local absolute path",
    )


def read_json(path: Path) -> tuple[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    require_no_local_paths(text)
    value = json.loads(text)
    require(isinstance(value, dict), f"JSON document must be an object: {path}")
    return text, value


def verify(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    candidate_root: Path | None = None,
    agent_com_root: Path | None = None,
    cargo_executable: Path | None = None,
    rebuild: bool = False,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    require(isinstance(document, dict), "manifest must be a mapping")
    require(document.get("schema") == "sipi.com-03-direct-port-bound.v2", "schema drift")
    require(document.get("status") == "direct_port_scoped_corpus_immutable_candidate_bound_open", "status drift")
    scope = document.get("scope")
    require(isinstance(scope, dict), "scope missing")
    require(scope.get("work_item") == "COM-03", "work item drift")
    require(scope.get("product_capability_promoted") is False, "product capability overclaim")
    require(scope.get("global_migration_row_closed") is False, "migration row overclaim")

    audit = document.get("audit")
    require(isinstance(audit, dict), "audit binding missing")
    audit_path = safe_repo_relative_file(repo_root, audit.get("path"), "audit")
    require(sha256(audit_path) == audit.get("sha256"), "audit content hash drift")

    candidate = document.get("candidate")
    require(isinstance(candidate, dict), "candidate manifest missing")
    require(candidate.get("commit") == CANDIDATE_COMMIT, "candidate commit drift")
    require(candidate.get("tree") == CANDIDATE_TREE, "candidate tree drift")
    require(candidate.get("source_materialization") == "clean_git_archive", "candidate source mode drift")
    require(candidate.get("cargo_build") == "clean_git_archive_with_independent_cargo_target_dir", "candidate build mode drift")
    require(candidate.get("build_log_normalization") == "stable_event_categories", "build log policy drift")
    require(candidate.get("isolation") == {
        "candidate_source_root": "independent_temporary_directory",
        "cargo_target_dir": "independent_temporary_directory",
    }, "candidate isolation drift")
    require(candidate.get("toolchain") == "1.97.0-x86_64-pc-windows-msvc", "toolchain drift")

    source = document.get("source")
    require(isinstance(source, dict), "upstream source missing")
    require(source.get("commit") == UPSTREAM_COMMIT, "upstream commit drift")
    require(source.get("tree") == UPSTREAM_TREE, "upstream tree drift")
    require(source.get("declared_license") == "MIT", "upstream license drift")
    if agent_com_root is not None:
        require(agent_com_root.is_dir(), "Agent-COM root missing")
        require(git(agent_com_root, "rev-parse", "HEAD") == UPSTREAM_COMMIT, "Agent-COM commit unavailable")
        require(git(agent_com_root, "rev-parse", f"{UPSTREAM_COMMIT}^{{tree}}") == UPSTREAM_TREE, "Agent-COM tree drift")
        require(source.get("archive_inventory_sha256") == git_archive_sha256(agent_com_root, UPSTREAM_COMMIT), "upstream archive inventory drift")
        for path, expected in REQUIRED_PATHS.items():
            require(source_observation(agent_com_root, path) == expected, f"upstream source drift: {path}")

    implementation = document.get("implementation") or {
        "crate": "crates/sipi-agent-com-direct"
    }
    crate = repo_root / str(implementation.get("crate"))
    require(crate.is_dir(), "direct-port crate missing")

    oracle = document.get("oracle")
    require(isinstance(oracle, dict), "oracle missing")
    require(oracle.get("report_schema") == BOUND_SCHEMA, "report schema drift")
    require(oracle.get("aggregate_schema") == AGGREGATE_SCHEMA, "aggregate schema drift")
    require(oracle.get("candidate_binding_status") == "immutable_candidate_bound", "candidate status drift")
    require(oracle.get("bound_mode") == "clean_git_archive_with_independent_cargo_target_dir", "bound mode drift")
    require(oracle.get("report_path_policy") == "redacted", "report path policy drift")
    require(oracle.get("diagnostic_policy") == "stable_categories_only", "diagnostic policy drift")
    expected_scenario_digest = scenario_set_sha256(scenario_documents())
    require(oracle.get("scenario_set_sha256") == expected_scenario_digest, "scenario-set digest drift")
    require(oracle.get("scenario_count") == len(SCENARIOS), "scenario count drift")
    require(oracle.get("all_cli_contracts_match") is True, "oracle contract not green")

    invocations = oracle.get("invocations")
    require(isinstance(invocations, list), "oracle invocations missing")
    reports = []
    invocation_paths = set()
    invocation_run_ids = set()
    invocation_report_sha256 = set()
    invocation_nonces = set()
    nonce_pattern = re.compile(r"[0-9a-f]{64}")
    for invocation in invocations:
        require(isinstance(invocation, dict), "bound invocation malformed")
        report_ref = invocation.get("report")
        require(isinstance(report_ref, str) and report_ref, "bound invocation report missing")
        path = repo_root / report_ref
        resolved_path = path.resolve()
        require(resolved_path not in invocation_paths, "duplicate bound report path")
        invocation_paths.add(resolved_path)
        require(path.is_file(), f"report missing: {path}")
        report_sha256 = sha256(path)
        require(report_sha256 == invocation.get("sha256"), f"report hash drift: {path}")
        require(report_sha256 not in invocation_report_sha256, "duplicate bound report digest")
        invocation_report_sha256.add(report_sha256)
        _, report = read_json(path)
        require(report.get("schema") == BOUND_SCHEMA, "report schema drift")
        require(report.get("source", {}).get("commit") == UPSTREAM_COMMIT, "report upstream commit drift")
        require(report.get("source", {}).get("tree") == UPSTREAM_TREE, "report upstream tree drift")
        require(report.get("source", {}).get("archive_inventory_sha256") == source.get("archive_inventory_sha256"), "report upstream archive drift")
        require(report.get("scenario_set_sha256") == expected_scenario_digest, "report scenario-set drift")
        require(report.get("scenario_count") == len(SCENARIOS), "report scenario count drift")
        require(report.get("all_cli_contracts_match") is True, "report contract not green")
        require(report.get("rust_binary") == {"mode": "candidate_archive_build"}, "binary source disclosure drift")
        run_id = report.get("run_id")
        require(isinstance(run_id, str) and run_id, "bound report run id missing")
        require(run_id == invocation.get("run_id"), "bound report run id binding drift")
        require(run_id not in invocation_run_ids, "duplicate bound report run id")
        invocation_run_ids.add(run_id)
        fresh_run_nonce = report.get("fresh_run_nonce")
        require(
            isinstance(fresh_run_nonce, str) and nonce_pattern.fullmatch(fresh_run_nonce) is not None,
            "bound report nonce missing or malformed",
        )
        require(fresh_run_nonce == invocation.get("fresh_run_nonce"), "bound report nonce binding drift")
        require(fresh_run_nonce not in invocation_nonces, "duplicate bound report nonce")
        invocation_nonces.add(fresh_run_nonce)
        require(
            report.get("execution") == {
                "candidate_source_root": "independent_temporary_directory",
                "candidate_target_root": "independent_temporary_directory",
                "scenario_output_root": "independent_temporary_directory",
            },
            "report isolation drift",
        )
        report_candidate = report.get("candidate")
        require(isinstance(report_candidate, dict), "report candidate binding missing")
        for key in (
            "status", "commit", "tree", "direct_crate_inventory_sha256", "cargo_lock_sha256",
            "toolchain", "cargo_build", "reproducibility_flags", "binary_sha256",
            "build_stdout_sha256", "build_stderr_sha256", "build_log_normalization",
            "source_date_epoch", "isolation",
        ):
            require(report_candidate.get(key) == candidate.get(key), f"candidate binding drift: {key}")
        require(text_sha256(report_candidate.get("cargo_vv", "")) == candidate.get("cargo_vv_sha256"), "cargo -Vv binding drift")
        require(text_sha256(report_candidate.get("rustc_vv", "")) == candidate.get("rustc_vv_sha256"), "rustc -Vv binding drift")
        require({item.get("id") for item in report.get("scenarios", [])} == SCENARIOS, "scenario matrix drift")
        require(all(item.get("cli_contract_match") is True for item in report["scenarios"]), "Rust/oracle mismatch")
        reports.append(report)
    require(len(reports) == 2, "two bound reports required")
    require(len(invocation_paths) == 2, "bound report paths are not fresh")
    require(len(invocation_run_ids) == 2, "bound report run ids are not fresh")
    require(len(invocation_report_sha256) == 2, "bound report digests are not fresh")
    require(len(invocation_nonces) == 2, "bound report nonces are not fresh")
    require(reports[0]["candidate"] == reports[1]["candidate"], "bound candidate identities differ")

    aggregate_path = repo_root / oracle["aggregate_report"]
    require(aggregate_path.is_file(), "aggregate report missing")
    require(sha256(aggregate_path) == oracle.get("aggregate_sha256"), "aggregate hash drift")
    _, aggregate = read_json(aggregate_path)
    require(aggregate.get("schema") == AGGREGATE_SCHEMA, "aggregate schema drift")
    require(aggregate.get("source") == reports[0].get("source"), "aggregate source drift")
    require(aggregate.get("candidate") == reports[0].get("candidate"), "aggregate candidate drift")
    require(aggregate.get("scenario_set_sha256") == expected_scenario_digest, "aggregate scenario-set drift")
    require(aggregate.get("scenario_count") == len(SCENARIOS), "aggregate scenario count drift")
    require(aggregate.get("fresh_runs") == 2, "aggregate fresh-run count drift")
    require(aggregate.get("scenario_outcomes_identical") is True, "aggregate outcome drift")
    require(aggregate.get("all_cli_contracts_match") is True, "aggregate contract not green")
    aggregate_invocations = aggregate.get("invocations")
    require(isinstance(aggregate_invocations, list) and len(aggregate_invocations) == 2, "aggregate invocation identity missing")
    for expected, actual in zip(invocations, aggregate_invocations):
        require(actual.get("report") == Path(expected["report"]).name, "aggregate report path binding drift")
        require(actual.get("run_id") == expected.get("run_id"), "aggregate run id binding drift")
        require(actual.get("sha256") == expected.get("sha256"), "aggregate report digest binding drift")
        require(actual.get("fresh_run_nonce") == expected.get("fresh_run_nonce"), "aggregate nonce binding drift")

    if candidate_root is not None:
        require(git(candidate_root, "rev-parse", "HEAD") == CANDIDATE_COMMIT, "candidate worktree commit drift")
        require(git(candidate_root, "rev-parse", f"{CANDIDATE_COMMIT}^{{tree}}") == CANDIDATE_TREE, "candidate worktree tree drift")
        require(git_archive_sha256(candidate_root, CANDIDATE_COMMIT, "crates/sipi-agent-com-direct") == candidate["direct_crate_inventory_sha256"], "crate inventory drift")
        require(git_blob_sha256(candidate_root, CANDIDATE_COMMIT, "crates/sipi-agent-com-direct/Cargo.lock") == candidate["cargo_lock_sha256"], "Cargo.lock drift")
        require(git(candidate_root, "show", "-s", "--format=%ct", CANDIDATE_COMMIT) == candidate["source_date_epoch"], "source date binding drift")
        if rebuild:
            with bound_candidate_binary(
                candidate_root=candidate_root,
                candidate_commit=CANDIDATE_COMMIT,
                toolchain=candidate["toolchain"],
                cargo_executable=cargo_executable,
            ) as (_, rebuilt):
                for key in (
                    "status", "commit", "tree", "direct_crate_inventory_sha256", "cargo_lock_sha256",
                    "toolchain", "cargo_build", "reproducibility_flags", "binary_sha256",
                    "build_stdout_sha256", "build_stderr_sha256", "build_log_normalization",
                    "source_date_epoch", "isolation",
                ):
                    require(rebuilt.get(key) == reports[0]["candidate"].get(key), f"rebuild binding drift: {key}")

    return {"schema": document["schema"], "status": document["status"], "scenario_count": len(SCENARIOS), "fresh_runs": 2, "rebuild_checked": rebuild}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--agent-com-root", type=Path)
    parser.add_argument("--cargo-executable", type=Path)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    try:
        print(
            verify(
                args.manifest,
                candidate_root=args.candidate_root,
                agent_com_root=args.agent_com_root,
                cargo_executable=args.cargo_executable,
                rebuild=args.rebuild,
            )
        )
    except VerificationError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
