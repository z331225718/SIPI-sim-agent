"""Verify the P3C-03 fixed COM/ERL/TD-ILN bundle capability."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/baselines/p3c-03-com-metric-bundle-capability.v1.yaml"
SCHEMA = "sipi.p3c-03.com-metric-bundle-capability.v1"
STATUS = "p3c_03_required_metric_bundle_prerequisite_implemented_acceptance_open"
REFERENCES = {
    "crates/sipi-compare/src/com_metric_bundle_v1.rs": "8cfaa822e666e2c9fae0710f2e41cabc001d55e2a8a13acb5e4fb370444c30ed",
    "crates/sipi-compare/src/lib.rs": "a8472e62b5892a8fa5a0b4aa88b26e33c12176f5ca3a2a81128a8406509e1b74",
    "docs/baselines/p5-06k-required-com-compare-contract-gap.v1.yaml": "6bf07e6265176569ceee8a5250bf3012fe47881d4c982a6edc8fb59ce65c91d9",
    "docs/baselines/audits/2026-08-21-p3c-03-com-metric-bundle-capability.md": "5722964c57ddfc814fffd290664c28cf7c8f13312858bce88255115477f2656d",
}


class P3C03BundleError(RuntimeError):
    pass


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise P3C03BundleError(message)


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    _expect(isinstance(value, dict), "document_not_mapping")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root: Path = ROOT) -> dict[str, Any]:
    evidence = _load(EVIDENCE)
    _expect(evidence.get("schema") == SCHEMA, "schema_invalid")
    _expect(evidence.get("status") == STATUS, "status_invalid")

    scope = evidence.get("scope")
    _expect(isinstance(scope, dict), "scope_missing")
    _expect(scope.get("work_item") == "P3C-03", "work_item_drift")
    _expect(scope.get("role") == "p5_06_prerequisite_capability", "role_drift")
    _expect(scope.get("main_item_closed") is False, "main_item_promoted")
    for key in ["external_runtime_invoked", "product_vs_oracle_compare_executed", "historical_evidence_rewritten", "c4_profile_changed", "acceptance_or_release_promoted"]:
        _expect(scope.get(key) is False, f"scope_{key}_promoted")

    implementation = evidence.get("implementation")
    _expect(isinstance(implementation, dict), "implementation_missing")
    _expect(implementation.get("policy") == "sipi.p3c-03.com-metric-bundle.v1.com-erl-td-iln-explicit-tolerances", "policy_drift")
    _expect(implementation.get("metrics") == [
        {"id": "com_db", "unit": "db"},
        {"id": "erl_db", "unit": "db"},
        {"id": "td_iln_db", "unit": "db"},
    ], "metric_surface_drift")
    for key in ["complete_typed_bundle_required", "finite_reference_and_candidate_required", "tolerance_per_metric_explicit"]:
        _expect(implementation.get(key) is True, f"implementation_{key}_missing")
    _expect(implementation.get("default_tolerance") is None, "default_tolerance_invented")
    _expect(implementation.get("compare_engine_reused") == "compare_metric_profile_v1", "compare_engine_drift")
    _expect(implementation.get("public_map_or_alias_input") is False, "map_or_alias_promoted")
    _expect(implementation.get("alignment") == "none", "alignment_invented")
    _expect(implementation.get("unit_conversion") == "none", "unit_conversion_invented")

    guard = evidence.get("substitution_guard")
    _expect(guard == {
        "icn_field_present": False,
        "icn_to_td_iln_alias": False,
        "legacy_c4_profile_unchanged": True,
    }, "substitution_guard_drift")

    blockers = evidence.get("remaining_blockers")
    _expect(blockers == [
        "authoritative_reference_artifact_missing",
        "td_iln_reference_value_missing",
        "clean_input_provenance_missing",
        "checkpoint_alignment_missing",
        "required_per_metric_acceptance_tolerances_missing",
    ], "remaining_blockers_drift")

    bindings = {
        implementation["source"]["path"]: implementation["source"]["sha256"],
        implementation["public_surface"]["path"]: implementation["public_surface"]["sha256"],
        evidence["required_contract"]["path"]: evidence["required_contract"]["sha256"],
        evidence["audit"]["path"]: evidence["audit"]["sha256"],
    }
    _expect(bindings == REFERENCES, "reference_inventory_drift")
    for relative, expected in REFERENCES.items():
        path = root / relative
        _expect(path.is_file(), f"reference_missing:{relative}")
        _expect(_sha256(path) == expected, f"reference_hash_invalid:{relative}")

    source = (root / implementation["source"]["path"]).read_text(encoding="utf-8")
    for token in ["pub struct ComMetricBundleV1", "pub struct ComMetricTolerancesV1", "pub fn compare_com_metric_bundle_v1", "compare_metric_profile_v1"]:
        _expect(token in source, f"source_token_missing:{token}")
    _expect('const METRIC_NAMES: [&str; 3] = ["com_db", "erl_db", "td_iln_db"]' in source, "fixed_metric_surface_missing")
    production_source = source.split("#[cfg(test)]", 1)[0]
    _expect("icn" not in production_source.lower(), "icn_surface_present")

    claims = set(evidence.get("non_claims", []))
    _expect({"not_td_iln_algorithm_implementation", "not_product_vs_oracle_compare", "not_acceptance_evidence", "not_release_evidence"} <= claims, "non_claim_missing")
    return {"schema": SCHEMA, "valid": True, "status": STATUS, "metric_count": 3, "main_item_closed": False}


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        result = validate(ROOT)
    except (OSError, UnicodeError, yaml.YAMLError, KeyError, P3C03BundleError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
