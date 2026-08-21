"""Verify the P4B parameter API selection baseline.

This gate is deliberately a selection gate, not an implementation or oracle
gate.  It binds all 193 feature-quarantined module exports to one disposition,
proves that the default host/worker consume only raw structural text, and
refuses a keep decision without both an AMI requirement and a live consumer.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "docs" / "baselines" / "p4b-02-parameter-selection-charter.v1.yaml"
LIB = ROOT / "crates" / "sipi-ami-text" / "src" / "lib.rs"
EVIDENCE_DIR = ROOT / "docs" / "baselines"
SCHEMA = "sipi.p4b-02.parameter-selection-charter.v1"
CFG = '#[cfg(any(test, feature = "p4b-self-crosscheck"))]'
MODULE_RE = re.compile(r"(?m)^mod (?:ami_|catalog_|parameter_)[A-Za-z0-9_]+;$")
EXPECTED_EVIDENCE_STATUS = "product_owned_self_crosscheck_unbound"
EXPECTED_MODULE_COUNT = 193
EXPECTED_MODULE_HASH = "f67ba0bc084823a6bdbe7f2852bb22c8169b18ec41d6edca94e49297ea018168"
EXPECTED_EVIDENCE_COUNT = 191
CLASSIFICATIONS = {
    "keep_for_product",
    "quarantine_pending_requirement",
    "delete_candidate",
}


class SelectionError(RuntimeError):
    """Raised when the selection charter is missing or inconsistent."""


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise SelectionError(f"yaml_load_failed:{path}") from error
    if not isinstance(value, dict):
        raise SelectionError(f"document_not_mapping:{path}")
    return value


def module_inventory(text: str) -> list[str]:
    modules = sorted(
        line.removeprefix("mod ").removesuffix(";")
        for line in MODULE_RE.findall(text)
    )
    if len(modules) != len(set(modules)):
        raise SelectionError("duplicate_module_declaration")
    return modules


def module_hash(modules: Iterable[str]) -> str:
    payload = "\n".join(modules) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _selector_matches(selector: dict[str, Any], modules: list[str], group_id: str) -> set[str]:
    if not isinstance(selector, dict):
        raise SelectionError(f"selector_not_mapping:{group_id}")
    exact = selector.get("exact", [])
    prefixes = selector.get("prefixes", [])
    exclude = selector.get("exclude", [])
    if not all(isinstance(item, str) for item in exact + prefixes + exclude):
        raise SelectionError(f"selector_item_not_string:{group_id}")
    module_set = set(modules)
    unknown_exact = sorted(set(exact) - module_set)
    unknown_exclude = sorted(set(exclude) - module_set)
    if unknown_exact:
        raise SelectionError(f"selector_unknown_exact:{group_id}:{unknown_exact[0]}")
    if unknown_exclude:
        raise SelectionError(f"selector_unknown_exclude:{group_id}:{unknown_exclude[0]}")
    selected = set(exact)
    for prefix in prefixes:
        selected.update(module for module in modules if module.startswith(prefix))
    selected.difference_update(exclude)
    if not selected:
        raise SelectionError(f"selector_matches_nothing:{group_id}")
    return selected


def _validate_references(root: Path, requirement: dict[str, Any], group_id: str) -> None:
    references = requirement.get("references")
    if not isinstance(references, list) or not references:
        raise SelectionError(f"requirement_references_missing:{group_id}")
    for reference in references:
        if not isinstance(reference, str) or not reference:
            raise SelectionError(f"requirement_reference_invalid:{group_id}")
        if not (root / reference).is_file():
            raise SelectionError(f"requirement_reference_missing:{group_id}:{reference}")


def _validate_group_metadata(root: Path, group: dict[str, Any], selected: set[str]) -> None:
    group_id = group.get("id")
    classification = group.get("classification")
    if not isinstance(group_id, str) or not group_id:
        raise SelectionError("group_id_missing")
    if classification not in CLASSIFICATIONS:
        raise SelectionError(f"classification_invalid:{group_id}")
    requirement = group.get("ami_contract_requirement")
    consumer = group.get("production_consumer")
    budget = group.get("complexity_budget")
    evidence = group.get("evidence_basis")
    if not all(isinstance(value, dict) for value in (requirement, consumer, budget, evidence)):
        raise SelectionError(f"group_metadata_missing:{group_id}")
    _validate_references(root, requirement, group_id)
    paths = consumer.get("paths")
    symbols = consumer.get("symbols")
    if not isinstance(paths, list) or not isinstance(symbols, list):
        raise SelectionError(f"consumer_shape_invalid:{group_id}")
    if classification == "keep_for_product":
        if requirement.get("status") != "required":
            raise SelectionError(f"keep_without_requirement:{group_id}")
        if not requirement.get("statement"):
            raise SelectionError(f"keep_requirement_statement_missing:{group_id}")
        if consumer.get("status") != "live_default_route" or not paths or not symbols:
            raise SelectionError(f"keep_without_consumer:{group_id}")
        if budget.get("status") != "allocated":
            raise SelectionError(f"keep_without_complexity_budget:{group_id}")
        if evidence.get("independent_oracle") is not True:
            raise SelectionError(f"keep_without_independent_oracle_gate:{group_id}")
        if evidence.get("can_authorize_product_keep") is not True:
            raise SelectionError(f"keep_self_crosscheck_authority:{group_id}")
        return
    if consumer.get("status") != "none_in_default_product" or paths or symbols:
        raise SelectionError(f"nonkeep_consumer_claim:{group_id}")
    if evidence.get("independent_oracle") is not False:
        raise SelectionError(f"nonkeep_oracle_claim:{group_id}")
    if evidence.get("can_authorize_product_keep") is not False:
        raise SelectionError(f"nonkeep_authority_claim:{group_id}")
    if classification == "quarantine_pending_requirement":
        if requirement.get("status") != "pending_owner_profile":
            raise SelectionError(f"quarantine_requirement_status:{group_id}")
        if budget.get("status") != "not_allocated":
            raise SelectionError(f"quarantine_budget_status:{group_id}")
    else:
        if requirement.get("status") != "none_identified":
            raise SelectionError(f"delete_requirement_status:{group_id}")
        if budget.get("status") != "zero_product_budget":
            raise SelectionError(f"delete_budget_status:{group_id}")
    if not selected:
        raise SelectionError(f"empty_group:{group_id}")


def _validate_group_coverage(root: Path, charter: dict[str, Any], modules: list[str]) -> dict[str, set[str]]:
    groups = charter.get("groups")
    if not isinstance(groups, list) or not groups:
        raise SelectionError("groups_missing")
    seen_ids: set[str] = set()
    seen_modules: dict[str, str] = {}
    by_classification: dict[str, set[str]] = {name: set() for name in CLASSIFICATIONS}
    for group in groups:
        if not isinstance(group, dict):
            raise SelectionError("group_not_mapping")
        group_id = group.get("id")
        if group_id in seen_ids:
            raise SelectionError(f"duplicate_group:{group_id}")
        if not isinstance(group_id, str):
            raise SelectionError("group_id_missing")
        seen_ids.add(group_id)
        selected = _selector_matches(group.get("selectors", {}), modules, group_id)
        _validate_group_metadata(root, group, selected)
        classification = group["classification"]
        by_classification[classification].update(selected)
        for module in selected:
            previous = seen_modules.get(module)
            if previous is not None:
                raise SelectionError(f"module_overlap:{module}:{previous}:{group_id}")
            seen_modules[module] = group_id
    missing = sorted(set(modules) - set(seen_modules))
    extra = sorted(set(seen_modules) - set(modules))
    if missing:
        raise SelectionError(f"module_not_classified:{missing[0]}")
    if extra:
        raise SelectionError(f"classified_module_not_in_inventory:{extra[0]}")
    return by_classification


def _validate_live_consumers(root: Path, charter: dict[str, Any], modules: list[str]) -> None:
    consumers = charter.get("observed_default_consumers")
    expected = {
        ("sipi-ami-host", "crates/sipi-ami-host/src/lib.rs"),
        ("sipi-ami-worker", "crates/sipi-ami-worker/src/lib.rs"),
    }
    actual = {
        (consumer.get("component"), consumer.get("path"))
        for consumer in consumers
        if isinstance(consumer, dict)
    } if isinstance(consumers, list) else set()
    if actual != expected:
        raise SelectionError("default_consumer_inventory_missing")
    production_manifest_names = {"sipi-ami-text"}
    for consumer in consumers:
        if not isinstance(consumer, dict):
            raise SelectionError("default_consumer_not_mapping")
        path = consumer.get("path")
        symbols = consumer.get("symbols")
        if not isinstance(path, str) or not (root / path).is_file():
            raise SelectionError(f"default_consumer_path_missing:{path}")
        parameter_semantics = consumer.get("parameter_semantics")
        if parameter_semantics not in (False, True):
            raise SelectionError(f"default_consumer_parameter_claim:{consumer.get('component')}")
        source = (root / path).read_text(encoding="utf-8")
        if not isinstance(symbols, list) or any(symbol not in source for symbol in symbols):
            raise SelectionError(f"default_consumer_symbol_missing:{consumer.get('component')}")
        if parameter_semantics is False and re.search(
            r"(?:AmiParameter|ParameterCatalog|RuntimeParam|ami_runtime_params|parameter_[a-z0-9_]+)",
            source,
        ):
            raise SelectionError(f"default_consumer_parameter_export:{consumer.get('component')}")
        if parameter_semantics is True:
            required = {
                "sipi-ami-host": ("initialize_forwarded_subset", "AmiForwardedParameterSubsetV1"),
                "sipi-ami-worker": (
                    "prepare_forwarded_parameter_subset_v1",
                    "AmiParameterProfileLimitsV1",
                ),
            }.get(consumer.get("component"), ())
            if any(token not in source for token in required):
                raise SelectionError(f"scoped_adapter_consumer_missing:{consumer.get('component')}")
    for manifest in (root / "crates").glob("*/Cargo.toml"):
        if manifest.parent.name not in production_manifest_names:
            text = manifest.read_text(encoding="utf-8")
            if "p4b-self-crosscheck" in text:
                raise SelectionError(f"production_feature_consumer:{manifest.parent.name}")
    # Every semantic module/export must remain hidden from the default build.
    library_path = LIB if root == ROOT else root / "crates" / "sipi-ami-text" / "src" / "lib.rs"
    library = library_path.read_text(encoding="utf-8")
    for module in modules:
        declaration = f"{CFG}\nmod {module};"
        if library.count(declaration) != 1:
            raise SelectionError(f"module_not_feature_quarantined:{module}")
        pub_uses = list(re.finditer(rf"(?m)^pub use {re.escape(module)}::", library))
        if len(pub_uses) != 1:
            raise SelectionError(f"export_inventory_drift:{module}")
        before = library[: pub_uses[0].start()].rstrip("\r\n").splitlines()
        if not before or before[-1] != CFG:
            raise SelectionError(f"export_not_feature_quarantined:{module}")


def _validate_evidence_documents(paths: Iterable[Path]) -> int:
    paths = sorted(paths)
    if len(paths) != EXPECTED_EVIDENCE_COUNT:
        raise SelectionError(f"evidence_count:{len(paths)}")
    for path in paths:
        document = load_yaml(path)
        if document.get("status") != EXPECTED_EVIDENCE_STATUS:
            raise SelectionError(f"evidence_status:{path.name}")
        if not str(document.get("schema", "")).startswith("sipi.p4b-02b"):
            raise SelectionError(f"evidence_schema:{path.name}")
    return len(paths)


def validate(root: Path = ROOT) -> dict[str, Any]:
    charter_path = CHARTER if root == ROOT else root / "docs" / "baselines" / CHARTER.name
    charter = load_yaml(charter_path)
    if charter.get("schema") != SCHEMA or charter.get("status") != "selection_baseline":
        raise SelectionError("charter_schema_or_status_invalid")
    if charter.get("baseline_commit") != "805ebb6bbaf588dec08685be4eb78a8ce2fff563":
        raise SelectionError("baseline_commit_drift")
    inventory = charter.get("inventory")
    if not isinstance(inventory, dict):
        raise SelectionError("inventory_missing")
    if inventory.get("source") != "crates/sipi-ami-text/src/lib.rs":
        raise SelectionError("inventory_source_drift")
    if inventory.get("module_pattern") != "^mod (ami_|catalog_|parameter_)[A-Za-z0-9_]+;$":
        raise SelectionError("inventory_pattern_drift")
    decision_rule = charter.get("decision_rule")
    if not isinstance(decision_rule, dict):
        raise SelectionError("decision_rule_missing")
    if decision_rule.get("self_crosscheck_is_not_authority") is not True:
        raise SelectionError("self_crosscheck_authority_rule_drift")
    if decision_rule.get("product_owned_self_crosscheck_status") != EXPECTED_EVIDENCE_STATUS:
        raise SelectionError("self_crosscheck_status_rule_drift")
    evidence_inventory = charter.get("evidence_inventory")
    if not isinstance(evidence_inventory, dict):
        raise SelectionError("evidence_inventory_missing")
    if (
        evidence_inventory.get("glob") != "docs/baselines/p4b-02b*-crosscheck-evidence.v1.yaml"
        or evidence_inventory.get("expected_count") != EXPECTED_EVIDENCE_COUNT
        or evidence_inventory.get("required_status") != EXPECTED_EVIDENCE_STATUS
        or evidence_inventory.get("independent_oracle") is not False
        or evidence_inventory.get("may_authorize_keep") is not False
    ):
        raise SelectionError("evidence_inventory_rule_drift")
    library_path = LIB if root == ROOT else root / "crates" / "sipi-ami-text" / "src" / "lib.rs"
    library = library_path.read_text(encoding="utf-8")
    modules = module_inventory(library)
    if inventory.get("module_count") != EXPECTED_MODULE_COUNT or len(modules) != EXPECTED_MODULE_COUNT:
        raise SelectionError("module_count_drift")
    expected_hash = inventory.get("module_inventory_sha256")
    if expected_hash != EXPECTED_MODULE_HASH or module_hash(modules) != expected_hash:
        raise SelectionError("module_inventory_hash_drift")
    counts = _validate_group_coverage(root, charter, modules)
    expected_counts = charter.get("expected_counts")
    actual_counts = {key: len(value) for key, value in counts.items()}
    if expected_counts != actual_counts:
        raise SelectionError("selection_counts_drift")
    if charter.get("current_keep_for_product") != sorted(counts["keep_for_product"]):
        raise SelectionError("keep_inventory_drift")
    if counts["keep_for_product"]:
        raise SelectionError("nonempty_keep_requires_followup_ticket")
    _validate_live_consumers(root, charter, modules)
    evidence_paths = (root / "docs" / "baselines").glob("p4b-02b*-crosscheck-evidence.v1.yaml")
    evidence_count = _validate_evidence_documents(evidence_paths)
    return {
        "valid": True,
        "schema": SCHEMA,
        "module_count": len(modules),
        "group_count": len(charter["groups"]),
        "selection_counts": actual_counts,
        "keep_count": 0,
        "evidence_count": evidence_count,
        "evidence_authority": EXPECTED_EVIDENCE_STATUS,
        "default_parameter_consumers": 0,
        "next_ticket": "T03",
        "next_ticket_consumer_path": "authorized AMI profile -> typed parameter adapter -> sipi-ami-host::AmiHostV1::initialize / sipi-ami-worker::run_one_job",
    }


def main() -> int:
    try:
        result = validate(ROOT)
    except SelectionError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
