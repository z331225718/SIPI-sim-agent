"""Verify the active upstream-first migration and deferred release ledgers."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/baselines/upstream-migration-inventory.v1.yaml"
RELEASE = ROOT / "docs/baselines/release-blockers-ledger.v1.yaml"
RECONCILIATION = ROOT / "docs/baselines/v0.2-v0.3-migration-reconciliation.v1.yaml"
HISTORICAL = ROOT / "docs/baselines/plan-remaining-items-ledger.v1.yaml"
PLAN = ROOT / "PLAN.md"
INTEGRATION_EVIDENCE = ROOT / "docs/baselines/upstream-cli-integration.v1.yaml"

SCHEMA = "sipi.upstream-migration-inventory.v1"
RELEASE_SCHEMA = "sipi.release-blockers-ledger.v1"
RECONCILIATION_SCHEMA = "sipi.v0.2-v0.3-migration-reconciliation.v1"

EXPECTED_REPOS = {
    "agent_spice": {
        "commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5",
        "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402",
        "cli_path": "src/agent_spice/cli.py",
        "cli_blob_oid_sha1": "321a32b860f969f0be74f883bedbbae3f67d6284",
        "cli_content_sha256": "908489c8c3a4826d49175c66b3d533413db4624b10fc3c797795b723b62262e1",
        "license_path": "LICENSE",
        "license_blob_oid_sha1": "55aac2e4f8c36a978d315efb02815972579b8293",
        "license_content_sha256": "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2",
        "declared_root_license": "MIT",
        "per_path_review_required": True,
    },
    "pybert": {
        "commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe",
        "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24",
        "cli_path": "src/pybert/cli.py",
        "cli_blob_oid_sha1": "4c1116007d31bcebf8db3252363eed7774c7b349",
        "cli_content_sha256": "3826b0c156166e6f04b0e9997ce64a53a53867db6d89143b7c582ca2cf4337c9",
        "license_path": "LICENSE",
        "license_blob_oid_sha1": "64d198ba43675ede5fbdef1ec918a63954951640",
        "license_content_sha256": "4ca68aea5b8f43e0d7337b182fbc277e02dae37d85b04196d92a80e9344926c1",
        "declared_root_license": "BSD-3-Clause",
        "per_path_review_required": True,
    },
    "agent_com": {
        "commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
        "tree": "7094ab6e84989b218730c52432c70da10261f8ea",
        "cli_path": "src/agent_com/cli.py",
        "cli_blob_oid_sha1": "7964d84bd52d60731bbf56ab9847bf4c190eacf9",
        "cli_content_sha256": "3ca1d26c097abaaa6197682a2c095dc2bc9d5810177429662a40463096fb51ca",
        "license_path": "LICENSE",
        "license_blob_oid_sha1": "55aac2e4f8c36a978d315efb02815972579b8293",
        "license_content_sha256": "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2",
        "declared_root_license": "MIT",
        "per_path_review_required": True,
    },
}

EXPECTED_ENTRYPOINTS = {
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

EXPECTED_HISTORICAL_IDS = {
    "P1-04B", "P3B-02", "P3C-03", "P4A-01", "P4A-03", "P4B-02",
    "P4B-08", "P4B-09", "P5-02", "P5-06", "P7-01", "P7-02",
    "P7-03", "P7-04", "P7-05", "P7-06", "P7-07", "P7-08", "P7-09",
}
EXPECTED_RELEASE_IDS = {f"P7-{number:02d}" for number in range(1, 10)}
ENTRY_KEYS = {
    "id", "repo", "public_entrypoint", "source_path", "target_crates",
    "adapter_status", "rust_replacement_status", "reachable_inventory",
    "license_review", "oracle_corpus", "parity_status", "completion",
}


class InventoryError(RuntimeError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise InventoryError(reason)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise InventoryError(f"document_invalid:{path.name}") from error
    _require(isinstance(value, dict), f"document_not_mapping:{path.name}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *arguments: str, binary: bool = False) -> str | bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        timeout=60,
    )
    _require(completed.returncode == 0, f"git_object_unavailable:{root.name}:{arguments[-1]}")
    if binary:
        return completed.stdout
    return completed.stdout.decode("utf-8", errors="strict").strip()


def _verify_source_root(repo_id: str, root: Path, expected: dict[str, Any]) -> None:
    _require(root.is_dir(), f"source_root_missing:{repo_id}")
    _require(_git(root, "rev-parse", "HEAD") == expected["commit"], f"source_commit_drift:{repo_id}")
    _require(_git(root, "rev-parse", "HEAD^{tree}") == expected["tree"], f"source_tree_drift:{repo_id}")
    for prefix in ("cli", "license"):
        path = expected[f"{prefix}_path"]
        _require(
            _git(root, "rev-parse", f"HEAD:{path}") == expected[f"{prefix}_blob_oid_sha1"],
            f"source_blob_drift:{repo_id}:{prefix}",
        )
        payload = _git(root, "show", f"HEAD:{path}", binary=True)
        _require(
            hashlib.sha256(payload).hexdigest() == expected[f"{prefix}_content_sha256"],
            f"source_content_drift:{repo_id}:{prefix}",
        )


def validate(
    inventory: dict[str, Any] | None = None,
    release: dict[str, Any] | None = None,
    reconciliation: dict[str, Any] | None = None,
    root: Path = ROOT,
    source_roots: dict[str, Path] | None = None,
) -> dict[str, Any]:
    inventory = _load(INVENTORY) if inventory is None else inventory
    release = _load(RELEASE) if release is None else release
    reconciliation = _load(RECONCILIATION) if reconciliation is None else reconciliation

    _require(inventory.get("schema") == SCHEMA, "inventory_schema_invalid")
    _require(inventory.get("status") == "active_upstream_integration_before_rust_consolidation", "inventory_status_invalid")
    _require(inventory.get("policy") == "sipi.upstream-capability-first-rust-consolidation.v1", "inventory_policy_invalid")
    _require(inventory.get("adr") == "docs/adr/ADR-015-upstream-capability-first-rust-consolidation.md", "inventory_adr_invalid")
    feature = inventory.get("feature_policy")
    _require(isinstance(feature, dict), "feature_policy_invalid")
    _require(feature.get("new_domain_features_allowed") is False, "new_feature_freeze_removed")
    _require(feature.get("silent_fallback") == "forbidden", "silent_fallback_allowed")
    _require(
        inventory.get("completion_states") == ["rust_parity_accepted", "retained_external_runtime", "excluded_by_owner"],
        "completion_states_invalid",
    )
    _require(inventory.get("source_repositories") == EXPECTED_REPOS, "source_repository_binding_invalid")
    integration = inventory.get("integration_evidence")
    _require(isinstance(integration, dict), "integration_evidence_invalid")
    _require(
        integration.get("path") == "docs/baselines/upstream-cli-integration.v1.yaml",
        "integration_evidence_path_invalid",
    )
    _require(
        integration.get("sha256") == _sha256(INTEGRATION_EVIDENCE),
        "integration_evidence_hash_drift",
    )

    entries = inventory.get("entries")
    _require(isinstance(entries, list), "entries_invalid")
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        _require(isinstance(entry, dict) and set(entry) == ENTRY_KEYS, "entry_shape_invalid")
        item_id = entry["id"]
        _require(item_id not in by_id, f"entry_duplicate:{item_id}")
        by_id[item_id] = entry
        _require(
            (entry["repo"], entry["public_entrypoint"]) == EXPECTED_ENTRYPOINTS.get(item_id),
            f"entrypoint_invalid:{item_id}",
        )
        expected_source = EXPECTED_REPOS[entry["repo"]]["cli_path"]
        if item_id == "COM-04":
            expected_source = "src/agent_com/__init__.py"
        _require(entry["source_path"] == expected_source, f"entry_source_path_invalid:{item_id}")
        _require(isinstance(entry["target_crates"], list) and entry["target_crates"], f"target_crates_empty:{item_id}")
        for crate in entry["target_crates"]:
            _require((root / "crates" / crate).is_dir(), f"target_crate_missing:{item_id}:{crate}")
        _require(entry["completion"] == "open", f"unsubstantiated_completion:{item_id}")
        _require(
            entry["adapter_status"] == "integrated_external_cli_route",
            f"adapter_route_not_integrated:{item_id}",
        )
        _require(
            entry["reachable_inventory"] == "pinned_reachable_inventory_bound",
            f"reachable_inventory_unbound:{item_id}",
        )
        _require(
            entry["license_review"] == "external_runtime_boundary_bound_direct_port_not_started",
            f"license_scope_invalid:{item_id}",
        )
        _require(entry["parity_status"] != "accepted", f"unsubstantiated_parity:{item_id}")
    _require(set(by_id) == set(EXPECTED_ENTRYPOINTS), "migration_entry_set_invalid")
    _require(
        inventory.get("summary") == {
            "migration_rows": 15,
            "external_adapter_routes_integrated": 15,
            "open": 15,
            "complete": 0,
            "new_feature_freeze": True,
        },
        "inventory_summary_invalid",
    )

    _require(release.get("schema") == RELEASE_SCHEMA, "release_schema_invalid")
    _require(release.get("status") == "deferred_until_consolidated_candidate_freeze", "release_status_invalid")
    _require(release.get("release_ready") is False and release.get("promotion_status") == "blocked", "release_promoted")
    release_items = release.get("items")
    _require(isinstance(release_items, list), "release_items_invalid")
    release_by_id = {item.get("id"): item for item in release_items if isinstance(item, dict)}
    _require(set(release_by_id) == EXPECTED_RELEASE_IDS and len(release_by_id) == len(release_items), "release_item_set_invalid")
    _require(all(item.get("status") == "blocked" for item in release_by_id.values()), "release_item_promoted")
    _require(release.get("summary") == {"items": 9, "blocked": 9}, "release_summary_invalid")

    _require(reconciliation.get("schema") == RECONCILIATION_SCHEMA, "reconciliation_schema_invalid")
    historical = reconciliation.get("historical_ledger")
    _require(isinstance(historical, dict), "historical_binding_invalid")
    _require(historical.get("path") == "docs/baselines/plan-remaining-items-ledger.v1.yaml", "historical_path_invalid")
    _require(historical.get("sha256") == _sha256(HISTORICAL), "historical_hash_drift")
    old = _load(HISTORICAL)
    old_ids = {item.get("id") for item in old.get("items", []) if isinstance(item, dict)}
    _require(old_ids == EXPECTED_HISTORICAL_IDS and historical.get("item_count") == 19, "historical_item_set_invalid")
    mappings = reconciliation.get("mappings")
    _require(isinstance(mappings, dict) and set(mappings) == EXPECTED_HISTORICAL_IDS, "reconciliation_mapping_set_invalid")
    for old_id, targets in mappings.items():
        _require(isinstance(targets, list) and targets, f"reconciliation_target_empty:{old_id}")
        allowed = EXPECTED_RELEASE_IDS if old_id.startswith("P7-") else set(EXPECTED_ENTRYPOINTS)
        _require(set(targets) <= allowed, f"reconciliation_target_invalid:{old_id}")

    plan = PLAN.read_text(encoding="utf-8")
    for token in (
        "实施计划 v0.3",
        "先整合原项目，再统一 Rust 重构",
        "新 public API",
        "upstream-migration-inventory.v1.yaml",
        "release-blockers-ledger.v1.yaml",
    ):
        _require(token in plan, f"plan_rebaseline_missing:{token}")

    checked = []
    if source_roots:
        for repo_id, source_root in source_roots.items():
            _require(repo_id in EXPECTED_REPOS, f"source_repo_unknown:{repo_id}")
            _verify_source_root(repo_id, source_root, EXPECTED_REPOS[repo_id])
            checked.append(repo_id)

    return {
        "valid": True,
        "migration_rows": len(by_id),
        "external_adapter_routes_integrated": len(by_id),
        "open": len(by_id),
        "release_blockers": len(release_by_id),
        "feature_freeze": True,
        "source_git_objects_checked": sorted(checked),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-spice-root", type=Path)
    parser.add_argument("--pybert-root", type=Path)
    parser.add_argument("--agent-com-root", type=Path)
    arguments = parser.parse_args()
    roots = {
        key: value
        for key, value in {
            "agent_spice": arguments.agent_spice_root,
            "pybert": arguments.pybert_root,
            "agent_com": arguments.agent_com_root,
        }.items()
        if value is not None
    }
    try:
        result = validate(source_roots=roots)
    except (InventoryError, OSError, UnicodeError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"schema": SCHEMA, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
