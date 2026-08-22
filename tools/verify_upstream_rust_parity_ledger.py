"""Verify the ordered upstream-to-direct-Rust parity state machine."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/baselines/upstream-rust-parity-ledger.v1.yaml"
INVENTORY = ROOT / "docs/baselines/upstream-migration-inventory.v1.yaml"
COVERAGE = ROOT / "docs/baselines/upstream-rust-candidate-coverage.v1.yaml"
CLI_INTEGRATION = ROOT / "docs/baselines/upstream-cli-integration.v1.yaml"

SCHEMA = "sipi.upstream-rust-parity-ledger.v1"
STAGES = ("source_admitted", "branch_frozen", "oracle_bound", "direct_port_present", "parity_observed", "completion")
TERMINAL_STATES = {"rust_parity_accepted", "retained_external_runtime", "excluded_by_owner"}
TERMINAL_STATE_ORDER = ["rust_parity_accepted", "retained_external_runtime", "excluded_by_owner"]
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

EXPECTED_ROWS = {
    "AS-01": ("agent_spice", "fit-sparam", "src/agent_spice/cli.py", "upstream.agent-spice.fit-sparam", "sipi-agent-spice-adapter"),
    "AS-02": ("agent_spice", "fit-sparam-cascade", "src/agent_spice/cli.py", "upstream.agent-spice.fit-sparam-cascade", "sipi-agent-spice-adapter"),
    "AS-03": ("agent_spice", "fit-yparam", "src/agent_spice/cli.py", "upstream.agent-spice.fit-yparam", "sipi-agent-spice-adapter"),
    "AS-04": ("agent_spice", "tune-yparam-tran", "src/agent_spice/cli.py", "upstream.agent-spice.tune-yparam-tran", "sipi-agent-spice-adapter"),
    "AS-05": ("agent_spice", "run-hspice", "src/agent_spice/cli.py", "upstream.agent-spice.run-hspice", "sipi-agent-spice-adapter"),
    "AS-06": ("agent_spice", "run-rfm", "src/agent_spice/cli.py", "upstream.agent-spice.run-rfm", "sipi-agent-spice-adapter"),
    "PB-01": ("pybert", "sim", "src/pybert/cli.py", "upstream.pybert.sim", "sipi-pybert-adapter"),
    "PB-02": ("pybert", "sim-native", "src/pybert/cli.py", "upstream.pybert.sim-native", "sipi-pybert-adapter"),
    "PB-03": ("pybert", "sim-rust", "src/pybert/cli.py", "upstream.pybert.sim-rust", "sipi-pybert-adapter"),
    "PB-04": ("pybert", "sim-auto", "src/pybert/cli.py", "upstream.pybert.sim-auto", "sipi-pybert-adapter"),
    "PB-05": ("pybert", "sim-compare", "src/pybert/cli.py", "upstream.pybert.sim-compare", "sipi-pybert-adapter"),
    "COM-01": ("agent_com", "config-validate", "src/agent_com/cli.py", "upstream.agent-com.config-validate", "sipi-agent-com-adapter"),
    "COM-02": ("agent_com", "run", "src/agent_com/cli.py", "upstream.agent-com.run", "sipi-agent-com-adapter"),
    "COM-03": ("agent_com", "compare", "src/agent_com/cli.py", "upstream.agent-com.compare", "sipi-agent-com-adapter"),
    "COM-04": ("agent_com", "load_config-run_com-write_artifacts", "src/agent_com/__init__.py", "upstream.agent-com.public-api", "sipi-agent-com-adapter"),
}
EXPECTED_SOURCES = {
    "agent_spice": {"commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5", "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402", "license": "MIT"},
    "pybert": {"commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe", "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24", "license": "BSD-3-Clause"},
    "agent_com": {"commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea", "license": "MIT"},
}
EXPECTED_ENTRYPOINT_BLOBS = {
    "agent_spice": ("321a32b860f969f0be74f883bedbbae3f67d6284", "908489c8c3a4826d49175c66b3d533413db4624b10fc3c797795b723b62262e1"),
    "pybert": ("4c1116007d31bcebf8db3252363eed7774c7b349", "3826b0c156166e6f04b0e9997ce64a53a53867db6d89143b7c582ca2cf4337c9"),
    "agent_com": ("7964d84bd52d60731bbf56ab9847bf4c190eacf9", "3ca1d26c097abaaa6197682a2c095dc2bc9d5810177429662a40463096fb51ca"),
}
EXPECTED_SPECIAL_BLOBS = {
    "src/agent_com/__init__.py": ("19942e5cc8e9ffa6572dd0ee6fc0861250ccf58b", "0608729cb58b26107264c005cb362f713635783cca01f70967ecf0fa8253a0e0"),
}
EXPECTED_RESERVED = {
    "PB-02": ["simulation_input_v1_schema", "native_extension_selection", "native_result_artifacts", "diagnostics", "pinned_runtime_attestation", "two_fresh_oracle_runs"],
    "COM-03": ["result_json_loader", "golden_schema", "mismatch_report", "tolerance", "pinned_runtime_attestation", "two_fresh_oracle_runs"],
}
EXPECTED_COVERAGE_ADAPTERS = {
    "sipi-agent-spice-adapter": "agent_spice_adapter",
    "sipi-pybert-adapter": "pybert_adapter",
    "sipi-agent-com-adapter": "agent_com_adapter",
}


class LedgerError(RuntimeError):
    """Raised when the parity ledger is malformed or over-promoted."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise LedgerError(reason)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise LedgerError(f"document_invalid:{path.name}") from error
    _require(isinstance(value, dict), f"document_not_mapping:{path.name}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hex(value: Any, pattern: re.Pattern[str], reason: str) -> None:
    _require(isinstance(value, str) and pattern.fullmatch(value) is not None, reason)


def _verify_binding(root: Path, binding: Any, expected_path: str, reason: str) -> None:
    _require(isinstance(binding, dict), f"{reason}_missing")
    _require(binding.get("path") == expected_path, f"{reason}_path_drift")
    _hex(binding.get("sha256"), HEX64, f"{reason}_hash_shape_invalid")
    path = root / expected_path
    _require(path.is_file(), f"{reason}_document_missing")
    _require(binding["sha256"] == _sha256(path), f"{reason}_hash_drift")


def _rows_by_id(value: Any, reason: str) -> dict[str, dict[str, Any]]:
    _require(isinstance(value, list), f"{reason}_invalid")
    result: dict[str, dict[str, Any]] = {}
    for item in value:
        _require(isinstance(item, dict) and isinstance(item.get("id"), str), f"{reason}_row_invalid")
        _require(item["id"] not in result, f"{reason}_duplicate:{item['id']}")
        result[item["id"]] = item
    return result


def _verify_related_documents(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    inventory = _load(root / "docs/baselines/upstream-migration-inventory.v1.yaml")
    coverage = _load(root / "docs/baselines/upstream-rust-candidate-coverage.v1.yaml")
    integration = _load(root / "docs/baselines/upstream-cli-integration.v1.yaml")
    _require(inventory.get("schema") == "sipi.upstream-migration-inventory.v1", "inventory_schema_invalid")
    _require(inventory.get("completion_states") == ["rust_parity_accepted", "retained_external_runtime", "excluded_by_owner"], "inventory_completion_states_invalid")
    _require(inventory.get("summary", {}).get("migration_rows") == 15, "inventory_row_count_invalid")
    _require(coverage.get("schema") == "sipi.upstream-rust-candidate-coverage.v1", "coverage_schema_invalid")
    _require(coverage.get("audit", {}).get("all_rows_completion") == "open", "coverage_promoted")
    _require(coverage.get("audit", {}).get("no_parity_acceptance") is True, "coverage_parity_claim")
    _require(integration.get("schema") == "sipi.upstream-cli-integration.v1", "integration_schema_invalid")
    _require(integration.get("scope", {}).get("product_capability") == "not_claimed", "integration_capability_claim")
    inventory_sources = inventory.get("source_repositories")
    _require(isinstance(inventory_sources, dict), "inventory_sources_missing")
    _require(inventory_sources == {repo: {**data, "cli_path": inventory_sources.get(repo, {}).get("cli_path")} for repo, data in inventory_sources.items()}, "inventory_sources_shape_invalid")
    for repo, expected in EXPECTED_SOURCES.items():
        actual = inventory_sources.get(repo)
        _require(isinstance(actual, dict), f"inventory_source_missing:{repo}")
        for key in ("commit", "tree"):
            _require(actual.get(key) == expected[key], f"inventory_source_{key}_drift:{repo}")
    inventory_rows = _rows_by_id(inventory.get("entries"), "inventory_entries")
    coverage_rows = _rows_by_id(coverage.get("entries"), "coverage_entries")
    integration_rows = _rows_by_id(integration.get("routes"), "integration_routes")
    _require(set(inventory_rows) == set(EXPECTED_ROWS), "inventory_row_set_invalid")
    _require(set(coverage_rows) == set(EXPECTED_ROWS), "coverage_row_set_invalid")
    _require(set(integration_rows) == set(EXPECTED_ROWS), "integration_row_set_invalid")
    source_objects = coverage.get("source_objects")
    _require(isinstance(source_objects, dict) and set(source_objects) == set(EXPECTED_SOURCES), "coverage_source_objects_invalid")
    for repo, expected in EXPECTED_SOURCES.items():
        source = source_objects[repo]
        _require(source.get("commit") == expected["commit"] and source.get("tree") == expected["tree"], f"coverage_source_object_identity_drift:{repo}")
        modules = source.get("modules")
        _require(isinstance(modules, list), f"coverage_source_modules_invalid:{repo}")
        for module in modules:
            _require(isinstance(module, dict) and set(module) == {"path", "blob_sha1", "sha256"}, f"coverage_source_module_shape_invalid:{repo}")
            _hex(module.get("blob_sha1"), HEX40, f"coverage_source_blob_shape_invalid:{repo}")
            _hex(module.get("sha256"), HEX64, f"coverage_source_hash_shape_invalid:{repo}")
    return inventory_rows, coverage_rows, integration_rows, source_objects


def _verify_source(row: dict[str, Any], item_id: str, inventory_row: dict[str, Any], coverage_row: dict[str, Any], coverage_source: dict[str, Any]) -> None:
    repo, entrypoint, source_path, _, _ = EXPECTED_ROWS[item_id]
    source = row.get("source")
    _require(isinstance(source, dict), f"source_missing:{item_id}")
    required = {"source_path", "entrypoint_blob_sha1", "entrypoint_sha256", "reachable_inventory_ref", "reachable_modules", "per_path_license"}
    _require(set(source) == required, f"source_shape_invalid:{item_id}")
    _require(row.get("repo") == repo and row.get("public_entrypoint") == entrypoint, f"row_identity_invalid:{item_id}")
    _require(source.get("source_path") == source_path, f"source_path_invalid:{item_id}")
    _hex(source.get("entrypoint_blob_sha1"), HEX40, f"entrypoint_blob_shape_invalid:{item_id}")
    _hex(source.get("entrypoint_sha256"), HEX64, f"entrypoint_hash_shape_invalid:{item_id}")
    expected_blob, expected_hash = EXPECTED_ENTRYPOINT_BLOBS[repo]
    if source_path in EXPECTED_SPECIAL_BLOBS:
        expected_blob, expected_hash = EXPECTED_SPECIAL_BLOBS[source_path]
    _require(source["entrypoint_blob_sha1"] == expected_blob and source["entrypoint_sha256"] == expected_hash, f"entrypoint_binding_drift:{item_id}")
    _require(source.get("reachable_inventory_ref") == f"candidate_coverage.entries.{item_id}.upstream", f"reachable_reference_invalid:{item_id}")
    upstream = coverage_row.get("upstream")
    _require(isinstance(upstream, dict), f"coverage_upstream_missing:{item_id}")
    _require(upstream.get("repo") == repo and upstream.get("entrypoint") == entrypoint and upstream.get("source_path") == source_path, f"coverage_source_identity_drift:{item_id}")
    modules = source.get("reachable_modules")
    _require(isinstance(modules, list) and modules and all(isinstance(path, str) and path.startswith("src/") for path in modules), f"reachable_modules_invalid:{item_id}")
    _require(modules == upstream.get("reachable_modules"), f"reachable_modules_drift:{item_id}")
    source_modules = {item["path"]: item for item in coverage_source.get("modules", [])}
    for module_path in modules:
        module = source_modules.get(module_path)
        _require(isinstance(module, dict), f"reachable_blob_unbound:{item_id}:{module_path}")
        _hex(module.get("blob_sha1"), HEX40, f"reachable_blob_shape_invalid:{item_id}:{module_path}")
        _hex(module.get("sha256"), HEX64, f"reachable_content_hash_shape_invalid:{item_id}:{module_path}")
    per_path = source.get("per_path_license")
    _require(isinstance(per_path, dict) and set(per_path) == {"status", "paths"}, f"per_path_license_shape_invalid:{item_id}")
    status = per_path.get("status")
    paths = per_path.get("paths")
    if status == "pending_per_path_review":
        _require(paths == [], f"pending_license_paths_present:{item_id}")
    elif status == "verified":
        _verify_per_path_license(per_path, source, item_id)
    else:
        raise LedgerError(f"per_path_license_status_invalid:{item_id}")
    adapter = row.get("adapter_route")
    _require(isinstance(adapter, dict) and set(adapter) == {"command_id", "adapter_crate"}, f"adapter_route_shape_invalid:{item_id}")
    _, _, _, expected_command, expected_crate = EXPECTED_ROWS[item_id]
    _require(adapter == {"command_id": expected_command, "adapter_crate": expected_crate}, f"adapter_route_drift:{item_id}")
    integration = coverage_row.get("external_transport")
    _require(isinstance(integration, dict) and integration.get("status") == "integrated_process_external", f"external_route_not_integrated:{item_id}")
    _require(integration.get("adapter") == EXPECTED_COVERAGE_ADAPTERS[expected_crate] and integration.get("product_cli_command") == expected_command, f"coverage_adapter_route_drift:{item_id}")
    _require(inventory_row.get("completion") == "open" and inventory_row.get("parity_status") != "accepted", f"active_inventory_promoted:{item_id}")


def _verify_per_path_license(per_path: dict[str, Any], source: dict[str, Any], item_id: str) -> None:
    paths = per_path.get("paths")
    _require(isinstance(paths, list) and paths, f"per_path_license_missing:{item_id}")
    expected_paths = {source["source_path"], *source["reachable_modules"]}
    seen: set[str] = set()
    for item in paths:
        _require(isinstance(item, dict) and set(item) == {"path", "blob_sha1", "sha256", "license", "license_evidence"}, f"per_path_license_item_invalid:{item_id}")
        path = item["path"]
        _require(isinstance(path, str) and path in expected_paths and path not in seen, f"per_path_license_path_invalid:{item_id}")
        seen.add(path)
        _hex(item["blob_sha1"], HEX40, f"per_path_license_blob_invalid:{item_id}")
        _hex(item["sha256"], HEX64, f"per_path_license_hash_invalid:{item_id}")
        _require(isinstance(item["license"], str) and item["license"] not in {"", "unknown", "pending"}, f"per_path_license_value_invalid:{item_id}")
        evidence = item["license_evidence"]
        _require(isinstance(evidence, dict) and set(evidence) == {"source_path", "blob_sha1", "sha256"}, f"per_path_license_evidence_invalid:{item_id}")
        _require(isinstance(evidence["source_path"], str) and evidence["source_path"], f"per_path_license_evidence_path_invalid:{item_id}")
        _require(not evidence["source_path"].startswith("crates/"), f"per_path_license_must_use_upstream_evidence:{item_id}")
        _hex(evidence["blob_sha1"], HEX40, f"per_path_license_evidence_blob_invalid:{item_id}")
        _hex(evidence["sha256"], HEX64, f"per_path_license_evidence_hash_invalid:{item_id}")
    _require(seen == expected_paths, f"per_path_license_coverage_incomplete:{item_id}")


def _verify_stage_shape(row: dict[str, Any], item_id: str) -> int:
    stages = row.get("stages")
    _require(isinstance(stages, dict) and set(stages) == set(STAGES), f"stage_set_invalid:{item_id}")
    statuses: list[str] = []
    for stage in STAGES:
        value = stages[stage]
        _require(isinstance(value, dict) and isinstance(value.get("status"), str), f"stage_invalid:{item_id}:{stage}")
        status = value["status"]
        _require(status in {"verified", "blocked", "not_started"}, f"stage_status_invalid:{item_id}:{stage}")
        statuses.append(status)
        if status == "verified":
            _require(isinstance(value.get("evidence"), list) and value["evidence"], f"stage_evidence_missing:{item_id}:{stage}")
        else:
            _require(isinstance(value.get("missing"), list) and value["missing"], f"stage_missing_reason:{item_id}:{stage}")
    first_nonverified = next((index for index, status in enumerate(statuses) if status != "verified"), len(STAGES))
    _require(all(status != "verified" for status in statuses[first_nonverified:]), f"stage_order_violation:{item_id}")
    if first_nonverified == 0 and row["source"]["per_path_license"].get("status") == "pending_per_path_review":
        expected_current = "source_identity_bound_pre_admission"
    else:
        expected_current = STAGES[first_nonverified - 1] if first_nonverified else STAGES[0]
    if first_nonverified == len(STAGES):
        expected_current = "completion"
    _require(row.get("current_state") == expected_current, f"current_state_drift:{item_id}")
    return first_nonverified


def _verify_stage_requirements(row: dict[str, Any], item_id: str, first_nonverified: int) -> None:
    stages = row["stages"]
    if stages["source_admitted"]["status"] == "verified":
        _require(set(stages["source_admitted"]["evidence"]) >= {"migration_inventory", "candidate_coverage"}, f"source_admission_evidence_missing:{item_id}")
        _require(row["source"]["per_path_license"].get("status") == "verified", f"source_admission_license_pending:{item_id}")
    elif row["source"]["per_path_license"].get("status") == "pending_per_path_review":
        _require(row["current_state"] == "source_identity_bound_pre_admission", f"source_pre_admission_state_invalid:{item_id}")
    branch = row.get("branch_inventory")
    _require(isinstance(branch, dict) and set(branch) == {"status", "unknown_counts", "evidence"}, f"branch_inventory_shape_invalid:{item_id}")
    if stages["branch_frozen"]["status"] == "verified":
        _require(branch.get("status") == "verified", f"branch_inventory_not_verified:{item_id}")
        counts = branch.get("unknown_counts")
        _require(counts == {"branch": 0, "default": 0, "error": 0, "artifact": 0}, f"branch_unknown_counts:{item_id}")
        _require(isinstance(branch.get("evidence"), list) and branch["evidence"], f"branch_inventory_evidence_missing:{item_id}")
    oracle = row.get("oracle")
    _require(isinstance(oracle, dict) and set(oracle) == {"status", "corpus", "runtime_attestation"}, f"oracle_shape_invalid:{item_id}")
    if stages["oracle_bound"]["status"] == "verified":
        _verify_oracle(oracle, row, item_id)
    direct = row.get("direct_rust")
    _require(isinstance(direct, dict) and set(direct) == {"status", "route", "calls_adapter", "source_hashes"}, f"direct_rust_shape_invalid:{item_id}")
    if stages["direct_port_present"]["status"] == "verified":
        _verify_direct(direct, row, item_id)
    parity = row.get("parity")
    _require(isinstance(parity, dict) and set(parity) == {"status", "tolerance", "observations", "mutation_coverage"}, f"parity_shape_invalid:{item_id}")
    if stages["parity_observed"]["status"] == "verified":
        _verify_parity(parity, item_id)
    _verify_completion(row, item_id, first_nonverified)


def _verify_oracle(oracle: dict[str, Any], row: dict[str, Any], item_id: str) -> None:
    _require(oracle.get("status") == "verified", f"oracle_status_invalid:{item_id}")
    corpus = oracle.get("corpus")
    _require(isinstance(corpus, list) and corpus, f"oracle_corpus_missing:{item_id}")
    for item in corpus:
        _require(isinstance(item, dict) and set(item) == {"id", "input_sha256", "expected_sha256"}, f"oracle_corpus_item_invalid:{item_id}")
        _require(isinstance(item["id"], str) and item["id"], f"oracle_corpus_id_invalid:{item_id}")
        _hex(item["input_sha256"], HEX64, f"oracle_input_hash_invalid:{item_id}")
        _hex(item["expected_sha256"], HEX64, f"oracle_expected_hash_invalid:{item_id}")
    attestation = oracle.get("runtime_attestation")
    _require(isinstance(attestation, dict) and set(attestation) == {"status", "source_commit", "source_tree", "fresh_run_ids", "runtime_source_authenticated"}, f"oracle_attestation_shape_invalid:{item_id}")
    source = row["repo"]
    _require(attestation.get("status") == "clean_pinned_two_fresh", f"oracle_attestation_status_invalid:{item_id}")
    _require(attestation.get("source_commit") == EXPECTED_SOURCES[source]["commit"], f"oracle_attestation_commit_invalid:{item_id}")
    _require(attestation.get("source_tree") == EXPECTED_SOURCES[source]["tree"], f"oracle_attestation_tree_invalid:{item_id}")
    runs = attestation.get("fresh_run_ids")
    _require(isinstance(runs, list) and len(runs) == 2 and len(set(runs)) == 2 and all(isinstance(value, str) and value for value in runs), f"oracle_fresh_runs_invalid:{item_id}")
    _require(attestation.get("runtime_source_authenticated") is True, f"oracle_runtime_unattested:{item_id}")


def _verify_hash_items(items: Any, item_id: str, label: str, require_files: bool) -> set[tuple[str, str]]:
    _require(isinstance(items, list) and items, f"{label}_missing:{item_id}")
    seen: set[tuple[str, str]] = set()
    for item in items:
        _require(isinstance(item, dict), f"{label}_item_invalid:{item_id}")
        _require(set(item) in ({"path", "sha256", "role"}, {"path", "sha256"}), f"{label}_item_shape_invalid:{item_id}")
        path = item.get("path")
        digest = item.get("sha256")
        _require(isinstance(path, str) and path.startswith("crates/"), f"{label}_path_invalid:{item_id}")
        _hex(digest, HEX64, f"{label}_hash_invalid:{item_id}")
        key = (path, digest)
        _require(key not in seen, f"{label}_duplicate:{item_id}")
        seen.add(key)
        if require_files:
            file = ROOT / path
            _require(file.is_file(), f"{label}_file_missing:{item_id}:{path}")
            _require(_sha256(file) == digest, f"{label}_hash_drift:{item_id}:{path}")
    return seen


def _verify_direct(direct: dict[str, Any], row: dict[str, Any], item_id: str) -> None:
    _require(direct.get("status") == "verified", f"direct_status_invalid:{item_id}")
    _require(isinstance(direct.get("route"), list) and direct["route"], f"direct_route_missing:{item_id}")
    _require(direct.get("calls_adapter") is False, f"direct_route_calls_adapter:{item_id}")
    _verify_hash_items(direct.get("source_hashes"), item_id, "direct_source_hashes", True)
    candidate = row.get("candidate_source_hashes")
    _require(isinstance(candidate, dict) and candidate.get("status") == "verified", f"candidate_hashes_not_verified:{item_id}")
    candidate_items = _verify_hash_items(candidate.get("items"), item_id, "candidate_source_hashes", True)
    _require(candidate_items == {(item["path"], item["sha256"]) for item in direct["source_hashes"]}, f"candidate_direct_hash_set_drift:{item_id}")


def _verify_parity(parity: dict[str, Any], item_id: str) -> None:
    _require(parity.get("status") == "verified", f"parity_status_invalid:{item_id}")
    tolerance = parity.get("tolerance")
    _require(isinstance(tolerance, dict) and set(tolerance) == {"frozen_before_observation", "spec"}, f"tolerance_shape_invalid:{item_id}")
    _require(tolerance.get("frozen_before_observation") is True, f"tolerance_not_prefrozen:{item_id}")
    _require(isinstance(tolerance.get("spec"), list) and tolerance["spec"], f"tolerance_spec_missing:{item_id}")
    for item in tolerance["spec"]:
        _require(isinstance(item, dict) and set(item) == {"name", "absolute", "relative", "unit"}, f"tolerance_item_invalid:{item_id}")
        _require(isinstance(item["name"], str) and item["name"], f"tolerance_name_invalid:{item_id}")
        _require(isinstance(item["absolute"], (int, float)) and item["absolute"] >= 0, f"tolerance_absolute_invalid:{item_id}")
        _require(isinstance(item["relative"], (int, float)) and item["relative"] >= 0, f"tolerance_relative_invalid:{item_id}")
        _require(isinstance(item["unit"], str) and item["unit"], f"tolerance_unit_invalid:{item_id}")
    _require(isinstance(parity.get("observations"), list) and parity["observations"], f"parity_observations_missing:{item_id}")
    mutation = parity.get("mutation_coverage")
    _require(isinstance(mutation, dict) and set(mutation) == {"status", "tests"} and mutation.get("status") == "verified", f"mutation_coverage_invalid:{item_id}")
    _verify_hash_items(mutation.get("tests"), item_id, "mutation_tests", True)


def _verify_authority(root: Path, authority: Any, item_id: str) -> None:
    _require(isinstance(authority, dict) and set(authority) == {"kind", "decision_id", "path", "sha256", "statement"}, f"terminal_authority_shape_invalid:{item_id}")
    _require(authority.get("kind") in {"owner_decision", "release_governance_decision"}, f"terminal_authority_kind_invalid:{item_id}")
    _require(isinstance(authority.get("decision_id"), str) and authority["decision_id"], f"terminal_decision_id_missing:{item_id}")
    path = authority.get("path")
    _require(isinstance(path, str) and path.startswith("docs/"), f"terminal_authority_path_invalid:{item_id}")
    _hex(authority.get("sha256"), HEX64, f"terminal_authority_hash_invalid:{item_id}")
    _require(isinstance(authority.get("statement"), str) and authority["statement"], f"terminal_authority_statement_missing:{item_id}")
    file = root / path
    _require(file.is_file(), f"terminal_authority_file_missing:{item_id}")
    _require(_sha256(file) == authority["sha256"], f"terminal_authority_hash_drift:{item_id}")


def _verify_completion(row: dict[str, Any], item_id: str, first_nonverified: int) -> None:
    completion = row.get("completion")
    _require(isinstance(completion, dict) and set(completion) == {"status", "terminal_state", "authority_evidence"}, f"completion_shape_invalid:{item_id}")
    status = completion.get("status")
    terminal = completion.get("terminal_state")
    if terminal is None:
        _require(status == "open" and completion.get("authority_evidence") is None, f"open_completion_invalid:{item_id}")
        _require(first_nonverified < len(STAGES), f"open_completion_without_blocker:{item_id}")
        return
    _require(terminal in TERMINAL_STATES, f"terminal_state_invalid:{item_id}")
    _require(status == "closed", f"closed_status_invalid:{item_id}")
    if terminal == "rust_parity_accepted":
        _require(first_nonverified == len(STAGES), f"rust_parity_before_all_stages:{item_id}")
        _verify_parity_acceptance(row, item_id)
        _require(completion.get("authority_evidence") is None, f"rust_parity_authority_field_invalid:{item_id}")
    else:
        _verify_authority(ROOT, completion.get("authority_evidence"), item_id)
        _require(first_nonverified < len(STAGES), f"terminal_non_rust_without_completion_stage:{item_id}")


def _verify_parity_acceptance(row: dict[str, Any], item_id: str) -> None:
    source = row["source"]
    _require(source["per_path_license"]["status"] == "verified", f"rust_parity_license_pending:{item_id}")
    _verify_per_path_license(source["per_path_license"], source, item_id)
    _require(row["branch_inventory"].get("status") == "verified", f"rust_parity_branch_inventory_pending:{item_id}")
    _require(row["branch_inventory"].get("unknown_counts") == {"branch": 0, "default": 0, "error": 0, "artifact": 0}, f"rust_parity_unknown_reachable_paths:{item_id}")
    _verify_oracle(row["oracle"], row, item_id)
    _verify_direct(row["direct_rust"], row, item_id)
    _verify_parity(row["parity"], item_id)


def _git(root: Path, *args: str, binary: bool = False) -> str | bytes:
    completed = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=60)
    _require(completed.returncode == 0, f"git_object_unavailable:{root.name}:{args[-1]}")
    if binary:
        return completed.stdout
    return completed.stdout.decode("utf-8", errors="strict").strip()


def _verify_source_root(root: Path, repo: str, rows: dict[str, dict[str, Any]]) -> None:
    expected = EXPECTED_SOURCES[repo]
    _require(root.is_dir(), f"source_root_missing:{repo}")
    _require(_git(root, "rev-parse", "HEAD") == expected["commit"], f"source_commit_drift:{repo}")
    _require(_git(root, "rev-parse", "HEAD^{tree}") == expected["tree"], f"source_tree_drift:{repo}")
    for row in rows.values():
        if row["repo"] != repo:
            continue
        source = row["source"]
        path = source["source_path"]
        _require(_git(root, "rev-parse", f"HEAD:{path}") == source["entrypoint_blob_sha1"], f"source_blob_drift:{repo}:{path}")
        payload = _git(root, "show", f"HEAD:{path}", binary=True)
        _require(hashlib.sha256(payload).hexdigest() == source["entrypoint_sha256"], f"source_content_drift:{repo}:{path}")


def validate(document: dict[str, Any] | None = None, root: Path = ROOT, source_roots: dict[str, Path] | None = None) -> dict[str, Any]:
    document = _load(LEDGER) if document is None else copy.deepcopy(document)
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("policy") == "sipi.upstream-capability-first-rust-consolidation.v1", "policy_invalid")
    _require(document.get("status") == "active_open_before_rust_parity", "status_invalid")
    _require(document.get("as_of") == "2026-08-22", "date_invalid")
    machine = document.get("state_machine")
    _require(isinstance(machine, dict), "state_machine_missing")
    _require(machine.get("order") == list(STAGES), "state_order_invalid")
    _require(machine.get("pre_admission_state") == "source_identity_bound_pre_admission", "pre_admission_state_invalid")
    _require(machine.get("stage_statuses") == ["verified", "blocked", "not_started"], "stage_status_policy_invalid")
    _require(machine.get("transition_rule") == "contiguous_verified_prefix_then_blocked_or_not_started", "transition_policy_invalid")
    _require(machine.get("open_completion_state") == "open", "open_completion_policy_invalid")
    _require(machine.get("non_parity_routes") == ["process_external_adapter", "self_test", "fixed_profile", "generic_compare", "similar_name_candidate"], "non_parity_policy_invalid")
    _require(machine.get("terminal_states") == TERMINAL_STATE_ORDER, "terminal_state_policy_invalid")
    _require(machine.get("rust_parity_acceptance_requires") == [
        "exact_source_blobs_and_per_path_license", "reachable_branch_default_error_artifact_unknown_counts_zero", "clean_pinned_two_fresh_oracle_runtime_attestation", "pre_frozen_tolerance", "candidate_source_hashes", "direct_rust_route", "direct_route_does_not_call_adapter", "mutation_coverage",
    ], "acceptance_policy_invalid")
    _require(document.get("source_authority") == EXPECTED_SOURCES, "source_authority_policy_invalid")
    bindings = document.get("evidence_bindings")
    _require(isinstance(bindings, dict), "evidence_bindings_missing")
    _verify_binding(root, bindings.get("migration_inventory"), "docs/baselines/upstream-migration-inventory.v1.yaml", "migration_inventory_binding")
    _verify_binding(root, bindings.get("candidate_coverage"), "docs/baselines/upstream-rust-candidate-coverage.v1.yaml", "candidate_coverage_binding")
    _verify_binding(root, bindings.get("cli_integration"), "docs/baselines/upstream-cli-integration.v1.yaml", "cli_integration_binding")
    _verify_binding(root, bindings.get("audit_document"), "docs/baselines/audits/2026-08-22-upstream-rust-parity-ledger.md", "audit_binding")
    inventory_rows, coverage_rows, integration_rows, coverage_sources = _verify_related_documents(root)
    reserved = document.get("reserved_evidence_interfaces")
    _require(reserved == {key: {"status": "reserved_not_bound", "required_fields": value} for key, value in EXPECTED_RESERVED.items()}, "reserved_interface_policy_invalid")
    rows = _rows_by_id(document.get("rows"), "ledger_rows")
    _require(set(rows) == set(EXPECTED_ROWS), "ledger_row_set_invalid")
    counts = {stage: 0 for stage in STAGES}
    pre_admission_count = 0
    terminal_counts = {state: 0 for state in TERMINAL_STATES}
    for item_id, row in rows.items():
        _require(set(row) <= {"id", "repo", "public_entrypoint", "adapter_route", "reserved_interface", "source", "candidate_source_hashes", "stages", "direct_rust", "branch_inventory", "oracle", "parity", "completion", "current_state"}, f"ledger_row_unknown_fields:{item_id}")
        expected = EXPECTED_ROWS[item_id]
        _require(row.get("id") == item_id, f"ledger_row_id_invalid:{item_id}")
        _require((row.get("repo"), row.get("public_entrypoint")) == expected[:2], f"ledger_row_identity_invalid:{item_id}")
        if item_id in EXPECTED_RESERVED:
            _require(row.get("reserved_interface") == item_id, f"reserved_interface_missing:{item_id}")
        else:
            _require("reserved_interface" not in row, f"unexpected_reserved_interface:{item_id}")
        _verify_source(row, item_id, inventory_rows[item_id], coverage_rows[item_id], coverage_sources[row["repo"]])
        integration = integration_rows[item_id]
        _require(integration.get("command_id") == expected[3] and integration.get("adapter_crate") == expected[4] and integration.get("status") == "route_integrated", f"integration_route_invalid:{item_id}")
        first_nonverified = _verify_stage_shape(row, item_id)
        _verify_stage_requirements(row, item_id, first_nonverified)
        current = row["current_state"]
        if current in counts:
            counts[current] += 1
        elif current == "source_identity_bound_pre_admission":
            pre_admission_count += 1
        else:
            raise LedgerError(f"current_state_unknown:{item_id}")
        terminal = row["completion"]["terminal_state"]
        if terminal is not None:
            terminal_counts[terminal] += 1
        candidate = row["candidate_source_hashes"]
        _require(
            (isinstance(candidate, dict) and set(candidate) == {"status", "evidence_ref"})
            if candidate.get("status") != "verified"
            else (isinstance(candidate, dict) and set(candidate) == {"status", "items", "evidence_ref"}),
            f"candidate_source_hash_shape_invalid:{item_id}",
        )
        if candidate.get("status") == "partial_or_missing":
            _require(candidate.get("evidence_ref") == f"candidate_coverage.entries.{item_id}.candidate.surfaces", f"candidate_evidence_ref_invalid:{item_id}")
        else:
            _require(candidate.get("evidence_ref") == f"candidate_coverage.entries.{item_id}.candidate.surfaces", f"candidate_evidence_ref_invalid:{item_id}")
            _verify_hash_items(candidate.get("items"), item_id, "candidate_source_hashes", True)
    summary = document.get("summary")
    _require(isinstance(summary, dict), "summary_missing")
    expected_summary = {"rows": 15, "source_identity_bound_pre_admission": pre_admission_count, "source_admitted": counts["source_admitted"], "branch_frozen": counts["branch_frozen"], "oracle_bound": counts["oracle_bound"], "direct_port_present": counts["direct_port_present"], "parity_observed": counts["parity_observed"], "completion": counts["completion"], "open": sum(1 for row in rows.values() if row["completion"]["status"] == "open"), **terminal_counts}
    _require(summary == expected_summary, "summary_drift")
    return {"valid": True, "rows": len(rows), "current_states": counts, "terminal_states": terminal_counts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-spice-root", type=Path)
    parser.add_argument("--pybert-root", type=Path)
    parser.add_argument("--agent-com-root", type=Path)
    args = parser.parse_args()
    try:
        roots = {key: value for key, value in {"agent_spice": args.agent_spice_root, "pybert": args.pybert_root, "agent_com": args.agent_com_root}.items() if value is not None}
        result = validate(source_roots=roots or None)
        if roots:
            rows = _rows_by_id(_load(LEDGER).get("rows"), "ledger_rows")
            for repo, source_root in roots.items():
                _verify_source_root(source_root, repo, rows)
                result.setdefault("source_git_objects_checked", []).append(repo)
    except (LedgerError, OSError, UnicodeError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"schema": SCHEMA, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
