"""Fail closed on the P4B-02b1 typed .ami parameter value validation core.

The charter fixes the syntax-only semantics: caller-supplied (name, type
token, value token) triples validated against explicit product-owned rules,
with no reserved-name catalog, no default inference, no document decoding,
and no IBIS-AMI parameter catalog coverage claim. The verifier cross-binds
the charter against the sipi-ami-text implementation source and the PLAN
P4B-02b1 row.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p4b-02b1-parameter-value-core.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "parameter_value_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b1.parameter-value-core.v1"
POLICY = "sipi.p4b-02b1.parameter-value-v1.syntax-only-no-catalog-no-defaults"


class ParameterValueError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParameterValueError("document_not_mapping")
    return value


def verify_document(document: object) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise ParameterValueError("schema_invalid")
    if document.get("status") != "product_owned_parameter_value_core_specified_no_catalog_no_defaults":
        raise ParameterValueError("status_invalid")
    if document.get("name_rule") != "ascii_start_letter_or_underscore_then_alphanumerics_or_underscore":
        raise ParameterValueError("name_rule_drift")
    if document.get("type_tokens") != ["Float", "Integer", "Boolean", "String", "List"]:
        raise ParameterValueError("type_tokens_drift")
    if document.get("value_rules") != {
        "Float": "parses_as_finite_f64",
        "Integer": "parses_as_i64",
        "Boolean": "exactly_true_or_false",
        "String": "nonempty",
        "List": "parenthesized_comma_separated_nonempty_items",
    }:
        raise ParameterValueError("value_rules_drift")
    if document.get("scope_policy") != POLICY:
        raise ParameterValueError("scope_policy_drift")
    if document.get("implementation") != { "crate": "sipi-ami-text", "module": "parameter_value_v1", "types": ["AmiParameterValueV1", "AmiParameterTypeV1", "AmiParameterValueErrorV1"] }:
        raise ParameterValueError("implementation_drift")
    if document.get("admission") != { "profile_accepted": False, "reserved_names": "not_in_this_slice", "defaults": "not_in_this_slice", "document_decoding": False, "binding_connection": "pending_later_slice", "external_reference_binding": "not_evaluated" }:
        raise ParameterValueError("admission_drift")
    claims = document.get("non_claims")
    expected_claims = ["not_ibis_ami_catalog", "not_reserved_names", "not_defaults", "not_model_specific_semantics", "not_document_decoding", "not_profile_acceptance"]
    if not isinstance(claims, list) or claims != expected_claims:
        raise ParameterValueError("non_claims_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub struct AmiParameterValueV1",
        "pub enum AmiParameterTypeV1",
        "pub enum AmiParameterValueErrorV1",
        "UnknownTypeToken",
        "InvalidFloat",
        "InvalidInteger",
        "InvalidBoolean",
        "InvalidList",
        "pub const PARAMETER_VALUE_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise ParameterValueError("implementation_binding_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b1" not in plan_text:
        raise ParameterValueError("plan_row_missing")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": document["status"],
        "parameter_value_core": "specified",
        "profile_accepted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        result = verify_document(load_yaml(arguments.core))
    except (OSError, ValueError, yaml.YAMLError, ParameterValueError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
