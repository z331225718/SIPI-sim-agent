"""Verify the additive P1-04B oracle-only fixture boundary closure.

This gate closes only the mechanical boundary owned by P1-04B.  It keeps
the owner comparison permission narrow and carries exact profile, custody,
rights, and distribution blockers into the domain-owned P3B/P4A/P4B/P5
records.  It never turns a manifest label into an admission decision.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/baselines/p1-04b-oracle-only-scope-closure.v1.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p1-04b-oracle-only-scope-closure.md"
MANIFEST = ROOT / "fixtures/manifest.v1.json"
FACTS = ROOT / "docs/baselines/p1-legacy-fixture-required-profile-facts.v1.yaml"
RECONCILIATION = ROOT / "docs/baselines/p1-04b-comparison-permission-reconciliation.v1.yaml"
SCHEMA = "sipi.p1-04b.oracle-only-scope-closure.v1"

ASSET_IDS = (
    "agent-spice-python-fixtures",
    "agent-spice-native-fixtures",
    "agent-spice-sparam-benchmarks",
    "agent-spice-third-party-solver-material",
    "agent-spice-generated-images",
    "pybert-models",
    "pybert-golden-fixtures",
    "pybert-user-images",
    "agent-com-matlab-source-and-workbooks",
    "agent-com-synthetic-sparameter-fixtures",
    "agent-com-benchmarks-and-images",
    "agent-com-local-partial-matlab-oracle",
    "agent-com-authoritative-matlab-golden",
    "ads-solver-unresolved",
)
REQUIRED_ASSET_IDS = (
    "agent-spice-python-fixtures",
    "agent-spice-native-fixtures",
    "pybert-models",
    "pybert-golden-fixtures",
    "agent-com-matlab-source-and-workbooks",
    "agent-com-synthetic-sparameter-fixtures",
    "agent-com-local-partial-matlab-oracle",
    "agent-com-authoritative-matlab-golden",
    "ads-solver-unresolved",
)

EXPECTED_RESPONSIBILITIES = {
    "agent-spice-python-fixtures": {"domain": "P2-circuit", "gate": "G4 circuit", "requirement": "required", "owner": "agent-spice-maintainer"},
    "agent-spice-native-fixtures": {"domain": "P2-circuit", "gate": "G4 circuit", "requirement": "required", "owner": "agent-spice-maintainer"},
    "agent-spice-sparam-benchmarks": {"domain": "P3A-channel", "gate": "G4 s-parameter", "requirement": "optional", "owner": "agent-spice-maintainer"},
    "agent-spice-third-party-solver-material": {"domain": "P2-circuit", "gate": "G4 external solver", "requirement": "optional", "owner": "third-party-compliance-owner"},
    "agent-spice-generated-images": {"domain": "migration-documentation", "gate": "documentation", "requirement": "optional", "owner": "agent-spice-maintainer"},
    "pybert-models": {"domain": "P4B-AMI", "gate": "G4 ibis-ami", "requirement": "required", "owner": "pybert-maintainer"},
    "pybert-golden-fixtures": {"domain": "P3B-link", "gate": "G4 link", "requirement": "required", "owner": "pybert-maintainer"},
    "pybert-user-images": {"domain": "migration-documentation", "gate": "documentation", "requirement": "optional", "owner": "pybert-maintainer"},
    "agent-com-matlab-source-and-workbooks": {"domain": "P5-COM", "gate": "G4 COM", "requirement": "required", "owner": "agent-com-maintainer"},
    "agent-com-synthetic-sparameter-fixtures": {"domain": "P5-COM", "gate": "G4 COM", "requirement": "required", "owner": "agent-com-maintainer"},
    "agent-com-benchmarks-and-images": {"domain": "P5-COM", "gate": "benchmark publication", "requirement": "optional", "owner": "agent-com-maintainer"},
    "agent-com-local-partial-matlab-oracle": {"domain": "P5-COM", "gate": "G4 COM golden", "requirement": "required", "owner": "agent-com-maintainer"},
    "agent-com-authoritative-matlab-golden": {"domain": "P5-COM", "gate": "G4 COM golden", "requirement": "required", "owner": "agent-com-maintainer"},
    "ads-solver-unresolved": {"domain": "P4B-AMI", "gate": "G4 ADS", "requirement": "required", "owner": "external-solver-owner"},
}

EXPECTED_BLOCKERS = [
    {
        "domain": "P3B",
        "work_items": ["P3B-02"],
        "assets": ["pybert-golden-fixtures"],
        "gate_refs": [
            "tools/verify_p3b_02_pybert_semantics.py",
            "docs/baselines/p3b-02-pybert-source-semantic-observation.v1.yaml",
        ],
        "required_profile": "external_asset_oracle",
        "profile": {"selected": None, "status": "unselected_conflicting_source_defaults"},
        "custody": "external_only_hash_bound_observation",
        "rights": "not_established",
        "distribution": "blocked_unknown",
        "oracle": "not_admitted",
    },
    {
        "domain": "P4A",
        "work_items": ["P4A-01", "P4A-03"],
        "assets": [],
        "gate_refs": [
            "tools/verify_p4a_03_selected_model_grammar_consumer.py",
            "docs/baselines/p4a-03-selected-model-grammar-consumer.v1.yaml",
            "docs/baselines/p4a-01-official-object-rights-recheck.v1.yaml",
        ],
        "required_profile": "external_asset_oracle",
        "profile": {"selected": None, "status": "missing_required_selected_profile"},
        "custody": "external_operator_only_observation",
        "rights": "blocked_external_rights",
        "distribution": "blocked_unknown",
        "oracle": "not_admitted",
    },
    {
        "domain": "P4B",
        "work_items": ["P4B-02", "P4B-08", "P4B-09"],
        "assets": ["pybert-models", "ads-solver-unresolved"],
        "gate_refs": [
            "tools/verify_p4b_02_parameter_subset_observation.py",
            "docs/baselines/p4b-02-ads-pcie-gen5-parameter-subset-observation.v1.json",
            "tools/verify_p4b_dual_ami_lane3_admission.py",
            "docs/baselines/p4b-ads-pcie-gen5-dual-ami-lane3-admission.v1.yaml",
        ],
        "required_profile": "external_asset_oracle",
        "profile": {"selected": "ads-pcie-gen5-dual-ami-windows-x64-v1", "status": "observed_external_binding_not_admitted"},
        "custody": "external_observation_only",
        "rights": "not_established",
        "distribution": "blocked_unknown",
        "oracle": "runtime_not_admitted",
    },
    {
        "domain": "P5",
        "work_items": ["P5-02", "P5-06"],
        "assets": [
            "agent-com-matlab-source-and-workbooks",
            "agent-com-synthetic-sparameter-fixtures",
            "agent-com-local-partial-matlab-oracle",
            "agent-com-authoritative-matlab-golden",
        ],
        "gate_refs": [
            "tools/verify_p5_06r_agent_com_metric_authority_observation.py",
            "docs/baselines/p5-06r-agent-com-metric-authority-observation.v1.yaml",
        ],
        "required_profile": "external_asset_oracle",
        "profile": {"selected": "r480", "status": "observed_external_profile_not_authoritative"},
        "custody": "external_source_and_run_observation_only",
        "rights": "not_established",
        "distribution": "blocked_unknown",
        "oracle": "compare_not_admitted",
    },
]
PRODUCT_PREFIXES = ("crates", "fixtures", "schemas", "apps", "packages", "tests")


class ScopeClosureError(RuntimeError):
    """Raised when the P1-04B scoped closure drifts or overclaims."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ScopeClosureError(reason)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ScopeClosureError(f"document_load_failed:{path}") from error
    _require(isinstance(value, dict), f"document_not_mapping:{path}")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ScopeClosureError(f"read_failed:{path}") from error


