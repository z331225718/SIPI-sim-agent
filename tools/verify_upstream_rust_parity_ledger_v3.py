"""Verify the additive, immutable-bound upstream Rust parity ledger v3."""

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
LEDGER = ROOT / "docs/baselines/upstream-rust-parity-ledger.v3.yaml"
SCHEMA = "sipi.upstream-rust-parity-ledger.v3"
POLICY = "sipi.upstream-capability-first-rust-consolidation.v1"
EVIDENCE_COMMIT = "025ef934ff79e1231bd6f80e2be3d12207e814d6"
EVIDENCE_TREE = "bc14798cae8d6a912881264044dae3f272aa338a"
PREPARATION_COMMIT = "9914a23dc747d94405f2fed9227538ae7aea8629"
PREPARATION_TREE = "94a25c6254fdec3802b4946ec777ce65f22fdc0c"
EVIDENCE_ARCHIVE = "5f78ed7c16d6a649e39f46605174aa6630a3a42884b2c9b30c45f78e709fd9aa"
PREDECESSOR_PATH = "docs/baselines/upstream-rust-parity-ledger.v2.yaml"
PREDECESSOR_SHA256 = "2c08c4ca91056a401d37800e560bfefb408b4788fe86fe5b0eb1233c99ba5e7e"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ABSOLUTE = re.compile(r"(?<![A-Za-z0-9])(?:(?:[A-Za-z]):[\\/]|/Users/|/home/)")
FORBIDDEN = ("rust_parity_accepted", "parity_accepted", "release_ready", "product_capability_claimed")

