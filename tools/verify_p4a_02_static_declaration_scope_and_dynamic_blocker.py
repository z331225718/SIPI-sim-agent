"""Verify the P4A-02 bounded static/declaration split and dynamic blocker."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/p4a-02-static-declaration-scope-and-dynamic-blocker.v1.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p4a-02-static-scope-dynamic-blocker.md"
SCHEMA = "sipi.p4a-02.static-declaration-scope-and-dynamic-blocker.v1"
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


class ScopeSplitError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ScopeSplitError("yaml_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    manifest = load_yaml(root / MANIFEST.relative_to(ROOT))
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "bounded_static_declaration_scope_closed_dynamic_endpoint_blocked":
        raise ScopeSplitError("schema_or_status_drift")
    if manifest.get("promotion_eligible") is not False:
        raise ScopeSplitError("promotion_boundary_drift")

    loaded: dict[str, dict[str, Any]] = {}
    for name, spec in manifest.get("predecessors", {}).items():
        path = root / Path(spec.get("path", ""))
        if not path.is_file() or sha256(path.read_bytes()) != spec.get("sha256"):
            raise ScopeSplitError(f"predecessor_hash_drift:{name}")
        loaded[name] = load_yaml(path)
    if set(loaded) != {
        "authorized_behavior_observation",
        "static_conformance_matrix",
        "typed_declaration_linkage_consumer",
        "dynamic_composition_contract",
    }:
        raise ScopeSplitError("predecessor_set_drift")

    behavior = loaded["authorized_behavior_observation"]
    observation = behavior.get("behavior_spec_observation", {})
    boundary = behavior.get("semantic_boundary", {})
    if behavior.get("status") != "authorized_behavior_spec_observed":
        raise ScopeSplitError("behavior_observation_status_drift")
    if observation.get("tx_model", {}).get("probe_status") != "success_all":
        raise ScopeSplitError("tx_observation_drift")
    if observation.get("rx_model", {}).get("probe_status") != "probe_crash_all":
        raise ScopeSplitError("rx_observation_drift")
    if boundary.get("parser_interpolation_clamp_package_pvt_semantics") != "not_defined" or boundary.get("product_runtime_incurs") is not False:
        raise ScopeSplitError("behavior_semantic_boundary_drift")

    if loaded["static_conformance_matrix"].get("status") != "boundary_recorded":
        raise ScopeSplitError("static_matrix_boundary_drift")
    if loaded["typed_declaration_linkage_consumer"].get("status") != "bounded_declaration_linkage_scope_closed":
        raise ScopeSplitError("typed_consumer_boundary_drift")
    dynamic = loaded["dynamic_composition_contract"]
    t12 = dynamic.get("t12_admission", {})
    if dynamic.get("status") != "specified_blocked_dynamic_semantics_pending" or t12.get("state") != "blocked" or t12.get("admission") is not False:
        raise ScopeSplitError("dynamic_contract_admission_drift")
    if t12.get("blockers") != EXPECTED_BLOCKERS:
        raise ScopeSplitError("dynamic_contract_blocker_drift")

    closeable = manifest.get("closeable_scope", {})
    if closeable.get("status") != "closed_evidence_reconciled" or closeable.get("product_runtime_incurred") is not False:
        raise ScopeSplitError("closeable_scope_drift")
    blocker = manifest.get("dynamic_endpoint_blocker", {})
    if blocker.get("id") != "P4A-T12" or blocker.get("admission") is not False or blocker.get("implementation_authorized") is not False:
        raise ScopeSplitError("dynamic_blocker_admission_drift")
    if blocker.get("missing_fields") != EXPECTED_BLOCKERS:
        raise ScopeSplitError("dynamic_blocker_field_drift")

    admission = manifest.get("admission", {})
    if admission.get("bounded_static_declaration_scope_closeable") is not True:
        raise ScopeSplitError("static_scope_admission_drift")
    for field in (
        "general_ibis",
        "gen5_profile_selected",
        "electrical_behavior_implemented",
        "dynamic_endpoint",
        "transient_integration",
        "ami_runtime",
        "external_profile_acceptance",
        "release_promotion",
    ):
        if admission.get(field) is not False:
            raise ScopeSplitError(f"non_claim_boundary_drift:{field}")

    audit = manifest.get("audit", {})
    if audit.get("path") != AUDIT.relative_to(ROOT).as_posix():
        raise ScopeSplitError("audit_path_drift")
    audit_path = root / Path(audit["path"])
    if sha256(audit_path.read_bytes()) != audit.get("sha256"):
        raise ScopeSplitError("audit_hash_drift")
    audit_text = audit_path.read_text(encoding="utf-8")
    for token in ("# P4A-02 Static Scope and Dynamic Blocker", "cannot be implemented without guessing", "P4A-T12"):
        if token not in audit_text:
            raise ScopeSplitError("audit_content_drift")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": manifest["status"],
        "dynamic_endpoint_admission": False,
        "missing_dynamic_fields": len(EXPECTED_BLOCKERS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        report = validate(args.root)
    except (OSError, yaml.YAMLError, ScopeSplitError) as error:
        report = {"schema": SCHEMA, "valid": False, "reason": str(error)}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