def _import_gate(name: str):
    try:
        return importlib.import_module(f"tools.{name}")
    except ImportError:
        return importlib.import_module(name)


def _validate_manifest(document: dict[str, Any], root: Path) -> dict[str, Any]:
    _require(document.get("schema") == "sipi.fixture-manifest.v1", "manifest_schema_invalid")
    _require(_sha256(root / MANIFEST.relative_to(ROOT)) == "9601a1755c628bd85da0b4205858fa232687ecd39d1a398f3d26cd6a8a612e79", "manifest_hash_invalid")
    _require((root / MANIFEST.relative_to(ROOT)).stat().st_size == 12904, "manifest_bytes_invalid")
    assets = document.get("assets")
    _require(isinstance(assets, list) and len(assets) == len(ASSET_IDS), "manifest_asset_count_invalid")
    by_id = {}
    for asset in assets:
        _require(isinstance(asset, dict), "manifest_asset_not_mapping")
        asset_id = asset.get("id")
        _require(asset_id in ASSET_IDS and asset_id not in by_id, f"manifest_asset_id_invalid:{asset_id}")
        by_id[asset_id] = asset
        _require(asset.get("source_ref") in {"agent-spice", "pybert", "agent-com", "external"}, f"manifest_source_invalid:{asset_id}")
        location = asset.get("location")
        _require(isinstance(location, dict) and isinstance(location.get("relative_path"), str) and location["relative_path"], f"manifest_location_invalid:{asset_id}")
        distribution = asset.get("distribution")
        _require(isinstance(distribution, dict) and distribution.get("status") == "blocked_unknown", f"manifest_distribution_promoted:{asset_id}")
        _require(isinstance(distribution.get("owner"), str) and distribution["owner"], f"manifest_owner_missing:{asset_id}")
        required_by = asset.get("required_by")
        _require(isinstance(required_by, list) and len(required_by) == 1, f"manifest_required_by_invalid:{asset_id}")
        row = required_by[0]
        _require(isinstance(row, dict) and isinstance(row.get("gate"), str) and row.get("requirement") in {"required", "optional"}, f"manifest_required_by_invalid:{asset_id}")
    _require(tuple(by_id) == ASSET_IDS, "manifest_asset_order_invalid")
    required = tuple(asset_id for asset_id in ASSET_IDS if by_id[asset_id]["required_by"][0]["requirement"] == "required")
    _require(required == REQUIRED_ASSET_IDS, "manifest_required_by_set_invalid")
    return by_id


