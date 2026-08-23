"""Verify the bounded specified/non-oracle COM artifact route prerequisite."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/baselines/p5-08f-specified-com-artifact-route.v2.yaml"
SCHEMA = "sipi.p5-08f.specified-com-artifact-route.v2"


class RouteError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RouteError(f"document_not_mapping:{path.name}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise RouteError(reason)


def validate(document: dict[str, Any] | None = None) -> dict[str, Any]:
    document = _load(DOCUMENT) if document is None else document
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == "specified_route_prerequisite_implemented_p5_08_open", "status_invalid")
    _require(document.get("policy") == "sipi.p5-08f.com-run-artifact-specified-v1.product-owned-non-oracle", "policy_invalid")
    _require(document.get("relationship") == {
        "predecessor_evidence": "docs/baselines/p5-08f-specified-com-artifact-route.v1.yaml",
        "predecessor_verifier": "tools/verify_p5_08f_specified_com_artifact_route.py",
        "predecessor_retained": True,
        "successor_reason": "current_public_surface_source_rebind",
    }, "predecessor_binding_invalid")
    implementation = document.get("implementation")
    _require(isinstance(implementation, dict), "implementation_invalid")
    for key in ("parameter_module", "execution_module", "public_surface", "cli_surface", "contract_surface"):
        binding = implementation.get(key)
        _require(isinstance(binding, dict) and set(binding) == {"path", "sha256"}, f"source_binding_invalid:{key}")
        path = ROOT / binding["path"]
        _require(path.is_file() and _sha256(path) == binding["sha256"], f"source_hash_drift:{key}")
    _require(implementation.get("route") == ["com", "run-artifact"], "route_invalid")
    _require(implementation.get("request_schema") == "sipi.com.run-artifact-request.v1", "request_schema_invalid")
    _require(implementation.get("response_schema") == "sipi.com.run-artifact-specified-result.v1", "response_schema_invalid")
    _require(implementation.get("legacy_com_route") == {"id": "com.run", "availability": "unavailable"}, "legacy_route_promoted")

    contract = document.get("contract")
    _require(isinstance(contract, dict), "contract_invalid")
    _require(contract.get("explicit_partition") is True, "partition_not_explicit")
    _require(contract.get("partition_authority") == "caller_supplied_product_owned_not_workbook_or_profile", "partition_authority_invalid")
    _require(contract.get("unknown_fields") == "rejected", "unknown_fields_not_rejected")
    _require(contract.get("finite_values_only") is True, "finite_gate_missing")
    _require(contract.get("pulse_file") == "pulse.f64le", "pulse_file_invalid")
    _require(contract.get("output_publication") == "immutable_publish_new", "publication_invalid")
    _require(contract.get("input_manifest_max_bytes") == 65_536, "manifest_budget_invalid")
    _require(contract.get("pulse_max_bytes") == 524_288, "pulse_budget_invalid")
    _require(contract.get("result_max_bytes") == 16_384, "result_budget_invalid")

    scope = document.get("scope")
    _require(isinstance(scope, dict), "scope_invalid")
    _require(scope.get("product_owned_bounded_execution") is True, "product_scope_missing")
    _require(scope.get("workbook_read") is False, "workbook_claim_invalid")
    _require(scope.get("p5_05g_workbook_ingestion_reused") is False, "p5_05g_false_binding")
    _require(scope.get("independent_explicit_partition") is True, "independent_partition_missing")
    _require(scope.get("profile_inference") is False and scope.get("auto_tuning") is False, "profile_or_tuning_promotion")
    _require(scope.get("agent_com_parity") == "not_claimed", "parity_promoted")
    _require(scope.get("external_acceptance") == "blocked", "acceptance_promoted")
    _require(scope.get("release_evidence") is False, "release_promoted")
    legacy = document.get("legacy_boundary")
    _require(isinstance(legacy, dict), "legacy_boundary_invalid")
    _require(legacy.get("p5_08_main_item_closed") is False, "main_item_false_close")
    _require(all(legacy.get(key) is True for key in ("p5_08e_source_unchanged", "legacy_wire_unchanged", "p5_08d_source_unchanged", "new_route_is_not_p7_acceptance")), "legacy_boundary_drift")
    _require(set(document.get("non_claims", [])) == {
        "not_agent_com_parity", "not_external_oracle_compare", "not_acceptance_evidence",
        "not_ieee_certification", "not_release_evidence", "not_hostile_writer_safe",
        "not_p5_05g_workbook_ingestion",
    }, "non_claims_invalid")
    audit = document.get("audit")
    _require(isinstance(audit, dict) and set(audit) == {"path", "sha256"}, "audit_binding_invalid")
    audit_path = ROOT / audit["path"]
    _require(audit_path.is_file() and _sha256(audit_path) == audit["sha256"], "audit_hash_drift")

    cli = (ROOT / implementation["cli_surface"]["path"]).read_text(encoding="utf-8")
    _require('id: "com.run-artifact"' in cli and '["com", "run-artifact"]' in cli, "cli_route_missing")
    _require('id: "com.run"' in cli and 'unavailable_reason: Some("com_profile_not_admitted")' in cli, "legacy_com_route_drift")
    _require("COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1" in cli, "request_budget_not_applied_before_parse")
    return {"schema": SCHEMA, "valid": True, "route": "com.run-artifact", "p5_08_closed": False}


def main() -> int:
    try:
        print(json.dumps(validate(), sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, yaml.YAMLError, RouteError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