EXPECTED_ROWS = {
    "AS-01": ("agent_spice", "fit-sparam"),
    "AS-02": ("agent_spice", "fit-sparam-cascade"),
    "AS-03": ("agent_spice", "fit-yparam"),
    "AS-04": ("agent_spice", "tune-yparam-tran"),
    "AS-05": ("agent_spice", "run-hspice"),
    "AS-06": ("agent_spice", "run-rfm"),
    "PB-01": ("pybert", "sim"),
    "PB-02": ("pybert", "sim-native"),
    "PB-03": ("pybert", "sim-rust"),
    "PB-04": ("pybert", "sim-auto"),
    "PB-05": ("pybert", "sim-compare"),
    "COM-01": ("agent_com", "config-validate"),
    "COM-02": ("agent_com", "run"),
    "COM-03": ("agent_com", "compare"),
    "COM-04": ("agent_com", "load_config-run_com-write_artifacts"),
}
EXPECTED_SOURCE_AUTHORITY = {
    "agent_spice": {"commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5", "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402", "license": "MIT"},
    "pybert": {"commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe", "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24", "license": "BSD-3-Clause"},
    "agent_com": {"commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea", "license": "MIT"},
}
EXPECTED_STATES = {
    "AS-01": "numeric_mismatch_open",
    "AS-02": "numeric_mismatch_open",
    "AS-03": "numeric_mismatch_open",
    "AS-04": "external_blocked",
    "AS-05": "external_blocked",
    "AS-06": "external_blocked",
    "PB-01": "fixed_fixture_scoped_pass_branch_scope_open",
    "PB-02": "fixed_fixture_scoped_pass_branch_scope_open",
    "PB-03": "rust_branch_coverage_only_oracle_open",
    "PB-04": "external_blocked",
    "PB-05": "external_blocked",
    "COM-01": "historical_only",
    "COM-02": "upstream_portable_leaf_observed_full_timeout_open",
    "COM-03": "historical_only",
    "COM-04": "upstream_portable_leaf_observed_full_timeout_open",
}
EXPECTED_PARITY = {
    "AS-01": "numeric_mismatch_open",
    "AS-02": "numeric_mismatch_open",
    "AS-03": "numeric_mismatch_open",
    "AS-04": "not_accepted",
    "AS-05": "not_accepted",
    "AS-06": "not_accepted",
    "PB-01": "fixed_fixture_scoped_only_not_global",
    "PB-02": "fixed_fixture_scoped_only_not_global",
    "PB-03": "rust_branch_coverage_only_not_global",
    "PB-04": "not_accepted",
    "PB-05": "not_accepted",
    "COM-01": "not_accepted",
    "COM-02": "upstream_only_not_candidate_parity",
    "COM-03": "not_accepted",
    "COM-04": "upstream_only_not_candidate_parity",
}
CURRENT_MANIFESTS = {
    "AS-01": "docs/baselines/as-01-fit-sparam-bound-clean-archive-v3.yaml",
    "AS-02": "docs/baselines/as-02-fit-sparam-cascade-numeric-bound-v2.yaml",
    "AS-03": "docs/baselines/as-03-fit-yparam-numeric-bound-v2.yaml",
    "AS-04": "docs/baselines/as-04-tune-yparam-tran-direct-port.v2.yaml",
    "AS-05": "docs/baselines/as-05-run-hspice-rust-control-direct-port.v2.yaml",
    "AS-06": "docs/baselines/as-06-run-rfm-direct-port.v2.yaml",
    "PB-01": "docs/baselines/pb-01-legacy-leaf-current-d3154093.v1.yaml",
    "PB-02": "docs/baselines/pb-02-direct-current-d3154093.v1.yaml",
    "PB-03": "docs/baselines/pb-03-legacy-branch-coverage-d3154093.v1.yaml",
    "PB-04": "docs/baselines/pb-04-direct-port.current-bound.v1.yaml",
    "PB-05": "docs/baselines/pb-05-direct-port.current-bound.v1.yaml",
    "COM-02": "docs/baselines/com-upstream-runtime-oracle.v2.yaml",
    "COM-04": "docs/baselines/com-upstream-runtime-oracle.v2.yaml",
}
EXPECTED_AUDITS = {
    "AS-01": ("docs/baselines/audits/2026-08-23-as-01-fit-sparam-clean-archive-v3.md", "ad8f3879d22295f017b4a33d0bbaa03c15bba77aa30244e9ea35c5021eddc246"),
    "AS-02": ("docs/baselines/audits/2026-08-23-as-02-as-03-numeric-bound-v2.md", "4df48bb4debbb2475a09d7cdbb5b05beb84ea98a0c204510e0e7ea77b461fccb"),
    "AS-03": ("docs/baselines/audits/2026-08-23-as-02-as-03-numeric-bound-v2.md", "4df48bb4debbb2475a09d7cdbb5b05beb84ea98a0c204510e0e7ea77b461fccb"),
    "AS-04": ("docs/baselines/audits/2026-08-23-as-04-tune-yparam-tran-v2.md", "2585655813258816e5122e88b7556d328f2191595b836b60c5c0182268e83408"),
    "AS-05": ("docs/baselines/audits/2026-08-23-as-05-run-hspice-rust-control-v2.md", "1a95b47dec0a9872cf0c50d3fa41b2767d3aaeea2c24781ad6723b71269240be"),
    "AS-06": ("docs/baselines/audits/2026-08-23-as-06-run-rfm-v2.md", "7944aacab9717939b9912cce1312a1c7fa0ea33a54a30a1cb1f7e95f06df781b"),
    "PB-01": ("docs/baselines/audits/2026-08-23-pb-01-current-d3154093.md", "2842e3e731ad35f7ca0440a0176b9c3cb07529227a8796b50fdd635cc2ade255"),
    "PB-02": ("docs/baselines/audits/2026-08-23-pb-02-current-d3154093.md", "439afb8c57b95fcded09aee8f09e096a654677fb8a215e8006d591827246f74f"),
    "PB-03": ("docs/baselines/audits/2026-08-23-pb-03-legacy-branch-coverage-d3154093.md", "c60e6aa4860e473d75e3abb04624ed31a21a67be8e4c51a2b29f3e53a2814dfa"),
    "PB-04": ("docs/baselines/audits/2026-08-23-pb-04-current-bound.md", "70ff7c652fc7822dd53371736be4f583b59e73887d67698dea661bc25c387907"),
    "PB-05": ("docs/baselines/audits/2026-08-23-pb-05-current-bound.md", "925e86126e04db80671ef96b4830c8e38fa164918e5df792bac148f56a9c6bd4"),
    "COM-02": ("docs/baselines/audits/2026-08-23-com-upstream-runtime-oracle-v2.md", "52d07a557c67a47f4ffee1968df468f9f0354eea9935a53933941d94a1a7b992"),
    "COM-04": ("docs/baselines/audits/2026-08-23-com-upstream-runtime-oracle-v2.md", "52d07a557c67a47f4ffee1968df468f9f0354eea9935a53933941d94a1a7b992"),
}
EXPECTED_HISTORICAL_AUDITS = {
    "COM-01": ("docs/baselines/audits/2026-08-23-com-01-direct-replay-bound.md", "5dec2592a9b83001b6f31cb1a56ac7e86399ff306ffdfaeb8d65a2df5d700c4b"),
    "COM-03": ("docs/baselines/audits/2026-08-23-com-03-direct-port-bound.md", "35c3a402a7f3cdc16ff64d38e798ec6bece63c4a6e9cc3e517fc115fdd7883c3"),
}
HISTORICAL_MANIFESTS = {
    "COM-01": "docs/baselines/com-01-direct-replay-bound.v2.yaml",
    "COM-03": "docs/baselines/com-03-direct-port-bound.v2.yaml",
}
EXPECTED_MANIFEST_STATUS = {
    "AS-01": "completed_numeric_mismatch",
    "AS-02": "completed_numeric_mismatch_open",
    "AS-03": "completed_numeric_mismatch_open",
    "AS-04": "completed_external_blocker_open",
    "AS-05": "completed_external_blocker_open",
    "AS-06": "completed_external_blocker_open",
    "PB-01": "passed_replay_open",
    "PB-02": "passed_replay_open",
    "PB-03": "branch_probe_open",
    "PB-04": "blocked_external_python_reference_required",
    "PB-05": "blocked_not_evaluated_external_reference_required",
    "COM-02": "portable_numeric_observed_full_entrypoint_blocked",
    "COM-04": "portable_numeric_observed_full_entrypoint_blocked",
}
LEGACY_SOURCE = {"commit": "64b783f66d7e986d0975be5ac3946b453b15c4ed", "tree": "0e11721f2bb5b564002820cc7a5aaab45e30ba3b", "archive_sha256": "c89bc44b36849724b9544eb6222a6431ecd3855ce4c943e6a3845cafe19375b9"}
NEW_AS_SOURCE = {"commit": PREPARATION_COMMIT, "tree": PREPARATION_TREE}
NEW_PB_SOURCE = {"commit": "d3154093fd58aeaa596444825dc17be6cb7e35c0", "tree": "2d51e84554558bb4947c0152259af9bf7f927efe", "archive_sha256": "693c95330b36f0a8068db3ce9a44bf4d45bfd1b73f47189d8149d67cfd909a24"}
NEW_COM_SOURCE = {"commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea", "archive_sha256": "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf"}
NEW_ROWS = {"AS-01", "AS-02", "AS-03", "PB-01", "PB-02", "PB-03", "COM-02", "COM-04"}
LEGACY_ROWS = {"AS-04", "AS-05", "AS-06", "PB-04", "PB-05"}