def _worktree_materialized_asset_paths(root: Path) -> list[str]:
    """Check product-owned worktree paths, including untracked files."""
    materialized: list[str] = []
    for prefix in PRODUCT_PREFIXES:
        base = root / prefix
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            parts = path.relative_to(root).parts
            if any(part in {".git", "target", "__pycache__"} for part in parts):
                continue
            if any(asset_id in parts for asset_id in ASSET_IDS):
                materialized.append(path.relative_to(root).as_posix())
    return sorted(materialized)


def _validate_domain_records(root: Path) -> None:
    p3b = _import_gate("verify_p3b_02_pybert_semantics")
    p3b_doc = p3b._load(root / "docs/baselines/p3b-02-pybert-source-semantic-observation.v1.yaml")
    _require(p3b.validate_document(p3b_doc)["profile_required"] == "external_asset_oracle", "p3b_profile_promoted")

    p4a_doc = _load_yaml(root / "docs/baselines/p4a-03-selected-model-grammar-consumer.v1.yaml")
    _require(p4a_doc.get("status") == "bounded_explicit_grammar_consumer_closed_external_profile_missing", "p4a_profile_promoted")
    official = p4a_doc.get("external_official_observation", {})
    _require(official.get("selected_profile_status") == "missing_required_selected_profile" and official.get("promotion_eligible") is False, "p4a_external_profile_promoted")
    disposition = p4a_doc.get("disposition", {})
    _require(disposition.get("p4a_03_external_profile_oracle") == "blocked_external_asset_oracle", "p4a_oracle_promoted")
    _require(disposition.get("p4a_01_rights") == "blocked_external_rights", "p4a_rights_promoted")
    p4a_rights = _load_yaml(root / "docs/baselines/p4a-01-official-object-rights-recheck.v1.yaml")
    _require(p4a_rights.get("status") == "exact_identity_revalidated_external_only_rights_unverified", "p4a_rights_status_promoted")
    rights_disposition = p4a_rights.get("rights_disposition", {})
    _require(
        rights_disposition.get("rights_status") == "unverified"
        and rights_disposition.get("product_source_use_authorized") is False
        and rights_disposition.get("redistribution_authorized") is False,
        "p4a_rights_authorized",
    )

    p4b = _import_gate("verify_p4b_02_parameter_subset_observation")
    p4b.validate(root / "docs/baselines/p4b-02-ads-pcie-gen5-parameter-subset-observation.v1.json")
    p4b_admission = _load_yaml(root / "docs/baselines/p4b-ads-pcie-gen5-dual-ami-lane3-admission.v1.yaml")
    _require(p4b_admission.get("status") == "blocked_before_vendor_load_missing_runtime_rights_and_runtime_observation", "p4b_runtime_promoted")
    _require(p4b_admission.get("selected_profile", {}).get("id") == "ads-pcie-gen5-dual-ami-windows-x64-v1", "p4b_profile_identity_drift")
    rights_snapshot = p4b_admission.get("asset_identity_and_rights_snapshot", {})
    _require(rights_snapshot.get("status") == "identity_ready_rights_blocked", "p4b_rights_promoted")
    _require(rights_snapshot.get("runtime_rights", {}).get("redistribution_authorized") is False, "p4b_redistribution_authorized")

    p5 = _import_gate("verify_p5_06r_agent_com_metric_authority_observation")
    p5.validate_document(_load_yaml(root / "docs/baselines/p5-06r-agent-com-metric-authority-observation.v1.yaml"))


