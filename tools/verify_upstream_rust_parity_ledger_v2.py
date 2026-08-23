"""Verify the additive, immutable-bound upstream Rust parity ledger successor."""

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
LEDGER = ROOT / "docs/baselines/upstream-rust-parity-ledger.v2.yaml"
SCHEMA = "sipi.upstream-rust-parity-ledger.v2"
POLICY = "sipi.upstream-capability-first-rust-consolidation.v1"
EVIDENCE_COMMIT = "fa15b90c916ee27090d6a68a38f75f481aec270f"
PREPARATION_COMMIT = "64b783f66d7e986d0975be5ac3946b453b15c4ed"
EVIDENCE_TREE = "49f8bc1f747caaab526fdefae417445f80d850f9"
CANDIDATE_TREE = "0e11721f2bb5b564002820cc7a5aaab45e30ba3b"
CANDIDATE_ARCHIVE = "c89bc44b36849724b9544eb6222a6431ecd3855ce4c943e6a3845cafe19375b9"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_PROMOTION_VALUES = (
    "rust_parity_accepted",
    "parity_accepted",
    "release_ready",
    "product_capability_claimed",
)

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

CURRENT_MANIFESTS = {
    "AS-02": "docs/baselines/as-02-fit-sparam-cascade-direct-port.v2.yaml",
    "AS-03": "docs/baselines/as-03-fit-yparam-direct-port.v2.yaml",
    "AS-04": "docs/baselines/as-04-tune-yparam-tran-direct-port.v2.yaml",
    "AS-05": "docs/baselines/as-05-run-hspice-rust-control-direct-port.v2.yaml",
    "AS-06": "docs/baselines/as-06-run-rfm-direct-port.v2.yaml",
    "PB-01": "docs/baselines/pb-01-legacy-leaf.current-bound.v1.yaml",
    "PB-02": "docs/baselines/pb-02-direct-port.current-bound.v1.yaml",
    "PB-03": "docs/baselines/pb-03-direct-port.current-bound.v1.yaml",
    "PB-04": "docs/baselines/pb-04-direct-port.current-bound.v1.yaml",
    "PB-05": "docs/baselines/pb-05-direct-port.current-bound.v1.yaml",
    "COM-02": "docs/baselines/com-02-direct-port.v2.yaml",
    "COM-04": "docs/baselines/com-04-direct-port.v2.yaml",
}
HISTORICAL_MANIFESTS = {
    "AS-01": "docs/baselines/as-01-fit-sparam-bound.v2.yaml",
    "COM-01": "docs/baselines/com-01-direct-replay-bound.v2.yaml",
    "COM-03": "docs/baselines/com-03-direct-port-bound.v2.yaml",
}
EXPECTED_STATES = {
    "AS-01": "no_new_evidence_this_round",
    "AS-02": "portable_observation_open",
    "AS-03": "portable_observation_open",
    "AS-04": "external_blocked",
    "AS-05": "external_blocked",
    "AS-06": "external_blocked",
    "PB-01": "parity_blocked",
    "PB-02": "parity_blocked",
    "PB-03": "fixed_fixture_scoped_pass_branch_scope_open",
    "PB-04": "external_blocked",
    "PB-05": "external_blocked",
    "COM-01": "no_new_evidence_this_round",
    "COM-02": "archive_derived_internal_semantic_observation_open",
    "COM-03": "no_new_evidence_this_round",
    "COM-04": "archive_derived_internal_semantic_observation_open",
}
EXPECTED_MANIFEST_STATUS = {
    "AS-02": "completed_portable_observation_open",
    "AS-03": "completed_portable_observation_open",
    "AS-04": "completed_external_blocker_open",
    "AS-05": "completed_external_blocker_open",
    "AS-06": "completed_external_blocker_open",
    "PB-01": "blocked_numeric_payload",
    "PB-02": "blocked_payload_parity",
    "PB-03": "passed_replay_open",
    "PB-04": "blocked_external_python_reference_required",
    "PB-05": "blocked_not_evaluated_external_reference_required",
    "COM-02": "bound_clean_archive_observation_open",
    "COM-04": "bound_clean_archive_observation_open",
}
EXPECTED_PARITY = {
    "AS-01": "numeric_mismatch_open",
    "AS-02": "not_accepted",
    "AS-03": "not_accepted",
    "AS-04": "not_accepted",
    "AS-05": "not_accepted",
    "AS-06": "not_accepted",
    "PB-01": "blocked_payload_parity",
    "PB-02": "blocked_payload_parity",
    "PB-03": "fixed_fixture_scoped_only_not_global",
    "PB-04": "not_accepted",
    "PB-05": "not_accepted",
    "COM-01": "not_accepted",
    "COM-02": "not_accepted",
    "COM-03": "not_accepted",
    "COM-04": "not_accepted",
}
EXPECTED_AUDIT = {
    "AS-02": ("docs/baselines/audits/2026-08-23-as-02-fit-sparam-cascade-v2.md", "6acdfe175a3a5223fb2652981b030f2487b12e671095f60b700df6d031dbd945"),
    "AS-03": ("docs/baselines/audits/2026-08-23-as-03-fit-yparam-v2.md", "7e9a38a50acf964eee44426403d11082dc1c2e951a59bccaea5aaa84b9fcc90b"),
    "AS-04": ("docs/baselines/audits/2026-08-23-as-04-tune-yparam-tran-v2.md", "2585655813258816e5122e88b7556d328f2191595b836b60c5c0182268e83408"),
    "AS-05": ("docs/baselines/audits/2026-08-23-as-05-run-hspice-rust-control-v2.md", "1a95b47dec0a9872cf0c50d3fa41b2767d3aaeea2c24781ad6723b71269240be"),
    "AS-06": ("docs/baselines/audits/2026-08-23-as-06-run-rfm-v2.md", "7944aacab9717939b9912cce1312a1c7fa0ea33a54a30a1cb1f7e95f06df781b"),
    "PB-01": ("docs/baselines/audits/2026-08-23-pb-01-current-bound.md", "8b3381a44ae1262392ecbcfb45a009a1cfd4c34d297a63f8a75bd809c828266f"),
    "PB-02": ("docs/baselines/audits/2026-08-23-pb-02-current-bound.md", "381b65de82fb3fc4b077fac3a0cfa13bb1ad86f81cfd70881a4094663b34062a"),
    "PB-03": ("docs/baselines/audits/2026-08-23-pb-03-current-bound.md", "a7cf8e216aa98de672c2baa92f684d87011f84c968602f53b8e31c44504579f1"),
    "PB-04": ("docs/baselines/audits/2026-08-23-pb-04-current-bound.md", "70ff7c652fc7822dd53371736be4f583b59e73887d67698dea661bc25c387907"),
    "PB-05": ("docs/baselines/audits/2026-08-23-pb-05-current-bound.md", "925e86126e04db80671ef96b4830c8e38fa164918e5df792bac148f56a9c6bd4"),
    "COM-02": ("docs/baselines/audits/2026-08-23-com-02-direct-semantic-replay-v2.md", "9069646b14618b25a317db2987619d3ce4b1a4b146cbafc3746febcdc66fabed"),
    "COM-04": ("docs/baselines/audits/2026-08-23-com-04-direct-semantic-replay-v2.md", "17a59d3b131231d2ea22e94424ecf4b5179b5ca78cf24adb31b254a05c5341c2"),
}


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
    completed = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=60)
    _require(completed.returncode == 0, f"git_object_unavailable:{args[-1]}")
    if binary:
        return completed.stdout
    return completed.stdout.decode("utf-8", errors="strict").strip()