class LedgerError(RuntimeError):
    """Raised when the successor ledger is malformed or over-promoted."""


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
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise LedgerError(f"file_unreadable:{path}") from error


def _hex(value: object, pattern: re.Pattern[str], reason: str) -> None:
    _require(isinstance(value, str) and pattern.fullmatch(value) is not None, reason)


def _git(root: Path, *args: str, binary: bool = False) -> str | bytes:
    completed = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=120)
    _require(completed.returncode == 0, f"git_object_unavailable:{args[-1]}")
    if binary:
        return completed.stdout
    return completed.stdout.decode("utf-8", errors="strict").strip()


def _archive_sha(root: Path, commit: str) -> str:
    payload = _git(root, "archive", "--format=tar", commit, binary=True)
    return hashlib.sha256(payload).hexdigest()


def _safe_path(value: object) -> bool:
    return isinstance(value, str) and bool(value) and "\\" not in value and not value.startswith("/") and ".." not in value.split("/")


def _binding(root: Path, item: Any, expected_path: str, reason: str, *, immutable: bool) -> None:
    _require(isinstance(item, dict), f"{reason}_missing")
    _require(item.get("path") == expected_path and _safe_path(expected_path), f"{reason}_path_drift")
    _hex(item.get("sha256"), HEX64, f"{reason}_hash_shape_invalid")
    path = root / expected_path
    _require(path.is_file(), f"{reason}_file_missing")
    _require(_sha256(path) == item["sha256"], f"{reason}_hash_drift")
    if immutable:
        payload = _git(root, "show", f"{EVIDENCE_COMMIT}:{expected_path}", binary=True)
        _require(hashlib.sha256(payload).hexdigest() == item["sha256"], f"{reason}_immutable_hash_drift")


