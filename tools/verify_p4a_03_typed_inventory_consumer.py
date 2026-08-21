"""Verify the bounded P4A-03 typed inventory consumer and its asset boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "baselines" / "p4a-03-typed-inventory-consumer.v1.yaml"
IMPLEMENTATION = ROOT / "crates" / "sipi-ibis" / "src" / "typed_inventory_v1.rs"
ASSET = ROOT / "fixtures" / "ibis" / "as4c512m16md4v-053bin.ibs"
AUDIT = ROOT / "docs" / "baselines" / "audits" / "2026-08-21-p4a-03-typed-inventory-consumer.md"
SCHEMA = "sipi.p4a-03.typed-inventory-consumer.v1"
POLICY = "sipi.p4a-03.typed-inventory-consumer.v1.declaration-linkage-only"
ASSET_SHA256 = "d72cf62b56d67d30f4004f56ea3b79b4cb1241615692b147682f47540e615a0b"


class TypedInventoryError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypedInventoryError("manifest_not_mapping")
    return value


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def observe_asset(data: bytes) -> dict[str, Any]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as error:
        raise TypedInventoryError("asset_not_ascii") from error
    models: set[str] = set()
    selectors: dict[str, list[str]] = {}
    current_section: str | None = None
    current_selector: str | None = None
    version: str | None = None
    component: str | None = None
    for raw in text.splitlines():
        line = raw.split("|", 1)[0].strip()
        if not line:
            continue
        keyword = re.match(r"^\[([^\]]+)\]\s*(.*)$", line)
        if keyword:
            current_section = keyword.group(1).strip()
            payload = keyword.group(2).strip()
            current_selector = None
            if current_section == "IBIS Ver":
                version = payload
            elif current_section == "Component":
                component = payload
            elif current_section == "Model":
                models.add(payload)
            elif current_section == "Model Selector":
                current_selector = payload
                selectors[current_selector] = []
            continue
        if current_section == "Model Selector" and current_selector:
            fields = line.split()
            if fields:
                selectors[current_selector].append(fields[0])
    if version is None or component is None:
        raise TypedInventoryError("asset_header_missing")
    unknown: dict[str, str] = {}
    for selector, branches in selectors.items():
        for model in branches:
            if model not in models:
                unknown.setdefault(selector, model)
    return {
        "version": version,
        "component": component,
        "model_count": len(models),
        "selector_count": len(selectors),
        "selector_branch_unknown": unknown,
    }


def validate(root: Path = ROOT) -> dict[str, Any]:
    manifest_path = MANIFEST if root == ROOT else root / MANIFEST.relative_to(ROOT)
    manifest = load_yaml(manifest_path)
    implementation = root / IMPLEMENTATION.relative_to(ROOT)
    asset = root / ASSET.relative_to(ROOT)
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "implemented_self_tested_boundary":
        raise TypedInventoryError("manifest_schema_or_status_invalid")
    if manifest.get("policy") != POLICY:
        raise TypedInventoryError("policy_drift")
    audit = manifest.get("audit", {})
    if audit.get("path") != str(AUDIT.relative_to(ROOT)).replace("\\", "/"):
        raise TypedInventoryError("audit_path_drift")
    audit_path = root / Path(audit["path"])
    if not audit_path.is_file() or sha256(audit_path.read_bytes()) != audit.get("sha256"):
        raise TypedInventoryError("audit_hash_drift")
    audit_text = audit_path.read_text(encoding="utf-8")
    if any(
        token not in audit_text
        for token in (
            "# P4A-03 Typed Inventory Consumer",
            "DQ_PIN -> DQ_60OHM_60OHM_PREEMP_ON",
            "P4A-03 main item therefore remains",
        )
    ):
        raise TypedInventoryError("audit_content_drift")
    if not implementation.is_file() or sha256(implementation.read_bytes()) != manifest.get("source", {}).get("implementation_sha256"):
        raise TypedInventoryError("implementation_hash_drift")
    source = implementation.read_text(encoding="utf-8")
    required_tokens = (
        "pub struct IbisTypedInventoryServiceV1",
        "pub struct IbisTypedInventoryReportV1",
        "pub struct IbisPinReferenceLinkageV1",
        "lift_model_selectors",
        "classify_pin_references",
        POLICY,
        "electrical_behavior_status",
        "profile_selection_status",
    )
    if any(token not in source for token in required_tokens):
        raise TypedInventoryError("implementation_binding_drift")
    if not asset.is_file() or sha256(asset.read_bytes()) != ASSET_SHA256:
        raise TypedInventoryError("selected_asset_hash_drift")
    observed = observe_asset(asset.read_bytes())
    expected = manifest.get("selected_asset_observation", {})
    if observed["version"] != expected.get("observed_version"):
        raise TypedInventoryError("selected_asset_version_drift")
    if observed["component"] != expected.get("observed_component"):
        raise TypedInventoryError("selected_asset_component_drift")
    if observed["model_count"] != expected.get("observed_model_block_count"):
        raise TypedInventoryError("selected_asset_model_count_drift")
    if observed["selector_count"] != expected.get("observed_model_selector_count"):
        raise TypedInventoryError("selected_asset_selector_count_drift")
    rejection = expected.get("rejection", {})
    if observed["selector_branch_unknown"].get(rejection.get("selector")) != rejection.get("model"):
        raise TypedInventoryError("selected_asset_selector_gap_drift")
    admission = manifest.get("admission", {})
    for field in (
        "library_consumer_api",
        "bounded_ascii_input",
        "structural_parser_reused",
        "semantic_envelope_reused",
        "model_declarations_lifted",
        "model_selector_declarations_lifted",
        "pin_declarations_lifted",
        "selector_branch_must_reference_declared_model",
    ):
        if admission.get(field) is not True:
            raise TypedInventoryError(f"admission_drift:{field}")
    if admission.get("public_cli_route") is not False or admission.get("product_runtime_invoked") is not False:
        raise TypedInventoryError("consumer_route_boundary_drift")
    for field in (
        "model_or_selector_branch_selection",
        "corner_or_pvt_selection",
        "supply_or_reference_inference",
        "electrical_behavior",
        "transient_integration",
        "ami_runtime",
        "external_profile_acceptance",
        "release_promotion",
    ):
        if admission.get(field) is not False:
            raise TypedInventoryError(f"non_claim_boundary_drift:{field}")
    non_claims = manifest.get("non_claims", [])
    required_non_claims = {
        "not_complete_ibis_semantic_parser",
        "not_general_ibis_compatibility",
        "not_model_or_corner_selection",
        "not_electrical_behavior",
        "not_transient_or_quasi_static_upgrade",
        "not_ami_behavior_or_runtime",
        "not_external_profile_acceptance",
        "not_release_evidence",
    }
    if not required_non_claims.issubset(non_claims):
        raise TypedInventoryError("non_claims_drift")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": manifest["status"],
        "selected_asset_model_count": observed["model_count"],
        "selected_asset_selector_count": observed["selector_count"],
        "selector_gap": rejection,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        report = validate(args.root)
    except (OSError, yaml.YAMLError, TypedInventoryError) as error:
        report = {"schema": SCHEMA, "valid": False, "reason": str(error)}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
