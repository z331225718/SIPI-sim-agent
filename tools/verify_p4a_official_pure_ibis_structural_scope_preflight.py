"""Verify the fail-closed P4A external pure-IBIS structural-scope record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4a.external-pure-ibis-structural-scope-preflight.v1"
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "p4a-official-pure-ibis-structural-scope-preflight.v1.yaml"
OWNER_POLICY_PATH = ROOT / "docs" / "baselines" / "p4a-official-pure-ibis-owner-policy-authorization.v1.yaml"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ScopeError(RuntimeError):
    pass


def _exact_keys(value: object, keys: set[str], reason: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ScopeError(reason)
    return value


def _safe_ref(value: object) -> bool:
    return isinstance(value, str) and value and not value.startswith(("/", "file:")) and "\\" not in value and ".." not in value.split("/")


def _verify_ref(value: object, *, expected_path: str) -> None:
    ref = _exact_keys(value, {"path", "content_sha256"}, "reference_shape_invalid")
    if ref["path"] != expected_path or not _safe_ref(ref["path"]) or not isinstance(ref["content_sha256"], str) or not SHA256.fullmatch(ref["content_sha256"]):
        raise ScopeError("reference_invalid")
    source = ROOT / ref["path"]
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != ref["content_sha256"]:
        raise ScopeError("reference_content_mismatch")


def validate_owner_policy(document: object) -> None:
    value = _exact_keys(document, {"schema", "status", "authorization_anchor", "asset_identity", "scope", "non_claims"}, "owner_policy_shape_invalid")
    if value["schema"] != "sipi.p4a-official-pure-ibis-owner-policy-authorization.v1" or value["status"] != "authorized_external_oracle_only" or value["authorization_anchor"] != "user_confirmation_2026-08-10":
        raise ScopeError("owner_policy_status_invalid")
    if value["asset_identity"] != {"content_sha256": "46c53a49a31dea27769f0dddddadea72f03f1f956fb8e60aeaa24f83a7201b95", "byte_length": 406532}:
        raise ScopeError("owner_policy_identity_invalid")
    expected_scope = {
        "allowed_uses": ["external_oracle", "acceptance_selection_review"],
        "external_custody": "retained_external_operator_custody",
        "third_party_rights_status": "unverified",
        "prohibited_uses": ["git_asset", "product_fixture", "product_source", "release_bundle", "default_runtime", "redistribution"],
    }
    if value["scope"] != expected_scope:
        raise ScopeError("owner_policy_scope_invalid")
    if not isinstance(value["non_claims"], list) or len(value["non_claims"]) != 3 or not all(isinstance(item, str) and item for item in value["non_claims"]):
        raise ScopeError("owner_policy_non_claims_invalid")


def validate_manifest(document: object) -> dict[str, Any]:
    value = _exact_keys(document, {"schema", "status", "promotion_eligible", "identity_preflight_ref", "owner_policy_ref", "asset_identity", "observer", "scan_scope", "facts", "negative_observations", "unexamined", "classification", "non_claims"}, "manifest_shape_invalid")
    if value["schema"] != SCHEMA or value["status"] != "structural_scope_pass_for_owner_selection" or value["promotion_eligible"] is not False:
        raise ScopeError("manifest_status_invalid")
    _verify_ref(value["identity_preflight_ref"], expected_path="docs/baselines/p4a-official-pure-ibis-license-identity-preflight.v1.yaml")
    _verify_ref(value["owner_policy_ref"], expected_path="docs/baselines/p4a-official-pure-ibis-owner-policy-authorization.v1.yaml")
    validate_owner_policy(yaml.safe_load(OWNER_POLICY_PATH.read_text(encoding="utf-8")))
    identity = _exact_keys(value["asset_identity"], {"content_sha256", "byte_length"}, "asset_identity_shape_invalid")
    if identity != {"content_sha256": "46c53a49a31dea27769f0dddddadea72f03f1f956fb8e60aeaa24f83a7201b95", "byte_length": 406532}:
        raise ScopeError("asset_identity_invalid")
    observer = _exact_keys(value["observer"], {"source_sha256", "mode", "product_parser_not_used"}, "observer_shape_invalid")
    source = ROOT / "tools" / "observe_p4a_external_pure_ibis_structural_scope.py"
    if observer != {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "mode": "external_read_only", "product_parser_not_used": True}:
        raise ScopeError("observer_invalid")
    expected_scope = {"allowed": ["line_structure", "bracket_headers", "section_counts", "identifier_digests", "source_span_digests", "fixed_indicator_counts"], "forbidden": ["numeric_tables", "curves", "parameter_values", "package_pvt_evaluation", "interpolation", "simulation", "ami_dll_calls"]}
    if value["scan_scope"] != expected_scope:
        raise ScopeError("scan_scope_invalid")
    facts = value["facts"]
    expected_facts = {
        "ibis_header": {"count": 1, "span_digest": "dcb6b2889933e08df8b896267454e1c4d858f936a9a315dc5b7e50aca2d93c49"},
        "component": {"count": 1, "span_digest": "03431b2c1e99903f1a1dfbb0e5e5082ea20e08f43afea8932879f39453855919"},
        "model": {"count": 14, "span_digest": "f506e3d344a77f670d1b7687d99f9b265f55a9337f0ffc65f17c24bd450b6dfc", "identifier_digest": "f57816aa073de9e5d4392044df0ced54571e42f70e8994f9dcf7ce7ad967238c"},
        "model_selector": {"count": 1, "span_digest": "64abf63a6a05151082b2e7adb12c453670e92d9f1f877427a7691234d47e2be3", "identifier_digest": "38d24de7ff5f21517797dc3a3644e3c511764d99511b5767060b341ddfdf1f46"},
        "model_type_input": {"count": 5, "span_digest": "67b6bd44e6111dff3e9ed627bc3e709559aee36180d20e17e12b2eba5d1932f6"},
    }
    if facts != expected_facts:
        raise ScopeError("facts_invalid")
    expected_negative = {"indicator_rule_sha256": "2a16416dcf78ffec7f035c37028a538d482ad0bdb089d34a3b817bab0a58e977", "counts": {"algorithmic_model": 0, "ami_file": 0, "dynamic_library": 0, "include": 0}, "meaning": "not_observed_in_declared_scope_only"}
    if value["negative_observations"] != expected_negative:
        raise ScopeError("negative_observations_invalid")
    if value["unexamined"] != ["model_selector_choice", "model_semantics", "numeric_data", "ami_binary_dependencies", "license", "electrical_behavior"]:
        raise ScopeError("unexamined_invalid")
    expected_classification = {"boundary": "external_only", "third_party_rights_status": "unverified", "required": False, "product_asset": False, "parser_fixture": False, "oracle_runnable": False, "release_input": False, "selection_eligibility": "eligible_for_owner_selection"}
    if value["classification"] != expected_classification:
        raise ScopeError("classification_invalid")
    if not isinstance(value["non_claims"], list) or len(value["non_claims"]) != 4 or not all(isinstance(item, str) and item for item in value["non_claims"]):
        raise ScopeError("non_claims_invalid")
    return {"schema": SCHEMA, "status": value["status"], "asset_identity": identity["content_sha256"], "required": False, "selection_eligibility": "eligible_for_owner_selection", "promotion_eligible": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = validate_manifest(yaml.safe_load(args.manifest.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ScopeError, TypeError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if args.report:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["status"] == "structural_scope_pass_for_owner_selection" else 2


if __name__ == "__main__":
    raise SystemExit(main())