def validate(document: dict[str, Any] | None = None, root: Path = ROOT) -> dict[str, Any]:
    document = _load_yaml(root / EVIDENCE.relative_to(ROOT)) if document is None else document
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == "scoped_boundary_closed_external_facts_pending", "status_invalid")
    _require(
        document.get("closure") == {
            "item": "P1-04B",
            "closure_kind": "additive_child_scope_closure",
            "boundary": "legacy_fixture_oracle_only",
            "oracle_only_boundary_closed": True,
            "p1_04b_main_item_closed": False,
            "product_materialization": False,
            "legacy_schema_in_product_rust": False,
            "product_input_admitted": False,
            "runtime_admitted": False,
            "release_admitted": False,
            "redistribution_authorized": False,
            "rights_conclusion": False,
            "unresolved_external_facts_retained": True,
            "retained_external_facts": [
                "exact_selected_profile",
                "external_custody_identity",
                "consumption_and_distribution_rights",
            ],
        },
        "closure_scope_or_promotion_invalid",
    )
    _require(
        document.get("comparison_permission") == {
            "source": "docs/baselines/owner-input-request.v1.yaml",
            "decision": "external fixtures are globally trusted; do not block comparison",
            "comparison_permission_decided": True,
            "permitted_scope": "external_comparison_only",
            "profile_selection": False,
            "redistribution": False,
            "product_input_admission": False,
            "runtime_admission": False,
            "release_admission": False,
            "license_or_rights_conclusion": False,
        },
        "comparison_permission_scope_invalid",
    )

    manifest_spec = document.get("manifest")
    _require(isinstance(manifest_spec, dict), "manifest_binding_missing")
    _require(
        manifest_spec == {
            "path": "fixtures/manifest.v1.json",
            "sha256": "9601a1755c628bd85da0b4205858fa232687ecd39d1a398f3d26cd6a8a612e79",
            "bytes": 12904,
            "asset_count": 14,
            "required_by_required_count": 9,
            "required_by_optional_count": 5,
            "required_asset_ids": list(REQUIRED_ASSET_IDS),
            "all_distribution_status": "blocked_unknown",
        },
        "manifest_binding_spec_invalid",
    )
    try:
        live_manifest = json.loads((root / MANIFEST.relative_to(ROOT)).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ScopeClosureError("manifest_load_failed") from error
    assets = _validate_manifest(live_manifest, root)

    responsibilities = document.get("asset_responsibilities")
    _require(isinstance(responsibilities, list) and len(responsibilities) == len(ASSET_IDS), "asset_responsibility_count_invalid")
    seen = set()
    for entry in responsibilities:
        _require(isinstance(entry, dict) and set(entry) == {"id", "domain", "gate", "requirement", "owner"}, "asset_responsibility_shape_invalid")
        asset_id = entry["id"]
        _require(asset_id not in seen and asset_id in assets, f"asset_responsibility_id_invalid:{asset_id}")
        seen.add(asset_id)
        _require(entry == {"id": asset_id, **EXPECTED_RESPONSIBILITIES[asset_id]}, f"asset_responsibility_drift:{asset_id}")
        manifest_row = assets[asset_id]
        _require(manifest_row["required_by"][0]["gate"] == entry["gate"], f"asset_gate_mismatch:{asset_id}")
        _require(manifest_row["required_by"][0]["requirement"] == entry["requirement"], f"asset_requirement_mismatch:{asset_id}")
        _require(manifest_row["distribution"]["owner"] == entry["owner"], f"asset_owner_mismatch:{asset_id}")
    _require(seen == set(ASSET_IDS), "asset_responsibility_set_invalid")

    _require(document.get("external_blockers") == EXPECTED_BLOCKERS, "external_blocker_matrix_invalid")
    for blocker in EXPECTED_BLOCKERS:
        for relative in blocker["gate_refs"]:
            _require((root / relative).is_file(), f"domain_gate_missing:{relative}")

    rights = document.get("rights_retention")
    _require(
        rights == {
            "unresolved_asset_ids": list(ASSET_IDS),
            "distribution_authorized": False,
            "custody_transferred": False,
            "rights_lost": False,
            "owner_facts_preserved": True,
        },
        "rights_retention_invalid",
    )

    bindings = document.get("bindings")
    _require(isinstance(bindings, dict), "bindings_missing")
    for key, relative, digest in (
        ("legacy_boundary_verifier", "tools/verify_p1_04b_legacy_fixture_boundary.py", "1d8886af9a94caae2ff5c5b8db3637a9d4f82c9fba678515ede34a8298b48e3d"),
        ("legacy_boundary_audit", "docs/baselines/audits/2026-08-16-p1-04b-legacy-fixture-boundary.md", "ab6c3b8408fbbce0f3b3b931b83b0aaf2e91d87f813c36f01c4418cdc3476ed4"),
        ("required_profile_facts_verifier", "tools/verify_p1_legacy_fixture_required_profile_facts.py", "5b2229664ce376fdca6b37d5664879c34592f9873b22916a21c211263827f922"),
        ("comparison_permission_verifier", "tools/verify_p1_04b_comparison_permission_reconciliation.py", "cc6bdcf7b610cac8c0bddf2cb551a4be3406af393350d021d3523d359c5789c7"),
    ):
        _require(bindings.get(key) == {"path": relative, "sha256": digest}, f"p1_binding_invalid:{key}")
        _require(_sha256(root / relative) == digest, f"p1_binding_hash_invalid:{key}")
    facts_binding = bindings.get("required_profile_facts")
    recon_binding = bindings.get("comparison_permission_reconciliation")
    _require(facts_binding == {"path": "docs/baselines/p1-legacy-fixture-required-profile-facts.v1.yaml", "sha256": "3848535dcd03008a8815bd1631f9fea9d8790112c56a3fa401f6821dd9f14596"}, "facts_binding_invalid")
    _require(isinstance(recon_binding, dict) and set(recon_binding) == {"path", "sha256"}, "reconciliation_binding_shape_invalid")
    _require(recon_binding["path"] == "docs/baselines/p1-04b-comparison-permission-reconciliation.v1.yaml" and recon_binding["sha256"] == _sha256(root / RECONCILIATION.relative_to(ROOT)), "reconciliation_binding_invalid")

    facts_gate = _import_gate("verify_p1_legacy_fixture_required_profile_facts")
    facts_doc = facts_gate._load(root / FACTS.relative_to(ROOT))
    facts_result = facts_gate.validate(facts_doc)
    _require(facts_result.get("valid") is True and facts_doc["gates"]["required_profile_selected"] is False and facts_doc["gates"]["distribution_authorized"] is False, "required_profile_facts_promoted")
    boundary_gate = _import_gate("verify_p1_04b_legacy_fixture_boundary")
    boundary_result = boundary_gate.validate(live_manifest, root)
    _require(boundary_result.get("valid") is True and boundary_result.get("external_assets") == 14 and boundary_result.get("legacy_schema_ids") == 0, "legacy_boundary_not_closed")
    _require(not _worktree_materialized_asset_paths(root), "legacy_fixture_worktree_materialized")
    reconciliation_gate = _import_gate("verify_p1_04b_comparison_permission_reconciliation")
    reconciliation_result = reconciliation_gate.validate()
    _require(reconciliation_result.get("valid") is True and reconciliation_result.get("comparison_permission_decided") is True and reconciliation_result.get("external_facts_pending") is True, "comparison_reconciliation_drift")
    _validate_domain_records(root)

    non_claims = document.get("non_claims")
    _require(non_claims == [
        "scoped_close_is_not_full_p1_04b_item_close",
        "trusted_comparison_is_not_redistribution_permission",
        "trusted_comparison_is_not_product_or_runtime_admission",
        "required_by_labels_are_not_profile_selection",
        "source_archive_identity_is_not_distribution_authority",
        "no_license_or_rights_conclusion",
        "no_external_oracle_acceptance",
        "no_release_promotion",
    ], "non_claims_invalid")
    audit = document.get("audit")
    _require(isinstance(audit, dict) and audit.get("path") == "docs/baselines/audits/2026-08-21-p1-04b-oracle-only-scope-closure.md", "audit_binding_invalid")
    audit_path = root / audit["path"]
    _require(audit_path.is_file() and audit.get("sha256") == _sha256(audit_path), "audit_hash_invalid")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": document["status"],
        "asset_count": len(ASSET_IDS),
        "required_by_required_count": len(REQUIRED_ASSET_IDS),
        "legacy_schema_ids": boundary_result["legacy_schema_ids"],
        "worktree_materialized_asset_paths": 0,
        "domain_blocker_groups": len(EXPECTED_BLOCKERS),
        "external_facts_pending": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = validate(root=args.root)
    except (OSError, ValueError, ScopeClosureError, yaml.YAMLError) as error:
        result = {"schema": SCHEMA, "valid": False, "reason": str(error)}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
