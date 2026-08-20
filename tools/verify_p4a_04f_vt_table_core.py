"""Fail closed on the P4A-04f typed V-T table core.

The charter fixes the V-T slice semantics: strictly time-ascending finite
knots, linear interpolation within the closed table domain, explicit
out-of-domain rejection, and no ramp/package/decoder/CLI/profile claims.
The verifier cross-binds the charter against the sipi-ibis implementation
source and the PLAN P4A-04f row.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p4a-04f-vt-table-core.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ibis" / "src" / "vt_table_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4a-04f.vt-table-core.v1"
POLICY = "sipi.p4a-04f.vt-table-v1.linear-within-domain.reject-out-of-domain"


class VtCoreError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VtCoreError("document_not_mapping")
    return value


def verify_document(document: object) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise VtCoreError("schema_invalid")
    if document.get("status") != "product_owned_vt_table_core_specified_no_profile_acceptance":
        raise VtCoreError("status_invalid")
    if document.get("slice") != { "iv": "delivered_by_p4a_04b", "vt": "this_slice", "ramp": "not_in_this_slice", "package": "not_in_this_slice", "decoder": "not_in_this_slice", "cli": "not_in_this_slice" }:
        raise VtCoreError("slice_scope_drift")
    if document.get("evaluation_policy") != { "policy": POLICY, "interpolation": "linear_within_table_domain", "extrapolation": "reject_out_of_domain", "domain": "closed_first_last" }:
        raise VtCoreError("evaluation_policy_drift")
    if document.get("table_rules") != { "min_knots": 2, "time_order": "strictly_increasing", "finiteness": "enforced_by_sipi_types" }:
        raise VtCoreError("table_rules_drift")
    if document.get("units") != {"time": "seconds", "voltage": "volts"}:
        raise VtCoreError("units_drift")
    if document.get("implementation") != { "crate": "sipi-ibis", "module": "vt_table_v1", "entrypoint": "evaluate_vt_v1", "types": ["VtKnotV1", "VtTableV1", "VtTableErrorV1", "VtEvaluationErrorV1"] }:
        raise VtCoreError("implementation_drift")
    if document.get("admission") != { "profile_accepted": False, "ibis_text_decoded": False, "electrical_evaluation": False, "cli_route": False, "external_reference_binding": "not_evaluated" }:
        raise VtCoreError("admission_drift")
    claims = document.get("non_claims")
    expected_claims = ["not_ibis_text_decoding", "not_ramp_semantics", "not_package_semantics", "not_profile_acceptance", "not_electrical_evaluation"]
    if not isinstance(claims, list) or claims != expected_claims:
        raise VtCoreError("non_claims_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub struct VtKnotV1",
        "pub struct VtTableV1",
        "pub enum VtTableErrorV1",
        "TooFewKnots",
        "TimeNotStrictlyIncreasing",
        "pub enum VtEvaluationErrorV1",
        "OutOfDomain",
        "pub const VT_EVALUATION_POLICY_V1",
        POLICY,
        "pub fn evaluate_vt_v1",
    )
    if any(token not in source for token in required_tokens):
        raise VtCoreError("implementation_binding_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4A-04f" not in plan_text:
        raise VtCoreError("plan_row_missing")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": document["status"],
        "vt_table_core": "specified",
        "profile_accepted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        result = verify_document(load_yaml(arguments.core))
    except (OSError, ValueError, yaml.YAMLError, VtCoreError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