def _file_payload(root: Path, item: Any, reason: str) -> Any:
    _require(isinstance(item, dict), f"{reason}_shape_invalid")
    path_value = item.get("path")
    _require(_safe_path(path_value), f"{reason}_path_invalid")
    _hex(item.get("sha256"), HEX64, f"{reason}_hash_shape_invalid")
    path = root / path_value
    _require(path.is_file(), f"{reason}_file_missing")
    _require(_sha256(path) == item["sha256"], f"{reason}_hash_drift")
    text = path.read_text(encoding="utf-8", errors="replace")
    _require(ABSOLUTE.search(text) is None, f"{reason}_absolute_path_leak")
    if path.suffix.lower() != ".json":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise LedgerError(f"{reason}_json_invalid") from error


def _rows(value: Any) -> dict[str, dict[str, Any]]:
    _require(isinstance(value, list), "rows_invalid")
    result: dict[str, dict[str, Any]] = {}
    for row in value:
        _require(isinstance(row, dict) and isinstance(row.get("id"), str), "row_invalid")
        _require(row["id"] not in result, f"row_duplicate:{row['id']}")
        result[row["id"]] = row
    return result


def _verify_related_documents(root: Path, document: dict[str, Any]) -> None:
    bindings = document.get("evidence_bindings")
    _require(isinstance(bindings, dict), "evidence_bindings_missing")
    _binding(root, bindings.get("audit_document"), "docs/baselines/audits/2026-08-23-upstream-rust-parity-ledger-v3.md", "audit_document", immutable=False)
    for key, path in (
        ("candidate_coverage_v2", "docs/baselines/upstream-rust-candidate-coverage.v2.yaml"),
        ("migration_inventory", "docs/baselines/upstream-migration-inventory.v1.yaml"),
        ("cli_integration", "docs/baselines/upstream-cli-integration.v1.yaml"),
    ):
        _binding(root, bindings.get(key), path, key, immutable=True)
    for key, path in (
        ("product_boundary", "product-boundary.v1.yaml"),
        ("license_manifest", "license-manifest.v2.yaml"),
        ("source_map", "rust-candidate-source-map.v1.yaml"),
    ):
        _binding(root, bindings.get(key), path, key, immutable=False)
    harness = document.get("harness")
    _require(isinstance(harness, dict), "harness_missing")
    _binding(root, harness.get("verifier"), "tools/verify_upstream_rust_parity_ledger_v3.py", "harness_verifier", immutable=False)
    _binding(root, harness.get("mutation_tests"), "tools/test_verify_upstream_rust_parity_ledger_v3.py", "harness_mutation_tests", immutable=False)
    coverage = _load(root / "docs/baselines/upstream-rust-candidate-coverage.v2.yaml")
    _require(coverage.get("schema") == "sipi.upstream-rust-candidate-coverage.v2", "candidate_coverage_schema_invalid")
    _require(coverage.get("status") == "audited_open_no_upstream_parity", "candidate_coverage_promoted")
    coverage_rows = _rows(coverage.get("entries"))
    _require(set(coverage_rows) == set(EXPECTED_ROWS), "candidate_coverage_row_set_invalid")
    for item_id, row in coverage_rows.items():
        candidate = row.get("candidate", {})
        _require(candidate.get("classification") == "partial_surface", f"candidate_class_invalid:{item_id}")
        _require(candidate.get("completion") == "open" and candidate.get("parity") == "not_evaluated", f"candidate_state_promoted:{item_id}")
    inventory = _load(root / "docs/baselines/upstream-migration-inventory.v1.yaml")
    _require(inventory.get("schema") == "sipi.upstream-migration-inventory.v1", "migration_inventory_schema_invalid")
    _require(inventory.get("summary", {}).get("migration_rows") == 15, "migration_inventory_row_count_invalid")
    inventory_rows = _rows(inventory.get("entries"))
    _require(set(inventory_rows) == set(EXPECTED_ROWS), "migration_inventory_row_set_invalid")
    for item_id, row in inventory_rows.items():
        _require(row.get("completion") == "open", f"migration_inventory_completion_promoted:{item_id}")
        _require(row.get("parity_status") in {"not_evaluated", "profile_only_not_workflow_parity"}, f"migration_inventory_parity_promoted:{item_id}")


