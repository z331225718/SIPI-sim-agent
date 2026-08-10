"""Verify the selected-but-unsolved P4A electrical endpoint contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4a-electrical-endpoint-semantic-contract.v1"
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "p4a-electrical-endpoint-semantic-contract.v1.yaml"


class ContractError(RuntimeError):
    pass


def _exact_keys(value: dict[str, Any], keys: set[str], reason: str) -> None:
    if set(value) != keys:
        raise ContractError(reason)


def validate_contract(document: dict[str, Any]) -> dict[str, Any]:
    _exact_keys(document, {"schema", "status", "promotion_eligible", "profile", "terminals", "components", "conventions", "acceptance_status", "future_capabilities", "non_claims"}, "contract_shape_invalid")
    if document["schema"] != SCHEMA or document["status"] != "selected_pending_reference_and_acceptance_policy" or document["promotion_eligible"] is not False:
        raise ContractError("contract_status_invalid")
    if document["profile"] != {"id": "rx-electrical-load-diff100-cload1pf-per-leg-v1", "selected_by": "user-confirmed-2026-08-10-per-leg-c-load", "required": False, "runtime_status": "not_supported"}:
        raise ContractError("profile_invalid")
    terminals = document["terminals"]
    if terminals != [{"id": "p", "role": "differential_positive"}, {"id": "n", "role": "differential_negative"}, {"id": "ref", "role": "endpoint_reference_terminal"}]:
        raise ContractError("terminals_invalid")
    expected_components = [
        {"id": "r_diff", "kind": "resistor", "value_ohm": 100.0, "endpoints": ["p", "n"], "passive_current_direction": "p_to_n"},
        {"id": "c_p_ref", "kind": "capacitor", "value_pf": 1.0, "endpoints": ["p", "ref"], "passive_current_direction": "into_p"},
        {"id": "c_n_ref", "kind": "capacitor", "value_pf": 1.0, "endpoints": ["n", "ref"], "passive_current_direction": "into_n"},
    ]
    if document["components"] != expected_components:
        raise ContractError("components_invalid")
    expected_conventions = {
        "differential_voltage": "V_p_minus_V_n",
        "reference_default": "forbidden",
        "global_ground_or_node_zero_default": "forbidden",
        "total_differential_equivalent_substitution": "forbidden",
        "solver_semantics": "not_defined",
    }
    if document["conventions"] != expected_conventions:
        raise ContractError("conventions_invalid")
    acceptance = document["acceptance_status"]
    if acceptance != {"state": "blocked", "blockers": ["explicit_ref_to_channel_return_binding", "stimulus_timebase_and_initial_state", "observable_alignment_and_tolerance", "external_or_product_owned_acceptance_evidence"]}:
        raise ContractError("acceptance_status_invalid")
    futures = document["future_capabilities"]
    if futures != [
        {"id": "c_across_pair", "terminals": ["p", "n"], "status": "planned_not_supported", "non_equivalence": "not_inferred_from_per_leg_capacitors"},
        {"id": "single_ended_channel", "terminals": ["sig", "ref"], "status": "planned_not_supported", "non_equivalence": "not_inferred_by_removing_n_from_differential_profile"},
    ]:
        raise ContractError("future_capabilities_invalid")
    if not isinstance(document["non_claims"], list) or len(document["non_claims"]) != 3:
        raise ContractError("non_claims_invalid")
    return {
        "schema": SCHEMA,
        "status": "selected_pending_reference_and_acceptance_policy",
        "profile_id": document["profile"]["id"],
        "required": False,
        "runtime_status": "not_supported",
        "reference_terminal": "ref",
        "promotion_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        document = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ContractError("manifest_invalid")
        report = validate_contract(document)
    except (OSError, yaml.YAMLError, ContractError, KeyError, TypeError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if args.report:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["status"] == "selected_pending_reference_and_acceptance_policy" else 2


if __name__ == "__main__":
    raise SystemExit(main())
