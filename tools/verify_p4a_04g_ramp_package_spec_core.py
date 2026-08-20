"""Fail closed on the P4A-04g typed Ramp/Package declaration core.

The charter fixes the declaration-only semantics: finite strictly positive
typed fields for [Ramp] and [Package] sections, no waveform construction,
no initial-slope model, no terminal network solve, no decoder, no profile
acceptance. The verifier cross-binds the charter against the sipi-ibis
implementation source and the PLAN P4A-04g row.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs" / "baselines" / "p4a-04g-ramp-package-spec-core.v1.yaml"
SOURCE = ROOT / "crates" / "sipi-ibis" / "src" / "ramp_package_spec_v1.rs"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p4a-04g.ramp-package-spec-core.v1"
POLICY = "sipi.p4a-04g.ramp-package-spec-v1.declaration-only"


class RampPackageError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RampPackageError("document_not_mapping")
    return value


def verify_document(document: object) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise RampPackageError("schema_invalid")
    if document.get("status") != "product_owned_ramp_package_declaration_core_specified_no_profile_acceptance":
        raise RampPackageError("status_invalid")
    if document.get("slice") != { "vt": "delivered_by_p4a_04f", "ramp": "this_slice", "package": "this_slice", "decoder": "not_in_this_slice", "network_solve": "not_in_this_slice", "cli": "not_in_this_slice" }:
        raise RampPackageError("slice_scope_drift")
    if document.get("validation_rules") != {
        "ramp": { "d_v_dt_r": "finite_strictly_positive", "d_v_dt_f": "finite_strictly_positive", "r_load": "finite_strictly_positive" },
        "package": { "r_pin": "finite_strictly_positive", "l_pin": "finite_strictly_positive", "c_pin": "finite_strictly_positive" },
    }:
        raise RampPackageError("validation_rules_drift")
    if document.get("units") != { "d_v_dt": "volts_per_second", "r": "ohms", "l": "henries", "c": "farads" }:
        raise RampPackageError("units_drift")
    if document.get("scope_policy") != POLICY:
        raise RampPackageError("scope_policy_drift")
    if document.get("implementation") != { "crate": "sipi-ibis", "module": "ramp_package_spec_v1", "types": ["RampSpecV1", "RampSpecErrorV1", "PackageSpecV1", "PackageSpecErrorV1"] }:
        raise RampPackageError("implementation_drift")
    if document.get("admission") != { "profile_accepted": False, "ibis_text_decoded": False, "electrical_evaluation": False, "network_solve": False, "cli_route": False, "external_reference_binding": "not_evaluated" }:
        raise RampPackageError("admission_drift")
    claims = document.get("non_claims")
    expected_claims = ["not_waveform_construction", "not_initial_slope_model", "not_terminal_network_solve", "not_ibis_text_decoding", "not_profile_acceptance"]
    if not isinstance(claims, list) or claims != expected_claims:
        raise RampPackageError("non_claims_drift")
    source = SOURCE.read_text(encoding="utf-8")
    required_tokens = (
        "pub struct RampSpecV1",
        "pub enum RampSpecErrorV1",
        "NonPositiveSlopeRise",
        "NonPositiveSlopeFall",
        "NonPositiveLoad",
        "pub struct PackageSpecV1",
        "pub enum PackageSpecErrorV1",
        "NonPositiveResistance",
        "NonPositiveInductance",
        "NonPositiveCapacitance",
        "pub const RAMP_PACKAGE_SCOPE_POLICY_V1",
        POLICY,
    )
    if any(token not in source for token in required_tokens):
        raise RampPackageError("implementation_binding_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P4A-04g" not in plan_text:
        raise RampPackageError("plan_row_missing")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": document["status"],
        "ramp_package_declaration_core": "specified",
        "profile_accepted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, default=DEFAULT)
    arguments = parser.parse_args(argv)
    try:
        result = verify_document(load_yaml(arguments.core))
    except (OSError, ValueError, yaml.YAMLError, RampPackageError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