def _verify_source_binding(item_id: str, row: dict[str, Any], manifest: dict[str, Any]) -> None:
    binding = row.get("source_binding")
    _require(isinstance(binding, dict), f"source_binding_missing:{item_id}")
    if item_id.startswith("AS-"):
        source = manifest.get("source")
        _require(isinstance(source, dict), f"manifest_source_missing:{item_id}")
        candidate = source.get("candidate")
        _require(isinstance(candidate, dict), f"manifest_candidate_missing:{item_id}")
        actual = {"candidate_commit": candidate.get("commit"), "candidate_tree": candidate.get("tree"), "candidate_archive_sha256": candidate.get("archive_sha256")}
        _require(actual == binding, f"source_binding_drift:{item_id}")
        upstream = source.get("upstream")
        _require(isinstance(upstream, dict), f"manifest_upstream_missing:{item_id}")
        _require(upstream.get("commit") == EXPECTED_SOURCE_AUTHORITY["agent_spice"]["commit"] and upstream.get("tree") == EXPECTED_SOURCE_AUTHORITY["agent_spice"]["tree"], f"upstream_source_drift:{item_id}")
    elif item_id.startswith("PB-"):
        source = manifest.get("source")
        _require(isinstance(source, dict), f"manifest_source_missing:{item_id}")
        if item_id == "PB-03":
            actual = {"candidate_commit": source.get("candidate_commit"), "candidate_tree": source.get("candidate_tree"), "lane_inventory_sha256": source.get("lane_inventory_sha256")}
        else:
            actual = {"candidate_commit": source.get("candidate_commit"), "candidate_tree": source.get("candidate_tree"), "candidate_archive_sha256": source.get("candidate_archive_sha256")}
        _require(actual == binding, f"source_binding_drift:{item_id}")
        _require(source.get("upstream_commit") == EXPECTED_SOURCE_AUTHORITY["pybert"]["commit"] and source.get("upstream_tree") == EXPECTED_SOURCE_AUTHORITY["pybert"]["tree"], f"upstream_source_drift:{item_id}")
    else:
        upstream = manifest.get("upstream")
        _require(isinstance(upstream, dict), f"manifest_upstream_missing:{item_id}")
        actual = {"upstream_commit": upstream.get("commit"), "upstream_tree": upstream.get("tree"), "upstream_archive_sha256": upstream.get("archive_sha256")}
        _require(actual == binding, f"source_binding_drift:{item_id}")
        _require(upstream.get("observation_scope") == "upstream_only", f"com_observation_scope_drift:{item_id}")


