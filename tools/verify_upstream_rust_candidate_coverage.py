"""Verify the read-only upstream-to-Rust candidate coverage audit."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/baselines/upstream-rust-candidate-coverage.v1.yaml"
INVENTORY = ROOT / "docs/baselines/upstream-migration-inventory.v1.yaml"

SCHEMA = "sipi.upstream-rust-candidate-coverage.v1"
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
EXPECTED_CLASSES = {item_id: "partial_surface" for item_id in EXPECTED_ROWS}
EXPECTED_TRANSPORTS = {
    "AS-01": ("agent_spice_adapter", "upstream.agent-spice.fit-sparam"),
    "AS-02": ("agent_spice_adapter", "upstream.agent-spice.fit-sparam-cascade"),
    "AS-03": ("agent_spice_adapter", "upstream.agent-spice.fit-yparam"),
    "AS-04": ("agent_spice_adapter", "upstream.agent-spice.tune-yparam-tran"),
    "AS-05": ("agent_spice_adapter", "upstream.agent-spice.run-hspice"),
    "AS-06": ("agent_spice_adapter", "upstream.agent-spice.run-rfm"),
    "PB-01": ("pybert_adapter", "upstream.pybert.sim"),
    "PB-02": ("pybert_adapter", "upstream.pybert.sim-native"),
    "PB-03": ("pybert_adapter", "upstream.pybert.sim-rust"),
    "PB-04": ("pybert_adapter", "upstream.pybert.sim-auto"),
    "PB-05": ("pybert_adapter", "upstream.pybert.sim-compare"),
    "COM-01": ("agent_com_adapter", "upstream.agent-com.config-validate"),
    "COM-02": ("agent_com_adapter", "upstream.agent-com.run"),
    "COM-03": ("agent_com_adapter", "upstream.agent-com.compare"),
    "COM-04": ("agent_com_adapter", "upstream.agent-com.public-api"),
}
EXPECTED_INTEGRATION_SURFACES = {
    "agent_spice_adapter": "crates/sipi-agent-spice-adapter/src/lib.rs",
    "pybert_adapter": "crates/sipi-pybert-adapter/src/lib.rs",
    "agent_com_adapter": "crates/sipi-agent-com-adapter/src/lib.rs",
    "product_cli_dispatch": "crates/sipi-cli/src/upstream_migration.rs",
    "product_cli_registry": "crates/sipi-cli/src/main.rs",
}
FORBIDDEN_STALE_ROUTE_TERMS = (
    "cli_manifest_without_fit_route",
    "product_cli_not_pybert_route",
    "no_pybert_auto_selection_or_fallback_route",
    "no_fit_sparam_route",
    "no_config_validate_cli_route",
    "no_cli_com_compare_route",
)
EXPECTED_ACCOUNTED = {
    "agent_spice": ["research_cli_families", "external_or_research_artifacts"],
    "pybert": ["web_fastapi", "gui_traits", "redis_or_worker_storage", "engine_and_artifact_branches"],
    "agent_com": ["matlab_runtime", "workbook_and_schema", "golden_payloads", "runtime_and_reporting"],
}
UPSTREAM_ROOT_HINTS = {
    "agent_spice": Path(r"C:\Users\z3312\code\agent-spice"),
    "pybert": Path(r"C:\Users\z3312\code\Py-bert-agent"),
    "agent_com": Path(r"C:\Users\z3312\code\COM"),
}


class CoverageError(RuntimeError):
    """Raised when the coverage evidence is incomplete or has drifted."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise CoverageError(reason)


def _load(path: Path = EVIDENCE) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise CoverageError(f"document_invalid:{path.name}") from error
    _require(isinstance(document, dict), "document_not_mapping")
    return document


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


def _valid_sha(value: object, length: int = 64) -> bool:
    if not isinstance(value, str) or len(value) != length:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _verify_inventory_binding(root: Path, document: dict[str, Any]) -> None:
    binding = document.get("inventory")
    _require(isinstance(binding, dict), "inventory_binding_missing")
    _require(binding.get("path") == "docs/baselines/upstream-migration-inventory.v1.yaml", "inventory_path_drift")
    path = root / binding["path"]
    _require(path.is_file(), "inventory_missing")
    _require(binding.get("sha256") == _sha256(path), "inventory_hash_drift")
    _require(binding.get("row_count") == 15, "inventory_row_count_invalid")


