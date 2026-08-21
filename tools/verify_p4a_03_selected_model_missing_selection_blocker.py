"""Verify the additive P4A-03 missing selected-model decision blocker."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/p4a-03-selected-model-missing-selection-blocker.v1.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p4a-03-selected-model-missing-selection.md"
OFFICIAL_SOURCE = Path(r"C:\Users\z3312\code\.sipi-p4a-official-asset-20260821\as4c512m16md4v-053bin.ibs")
SCHEMA = "sipi.p4a-03.selected-model-missing-selection-blocker.v1"
BEHAVIOR_SECTIONS = {
    "Composite Current",
    "Falling Waveform",
    "GND Clamp",
    "ISSO_PD",
    "ISSO_PU",
    "POWER Clamp",
    "Pulldown",
    "Pullup",
    "Ramp",
    "Rising Waveform",
}


class MissingSelectionError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MissingSelectionError("yaml_not_mapping")
    return value


def observe(data: bytes) -> dict[str, Any]:
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise MissingSelectionError("asset_not_ascii") from error
    models: dict[str, dict[str, Any]] = {}
    selectors: dict[str, list[str]] = {}
    pin_refs: list[str] = []
    section: str | None = None
    selector: str | None = None
    model: str | None = None
    for raw in lines:
        line = raw.split("|", 1)[0].strip()
        if not line:
            continue
        keyword = re.match(r"^\[([^\]]+)\]\s*(.*)$", line)
        if keyword:
            section, payload = keyword.group(1).strip(), keyword.group(2).strip()
            selector = None
            if section == "Model Selector":
                model = None
                selector = payload
                selectors[selector] = []
            elif section == "Model":
                model = payload
                models[model] = {"model_type": None, "sections": set()}
            elif section == "End":
                model = None
            elif model and section in BEHAVIOR_SECTIONS:
                models[model]["sections"].add(section)
            continue
        fields = line.split()
        if selector and fields:
            selectors[selector].append(fields[0])
        elif section == "Pin" and len(fields) >= 3:
            pin_refs.append(fields[2])
        elif model and section == "Model" and len(fields) >= 2 and fields[0].lower() == "model_type":
            models[model]["model_type"] = fields[1]
    branches = {branch for values in selectors.values() for branch in values}
    direct_models = sorted({reference for reference in pin_refs if reference in models})
    families: dict[str, dict[str, Any]] = {}
    for model_type in ("Input", "I/O"):
        selected = [value for value in models.values() if value["model_type"] == model_type]
        distinct = {tuple(sorted(value["sections"])) for value in selected}
        if len(distinct) != 1:
            raise MissingSelectionError(f"{model_type}_keyword_family_not_unique")
        families[model_type] = {"model_count": len(selected), "sections": list(next(iter(distinct)))}
    return {
        "sha256": sha256(data),
        "model_count": len(models),
        "model_types": dict(Counter(value["model_type"] for value in models.values())),
        "pin_reference_counts": dict(Counter(pin_refs)),
        "selectors": {name: len(values) for name, values in selectors.items()},
        "selector_branch_model_count": len(branches),
        "direct_referenced_models": direct_models,
        "referenced_declared_model_count": len(branches | set(direct_models)),
        "families": families,
    }


def validate(root: Path = ROOT, official_source: Path = OFFICIAL_SOURCE) -> dict[str, Any]:
    manifest = load_yaml(root / MANIFEST.relative_to(ROOT))
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "d4_scoped_grammar_authorized_selection_missing":
        raise MissingSelectionError("schema_or_status_drift")
    if manifest.get("promotion_eligible") is not False:
        raise MissingSelectionError("promotion_boundary_drift")
    decision = manifest.get("decision", {})
    if decision.get("d4") != "A" or decision.get("rule") != "implement_only_grammar_required_by_explicitly_selected_model":
        raise MissingSelectionError("d4_decision_drift")
    predecessors = manifest.get("predecessors", {})
    expected_predecessors = {
        "required_profile_inventory": "docs/baselines/p4a-01-required-profile-inventory.v1.yaml",
        "owner_decision_reconciliation": "docs/baselines/owner-decision-reconciliation.v2.yaml",
        "official_rights_recheck": "docs/baselines/p4a-01-official-object-rights-recheck.v1.yaml",
        "complete_typed_inventory": "docs/baselines/p4a-03-complete-typed-inventory-consumer.v2.yaml",
    }
    for name, relative in expected_predecessors.items():
        spec = predecessors.get(name, {})
        if spec.get("path") != relative or sha256((root / relative).read_bytes()) != spec.get("sha256"):
            raise MissingSelectionError(f"predecessor_drift:{name}")
    required = load_yaml(root / expected_predecessors["required_profile_inventory"])
    if "model" in required or "selector" in required or "corner" in required or "pvt" in required or "table_family" in required:
        raise MissingSelectionError("required_profile_selection_shape_drift")
    reconciliation = load_yaml(root / expected_predecessors["owner_decision_reconciliation"])
    decisions = [item for item in reconciliation.get("decisions", []) if item.get("id") == "P4A-01"]
    if len(decisions) != 1:
        raise MissingSelectionError("owner_reconciliation_shape_drift")
    recommendation = decisions[0].get("recommendation", {})
    if recommendation.get("model_selector") != "not_selected" or recommendation.get("corner") != "not_selected" or recommendation.get("guessing") != "prohibited":
        raise MissingSelectionError("owner_selection_boundary_drift")

    observed = observe(official_source.read_bytes())
    inventory = manifest.get("exact_external_inventory", {})
    comparisons = {
        "asset_sha256": observed["sha256"],
        "model_count": observed["model_count"],
        "model_types": observed["model_types"],
        "pin_reference_counts": observed["pin_reference_counts"],
        "selectors": observed["selectors"],
        "selector_branch_model_count": observed["selector_branch_model_count"],
        "direct_referenced_models": observed["direct_referenced_models"],
        "referenced_declared_model_count": observed["referenced_declared_model_count"],
    }
    for field, value in comparisons.items():
        if inventory.get(field) != value:
            raise MissingSelectionError(f"external_inventory_drift:{field}")
    family_spec = inventory.get("declaration_keyword_families", {})
    for key, model_type in (("input_models", "Input"), ("io_models", "I/O")):
        if family_spec.get(key) != observed["families"][model_type]:
            raise MissingSelectionError(f"keyword_family_drift:{key}")

    uniqueness = manifest.get("mechanical_uniqueness", {})
    for field in ("signal_role_unique", "selector_unique", "selector_branch_unique", "model_unique", "corner_or_pvt_unique", "table_family_unique", "direct_cke_reference_is_global_product_selection"):
        if uniqueness.get(field) is not False:
            raise MissingSelectionError(f"mechanical_uniqueness_drift:{field}")
    required_missing = {
        "product_signal_or_pin_role",
        "model_or_model_selector",
        "selector_branch_if_selector_is_used",
        "corner_and_pvt_policy",
        "required_table_or_behavior_family",
    }
    if set(manifest.get("missing_selection_fields", [])) != required_missing:
        raise MissingSelectionError("missing_selection_fields_drift")
    disposition = manifest.get("disposition", {})
    for field in ("selected_model_scoped_grammar_admitted", "selected_model_electrical_consumer_admitted"):
        if disposition.get(field) is not False:
            raise MissingSelectionError(f"implementation_admission_drift:{field}")
    if disposition.get("existing_declaration_linkage_consumer_continues") is not True:
        raise MissingSelectionError("existing_consumer_disposition_drift")

    audit = manifest.get("audit", {})
    if audit.get("path") != AUDIT.relative_to(ROOT).as_posix() or sha256((root / AUDIT.relative_to(ROOT)).read_bytes()) != audit.get("sha256"):
        raise MissingSelectionError("audit_binding_drift")
    audit_text = (root / AUDIT.relative_to(ROOT)).read_text(encoding="utf-8")
    for token in ("# P4A-03 Selected Model Missing-Selection Audit", "not mechanically unique", "No selected-model grammar"):
        if token not in audit_text:
            raise MissingSelectionError("audit_content_drift")
    return {"schema": SCHEMA, "valid": True, "status": manifest["status"], "model_count": observed["model_count"], "selector_branch_model_count": observed["selector_branch_model_count"], "implementation_admitted": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--official-source", type=Path, default=OFFICIAL_SOURCE)
    args = parser.parse_args()
    try:
        report = validate(args.root, args.official_source)
    except (OSError, yaml.YAMLError, MissingSelectionError) as error:
        report = {"schema": SCHEMA, "valid": False, "reason": str(error)}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