def _verify_reports(root: Path, item_id: str, manifest: dict[str, Any], *, key: str = "reports") -> None:
    if item_id.startswith("AS-"):
        reports = manifest.get("reports")
        aggregate = manifest.get("aggregate")
    else:
        evidence = manifest.get("evidence")
        _require(isinstance(evidence, dict), f"manifest_evidence_missing:{item_id}")
        if item_id.startswith("COM-"):
            mode = item_id.lower()
            evidence = evidence.get(mode)
            _require(isinstance(evidence, dict), f"com_evidence_missing:{item_id}")
        reports = evidence.get(key) if isinstance(evidence, dict) else None
        aggregate = evidence.get("aggregate") if isinstance(evidence, dict) else None
    _require(isinstance(reports, list) and len(reports) == 2, f"report_count_invalid:{item_id}")
    aggregate_payload = _file_payload(root, aggregate, f"aggregate:{item_id}")
    identities: set[tuple[str, str]] = set()
    report_refs: set[tuple[str, str]] = set()
    for report in reports:
        payload = _file_payload(root, report, f"report:{item_id}")
        _require(isinstance(payload, dict), f"report_payload_invalid:{item_id}")
        run_id = report.get("run_id") or payload.get("run_id")
        nonce = report.get("nonce") or report.get("fresh_run_nonce") or payload.get("nonce") or payload.get("fresh_run_nonce")
        _require(isinstance(run_id, str) and run_id, f"run_id_missing:{item_id}")
        _hex(nonce, HEX64, f"nonce_invalid:{item_id}")
        identities.add((run_id, nonce))
        report_refs.add((report["path"], report["sha256"]))
        if item_id.startswith("AS-"):
            candidate = payload.get("candidate")
            _require(isinstance(candidate, dict), f"report_candidate_missing:{item_id}")
            _require(candidate.get("commit") == report.get("candidate_commit", candidate.get("commit")), f"report_candidate_shape_invalid:{item_id}")
            _require(payload.get("parity_claim") is False or payload.get("numeric_parity") is False, f"report_parity_claim:{item_id}")
        elif item_id.startswith("PB-"):
            _require(payload.get("source_mode") == "git_archive_at_immutable_commit", f"report_source_mode:{item_id}")
            candidate = payload.get("candidate")
            _require(isinstance(candidate, dict), f"report_candidate_missing:{item_id}")
        else:
            upstream = payload.get("upstream")
            _require(isinstance(upstream, dict) and upstream.get("observation_scope") == "upstream_only", f"report_upstream_scope:{item_id}")
            entrypoint = payload.get("entrypoint")
            _require(isinstance(entrypoint, dict) and entrypoint.get("status") == "blocked", f"com_entrypoint_not_blocked:{item_id}")
            _require(entrypoint.get("timeout_seconds") == 15, f"com_timeout_drift:{item_id}")
    _require(len(identities) == 2, f"fresh_run_identity_not_distinct:{item_id}")
    if isinstance(aggregate_payload, dict) and isinstance(aggregate_payload.get("reports"), list):
        aggregate_refs = {(item.get("path"), item.get("sha256")) for item in aggregate_payload["reports"] if isinstance(item, dict)}
        _require(aggregate_refs == report_refs, f"aggregate_report_binding_drift:{item_id}")


def _verify_manifest(root: Path, item_id: str, row: dict[str, Any], manifest: dict[str, Any]) -> None:
    _require(manifest.get("status") == EXPECTED_MANIFEST_STATUS[item_id], f"manifest_status_drift:{item_id}")
    _require(ABSOLUTE.search(json.dumps(manifest, sort_keys=True)) is None, f"manifest_absolute_path_leak:{item_id}")
    _verify_source_binding(item_id, row, manifest)
    if item_id in {"AS-01", "AS-02", "AS-03"}:
        _require(manifest.get("scope", {}).get("parity_claim") is False or manifest.get("parity_claim") is False, f"as_parity_claim:{item_id}")
        _require(manifest.get("scope", {}).get("numeric_mismatch_open") is True or manifest.get("numeric_parity") is False, f"as_numeric_boundary:{item_id}")
        _verify_reports(root, item_id, manifest)
    elif item_id in {"PB-01", "PB-02"}:
        claims = manifest.get("claims", {})
        _require(claims.get("fixture_payload_parity") is True and claims.get("global_row_closed") is False and claims.get("promotion") is False, f"pb_fixture_scope:{item_id}")
        _verify_reports(root, item_id, manifest)
    elif item_id == "PB-03":
        verification = manifest.get("verification", {})
        claims = manifest.get("claims", {})
        _require(verification.get("oracle") == "not_run", "pb03_oracle_promoted")
        _require("18" in str(verification.get("focused_test_result", "")), "pb03_branch_count_drift")
        _require(claims.get("oracle_payload_parity") is False and claims.get("global_row_closed") is False, "pb03_scope_promoted")
    elif item_id in {"COM-02", "COM-04"}:
        upstream = manifest.get("upstream", {})
        oracle = manifest.get("oracle_contract", {})
        _require(upstream.get("runtime_executed") is True and upstream.get("observation_scope") == "upstream_only", f"com_upstream_scope:{item_id}")
        _require(oracle.get("full_run_numeric_parity") is False and oracle.get("entrypoint_timeout_seconds") == 15, f"com_parity_boundary:{item_id}")
        _verify_reports(root, item_id, manifest)