def _verify_source_descriptor(repo_id: str, source: dict[str, Any], root: Path | None) -> dict[str, Any]:
    _require(isinstance(source, dict), f"source_descriptor_invalid:{repo_id}")
    for key in ("commit", "tree", "cli", "modules"):
        _require(key in source, f"source_descriptor_missing:{repo_id}:{key}")
    cli = source["cli"]
    _require(isinstance(cli, dict), f"source_cli_invalid:{repo_id}")
    _require(cli.get("path") == "src/agent_spice/cli.py" if repo_id == "agent_spice" else cli.get("path") == "src/pybert/cli.py" if repo_id == "pybert" else cli.get("path") == "src/agent_com/cli.py", f"source_cli_path_invalid:{repo_id}")
    _require(isinstance(source["modules"], list) and source["modules"], f"source_modules_empty:{repo_id}")
    module_map: dict[str, dict[str, Any]] = {}
    for item in source["modules"]:
        _require(isinstance(item, dict), f"source_module_invalid:{repo_id}")
        _require(set(item) == {"path", "blob_sha1", "sha256"}, f"source_module_shape_invalid:{repo_id}")
        path = item["path"]
        _require(isinstance(path, str) and path.startswith("src/"), f"source_module_path_invalid:{repo_id}")
        _require(path not in module_map, f"source_module_duplicate:{repo_id}:{path}")
        _require(_valid_sha(item["blob_sha1"], 40), f"source_blob_sha_invalid:{repo_id}:{path}")
        _require(_valid_sha(item["sha256"]), f"source_sha_invalid:{repo_id}:{path}")
        module_map[path] = item
    if root is not None and root.is_dir():
        _require(_git(root, "rev-parse", "HEAD") == source["commit"], f"source_commit_drift:{repo_id}")
        _require(_git(root, "rev-parse", "HEAD^{tree}") == source["tree"], f"source_tree_drift:{repo_id}")
        _verify_git_file(root, source["commit"], cli, f"{repo_id}:cli")
        for item in [cli, *source["modules"]]:
            _verify_git_file(root, source["commit"], item, f"{repo_id}:{item['path']}")
    return module_map


def _verify_git_file(root: Path, commit: str, item: dict[str, Any], label: str) -> None:
    path = item["path"]
    _require(_git(root, "rev-parse", f"{commit}:{path}") == item["blob_sha1"], f"source_blob_drift:{label}")
    payload = _git(root, "show", f"{commit}:{path}", binary=True)
    _require(hashlib.sha256(payload).hexdigest() == item["sha256"], f"source_content_drift:{label}")


def _verify_candidate_path(root: Path, item: dict[str, Any], label: str) -> None:
    _require(isinstance(item, dict), f"candidate_surface_invalid:{label}")
    _require(set(item) >= {"path", "sha256"}, f"candidate_surface_shape_invalid:{label}")
    path_text = item["path"]
    _require(isinstance(path_text, str) and path_text.startswith("crates/"), f"candidate_path_invalid:{label}")
    path = (root / path_text).resolve()
    _require(path.is_file() and path.is_relative_to(root.resolve()), f"candidate_path_missing:{label}")
    _require(_sha256(path) == item["sha256"], f"candidate_hash_drift:{label}")


def _verify_integration_surfaces(root: Path, document: dict[str, Any]) -> None:
    surfaces = document.get("integration_surfaces")
    _require(isinstance(surfaces, dict), "integration_surfaces_missing")
    _require(set(surfaces) == set(EXPECTED_INTEGRATION_SURFACES), "integration_surface_set_drift")
    for name, expected_path in EXPECTED_INTEGRATION_SURFACES.items():
        surface = surfaces[name]
        _require(isinstance(surface, dict), f"integration_surface_invalid:{name}")
        _require(surface.get("path") == expected_path, f"integration_surface_path_drift:{name}")
        _verify_candidate_path(root, surface, f"integration:{name}")


def _verify_product_cli_routes(root: Path) -> None:
    registry = (root / EXPECTED_INTEGRATION_SURFACES["product_cli_registry"]).read_text(encoding="utf-8")
    dispatch = (root / EXPECTED_INTEGRATION_SURFACES["product_cli_dispatch"]).read_text(encoding="utf-8")
    for item_id, (_, command) in EXPECTED_TRANSPORTS.items():
        _require(f'id: "{command}"' in registry, f"product_cli_route_missing:{item_id}")
        adapter_route = command.removeprefix("upstream.")
        _require(f'"{adapter_route}"' in dispatch, f"product_cli_dispatch_missing:{item_id}")


