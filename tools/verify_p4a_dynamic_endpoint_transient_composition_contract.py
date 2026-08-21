"""Fail-closed verifier for the P4A dynamic endpoint composition contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4a-dynamic-endpoint-transient-composition-contract.v1"
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "p4a-dynamic-endpoint-transient-composition-contract.v1.yaml"


class ContractError(RuntimeError):
    pass


def _exact_keys(value: object, keys: set[str], reason: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ContractError(reason)


def _exact(value: object, expected: object, reason: str) -> None:
    if value != expected:
        raise ContractError(reason)


REQUIRED_BLOCKERS = {
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
}

PREDECESSOR_KEYS = {
    "endpoint_semantics",
    "endpoint_baseline",
    "ibis_static_profile",
    "ibis_static_acceptance",
    "ibis_quasi_static",
    "p2_transient_semantics",
    "p2_acceptance",
    "p2_one_node_rc",
    "p2_one_node_pwl",
    "p2_semantic_freeze",
}


def validate_contract(document: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    _exact_keys(
        document,
        {
            "schema",
            "status",
            "promotion_eligible",
            "t12_admission",
            "profile",
            "predecessor_contracts",
            "reference_node",
            "supply",
            "initial_state",
            "integration_timebase_output",
            "channel_return_stimulus",
            "ibis_constitutive_semantics",
            "units",
            "bounds",
            "tolerance",
            "failure_behavior",
            "non_claims",
        },
        "contract_shape_invalid",
    )
    _exact(document["schema"], SCHEMA, "contract_schema_invalid")
    _exact(document["status"], "specified_blocked_dynamic_semantics_pending", "contract_status_invalid")
    _exact(document["promotion_eligible"], False, "contract_promotion_invalid")

    _exact_keys(document["t12_admission"], {"state", "admission", "rule", "blockers"}, "t12_shape_invalid")
    admission = document["t12_admission"]
    if admission.get("state") != "blocked" or admission.get("admission") is not False or admission.get("rule") != "all_required_dynamic_fields_confirmed_and_evidenced":
        raise ContractError("t12_admission_invalid")
    blockers = admission.get("blockers")
    if (
        not isinstance(blockers, list)
        or not all(isinstance(blocker, str) for blocker in blockers)
        or set(blockers) != REQUIRED_BLOCKERS
        or len(blockers) != len(REQUIRED_BLOCKERS)
    ):
        raise ContractError("t12_admission_invalid")

    _exact(
        document["profile"],
        {
            "id": "p4a-ibis-input-typ-plus-selected-differential-rc-transient-v1",
            "state": "candidate_contract_only",
            "required": False,
            "ibis_input_profile": "ibis-org-sample1-input-typ-static-v2",
            "electrical_load_profile": "rx-electrical-load-diff100-cload1pf-per-leg-v1",
        },
        "profile_invalid",
    )

    predecessors = document["predecessor_contracts"]
    _exact_keys(predecessors, PREDECESSOR_KEYS, "predecessor_shape_invalid")
    for relative in predecessors.values():
        if not isinstance(relative, str) or not (root / relative).is_file():
            raise ContractError("predecessor_missing")

    _exact(
        document["reference_node"],
        {
            "status": "endpoint_role_confirmed_binding_pending",
            "endpoint_role": "ref",
            "ibis_signal_role": "sig",
            "electrical_load_roles": ["p", "n", "ref"],
            "channel_return_binding": "pending_owner_decision",
            "ibis_to_load_terminal_map": "pending_owner_decision",
            "implicit_global_ground": "forbidden",
            "implicit_node_zero": "forbidden",
            "inferred_reference_from_waveform": "forbidden",
        },
        "reference_node_invalid",
    )
    _exact(
        document["supply"],
        {
            "status": "blocked_not_defined",
            "source": "pending_owner_decision",
            "power_clamp_binding": "explicit_independent_drive_only_until_supply_is_selected",
            "pvt_or_corner_inference": "forbidden",
            "signal_or_reference_inference": "forbidden",
            "implicit_default": "forbidden",
        },
        "supply_invalid",
    )
    _exact(
        document["initial_state"],
        {
            "status": "blocked_owner_decision",
            "retained_state_surface": "pending_owner_decision",
            "initialization_mode": "pending_owner_decision",
            "operating_point": "unsupported_not_selected",
            "uic_like_mode": "unsupported_not_selected",
            "implicit_initialization": "forbidden",
            "inherit_p2_zero_initial_output": "forbidden",
        },
        "initial_state_invalid",
    )
    _exact(
        document["integration_timebase_output"],
        {
            "status": "blocked_owner_decision",
            "integration_method": "pending_owner_decision",
            "internal_stepping": "pending_owner_decision",
            "timebase": "pending_owner_decision",
            "output_grid": "pending_owner_decision",
            "output_alignment": "pending_owner_decision",
            "p2_reference_only": {
                "method": "backward_euler_f64",
                "stepping": "fixed_breakpoint_union",
                "output_sampling": "requested_axis_only",
                "adopted_by_p4a_composition": False,
            },
        },
        "integration_timebase_output_invalid",
    )
    _exact(
        document["channel_return_stimulus"],
        {
            "status": "blocked_owner_decision",
            "return_binding": "pending_owner_decision",
            "stimulus_binding": "pending_owner_decision",
            "stimulus_kind": "pending_owner_decision",
            "waveform_owner": "pending_owner_decision",
            "derivative_source": "pending_owner_decision",
            "implicit_channel_or_stimulus": "forbidden",
            "slope_inference_from_unaligned_samples": "forbidden",
        },
        "channel_return_stimulus_invalid",
    )
    _exact(
        document["ibis_constitutive_semantics"],
        {
            "status": "constitutive_core_confirmed_dynamic_coupling_pending",
            "model_scope": "input_typ_typical_only",
            "clamp": {
                "drives": "explicit_independent_ground_and_power_voltages",
                "interpolation": "linear_within_table_domain",
                "out_of_domain": "reject",
                "extrapolation": "forbidden",
                "current_sign": "positive_into_sig_shunt",
                "total": "ground_plus_power",
            },
            "c_comp": {
                "units": "farads",
                "domain": "finite_nonnegative",
                "relation": "C_comp_times_d_dt_V_SIG_minus_V_REF",
                "current_sign": "positive_into_sig_shunt",
                "zero_slope_contribution": "zero",
                "slope_input": "explicit_continuous_derivative",
                "dynamic_state_and_initialization": "pending_owner_decision",
            },
            "composition_current": {
                "algebraic_sum": "ground_plus_power_plus_c_comp",
                "hidden_supply_or_pvt_term": "forbidden",
            },
        },
        "ibis_constitutive_semantics_invalid",
    )
    _exact(
        document["units"],
        {
            "status": "confirmed_existing_typed_contracts",
            "voltage": "V",
            "current": "A",
            "resistance": "ohm",
            "capacitance": "F",
            "time": "s",
            "voltage_derivative": "V_per_s",
            "selected_one_pf_canonical_value": 1.0e-12,
            "implicit_unit_inference": "forbidden",
        },
        "units_invalid",
    )
    _exact(
        document["bounds"],
        {
            "status": "invariants_confirmed_numeric_caps_pending",
            "invariants": [
                "finite_inputs_and_derived_values",
                "positive_resistance_and_rc_capacitance",
                "nonnegative_finite_c_comp",
                "strictly_ordered_explicit_axes_when_an_axis_is_selected",
                "no_partial_output_on_rejection",
                "no_table_extrapolation",
            ],
            "numeric_caps": {
                "output_samples": "pending_owner_decision",
                "stimulus_points": "pending_owner_decision",
                "ibis_table_knots": "pending_owner_decision",
                "integration_breakpoints": "pending_owner_decision",
                "work_units": "pending_owner_decision",
            },
            "predecessor_limits_not_adopted": {
                "p2_max_output_samples": 4096,
                "p2_max_integration_breakpoints": 16384,
                "ibis_batch_max_probes": 1024,
            },
        },
        "bounds_invalid",
    )
    _exact(
        document["tolerance"],
        {
            "status": "blocked_owner_decision",
            "time_axis": "pending_owner_decision",
            "output_grid_alignment": "pending_owner_decision",
            "voltage_waveform": "pending_owner_decision",
            "current_waveform": "pending_owner_decision",
            "state_or_trace": "pending_owner_decision",
            "comparison_rule": "pending_owner_decision",
            "external_oracle_or_parity": "prohibited",
            "predecessor_tolerances_not_adopted": {
                "p4a_static_dc_absolute_current_a": 1.0e-12,
                "p4a_static_dc_relative_current": 1.0e-09,
                "p2_time_absolute_s": 1.0e-15,
                "p2_voltage_out_absolute_v": 2.0e-06,
            },
        },
        "tolerance_invalid",
    )
    _exact(
        document["failure_behavior"],
        {
            "status": "confirmed_fail_closed_boundary",
            "missing_or_pending_required_field": "reject_admission",
            "nonfinite_input_or_derived_value": "reject_without_partial_output",
            "out_of_domain_table_drive": "reject_without_extrapolation",
            "overflow_or_invalid_state": "reject_without_partial_output",
            "unknown_or_implicit_binding": "reject",
            "quasi_static_or_batch_as_transient_evidence": "forbidden",
            "general_netlist_or_spice_fallback": "forbidden",
            "external_engine_or_parity_fallback": "forbidden",
            "accepted_result_while_t12_blocked": "forbidden",
        },
        "failure_behavior_invalid",
    )
    if document["non_claims"] != [
        "This is a semantic admission boundary, not a Rust solver or public API.",
        "Quasi-static and quasi-static-batch routes remain memoryless and are not transient evidence.",
        "No general netlist/SPICE, AMI runtime, channel resolver, external parity, or release claim is made.",
    ]:
        raise ContractError("non_claims_invalid")

    return {
        "schema": SCHEMA,
        "status": document["status"],
        "t12_admission": False,
        "promotion_eligible": False,
        "confirmed_fields": ["reference_node.endpoint_role", "ibis_constitutive_semantics", "units", "failure_behavior"],
        "blocked_fields": [
            "reference_node.channel_return_binding",
            "supply",
            "initial_state",
            "integration_timebase_output",
            "channel_return_stimulus",
            "bounds.numeric_caps",
            "tolerance",
        ],
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
    except (OSError, UnicodeError, yaml.YAMLError, ContractError, TypeError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error), "t12_admission": False}
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if args.report:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report.get("status") == "specified_blocked_dynamic_semantics_pending" else 2


if __name__ == "__main__":
    raise SystemExit(main())