def _verify_rows(root: Path, document: dict[str, Any]) -> None:
    rows = _rows(document.get("rows"))
    _require(set(rows) == set(EXPECTED_ROWS) and len(rows) == 15, "ledger_row_set_invalid")
    for item_id, row in rows.items():
        _require(row.get("repo") == EXPECTED_ROWS[item_id][0] and row.get("public_entrypoint") == EXPECTED_ROWS[item_id][1], f"row_identity_drift:{item_id}")
        _require(row.get("state") == EXPECTED_STATES[item_id], f"row_state_drift:{item_id}")
        _require(row.get("parity") == EXPECTED_PARITY[item_id], f"row_parity_drift:{item_id}")
        _require(row.get("completion") == "open", f"row_completion_promoted:{item_id}")
        _require(row.get("product_capability") == "not_claimed", f"row_product_capability_promoted:{item_id}")
        _require(row.get("candidate_coverage_entry") == item_id, f"candidate_coverage_row_ref_invalid:{item_id}")
        _require(isinstance(row.get("non_claims"), list) and row["non_claims"], f"non_claims_missing:{item_id}")
        if item_id in {"PB-01", "PB-02"}:
            _require(row.get("scope") == {"workflow_payload_parity": True, "global_row_parity": False, "branch_scope_open": True}, f"pb_scope_promoted:{item_id}")
        if item_id == "PB-03":
            _require(row.get("scope") == {"rust_branch_count": 18, "oracle": "not_run", "global_row_parity": False}, "pb03_scope_promoted")
        if item_id in {"COM-02", "COM-04"}:
            _require(row.get("scope") == {"observation_scope": "upstream_only", "portable_leaf_observed": True, "full_entrypoint": "timeout_blocked", "candidate_vs_upstream_parity": "not_executed"}, f"com_scope_promoted:{item_id}")
        serialized = json.dumps(row, sort_keys=True)
        for term in FORBIDDEN:
            _require(term not in serialized, f"forbidden_promotion_term:{item_id}:{term}")
        evidence = row.get("evidence")
        _require(isinstance(evidence, dict), f"evidence_missing:{item_id}")
        if item_id in HISTORICAL_MANIFESTS:
            _require("manifest" not in evidence and isinstance(evidence.get("historical_manifest"), dict), f"historical_shape:{item_id}")
            _binding(root, evidence["historical_manifest"], HISTORICAL_MANIFESTS[item_id], f"historical_manifest:{item_id}", immutable=False)
            _require(evidence["historical_manifest"].get("bound_to_evidence_commit") is False, f"historical_rebound:{item_id}")
            audit_path, audit_sha = EXPECTED_HISTORICAL_AUDITS[item_id]
            _require(evidence["historical_audit"].get("path") == audit_path and evidence["historical_audit"].get("sha256") == audit_sha, f"historical_audit_binding_drift:{item_id}")
            _binding(root, evidence.get("historical_audit"), audit_path, f"historical_audit:{item_id}", immutable=False)
            continue
        _binding(root, evidence.get("manifest"), CURRENT_MANIFESTS[item_id], f"manifest:{item_id}", immutable=True)
        audit_path, audit_sha = EXPECTED_AUDITS[item_id]
        _require(evidence["audit"].get("path") == audit_path and evidence["audit"].get("sha256") == audit_sha, f"audit_binding_drift:{item_id}")
        _binding(root, evidence.get("audit"), audit_path, f"audit:{item_id}", immutable=True)
        manifest = _load(root / CURRENT_MANIFESTS[item_id])
        _verify_manifest(root, item_id, row, manifest)


