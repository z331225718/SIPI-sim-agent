"""Verify the closed bounded P4A-03 declaration/linkage consumer scope."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/p4a-03-complete-typed-inventory-consumer.v2.yaml"
PREDECESSOR = ROOT / "docs/baselines/p4a-03-typed-inventory-consumer.v1.yaml"
PREDECESSOR_SHA256 = "3b7c8132321f356947b3e9b8e363dcdf6dfa8c09d1a1daed56eb2b640313c5d7"
IMPLEMENTATION = ROOT / "crates/sipi-ibis/src/typed_inventory_v1.rs"
RUNNER = ROOT / "crates/sipi-ibis/tests/p4a_03_typed_inventory_runner.rs"
ASSET = ROOT / "fixtures/ibis/as4c512m16md4v-053bin.ibs"
DISPOSITION = ROOT / "docs/baselines/p4a-01-selected-ibis-truncation-disposition.v1.yaml"
EVIDENCE = ROOT / "docs/baselines/p4a-03-official-external-typed-inventory-observation.v1.json"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p4a-03-complete-typed-inventory-consumer.md"
OFFICIAL_SOURCE = Path(
    r"C:\Users\z3312\code\.sipi-p4a-official-asset-20260821\as4c512m16md4v-053bin.ibs"
)
SCHEMA = "sipi.p4a-03.complete-typed-inventory-consumer.v2"
POLICY = "sipi.p4a-03.typed-inventory-consumer.v1.declaration-linkage-only"


class TypedInventoryError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypedInventoryError("manifest_not_mapping")
    return value


def observe_complete_asset(data: bytes, markers: set[str]) -> dict[str, Any]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as error:
        raise TypedInventoryError("asset_not_ascii") from error
    models: set[str] = set()
    selectors: dict[str, list[str]] = {}
    pins: list[str] = []
    current_section: str | None = None
    current_selector: str | None = None
    version: str | None = None
    components: list[str] = []
    records: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.split("|", 1)[0].strip()
        if not line:
            continue
        keyword = re.match(r"^\[([^\]]+)\]\s*(.*)$", line)
        if keyword:
            current_section = keyword.group(1).strip()
            payload = keyword.group(2).strip()
            records.append((current_section, payload))
            current_selector = None
            if current_section == "IBIS Ver":
                version = payload
            elif current_section == "Component":
                components.append(payload)
            elif current_section == "Model":
                models.add(payload)
            elif current_section == "Model Selector":
                current_selector = payload
                selectors[current_selector] = []
            continue
        records.append(("data", line))
        fields = line.split()
        if current_selector and fields:
            selectors[current_selector].append(fields[0])
        elif current_section == "Pin" and len(fields) >= 3:
            pins.append(fields[2])
    ends = [index for index, record in enumerate(records) if record == ("End", "")]
    if ends != [len(records) - 1]:
        raise TypedInventoryError("official_complete_document_boundary_drift")
    unknown = [
        (selector, model)
        for selector, branches in selectors.items()
        for model in branches
        if model not in models
    ]
    unresolved = [reference for reference in pins if reference not in models and reference not in selectors and reference not in markers]
    if unknown or unresolved:
        raise TypedInventoryError("official_linkage_drift")
    return {
        "input_byte_length": len(data),
        "input_sha256": sha256(data),
        "declared_version": version,
        "component_names": components,
        "model_count": len(models),
        "selector_count": len(selectors),
        "pin_count": len(pins),
        "direct_model_pin_count": sum(reference in models for reference in pins),
        "selector_pin_count": sum(reference in selectors for reference in pins),
        "marker_pin_count": sum(reference in markers for reference in pins),
        "electrical_behavior_status": "not_evaluated",
        "profile_selection_status": "not_selected",
    }


def validate(root: Path = ROOT, official_source: Path = OFFICIAL_SOURCE) -> dict[str, Any]:
    manifest = load_yaml(root / MANIFEST.relative_to(ROOT))
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "bounded_declaration_linkage_scope_closed":
        raise TypedInventoryError("manifest_schema_or_status_invalid")
    if manifest.get("predecessor") != {
        "path": "docs/baselines/p4a-03-typed-inventory-consumer.v1.yaml",
        "sha256": PREDECESSOR_SHA256,
        "unchanged": True,
    }:
        raise TypedInventoryError("predecessor_binding_invalid")
    if sha256((root / PREDECESSOR.relative_to(ROOT)).read_bytes()) != PREDECESSOR_SHA256:
        raise TypedInventoryError("predecessor_hash_drift")
    if manifest.get("policy") != POLICY:
        raise TypedInventoryError("policy_drift")
    source_spec = manifest.get("source", {})
    bindings = (
        (IMPLEMENTATION, "implementation", "implementation_sha256"),
        (RUNNER, "external_test_runner", "external_test_runner_sha256"),
        (DISPOSITION, "p4a_01_disposition", "p4a_01_disposition_sha256"),
    )
    for absolute, path_field, hash_field in bindings:
        path = root / absolute.relative_to(ROOT)
        if source_spec.get(path_field) != absolute.relative_to(ROOT).as_posix():
            raise TypedInventoryError(f"{path_field}_path_drift")
        if sha256(path.read_bytes()) != source_spec.get(hash_field):
            raise TypedInventoryError(f"{path_field}_hash_drift")
    implementation = (root / IMPLEMENTATION.relative_to(ROOT)).read_text(encoding="utf-8")
    for token in (
        "pub struct IbisTypedInventoryServiceV1",
        "require_final_end",
        "MissingEnd",
        "DuplicateEnd",
        "InvalidEnd",
        "TrailingRecordAfterEnd",
        "lift_model_selectors",
        "classify_pin_references",
        POLICY,
    ):
        if token not in implementation:
            raise TypedInventoryError("implementation_binding_drift")
    runner = (root / RUNNER.relative_to(ROOT)).read_text(encoding="utf-8")
    for token in ("IbisTypedInventoryServiceV1::inspect", "--input", "--marker", "not a product asset route"):
        if token not in runner:
            raise TypedInventoryError("runner_binding_drift")

    for field, absolute in (("audit", AUDIT), ("evidence", EVIDENCE)):
        spec = manifest.get(field, {})
        if spec.get("path") != absolute.relative_to(ROOT).as_posix():
            raise TypedInventoryError(f"{field}_path_drift")
        path = root / absolute.relative_to(ROOT)
        if sha256(path.read_bytes()) != spec.get("sha256"):
            raise TypedInventoryError(f"{field}_hash_drift")
    audit_text = (root / AUDIT.relative_to(ROOT)).read_text(encoding="utf-8")
    for token in ("# P4A-03 Complete Typed Inventory Consumer", "closes only the bounded declaration/linkage consumer scope", "No selector branch"):
        if token not in audit_text:
            raise TypedInventoryError("audit_content_drift")

    tracked = (root / ASSET.relative_to(ROOT)).read_bytes()
    if sha256(tracked) != source_spec.get("selected_tracked_asset_sha256"):
        raise TypedInventoryError("selected_tracked_asset_hash_drift")
    if re.search(rb"(?mi)^\s*\[End\]\s*(?:\|.*)?$", tracked):
        raise TypedInventoryError("selected_tracked_asset_end_drift")
    rejection = manifest.get("selected_tracked_asset_observation", {}).get("rejection", {})
    if rejection != {"code": "missing_end"}:
        raise TypedInventoryError("selected_tracked_asset_rejection_drift")

    evidence = json.loads((root / EVIDENCE.relative_to(ROOT)).read_text(encoding="utf-8"))
    markers = evidence.get("explicit_markers")
    if markers != ["GND", "NC", "POWER"] or evidence.get("promotion_eligible") is not False:
        raise TypedInventoryError("evidence_boundary_drift")
    observed = observe_complete_asset(official_source.read_bytes(), set(markers))
    expected = manifest.get("external_official_observation", {})
    result = evidence.get("result", {})
    for field, value in observed.items():
        if expected.get(field) != value or result.get(field) != value:
            raise TypedInventoryError(f"official_observation_drift:{field}")
    if result.get("policy") != POLICY or result.get("valid") is not True:
        raise TypedInventoryError("evidence_result_drift")

    admission = manifest.get("admission", {})
    for field in (
        "library_consumer_api",
        "test_only_external_path_runner",
        "complete_document_required",
        "exactly_one_final_payload_free_end",
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
    for field in (
        "public_cli_route",
        "product_runtime_invoked",
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
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": manifest["status"],
        "model_count": observed["model_count"],
        "selector_count": observed["selector_count"],
        "pin_count": observed["pin_count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--official-source", type=Path, default=OFFICIAL_SOURCE)
    args = parser.parse_args()
    try:
        report = validate(args.root, args.official_source)
    except (OSError, ValueError, yaml.YAMLError, TypedInventoryError) as error:
        report = {"schema": SCHEMA, "valid": False, "reason": str(error)}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