def _verify_rows(root: Path, document: dict[str, Any], module_maps: dict[str, dict[str, dict[str, Any]]]) -> dict[str, int]:
    entries = document.get("entries")
    _require(isinstance(entries, list), "entries_invalid")
    serialized_entries = json.dumps(entries, sort_keys=True)
    for term in FORBIDDEN_STALE_ROUTE_TERMS:
        _require(term not in serialized_entries, f"stale_route_claim:{term}")
    _require(len(entries) == len(EXPECTED_ROWS), "row_count_invalid")
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        _require(isinstance(entry, dict), "entry_invalid")
        item_id = entry.get("id")
        _require(item_id in EXPECTED_ROWS and item_id not in by_id, f"row_set_invalid:{item_id}")
        by_id[item_id] = entry
        expected_repo, expected_entrypoint = EXPECTED_ROWS[item_id]
        upstream = entry.get("upstream")
        _require(isinstance(upstream, dict), f"upstream_missing:{item_id}")
        _require(upstream.get("repo") == expected_repo, f"upstream_repo_drift:{item_id}")
        _require(upstream.get("entrypoint") == expected_entrypoint, f"upstream_entrypoint_drift:{item_id}")
        _require(upstream.get("source_path") == ("src/agent_com/__init__.py" if item_id == "COM-04" else f"src/{'agent_spice' if expected_repo == 'agent_spice' else 'pybert' if expected_repo == 'pybert' else 'agent_com'}/cli.py"), f"upstream_path_drift:{item_id}")
        reachable = upstream.get("reachable_modules")
        _require(isinstance(reachable, list) and reachable, f"reachable_inventory_missing:{item_id}")
        module_map = module_maps[expected_repo]
        for path in reachable:
            _require(path in module_map, f"reachable_module_unbound:{item_id}:{path}")
        _require(isinstance(entry.get("minimum_branch_completion"), list) and entry["minimum_branch_completion"], f"minimum_branch_missing:{item_id}")
        transport = entry.get("external_transport")
        _require(isinstance(transport, dict), f"external_transport_missing:{item_id}")
        expected_adapter, expected_command = EXPECTED_TRANSPORTS[item_id]
        _require(
            transport
            == {
                "status": "integrated_process_external",
                "adapter": expected_adapter,
                "product_cli_command": expected_command,
                "runtime_source_attestation": "not_performed",
                "product_capability": "not_claimed",
                "parity": "not_evaluated",
            },
            f"external_transport_drift:{item_id}",
        )
        candidate = entry.get("candidate")
        _require(isinstance(candidate, dict), f"candidate_missing:{item_id}")
        expected_class = EXPECTED_CLASSES[item_id]
        _require(candidate.get("classification") == expected_class, f"candidate_class_drift:{item_id}")
        _require(candidate.get("completion") == "open", f"candidate_promoted:{item_id}")
        _require(candidate.get("parity") == "not_evaluated", f"parity_promoted:{item_id}")
        _require(candidate.get("self_test_only") is True, f"self_test_flag_invalid:{item_id}")
        _require(candidate.get("profile_only") is not None, f"profile_flag_missing:{item_id}")
        surfaces = candidate.get("surfaces")
        _require(isinstance(surfaces, list), f"candidate_surfaces_invalid:{item_id}")
        for index, surface in enumerate(surfaces):
            _verify_candidate_path(root, surface, f"{item_id}:{index}")
        for index, related in enumerate(candidate.get("related_not_candidate", [])):
            _verify_candidate_path(root, related, f"{item_id}:related:{index}")
        coverage = entry.get("coverage")
        _require(isinstance(coverage, list), f"coverage_invalid:{item_id}")
        _require("process_external_adapter_and_product_cli_route" in coverage, f"external_transport_coverage_missing:{item_id}")
        _require(isinstance(entry.get("gaps"), list) and entry["gaps"], f"gaps_missing:{item_id}")
    _require(set(by_id) == set(EXPECTED_ROWS), "row_omission_or_extra")
    counts = {name: sum(item["candidate"]["classification"] == name for item in by_id.values()) for name in ("direct_surface", "partial_surface", "similar_name_only", "absent")}
    _require(counts == {"direct_surface": 0, "partial_surface": 15, "similar_name_only": 0, "absent": 0}, "candidate_counts_drift")
    return counts