def validate(document: dict[str, Any] | None = None, root: Path = ROOT) -> dict[str, Any]:
    document = _load(LEDGER) if document is None else copy.deepcopy(document)
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == "current_bound_open_no_upstream_parity", "status_invalid")
    _require(document.get("policy") == POLICY and document.get("as_of") == "2026-08-23", "policy_or_date_invalid")
    evidence = document.get("evidence_commit")
    _require(isinstance(evidence, dict), "evidence_commit_missing")
    _require(evidence.get("commit") == EVIDENCE_COMMIT and evidence.get("tree") == EVIDENCE_TREE, "evidence_commit_identity_drift")
    _require(evidence.get("parent_preparation_commit") == PREPARATION_COMMIT and evidence.get("candidate_tree") == PREPARATION_TREE, "preparation_identity_drift")
    _require(evidence.get("archive_sha256") == EVIDENCE_ARCHIVE and evidence.get("clean_archive_only") is True, "evidence_archive_drift")
    _require(_git(root, "rev-parse", EVIDENCE_COMMIT) == EVIDENCE_COMMIT, "evidence_commit_object_missing")
    _require(_git(root, "rev-parse", f"{EVIDENCE_COMMIT}^{{tree}}") == EVIDENCE_TREE, "evidence_tree_drift")
    _require(_git(root, "rev-parse", f"{EVIDENCE_COMMIT}^") == PREPARATION_COMMIT, "evidence_parent_drift")
    _require(_git(root, "rev-parse", f"{PREPARATION_COMMIT}^{{tree}}") == PREPARATION_TREE, "preparation_tree_drift")
    _require(_archive_sha(root, EVIDENCE_COMMIT) == EVIDENCE_ARCHIVE, "evidence_archive_hash_drift")
    _require(document.get("source_authority") == EXPECTED_SOURCE_AUTHORITY, "source_authority_drift")
    candidate_sources = document.get("candidate_sources")
    _require(isinstance(candidate_sources, dict), "candidate_sources_missing")
    _require(candidate_sources.get("agent_spice") == {"commit": PREPARATION_COMMIT, "tree": PREPARATION_TREE}, "agent_spice_candidate_anchor_drift")
    _require(candidate_sources.get("pybert") == {"commit": NEW_PB_SOURCE["commit"], "tree": NEW_PB_SOURCE["tree"]}, "pybert_candidate_anchor_drift")
    _require(candidate_sources.get("legacy_previous_candidate") == {"commit": LEGACY_SOURCE["commit"], "tree": LEGACY_SOURCE["tree"]}, "legacy_candidate_anchor_drift")
    predecessor = document.get("successor", {}).get("predecessor")
    _binding(root, predecessor, PREDECESSOR_PATH, "predecessor", immutable=False)
    _require(predecessor.get("sha256") == PREDECESSOR_SHA256 and predecessor.get("retained") is True, "predecessor_drift")
    _verify_related_documents(root, document)
    _verify_rows(root, document)
    summary = document.get("summary")
    _require(summary == {"rows": 15, "completion_open": 15, "parity_acceptance_count": 0, "product_capability_claim_count": 0, "current_evidence_rows": 13, "historical_only_rows": 2}, "summary_drift")
    return {"valid": True, "rows": 15, "completion_open": 15, "current_evidence_rows": 13, "historical_only_rows": 2}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate()
    except (LedgerError, OSError, UnicodeError, subprocess.SubprocessError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"schema": SCHEMA, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
