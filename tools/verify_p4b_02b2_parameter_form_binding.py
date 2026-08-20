"""Fail closed on the P4B-02b2 typed parameter form identity binding.

The charter fixes the identity-only semantics: one caller-declared typed
triple binds to one caller-selected structural form only via byte-exact
spelling identity; the API never interprets a form as a parameter. The
verifier cross-binds the charter against the sipi-ami-text implementation
source and the PLAN P4B-02b2 row.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p4b-02b2-parameter-form-binding.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ami-text" / "src" / "parameter_form_binding_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4b-02b2.parameter-form-binding.v1"
POLICY = "sipi.p4b-02b2.parameter-form-binding-v1.identity-only"


class FormBindingError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FormBindingError("document_not_mapping")
    return value


def verify_document(document: object) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise FormBindingError("schema_invalid")
    if document.get("status") != "product_owned_parameter_form_identity_binding_specified_no_semantics":
        raise FormBindingError("status_invalid")
    if document.get("identity_rules") != {
        "form_index": "must_be_in_range",
        "item_count": "exactly_three",
        "item_kind": "atom_or_quoted_no_nested_list",
        "name_match": "byte_exact",
        "type_token_match": "byte_exact",
        "value_token_match": "byte_exact",
    }:
        raise FormBindingError("identity_rules_drift")
    if document.get("scope_policy") != POLICY:
        raise FormBindingError("scope_policy_drift")
    if document.get("implementation") != { "crate": "sipi-ami-text", "module": "parameter_form_binding_v1", "entrypoint": "bind_parameter_value_v1", "types": ["ParameterFormBindingV1", "ParameterFormBindingErrorV1"] }:
        raise FormBindingError("implementation_drift")
    if document.get("admission") != { "profile_accepted": False, "two_item_forms": "not_interpreted", "semantic_interpretation": "never", "catalog_reserved_names": "not_in_this_slice", "defaults": "not_in_this_slice", "external_reference_binding": "not_evaluated" }:
        raise FormBindingError("admission_drift")
    claims = document.get("non_claims")
    expected_claims = ["not_parameter_grammar", "not_ibis_ami_catalog", "not_reserved_names", "not_defaults", "not_document_wide_interpretation", "not_profile_acceptance"]
    if not isinstance(claims, list) or claims != expected_claims:
        raise FormBindingError("non_claims_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub struct ParameterFormBindingV1",
        "pub enum ParameterFormBindingErrorV1",
        "FormIndexOutOfRange",
        "FormNotThreeItems",
        "FormItemIsNestedList",
        "NameSpellingMismatch",
        "TypeTokenSpellingMismatch",
        "ValueTokenSpellingMismatch",
        "pub fn bind_parameter_value_v1",
        "pub const PARAMETER_FORM_BINDING_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise FormBindingError("implementation_binding_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4B-02b2" not in plan_text:
        raise FormBindingError("plan_row_missing")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": document["status"],
        "parameter_form_identity_binding": "specified",
        "profile_accepted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        result = verify_document(load_yaml(arguments.core))
    except (OSError, ValueError, yaml.YAMLError, FormBindingError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