def _binding(root: Path, item: Any, expected_path: str, reason: str, *, in_evidence_commit: bool = False) -> None:
    _require(isinstance(item, dict), f"{reason}_missing")
    _require(item.get("path") == expected_path, f"{reason}_path_drift")
    _hex(item.get("sha256"), HEX64, f"{reason}_hash_shape_invalid")
    path = root / expected_path
    _require(path.is_file(), f"{reason}_file_missing")
    _require(item["sha256"] == _sha256(path), f"{reason}_hash_drift")
    if in_evidence_commit:
        payload = _git(root, "show", f"{EVIDENCE_COMMIT}:{expected_path}", binary=True)
        _require(hashlib.sha256(payload).hexdigest() == item["sha256"], f"{reason}_immutable_hash_drift")


def _rows(value: Any) -> dict[str, dict[str, Any]]:
    _require(isinstance(value, list), "rows_invalid")
    result: dict[str, dict[str, Any]] = {}
    for row in value:
        _require(isinstance(row, dict) and isinstance(row.get("id"), str), "row_invalid")
        _require(row["id"] not in result, f"row_duplicate:{row['id']}")
        result[row["id"]] = row
    return result


def _verify_related_documents(root: Path, document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    bindings = document.get("evidence_bindings")
    _require(isinstance(bindings, dict), "evidence_bindings_missing")
    _binding(root, bindings.get("audit_document"), "docs/baselines/audits/2026-08-23-upstream-rust-parity-ledger-v2.md", "audit_document", in_evidence_commit=False)
    _binding(root, bindings.get("candidate_coverage_v2"), "docs/baselines/upstream-rust-candidate-coverage.v2.yaml", "candidate_coverage_v2", in_evidence_commit=True)
    _binding(root, bindings.get("migration_inventory"), "docs/baselines/upstream-migration-inventory.v1.yaml", "migration_inventory", in_evidence_commit=True)
    _binding(root, bindings.get("cli_integration"), "docs/baselines/upstream-cli-integration.v1.yaml", "cli_integration", in_evidence_commit=True)
    coverage = _load(root / bindings["candidate_coverage_v2"]["path"])
    _require(coverage.get("schema") == "sipi.upstream-rust-candidate-coverage.v2", "candidate_coverage_schema_invalid")
    _require(coverage.get("status") == "audited_open_no_upstream_parity", "candidate_coverage_promoted")
    coverage_rows = _rows(coverage.get("entries"))
    _require(set(coverage_rows) == set(EXPECTED_ROWS), "candidate_coverage_row_set_invalid")
    for item_id, row in coverage_rows.items():
        _require(row.get("candidate", {}).get("classification") == "partial_surface", f"candidate_class_invalid:{item_id}")
        _require(row.get("candidate", {}).get("completion") == "open", f"candidate_completion_promoted:{item_id}")
        _require(row.get("candidate", {}).get("parity") == "not_evaluated", f"candidate_parity_promoted:{item_id}")
    inventory = _load(root / bindings["migration_inventory"]["path"])
    _require(inventory.get("schema") == "sipi.upstream-migration-inventory.v1", "migration_inventory_schema_invalid")
    _require(inventory.get("summary", {}).get("migration_rows") == 15, "migration_inventory_row_count_invalid")
    inventory_rows = _rows(inventory.get("entries"))
    _require(set(inventory_rows) == set(EXPECTED_ROWS), "migration_inventory_row_set_invalid")
    for item_id, row in inventory_rows.items():
        _require(row.get("completion") == "open", f"migration_inventory_completion_promoted:{item_id}")
        _require(row.get("parity_status") in {"not_evaluated", "profile_only_not_workflow_parity"}, f"migration_inventory_parity_promoted:{item_id}")
    return coverage_rows


def _verify_evidence_object(root: Path, item_id: str, row: dict[str, Any]) -> None:
    evidence = row.get("evidence")
    _require(isinstance(evidence, dict), f"evidence_missing:{item_id}")
    manifest = evidence.get("manifest")
    expected_path = CURRENT_MANIFESTS[item_id]
    _binding(root, manifest, expected_path, f"manifest:{item_id}", in_evidence_commit=True)
    _require(manifest.get("bound_to_evidence_commit") is True, f"manifest_not_immutable_bound:{item_id}")
    manifest_doc = _load(root / expected_path)
    _require(manifest_doc.get("status") == EXPECTED_MANIFEST_STATUS[item_id], f"manifest_status_drift:{item_id}")
    _verify_manifest_source(item_id, manifest_doc)
    audit_path, audit_hash = EXPECTED_AUDIT[item_id]
    audit = evidence.get("audit")
    _require(isinstance(audit, dict), f"audit_missing:{item_id}")
    _require(audit.get("path") == audit_path and audit.get("sha256") == audit_hash, f"audit_binding_drift:{item_id}")
    _binding(root, audit, audit_path, f"audit:{item_id}", in_evidence_commit=True)
    _verify_replay_files(root, item_id, manifest_doc)


def _verify_manifest_source(item_id: str, manifest: dict[str, Any]) -> None:
    if item_id.startswith("AS-"):
        source = manifest.get("source")
        _require(isinstance(source, dict), f"source_missing:{item_id}")
        candidate = source.get("candidate")
        _require(isinstance(candidate, dict), f"candidate_source_missing:{item_id}")
        _require(candidate.get("commit") == PREPARATION_COMMIT and candidate.get("tree") == CANDIDATE_TREE, f"candidate_source_drift:{item_id}")
        _require(candidate.get("archive_sha256") == CANDIDATE_ARCHIVE, f"candidate_archive_drift:{item_id}")
        materialization = source.get("materialization")
        _require(isinstance(materialization, dict), f"materialization_missing:{item_id}")
        _require(materialization.get("overlay_current_worktree") is False, f"worktree_overlay_present:{item_id}")
        _require(materialization.get("candidate") == "git_archive_clean_temporary_root", f"candidate_materialization_drift:{item_id}")
    elif item_id.startswith("PB-"):
        source = manifest.get("source")
        _require(isinstance(source, dict), f"source_missing:{item_id}")
        _require(source.get("candidate_commit") == PREPARATION_COMMIT and source.get("candidate_tree") == CANDIDATE_TREE, f"candidate_source_drift:{item_id}")
        _require(source.get("candidate_archive_sha256") == CANDIDATE_ARCHIVE, f"candidate_archive_drift:{item_id}")
    else:
        candidate = manifest.get("candidate")
        _require(isinstance(candidate, dict), f"candidate_source_missing:{item_id}")
        _require(candidate.get("commit") == PREPARATION_COMMIT and candidate.get("tree") == CANDIDATE_TREE, f"candidate_source_drift:{item_id}")
        _require(candidate.get("archive_sha256") == CANDIDATE_ARCHIVE, f"candidate_archive_drift:{item_id}")
        _require("no working-tree overlay" in str(candidate.get("materialization", "")).lower(), f"worktree_overlay_present:{item_id}")
        upstream = manifest.get("upstream")
        _require(isinstance(upstream, dict) and upstream.get("runtime_executed") is False, f"upstream_runtime_not_metadata_only:{item_id}")
        _require(manifest.get("oracle", {}).get("numeric_upstream_parity_claim") is False, f"numeric_parity_claim:{item_id}")


def _verify_replay_files(root: Path, item_id: str, manifest: dict[str, Any]) -> None:
    if item_id.startswith("AS-"):
        evidence = manifest.get("reports"), manifest.get("aggregate")
    else:
        evidence_obj = manifest.get("evidence")
        _require(isinstance(evidence_obj, dict), f"manifest_evidence_missing:{item_id}")
        evidence = evidence_obj.get("reports"), evidence_obj.get("aggregate")
    reports, aggregate = evidence
    _require(isinstance(reports, list) and len(reports) == 2, f"replay_report_count_invalid:{item_id}")
    _require(isinstance(aggregate, dict), f"aggregate_missing:{item_id}")
    _verify_payload_file(root, aggregate, f"aggregate:{item_id}")
    identities: set[tuple[str, str, str]] = set()
    toolchains: list[Any] = []
    for report in reports:
        _require(isinstance(report, dict), f"report_invalid:{item_id}")
        payload = _verify_payload_file(root, report, f"report:{item_id}")
        _verify_report_provenance(item_id, payload)
        run_id = report.get("run_id")
        nonce = report.get("nonce", report.get("fresh_run_nonce"))
        _require(isinstance(run_id, str) and run_id, f"run_id_missing:{item_id}")
        _verify_nonce(nonce, item_id)
        identities.add((run_id, nonce, report["sha256"]))
        toolchain = payload.get("toolchain") if isinstance(payload, dict) else None
        if toolchain is None:
            toolchain = payload.get("execution_binding", {}).get("toolchain") if isinstance(payload, dict) else None
        _require(isinstance(toolchain, dict), f"toolchain_missing:{item_id}")
        serialized_toolchain = json.dumps(toolchain, sort_keys=True)
        _require(re.search(r"(?<![A-Za-z0-9])(?:(?:[A-Za-z]):[\\/]|/Users/|/home/)", serialized_toolchain) is None, f"toolchain_absolute_path_leak:{item_id}")
        redaction_flags = [value for key, value in _walk_key_values(toolchain) if key == "path_redacted"]
        _require(redaction_flags and all(value is True for value in redaction_flags), f"toolchain_path_not_redacted:{item_id}")
        toolchains.append(toolchain)
    _require(len(identities) == 2, f"fresh_run_identity_not_distinct:{item_id}")
    _require(toolchains[0] == toolchains[1], f"toolchain_drift:{item_id}")


def _verify_report_provenance(item_id: str, payload: Any) -> None:
    _require(isinstance(payload, dict), f"report_payload_invalid:{item_id}")
    candidate = payload.get("candidate")
    _require(isinstance(candidate, dict), f"report_candidate_missing:{item_id}")
    _require(candidate.get("commit") == PREPARATION_COMMIT and candidate.get("tree") == CANDIDATE_TREE, f"report_candidate_source_drift:{item_id}")
    _require(candidate.get("archive_sha256") == CANDIDATE_ARCHIVE, f"report_candidate_archive_drift:{item_id}")
    if item_id.startswith("AS-"):
        _require(payload.get("source_mode") == "candidate_and_upstream_git_archive_at_immutable_commit", f"report_source_mode_drift:{item_id}")
        _require(payload.get("numeric_parity") is False and payload.get("parity_claim") is False, f"report_numeric_parity_claim:{item_id}")
    elif item_id.startswith("PB-"):
        _require(payload.get("source_mode") == "git_archive_at_immutable_commit", f"report_source_mode_drift:{item_id}")
        claims = payload.get("claims")
        if isinstance(claims, dict):
            _require(claims.get("global_row_closed") is False, f"report_global_row_close_claim:{item_id}")
            expected_payload_parity = item_id == "PB-03"
            _require(claims.get("payload_parity") is expected_payload_parity, f"report_payload_parity_scope_drift:{item_id}")
    else:
        materialization = str(candidate.get("materialization", "")).lower()
        _require("no working-tree overlay" in materialization, f"report_worktree_overlay_present:{item_id}")
        upstream = payload.get("upstream")
        _require(isinstance(upstream, dict) and upstream.get("runtime_executed") is False, f"report_upstream_runtime_claim:{item_id}")
        parity = payload.get("parity")
        _require(isinstance(parity, dict) and parity.get("numeric_upstream_parity_claim") is False, f"report_numeric_parity_claim:{item_id}")


def _verify_nonce(nonce: object, item_id: str) -> None:
    _require(isinstance(nonce, str), f"nonce_invalid:{item_id}")
    if len(nonce) == 64:
        _hex(nonce, HEX64, f"nonce_invalid:{item_id}")
    else:
        _require(len(nonce) == 32 and re.fullmatch(r"[0-9a-f]{32}", nonce) is not None, f"nonce_invalid:{item_id}")


def _walk_key_values(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from _walk_key_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_key_values(item)


def _verify_payload_file(root: Path, item: dict[str, Any], reason: str) -> Any:
    _require(isinstance(item.get("path"), str) and isinstance(item.get("sha256"), str), f"{reason}_shape_invalid")
    _hex(item["sha256"], HEX64, f"{reason}_hash_shape_invalid")
    path = root / item["path"]
    _require(path.is_file(), f"{reason}_file_missing")
    _require(_sha256(path) == item["sha256"], f"{reason}_hash_drift")
    text = path.read_text(encoding="utf-8", errors="replace")
    _require(re.search(r"(?<![A-Za-z0-9])(?:(?:[A-Za-z]):[\\/]|/Users/|/home/)", text) is None, f"{reason}_absolute_path_leak")
    if path.suffix.lower() == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise LedgerError(f"{reason}_json_invalid") from error
    return None


def _verify_row_shape(root: Path, row: dict[str, Any], item_id: str, coverage_rows: dict[str, dict[str, Any]]) -> None:
    _require(row.get("repo") == EXPECTED_ROWS[item_id][0] and row.get("public_entrypoint") == EXPECTED_ROWS[item_id][1], f"row_identity_drift:{item_id}")
    _require(row.get("state") == EXPECTED_STATES[item_id], f"row_state_drift:{item_id}")
    _require(row.get("parity") == EXPECTED_PARITY[item_id], f"row_parity_drift:{item_id}")
    _require(row.get("completion") == "open", f"row_completion_promoted:{item_id}")
    _require(row.get("product_capability") == "not_claimed", f"row_product_capability_promoted:{item_id}")
    _require(row.get("candidate_coverage_entry") == item_id and item_id in coverage_rows, f"candidate_coverage_row_ref_invalid:{item_id}")
    _require(isinstance(row.get("non_claims"), list) and row["non_claims"], f"non_claims_missing:{item_id}")
    if item_id == "PB-03":
        scope = row.get("scope")
        _require(isinstance(scope, dict), "pb03_scope_missing")
        _require(scope.get("fixed_fixture_payload_parity") is True, "pb03_fixture_scope_missing")
        _require(scope.get("global_row_parity") is False and scope.get("branch_scope_open") is True, "pb03_global_scope_promoted")
    if item_id in {"COM-02", "COM-04"}:
        _require(row.get("upstream_runtime") == "metadata_only", f"com_metadata_only_missing:{item_id}")
        _require(row.get("numeric_upstream_parity") == "not_evaluated", f"com_numeric_parity_promoted:{item_id}")
    serialized = json.dumps(row, sort_keys=True)
    for term in FORBIDDEN_PROMOTION_VALUES:
        _require(term not in serialized, f"forbidden_promotion_term:{item_id}:{term}")
    if item_id in CURRENT_MANIFESTS:
        _verify_evidence_object(root, item_id, row)
        candidate_source = row["evidence"].get("candidate_source")
        _require(isinstance(candidate_source, dict), f"candidate_source_binding_missing:{item_id}")
        _require(candidate_source.get("commit") == PREPARATION_COMMIT and candidate_source.get("tree") == CANDIDATE_TREE, f"row_candidate_source_drift:{item_id}")
        _require(candidate_source.get("overlay_current_worktree") is False, f"row_worktree_overlay_present:{item_id}")
    else:
        _require("manifest" not in row.get("evidence", {}), f"unexpected_current_manifest:{item_id}")
        historical = row.get("evidence", {}).get("historical_manifest")
        _require(isinstance(historical, dict), f"historical_manifest_missing:{item_id}")
        _require(historical.get("path") == HISTORICAL_MANIFESTS[item_id], f"historical_manifest_path_drift:{item_id}")
        _hex(historical.get("sha256"), HEX64, f"historical_manifest_hash_shape_invalid:{item_id}")
        _require(historical.get("bound_to_evidence_commit") is False, f"historical_manifest_currently_bound:{item_id}")
        _binding(root, historical, HISTORICAL_MANIFESTS[item_id], f"historical_manifest:{item_id}", in_evidence_commit=False)


def validate(document: dict[str, Any] | None = None, root: Path = ROOT) -> dict[str, Any]:
    document = _load(LEDGER) if document is None else copy.deepcopy(document)
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == "current_bound_open_no_upstream_parity", "status_invalid")
    _require(document.get("policy") == POLICY, "policy_invalid")
    _require(document.get("as_of") == "2026-08-23", "date_invalid")
    evidence_commit = document.get("evidence_commit")
    _require(isinstance(evidence_commit, dict), "evidence_commit_missing")
    _require(evidence_commit.get("commit") == EVIDENCE_COMMIT and evidence_commit.get("parent_preparation_commit") == PREPARATION_COMMIT, "evidence_commit_identity_drift")
    _require(evidence_commit.get("tree") == EVIDENCE_TREE and evidence_commit.get("candidate_tree") == CANDIDATE_TREE, "evidence_tree_drift")
    _require(evidence_commit.get("clean_archive_only") is True, "clean_archive_policy_missing")
    _require(_git(root, "rev-parse", f"{EVIDENCE_COMMIT}^{{commit}}") == EVIDENCE_COMMIT, "evidence_commit_object_missing")
    _require(_git(root, "rev-parse", f"{EVIDENCE_COMMIT}^{{tree}}") == EVIDENCE_TREE, "evidence_commit_tree_drift")
    _require(_git(root, "rev-parse", f"{EVIDENCE_COMMIT}^") == PREPARATION_COMMIT, "evidence_commit_parent_drift")
    _require(document.get("candidate") == {"commit": PREPARATION_COMMIT, "tree": CANDIDATE_TREE, "archive_sha256": CANDIDATE_ARCHIVE}, "candidate_binding_drift")
    _require(document.get("source_authority") == EXPECTED_SOURCE_AUTHORITY, "source_authority_drift")
    predecessor = document.get("successor", {}).get("predecessor")
    _binding(root, predecessor, "docs/baselines/upstream-rust-parity-ledger.v1.yaml", "predecessor", in_evidence_commit=False)
    _require(predecessor.get("retained") is True, "predecessor_not_retained")
    coverage_rows = _verify_related_documents(root, document)
    rows = _rows(document.get("rows"))
    _require(set(rows) == set(EXPECTED_ROWS) and len(rows) == 15, "ledger_row_set_invalid")
    for item_id, row in rows.items():
        _verify_row_shape(root, row, item_id, coverage_rows)
    summary = document.get("summary")
    _require(isinstance(summary, dict), "summary_missing")
    _require(summary.get("rows") == 15 and summary.get("completion_open") == 15 and summary.get("parity_acceptance_count") == 0 and summary.get("product_capability_claim_count") == 0, "summary_drift")
    return {"valid": True, "rows": 15, "completion_open": 15, "current_bound_rows": len(CURRENT_MANIFESTS), "no_new_evidence_rows": len(HISTORICAL_MANIFESTS)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate()
    except (LedgerError, OSError, UnicodeError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"schema": SCHEMA, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
