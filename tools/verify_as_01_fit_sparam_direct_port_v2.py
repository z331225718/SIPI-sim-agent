"""Verify the AS-01 fit-sparam contract candidate and frozen source map."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "as-01-fit-sparam-direct-port.v2.yaml"
UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
UPSTREAM_ARCHIVE_SHA256 = "7d59068d63e89913b4db6fc091eeedb94f01617353fdf60118ff584239f05a98"
REQUIRED_SOURCE_PATHS = {
    "src/agent_spice/cli.py": (
        "321a32b860f969f0be74f883bedbbae3f67d6284",
        135330,
        "908489c8c3a4826d49175c66b3d533413db4624b10fc3c797795b723b62262e1",
    ),
    "src/agent_spice/sparam/fitting.py": (
        "dd461c2f20f8b3fbf32cee90f79e430782ca9c76",
        157618,
        "db6be694d3959c1659a813dd108856651f97d3e0b206a1de14ccefe323c04f99",
    ),
    "src/agent_spice/sparam/target_fit.py": (
        "b57e5a070533e6e57988ac65eb3b477cb1482a56",
        15726,
        "fa265ddfd440c994c062b92e0b935e5f2bae9baa90e95935cbb0ceb55181041d",
    ),
    "src/agent_spice/sparam/io.py": (
        "0954ee70e24bba1339cdb89bd94f700906166122",
        2872,
        "6517a688e3230a012767743b3f2fef98b106bc757dc3e18cb5be0269b85ef7c9",
    ),
    "src/agent_spice/sparam/artifacts.py": (
        "ba7011f89c7fe0f6bf73fad13bce9248b96de9e5",
        18185,
        "f3131cc5117c41ab13674aaf1dfba68ed7ebed332a8154994cd9907b31299948",
    ),
    "src/agent_spice/sparam/rational_lft.py": (
        "969f7657565e67492e8b53ecfc35def0f00b7ee1",
        9569,
        "bc43fb22b4c4e49f4e0b5c654a58a6576d18c36e4e8c421d8f155d8aca5045a4",
    ),
    "src/agent_spice/sparam/y_pr.py": (
        "40e3a7abc18de1ef234a6870df7a4c7d4b83a9f2",
        16910,
        "317df34b898bb912f7b6e033f371aa568759303a30024914c0c8739071f2d38f",
    ),
}
PUBLIC_OPTIONS = [
    "--output",
    "--report",
    "--html-report",
    "--fitted-touchstone",
    "--rfm",
    "--rfm-wrapper",
    "--report-top-rms",
    "--log",
    "--rms-target",
    "--priority-band",
    "--outside-band-weight",
    "--passivity",
    "--max-order",
    "--min-order",
    "--max-order-step",
    "--quality-profile",
    "--fail-on-quality",
    "--allow-quality-warnings",
    "--subckt-name",
    "--tuning-profile",
    "--pole-spacing",
    "--fit-iterations",
    "--hf-complex-pairs",
    "--hf-pair-damping",
    "--hf-pair-start-fraction",
    "--passivity-max-iterations",
    "--passivity-samples",
    "--passivity-active-variables",
]
RUNTIME_SUPPORT = {
    "ports": [2],
    "touchstone_versions": ["1.x"],
    "data_formats": ["RI", "MA", "DB"],
    "artifacts_written": ["fitted_touchstone", "diagnostic_json", "diagnostic_log"],
    "path_identity_preflight": {
        "paths": ["input_touchstone", "diagnostic_json", "fitted_touchstone", "diagnostic_log"],
        "rejects": [
            "lexical_normalized_alias",
            "canonical_symlink_alias",
            "existing_file_identity_alias",
        ],
        "failure_atomicity": "no_artifact_write_before_preflight",
    },
    "artifact_options_rejected": ["--output", "--html-report", "--rfm", "--rfm-wrapper"],
    "unconsumed_options_rejected": [
        "--report-top-rms",
        "--outside-band-weight",
        "weighted --priority-band",
        "--quality-profile",
        "--fail-on-quality",
        "--allow-quality-warnings",
        "--subckt-name",
        "--tuning-profile",
        "--fit-iterations",
        "--hf-complex-pairs",
        "--hf-pair-damping",
        "--hf-pair-start-fraction",
        "--passivity-max-iterations",
        "--passivity-samples",
        "--passivity-active-variables",
        "--pole-spacing resonance",
    ],
    "budgets": {
        "touchstone_bytes": 16_777_216,
        "touchstone_line_bytes": 65_536,
        "touchstone_samples": 8_192,
        "priority_bands": 16,
        "max_fit_order": 100,
        "max_order_step": 100,
        "real_matrix_rows": 16_384,
        "real_matrix_columns": 204,
        "real_matrix_cells": 2_000_000,
        "artifact_bytes_each": 4_194_304,
        "artifact_path_bytes": 4_096,
    },
}
CANDIDATE_HASHES = {
    "module_sha256": (
        "crates/sipi-agent-spice-direct/src/fit_sparam.rs",
        "f343d1d75c256d1c9c0d85ce1f3cd903df79a9e1e145ab3a2ab3a050b56be624",
    ),
    "test_sha256": (
        "crates/sipi-agent-spice-direct/tests/as01.rs",
        "44d892e0676717e5939e8673b8df450ba168447b1a08143255b7cd5f6afff085",
    ),
    "cli_sha256": (
        "crates/sipi-agent-spice-direct/src/bin/sipi-agent-spice-fit-sparam.rs",
        "5546e6e42ceb8fe2cb5ea57615d57053f4a79da16f2a6f2ba05a6707e8957c9f",
    ),
    "cargo_toml_sha256": (
        "crates/sipi-agent-spice-direct/Cargo.toml",
        "f6c0bf28ea8d2b5aaf9bd1d6c3b572107eb93ba9833938c1667c3ad519b3361c",
    ),
    "cargo_lock_sha256": (
        "crates/sipi-agent-spice-direct/Cargo.lock",
        "b6ef55bcebb1669e20e8980c510f40ec0c9445f758ecc68208828e2968168879",
    ),
}


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str, raw: bool = False) -> bytes | str:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(root), *args],
            stderr=subprocess.STDOUT,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise VerificationError(f"git command failed: {error}") from error
    return output if raw else output.decode("ascii").strip()


def git_archive_sha256(root: Path, revision: str) -> str:
    process = subprocess.Popen(
        ["git", "-C", str(root), "archive", "--format=tar", revision, "--", *REQUIRED_SOURCE_PATHS],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    digest = hashlib.sha256()
    for block in iter(lambda: process.stdout.read(1024 * 1024), b""):
        digest.update(block)
    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    if process.wait() != 0:
        raise VerificationError(f"cannot hash upstream archive: {stderr}")
    return digest.hexdigest()


def source_observation(root: Path, path: str) -> dict[str, Any]:
    ref = f"{UPSTREAM_COMMIT}:{path}"
    content = bytes(git(root, "cat-file", "blob", ref, raw=True))
    return {
        "git_blob_sha1": str(git(root, "rev-parse", ref)),
        "bytes": len(content),
        "content_sha256": hashlib.sha256(content).hexdigest(),
    }


def verify(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    agent_spice_root: Path | None = None,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    try:
        document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise VerificationError(f"cannot read manifest: {error}") from error
    require(isinstance(document, dict), "manifest must be a mapping")
    require(
        document.get("schema") == "sipi.agent-spice-as-01-direct-port.v2",
        "schema drift",
    )
    require(document.get("status") == "native_vector_fitting_candidate_open", "status overclaim or drift")

    scope = document.get("scope")
    require(
        scope
        == {
            "work_item": "AS-01",
            "upstream_public_entrypoint": "fit-sparam",
            "target": "lane_local_rust_candidate",
            "product_capability_promoted": False,
            "migration_row_closed": False,
            "new_domain_functionality_added": False,
        },
        "scope drift",
    )

    source = document.get("source")
    require(isinstance(source, dict), "source missing")
    require(source.get("commit") == UPSTREAM_COMMIT, "upstream commit drift")
    require(source.get("tree") == UPSTREAM_TREE, "upstream tree drift")
    require(
        source.get("archive_inventory_sha256") == UPSTREAM_ARCHIVE_SHA256,
        "upstream archive digest drift",
    )
    require(source.get("declared_license") == "MIT", "license drift")
    paths = source.get("reachable_source_paths")
    require(isinstance(paths, list), "source path map missing")
    by_path = {item.get("path"): item for item in paths if isinstance(item, dict)}
    require(set(by_path) == set(REQUIRED_SOURCE_PATHS), "reachable path set drift")
    for path, (blob, size, digest) in REQUIRED_SOURCE_PATHS.items():
        item = by_path[path]
        require(item.get("git_blob_sha1") == blob, f"blob drift for {path}")
        require(item.get("bytes") == size, f"byte count drift for {path}")
        require(item.get("content_sha256") == digest, f"content digest drift for {path}")
    require(
        source.get("supporting_test_paths")
        == [
            "tests/test_cli_fit_sparam.py",
            "tests/test_sparam_fitting.py",
            "tests/test_sparam_native_vf.py",
        ],
        "supporting test inventory drift",
    )
    if agent_spice_root is not None:
        require(agent_spice_root.is_dir(), "Agent-Spice root is not a directory")
        require(git(agent_spice_root, "rev-parse", "HEAD") == UPSTREAM_COMMIT, "commit unavailable")
        require(
            git(agent_spice_root, "rev-parse", f"{UPSTREAM_COMMIT}^{{tree}}") == UPSTREAM_TREE,
            "tree drift",
        )
        for path, expected in REQUIRED_SOURCE_PATHS.items():
            observed = source_observation(agent_spice_root, path)
            require(
                observed
                == {
                    "git_blob_sha1": expected[0],
                    "bytes": expected[1],
                    "content_sha256": expected[2],
                },
                f"Git object drift for {path}",
            )
        require(
            git_archive_sha256(agent_spice_root, UPSTREAM_COMMIT) == UPSTREAM_ARCHIVE_SHA256,
            "archive digest unavailable",
        )

    implementation = document.get("implementation")
    require(isinstance(implementation, dict), "implementation missing")
    require(
        implementation.get("source_mode") == "working_tree_until_owner_commit",
        "candidate source mode drift",
    )
    require(
        implementation.get("candidate_status") == "bounded_two_port_diagnostic_fit_workflow",
        "candidate status drift",
    )
    require(
        implementation.get("side_effects")
        == "reads_bounded_touchstone_and_writes_fitted_touchstone_json_log_only",
        "candidate side-effect claim drift",
    )
    for key, (relative_path, expected_hash) in CANDIDATE_HASHES.items():
        candidate_path = repo_root / relative_path
        require(candidate_path.is_file(), f"candidate file missing: {relative_path}")
        require(implementation.get(key) == expected_hash, f"{key} manifest drift")
        require(sha256(candidate_path) == expected_hash, f"{key} content drift")
    crate = repo_root / str(implementation.get("crate"))
    module = repo_root / str(implementation.get("module"))
    require(crate.is_dir() and module.is_file(), "candidate files missing")
    notice = crate / "NOTICE-AGENT-SPICE-AS-01.txt"
    require(notice.is_file(), "MIT direct-port notice missing")
    require("2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5" in notice.read_text(encoding="utf-8"), "notice source binding missing")
    require(sha256(notice) == implementation.get("notice_sha256"), "notice hash drift")
    cargo = tomllib.loads((crate / "Cargo.toml").read_text(encoding="utf-8"))
    require(cargo.get("package", {}).get("name") == "sipi-agent-spice-direct", "crate drift")
    require("workspace" in cargo, "standalone workspace boundary missing")
    require(cargo.get("package", {}).get("license") == "MIT", "candidate license drift")
    require(cargo.get("dependencies", {}).get("same-file") == "1.0", "same-file identity dependency drift")
    audit = implementation.get("audit")
    require(isinstance(audit, dict), "audit binding missing")
    audit_path = repo_root / str(audit.get("path"))
    require(audit_path.is_file(), "audit file missing")
    require(sha256(audit_path) == audit.get("sha256"), "audit hash drift")
    source_text = module.read_text(encoding="utf-8")
    for marker in (
        "pub struct FitSparamOptions",
        "pub struct FitSparamRequest",
        "pub fn plan_fit_sparam",
        "pub fn read_touchstone",
        "pub fn fit_sparam",
        "pub fn write_fitted_touchstone",
        "pub fn resolve_passivity",
        "TargetBranch::PriorityBandOnly",
        "KernelStatus::NativeVectorFitting",
        "fn initial_poles",
        "fn fit_residues",
        "analyze_matched_two_port_v1",
        "FitSparamError::MissingRmsTarget",
        "FitSparamError::BudgetExceeded",
        "fn validate_execution_options",
        "pub struct FitSparamPublishedArtifacts",
        "pub const MAX_TOUCHSTONE_BYTES",
        "pub const MAX_TOUCHSTONE_LINE_BYTES",
        "pub const MAX_TOUCHSTONE_SAMPLES",
        "pub const MAX_REAL_MATRIX_ROWS",
        "pub const MAX_REAL_MATRIX_COLUMNS",
        "pub const MAX_REAL_MATRIX_CELLS",
        "fn normalize_absolute",
        "fn resolve_existing_ancestor",
        "fn ensure_artifact_boundaries",
        "same_file::is_same_file",
        '"weighted --priority-band"',
        '"unsupported_artifacts": ["spice_subcircuit", "html_report", "rfm", "rfm_wrapper"]',
    ):
        require(marker in source_text, f"implementation marker missing: {marker}")
    require("std::process::Command" not in source_text, "candidate must not spawn an external solver")
    for forbidden in ("fn write_spice_model", 'output.push_str(".SUBCKT', 'output.push_str("XMODEL'):
        require(forbidden not in source_text, f"placeholder artifact writer present: {forbidden}")
    cli_text = (crate / "src" / "bin" / "sipi-agent-spice-fit-sparam.rs").read_text(encoding="utf-8")
    for option in RUNTIME_SUPPORT["artifact_options_rejected"] + RUNTIME_SUPPORT["unconsumed_options_rejected"]:
        marker = "--pole-spacing" if option == "--pole-spacing resonance" else option.replace("weighted ", "")
        require(marker in cli_text, f"CLI rejection marker missing: {option}")
    require("not implemented by the bounded Rust fit route" in cli_text, "CLI fail-closed message missing")
    test_path = crate / "tests" / "as01.rs"
    require(test_path.is_file(), "AS-01 differential corpus test missing")
    test_text = test_path.read_text(encoding="utf-8")
    for marker in (
        "input_and_output_aliases_fail_before_any_existing_file_changes",
        "fs::hard_link",
        "symlink_file",
        'join("..")',
        "assert_alias_rejected_without_writes",
    ):
        require(marker in test_text, f"path-identity regression marker missing: {marker}")
    require(
        source_text.rindex("ensure_artifact_boundaries(&plan.touchstone, &artifacts)?")
        < source_text.rindex("write_fit_artifacts(&FitArtifactContext"),
        "artifact write occurs before path-identity preflight",
    )

    require(document.get("runtime_support") == RUNTIME_SUPPORT, "runtime support or budget drift")

    contract = document.get("contract")
    require(isinstance(contract, dict), "contract missing")
    require(contract.get("positional_arguments") == ["touchstone"], "positional contract drift")
    require(contract.get("public_options") == PUBLIC_OPTIONS, "public option contract drift")
    defaults = contract.get("defaults")
    require(
        defaults
        == {
            "report_top_rms": 5,
            "outside_band_weight": 0.1,
            "passivity": "check",
            "max_order": 100,
            "min_order": 1,
            "max_order_step": 8,
            "quality_profile": "explore",
            "fail_on_quality": False,
            "allow_quality_warnings": False,
            "subckt_name": "s_equivalent",
            "pole_spacing": "log",
            "fit_iterations": 14,
            "hf_complex_pairs": 2,
            "hf_pair_damping": 0.03,
            "hf_pair_start_fraction": 0.68,
            "passivity_max_iterations": 3,
            "passivity_samples": 8,
            "passivity_active_variables": 3072,
        },
        "default map drift",
    )
    require(contract.get("target_selection", {}).get("full_band_gate_formula") == "not priority_bands or rms_target_is_present", "target gate drift")

    oracle = document.get("oracle")
    require(isinstance(oracle, dict), "oracle preparation missing")
    require(oracle.get("status") == "preparation_only", "oracle status overclaim")
    require(oracle.get("required_future_runs") == 2, "two-stage oracle requirement drift")
    runner = repo_root / str(oracle.get("runner"))
    require(runner.is_file(), "oracle runner preparation missing")
    runner_text = runner.read_text(encoding="utf-8")
    for marker in ("upstream_pinned_execution", "rust_candidate_execution", "required_future_runs"):
        require(marker in runner_text, f"oracle runner marker missing: {marker}")
    require(oracle.get("report_payloads_committed") is False, "oracle payload overclaim")

    non_claims = document.get("non_claims")
    require(isinstance(non_claims, list), "non-claims missing")
    for expected in (
        "no_product_capability_promotion",
        "no_numeric_parity",
        "no_external_oracle_evidence",
        "no_n_port_above_two_support",
        "no_pole_relocation",
        "no_spice_subcircuit_artifact",
        "no_rfm_or_wrapper_artifact",
        "no_html_report_artifact",
    ):
        require(expected in non_claims, f"non-claim missing: {expected}")
    return {
        "status": document["status"],
        "source_paths": len(REQUIRED_SOURCE_PATHS),
        "runner": str(runner.relative_to(repo_root)),
        "candidate": str(module.relative_to(repo_root)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--agent-spice-root", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.manifest, agent_spice_root=args.agent_spice_root)
    except VerificationError as error:
        parser.error(str(error))
    print(f"valid AS-01 direct-port contract: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
