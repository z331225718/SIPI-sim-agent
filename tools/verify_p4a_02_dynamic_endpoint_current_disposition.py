"""Verify additive E3=A deferral while static/declaration P4A scope continues."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/p4a-02-dynamic-endpoint-current-disposition.v2.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p4a-02-dynamic-endpoint-current-disposition.md"
SCHEMA = "sipi.p4a-02.dynamic-endpoint-current-disposition.v2"
EXPECTED_BLOCKERS = [
    "reference_node_channel_return_binding_pending",
    "supply_semantics_pending",
    "initial_state_policy_pending",
    "integration_method_pending",
    "timebase_pending",
    "output_grid_pending",
    "channel_return_binding_pending",
    "stimulus_semantics_pending",
    "dynamic_numeric_bounds_pending",
    "dynamic_tolerance_pending",
    "dynamic_acceptance_evidence_missing",
]


class CurrentDispositionError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CurrentDispositionError("yaml_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    manifest = load_yaml(root / MANIFEST.relative_to(ROOT))
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "e3a_dynamic_endpoint_deferred_static_declaration_continues":
        raise CurrentDispositionError("schema_or_status_drift")
    if manifest.get("promotion_eligible") is not False or manifest.get("additive") is not True:
        raise CurrentDispositionError("additive_promotion_boundary_drift")
    decision = manifest.get("decision", {})
    if decision.get("e3") != "A" or decision.get("dynamic_endpoint_this_stage") != "do_not_implement":
        raise CurrentDispositionError("e3_decision_drift")

    loaded: dict[str, dict[str, Any]] = {}
    for name, spec in manifest.get("predecessors", {}).items():
        path = root / Path(spec.get("path", ""))
        if spec.get("unchanged") is not True or not path.is_file() or sha256(path.read_bytes()) != spec.get("sha256"):
            raise CurrentDispositionError(f"predecessor_drift:{name}")
        loaded[name] = load_yaml(path)
    if set(loaded) != {"static_scope_split", "dynamic_composition_contract"}:
        raise CurrentDispositionError("predecessor_set_drift")
    old_blocker = loaded["static_scope_split"].get("dynamic_endpoint_blocker", {})
    contract_t12 = loaded["dynamic_composition_contract"].get("t12_admission", {})
    if old_blocker.get("missing_fields") != EXPECTED_BLOCKERS or old_blocker.get("admission") is not False:
        raise CurrentDispositionError("prior_static_split_drift")
    if contract_t12.get("blockers") != EXPECTED_BLOCKERS or contract_t12.get("admission") is not False:
        raise CurrentDispositionError("dynamic_contract_drift")

    current = manifest.get("current_disposition", {})
    for field in ("structural_inventory_continues", "typed_declaration_linkage_continues", "admitted_static_primitives_continue"):
        if current.get(field) is not True:
            raise CurrentDispositionError(f"continuation_drift:{field}")
    for field in ("dynamic_endpoint_admission", "dynamic_endpoint_implementation", "transient_integration"):
        if current.get(field) is not False:
            raise CurrentDispositionError(f"dynamic_admission_drift:{field}")
    if current.get("quasi_static_or_batch_as_transient_evidence") != "forbidden":
        raise CurrentDispositionError("transient_evidence_boundary_drift")
    blocker = manifest.get("dynamic_blocker", {})
    if blocker.get("id") != "P4A-T12" or blocker.get("status") != "retained_unchanged_until_later_additive_profile" or blocker.get("missing_fields") != EXPECTED_BLOCKERS:
        raise CurrentDispositionError("retained_blocker_drift")
    reconsideration = manifest.get("reconsideration", {})
    for field in ("requires_later_owner_selected_profile", "all_dynamic_fields_must_be_frozen", "independent_acceptance_evidence_required"):
        if reconsideration.get(field) is not True:
            raise CurrentDispositionError(f"reconsideration_drift:{field}")
    if reconsideration.get("implicit_predecessor_defaults") != "forbidden":
        raise CurrentDispositionError("implicit_default_boundary_drift")

    audit = manifest.get("audit", {})
    if audit.get("path") != AUDIT.relative_to(ROOT).as_posix() or sha256((root / AUDIT.relative_to(ROOT)).read_bytes()) != audit.get("sha256"):
        raise CurrentDispositionError("audit_binding_drift")
    audit_text = (root / AUDIT.relative_to(ROOT)).read_text(encoding="utf-8")
    for token in ("# P4A-02 Dynamic Endpoint Current Disposition", "explicitly defers", "eleven blocker classes remain unchanged"):
        if token not in audit_text:
            raise CurrentDispositionError("audit_content_drift")
    return {"schema": SCHEMA, "valid": True, "status": manifest["status"], "dynamic_endpoint_admission": False, "retained_blocker_count": len(EXPECTED_BLOCKERS)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        report = validate(args.root)
    except (OSError, yaml.YAMLError, CurrentDispositionError) as error:
        report = {"schema": SCHEMA, "valid": False, "reason": str(error)}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