def _verify_accounting(document: dict[str, Any]) -> None:
    accounted = document.get("accounted_surfaces")
    _require(isinstance(accounted, dict), "accounted_surfaces_missing")
    _require(set(accounted) == set(EXPECTED_ACCOUNTED), "accounted_repo_omission")
    for repo, keys in EXPECTED_ACCOUNTED.items():
        value = accounted[repo]
        _require(isinstance(value, list), f"accounted_surface_invalid:{repo}")
        names = [item.get("name") if isinstance(item, dict) else None for item in value]
        _require(names == keys, f"accounted_surface_set_drift:{repo}")
        for item in value:
            _require(isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("items"), list) and item["items"], f"accounted_surface_shape_invalid:{repo}")
    non_numeric = document.get("non_numeric_completion_accounting")
    _require(isinstance(non_numeric, dict) and set(non_numeric) == set(EXPECTED_ACCOUNTED), "non_numeric_accounting_missing")
    for repo, keys in EXPECTED_ACCOUNTED.items():
        _require(non_numeric[repo] == keys, f"non_numeric_accounting_mismatch:{repo}")


def _verify_audit_binding(root: Path, document: dict[str, Any]) -> None:
    audit = document.get("audit_document")
    _require(isinstance(audit, dict), "audit_binding_missing")
    _require(audit.get("path") == "docs/baselines/audits/2026-08-22-upstream-rust-candidate-coverage.md", "audit_path_drift")
    path = root / audit["path"]
    _require(path.is_file(), "audit_document_missing")
    _require(audit.get("sha256") == _sha256(path), "audit_hash_drift")


def validate(document: dict[str, Any] | None = None, root: Path = ROOT, source_roots: dict[str, Path] | None = None) -> dict[str, Any]:
    document = _load() if document is None else copy.deepcopy(document)
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == "audited_open_no_upstream_parity", "status_invalid")
    _require(document.get("policy") == "sipi.upstream-capability-first-rust-consolidation.v1", "policy_invalid")
    _require(document.get("as_of") == "2026-08-22", "date_invalid")
    _verify_inventory_binding(root, document)
    _verify_audit_binding(root, document)
    _require(document.get("rules", {}).get("external_transport_is_not_rust_parity") is True, "external_transport_rule_removed")
    _require(document.get("rules", {}).get("product_cli_route_is_not_product_capability") is True, "product_capability_rule_removed")
    _require(document.get("rules", {}).get("caller_selected_runtime_is_not_source_attestation") is True, "runtime_attestation_rule_removed")
    _require(document.get("rules", {}).get("self_test_is_not_parity") is True, "self_test_rule_removed")
    _require(document.get("rules", {}).get("profile_only_is_not_parity") is True, "profile_rule_removed")
    _require(document.get("rules", {}).get("similar_name_is_not_surface") is True, "similar_name_rule_removed")
    sources = document.get("source_objects")
    _require(isinstance(sources, dict) and set(sources) == set(EXPECTED_ACCOUNTED), "source_set_invalid")
    checked: list[str] = []
    maps: dict[str, dict[str, dict[str, Any]]] = {}
    roots = UPSTREAM_ROOT_HINTS if source_roots is None else source_roots
    for repo_id, source in sources.items():
        source_root = roots.get(repo_id)
        maps[repo_id] = _verify_source_descriptor(repo_id, source, source_root if source_root is not None and source_root.is_dir() else None)
        if source_root is not None and source_root.is_dir():
            checked.append(repo_id)
    _verify_integration_surfaces(root, document)
    _verify_product_cli_routes(root)
    counts = _verify_rows(root, document, maps)
    _verify_accounting(document)
    audit = document.get("audit", {})
    _require(audit.get("all_rows_completion") == "open", "audit_promoted")
    _require(audit.get("no_parity_acceptance") is True, "audit_parity_promoted")
    _require(audit.get("candidate_counts") == counts, "audit_candidate_counts_drift")
    return {"valid": True, "rows": len(EXPECTED_ROWS), "candidate_counts": counts, "source_git_objects_checked": sorted(checked)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-spice-root", type=Path)
    parser.add_argument("--pybert-root", type=Path)
    parser.add_argument("--agent-com-root", type=Path)
    args = parser.parse_args()
    roots = {key: value for key, value in {"agent_spice": args.agent_spice_root, "pybert": args.pybert_root, "agent_com": args.agent_com_root}.items() if value is not None}
    try:
        result = validate(source_roots=roots or None)
    except (CoverageError, OSError, UnicodeError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"schema": SCHEMA, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
