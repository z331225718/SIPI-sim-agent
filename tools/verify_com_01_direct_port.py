"""Verify the COM-01 source-schema materialized direct-port boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from run_com_01_direct_oracle import (
    CORPUS,
    REQUIRED_SOURCE_PATHS,
    SCHEMA,
    UPSTREAM_COMMIT,
    UPSTREAM_TREE,
    git_archive_sha256,
    load_corpus,
    scenario_set_sha256,
    source_observation,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "com-01-direct-port-preparation.v1.yaml"
EXPECTED_SOURCE = {
    "src/agent_com/cli.py": {"git_blob_sha1": "7964d84bd52d60731bbf56ab9847bf4c190eacf9", "bytes": 15589, "content_sha256": "3ca1d26c097abaaa6197682a2c095dc2bc9d5810177429662a40463096fb51ca"},
    "src/agent_com/config/__init__.py": {"git_blob_sha1": "6c581ceb95ff6ba09c3e0569c8b1e49941a67010", "bytes": 684, "content_sha256": "ab2fb8f93efc466fb1988b20f77eba0bd95dedea449e44af5afecf27e7642e30"},
    "src/agent_com/config/consumption.py": {"git_blob_sha1": "50fc02d837a67f3b503a73672ec4fbcc40d39b73", "bytes": 210466, "content_sha256": "c6202e42b5e5ccb7fa1f78c780b9ecf031af5400b35cd23f20ef7348207d28a7"},
    "src/agent_com/config/derived.py": {"git_blob_sha1": "dc4ba2d07a42a93b8d2c916a07e94adc9865868f", "bytes": 5098, "content_sha256": "eebbafa8dfad36376ed08b8f1241255ada872072a7571c22b1ec9bae9e668ffc"},
    "src/agent_com/config/excel.py": {"git_blob_sha1": "1cce4365b64f3bb0ef1f7617107d2df4c929afc7", "bytes": 12218, "content_sha256": "2886e9986b9c3a7c1fbdc6179878679ae26bb92f511c6b0689644f9a6c053c4d"},
    "src/agent_com/config/literals.py": {"git_blob_sha1": "d751e991bc5622423044950bbc69ee8b18d62b96", "bytes": 4255, "content_sha256": "146e7f72c7340d14badfdb63202db62af4c9174ad30f18f9c5a8fb90582fed56"},
    "src/agent_com/config/materialize.py": {"git_blob_sha1": "a8856f91fe9208738446f539aa52ade2ea2c0bcf", "bytes": 19030, "content_sha256": "42f85e3cd5df74158acc10b9388f663419740b374756cdbd8332f052063d265c"},
    "src/agent_com/config/schema.py": {"git_blob_sha1": "568eb7621d52a639a4ba0ef028e7dd39c10cca2a", "bytes": 11477, "content_sha256": "df203a88eacb5e0738420230e6b14b78240e63a35c5fa6cd8914d6e64cd14ceb"},
    "src/agent_com/capabilities.py": {"git_blob_sha1": "0be8fa93ce54bd79cb61e6cf388c105f87cc4c50", "bytes": 2266, "content_sha256": "a5f7a529e4ed6aedaf29514e085cc963b3b9f52882e8226244aa909df17e51bf"},
    "schemas/behavior-presets.yaml": {"git_blob_sha1": "7f67deffd1e6100f1d67912df786bbf7612eb5cc", "bytes": 578, "content_sha256": "906e1b05bedf620fa431406b0ea41fae81dd235e759ff2155c17e68dccdf6d3e"},
    "schemas/r480-config.schema.yaml": {"git_blob_sha1": "28ffa5a5ff9890911643808da16665293eb693b0", "bytes": 70677, "content_sha256": "55a98abea9de8f8335cdfa327b3fded733f23ce60220b39117a951577c14760c"},
}

class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_repo_file(repo_root: Path, reference: Any, label: str) -> Path:
    require(isinstance(reference, str) and reference, f"{label} path missing")
    relative = Path(reference)
    require(not relative.is_absolute() and not relative.anchor, f"{label} path must be relative")
    require(".." not in relative.parts, f"{label} path traversal")
    resolved = (repo_root / relative).resolve()
    require(repo_root.resolve() in resolved.parents and resolved.is_file(), f"{label} file missing")
    return resolved


def git(root: Path, *args: str, raw: bool = False) -> bytes | str:
    try:
        output = subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError) as error:
        raise VerificationError(f"git command failed: {error}") from error
    return output if raw else output.decode("ascii").strip()


def verify(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    agent_com_root: Path | None = None,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    require(isinstance(document, dict), "manifest must be a mapping")
    require(document.get("schema") == SCHEMA, "schema drift")
    require(document.get("status") == "implementation_materialized_open", "status drift")
    scope = document.get("scope")
    require(isinstance(scope, dict), "scope missing")
    require(scope.get("work_item") == "COM-01", "work item drift")
    require(scope.get("upstream_public_entrypoint") == "config-validate", "entrypoint drift")
    require(scope.get("product_capability_promoted") is False, "product capability overclaim")
    require(scope.get("global_migration_row_closed") is False, "migration row overclaim")

    audit = document.get("audit")
    require(isinstance(audit, dict), "audit binding missing")
    audit_path = safe_repo_file(repo_root, audit.get("path"), "audit")
    require(sha256(audit_path) == audit.get("sha256"), "audit hash drift")

    source = document.get("source")
    require(isinstance(source, dict), "source missing")
    require(source.get("commit") == UPSTREAM_COMMIT, "upstream commit drift")
    require(source.get("tree") == UPSTREAM_TREE, "upstream tree drift")
    require(source.get("declared_license") == "MIT", "upstream license drift")
    require(source.get("archive_inventory_sha256") == "5f3f17e19edc07cf6498c9bfea20b8691082e2c05364b4462bc54df8549d0a04", "archive digest drift")
    paths = source.get("source_paths")
    require(isinstance(paths, list), "source paths missing")
    by_path = {item.get("path"): item for item in paths if isinstance(item, dict)}
    require(set(by_path) == set(EXPECTED_SOURCE) == set(REQUIRED_SOURCE_PATHS), "source path set drift")
    for path, expected in EXPECTED_SOURCE.items():
        item = by_path[path]
        for key, value in expected.items():
            require(item.get(key) == value, f"source identity drift: {path}:{key}")
    if agent_com_root is not None:
        require(git(agent_com_root, "rev-parse", "HEAD") == UPSTREAM_COMMIT, "upstream HEAD drift")
        require(git(agent_com_root, "rev-parse", f"{UPSTREAM_COMMIT}^{{tree}}") == UPSTREAM_TREE, "upstream tree unavailable")
        require(git_archive_sha256(agent_com_root, UPSTREAM_COMMIT) == source["archive_inventory_sha256"], "archive inventory drift")
        for path, expected in EXPECTED_SOURCE.items():
            require(source_observation(agent_com_root, path) == {"path": path, **expected}, f"Git object drift: {path}")

    implementation = document.get("implementation")
    require(isinstance(implementation, dict), "implementation missing")
    require(implementation.get("candidate_status") == "worktree_materialized_open", "candidate status drift")
    require(implementation.get("source_mode") == "working_tree_until_owner_commit", "candidate source mode drift")
    crate = repo_root / str(implementation.get("crate"))
    require(crate.is_dir(), "direct crate missing")
    require(sha256(crate / "Cargo.toml") == implementation.get("cargo_toml_sha256"), "Cargo.toml hash drift")
    require(sha256(crate / "Cargo.lock") == implementation.get("cargo_lock_sha256"), "Cargo.lock hash drift")
    source_map = safe_repo_file(repo_root, implementation.get("source_map"), "source map")
    require(sha256(source_map) == implementation.get("source_map_sha256"), "source map hash drift")
    implementation_files = implementation.get("files")
    require(isinstance(implementation_files, list) and len(implementation_files) == 7, "implementation file inventory drift")
    require(
        {item.get("path") for item in implementation_files if isinstance(item, dict)}
        == {
            "crates/sipi-agent-com-direct/src/lib.rs",
            "crates/sipi-agent-com-direct/src/config_preflight_v1.rs",
            "crates/sipi-agent-com-direct/src/config_validate_v1.rs",
            "crates/sipi-agent-com-direct/src/bin/config_validate.rs",
            "crates/sipi-agent-com-direct/quarantine/agent-com/schemas/r480-config.schema.yaml",
            "crates/sipi-agent-com-direct/quarantine/agent-com/schemas/behavior-presets.yaml",
            "crates/sipi-agent-com-direct/quarantine/agent-com/consumption-registry.v1.json",
        },
        "implementation path inventory drift",
    )
    for item in implementation_files:
        require(isinstance(item, dict), "implementation file malformed")
        path = safe_repo_file(repo_root, item.get("path"), "implementation file")
        if "sha256" in item:
            require(sha256(path) == item["sha256"], f"implementation file hash drift: {item.get('path')}")
    resources = implementation.get("embedded_resources")
    require(isinstance(resources, list) and len(resources) == 3, "embedded resource inventory drift")
    for resource in resources:
        path = safe_repo_file(repo_root, resource.get("path"), "embedded resource")
        require(sha256(path) == resource.get("sha256"), f"embedded resource hash drift: {resource.get('path')}")
        if path.name == "consumption-registry.v1.json":
            registry = json.loads(path.read_text(encoding="utf-8"))
            require(registry.get("_source_sha256") == resource.get("source_sha256"), "consumption source hash drift")
    notice = crate / "quarantine" / "agent-com" / "NOTICE-AGENT-COM-CONFIG-MIT.md"
    require(notice.is_file() and "MIT License" in notice.read_text(encoding="utf-8"), "MIT notice missing")
    crate_lib = (crate / "src" / "lib.rs").read_text(encoding="utf-8")
    lib = (crate / "src" / "config_validate_v1.rs").read_text(encoding="utf-8")
    preflight = (crate / "src" / "config_preflight_v1.rs").read_text(encoding="utf-8")
    cargo = (crate / "Cargo.toml").read_text(encoding="utf-8")
    binary = (crate / "src" / "bin" / "config_validate.rs").read_text(encoding="utf-8")
    for marker in (
        "serde_yaml",
        "r480-config.schema.yaml",
        "behavior-presets.yaml",
        "consumption-registry.v1.json",
        "materialize_r480",
        "resolve_default",
        "materialize_package_r480",
        "consumption_report",
        "materialized_fingerprint",
        "R480-PKG-DUP-NAME",
    ):
        require(marker in lib or marker in str(crate / "Cargo.toml"), f"implementation marker missing: {marker}")
    require("config validate" in binary and "ConfigValidateRequestV1" in binary, "CLI marker missing")
    for marker in (
        "MAX_CONFIG_FILE_BYTES",
        "MAX_CONFIG_CELLS",
        "MAX_NUMERIC_ELEMENTS",
        "MAX_COUNT_VALUE",
        "checked_mul",
        "bounded_integer",
        "canonicalize_override_keys",
        "validate_output_budget",
    ):
        require(marker in lib, f"bounded implementation marker missing: {marker}")
    for marker in (
        "MAX_XLSX_ARCHIVE_ENTRIES",
        "MAX_XLSX_ENTRY_BYTES",
        "MAX_XLSX_TOTAL_UNCOMPRESSED_BYTES",
        "MAX_XLSX_SHARED_STRINGS_BYTES",
        "preflight_sheet_grid",
        "checked_grid_extent",
        "MAX_MAT_EXPANDED_BYTES",
        "MAX_MAT_ELEMENTS",
        "MAX_MAT_DEPTH",
        "MAX_MAT_DIMENSIONS",
        "scan_mat_elements",
        "checked_mul",
    ):
        require(marker in preflight, f"reader preflight marker missing: {marker}")
    require("mod config_preflight_v1;" in crate_lib, "preflight module boundary missing")
    require(all(f'{dependency} = ' in cargo for dependency in ("flate2", "quick-xml", "zip")), "preflight dependency drift")
    require(
        lib.index("preflight_config_source_v1(path, &extension)?")
        < lib.index('"xlsx" => read_com_settings_xlsx_v1(path)'),
        "XLSX preflight does not precede shared reader",
    )
    require(
        lib.index("preflight_config_source_v1(path, &extension)?")
        < lib.index('"mat" => read_com_settings_mat_v1(path)'),
        "MAT preflight does not precede shared reader",
    )
    safety = implementation.get("safety_boundary")
    require(
        safety
        == {
            "max_config_file_bytes": 16777216,
            "max_config_cells": 1000000,
            "max_numeric_elements": 1000000,
            "max_count_value": 1000000,
            "array_dims_checked_mul": True,
            "consumed_nan_and_infinity_fail_closed": True,
            "optional_xlsx_nan_cell_uses_pinned_missing_default": True,
            "pinned_positive_infinity_default_preserved": True,
            "override_keys_canonicalized_after_case_insensitive_validation": True,
            "reader_preflight_before_shared_allocation": True,
            "xlsx_max_archive_entries": 2048,
            "xlsx_max_entry_uncompressed_bytes": 16777216,
            "xlsx_max_total_uncompressed_bytes": 67108864,
            "xlsx_max_metadata_xml_bytes": 1048576,
            "xlsx_max_shared_strings_bytes": 8388608,
            "xlsx_max_sheet_xml_bytes": 16777216,
            "xlsx_max_rectangular_grid_cells": 1000000,
            "mat_max_expanded_bytes": 33554432,
            "mat_max_elements": 1000000,
            "mat_max_depth": 16,
            "mat_max_dimensions": 16,
            "mat_max_matrix_elements": 1000000,
            "pinned_xlsx_and_mat_fixture_preflight_passed": True,
        },
        "safety boundary drift",
    )
    shared_review = implementation.get("shared_reader_review")
    require(isinstance(shared_review, list) and len(shared_review) == 2, "shared reader review missing")
    expected_shared = {
        "crates/sipi-com/src/workbook_v1.rs": (
            "14840d58b29269db739a5c2844796222ecc64e1fe9b1936a7fb86651736f90c3",
            "target_xml_and_rectangular_grid_allocate_after_decode",
        ),
        "crates/sipi-com/src/mat_reader_v1.rs": (
            "c7e327dc724e219d34b776699870fbb2e62b669bbe11712186fd02607685864d",
            "compressed_elements_and_parameter_grid_allocate_after_decode",
        ),
    }
    for item in shared_review:
        require(isinstance(item, dict) and item.get("path") in expected_shared, "shared reader review entry drift")
        expected_hash, expected_finding = expected_shared[item["path"]]
        path = safe_repo_file(repo_root, item["path"], "shared reader review")
        require(
            item.get("sha256") == expected_hash
            and sha256(path) == expected_hash
            and item.get("finding") == expected_finding,
            f"shared reader review binding drift: {item['path']}",
        )

    corpus = json.loads((repo_root / document["corpus"]["path"]).read_text(encoding="utf-8"))
    require(corpus.get("schema") == "sipi.com-01-direct-port-corpus.v1", "corpus schema drift")
    require(corpus.get("work_item") == "COM-01", "corpus work item drift")
    require(corpus.get("upstream", {}).get("commit") == UPSTREAM_COMMIT, "corpus source drift")
    require(document["corpus"]["scenario_count"] == len(corpus["scenarios"]) == 14, "corpus count drift")
    require(document["corpus"]["scenario_set_sha256"] == scenario_set_sha256(corpus), "corpus digest drift")
    require(corpus["fixture_policy"] == "owner_supplied_external_fixture_plus_derived_temp_package_fixture", "fixture policy drift")

    inventory = document.get("reachable_inventory")
    require(isinstance(inventory, dict), "reachable inventory missing")
    require(len(inventory.get("defaults", [])) == 4, "default inventory incomplete")
    require(len(inventory.get("branches", [])) == 10, "branch inventory incomplete")
    require(len(inventory.get("errors", [])) == 7, "error inventory incomplete")
    require(len(inventory.get("artifacts", [])) == 4, "artifact inventory incomplete")
    require(len(inventory.get("open", [])) == 4, "open inventory incomplete")

    runner_text = (repo_root / "tools" / "run_com_01_direct_oracle.py").read_text(encoding="utf-8")
    for marker in (
        "stage_1_source_and_candidate_archive",
        "stage_2_two_run_differential_execution",
        "values_equal_fingerprint_drift",
        "derive_package_warning_fixture",
        "_value_projection",
        "_artifact_summary",
        "difference_keys",
    ):
        require(marker in runner_text, f"runner marker missing: {marker}")

    runner = document.get("runner")
    require(isinstance(runner, dict), "runner binding missing")
    require(runner.get("stage_1") == "pinned_source_and_candidate_archive_ready", "runner stage 1 drift")
    require(runner.get("stage_2") == "two_run_differential_execution_ready_with_external_fixture", "runner stage 2 drift")
    require(runner.get("candidate_binding") == "executable_supplied_at_run_time", "runner candidate drift")
    require(
        runner.get("evidence_payload") == "hashes_counts_error_categories_and_bounded_difference_keys_only"
        and runner.get("complete_materialized_values_stored") is False,
        "differential payload scope drift",
    )
    for field, path in (
        ("preparation_runner_sha256", repo_root / "tools" / "run_com_01_direct_oracle.py"),
        ("differential_verifier_sha256", repo_root / "tools" / "verify_com_01_direct_differential.py"),
    ):
        require(sha256(path) == runner.get(field), f"runner binding drift: {field}")
    report_path = safe_repo_file(repo_root, runner.get("latest_external_fixture_report"), "differential report")
    require(sha256(report_path) == runner.get("latest_external_fixture_report_sha256"), "differential report hash drift")
    require(runner.get("latest_report_status") == "open_differential_mismatch_fingerprint_only", "differential status drift")

    for claim in (
        "no_branch_complete_parity",
        "no_com_runtime_execution",
        "no_product_capability_promotion",
        "no_global_migration_row_close",
        "no_workbook_or_mat_bytes_vendored",
        "no_external_fixture_custody",
        "no_release_readiness",
    ):
        require(claim in set(document.get("non_claims", [])), f"non-claim missing: {claim}")

    text = json.dumps(document, sort_keys=True)
    require(not re.search(r"(?:[A-Za-z]:[\\\\/]|/)(?:[^\\n\\r ]*[\\\\/])?(?:Users|user|tmp|Temp|var)[\\\\/]", text), "manifest contains local path")
    return {"schema": document["schema"], "status": document["status"], "scenario_count": len(corpus["scenarios"])}


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
