"""Verify the current owner-decision reconciliation and owner request.

The v1 owner request is historical and immutable.  This gate binds the
additive v2 decision record to the current ledger/PLAN state and requires the
current request to contain only the five external asset/oracle blockers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
RECONCILIATION = ROOT / "docs/baselines/owner-decision-reconciliation.v2.yaml"
CURRENT_REQUEST = ROOT / "docs/baselines/owner-input-request.v2.yaml"
LEDGER = ROOT / "docs/baselines/plan-remaining-items-ledger.v1.yaml"
PLAN = ROOT / "PLAN.md"
HISTORICAL_REQUEST = ROOT / "docs/baselines/owner-input-request.v1.yaml"
HISTORICAL_CHECKLIST = ROOT / "docs/baselines/owner-decision-checklist.v1.md"

SCHEMA = "sipi.owner-decision-reconciliation.v2"
CURRENT_REQUEST_SCHEMA = "sipi.owner-input-request.v2"
SEMANTICS = "semantics_not_implemented"
SCOPED_RESOLVED = "resolved_scoped"
EXTERNAL = "external_asset_oracle"
OWNER_IDS = ("P3B-02", "P3B-04", "P3B-05", "P3C-01", "P4A-01")
EXTERNAL_IDS = ("P1-04B", "P4B-08", "P4B-09", "P5-02", "P5-06")
CURRENT_REQUEST_PURPOSE = (
    "Current owner-input request after the five recorded semantic decisions were reconciled. "
    "Resolved owner-decision rows are not repeated here; only external asset/oracle blockers remain."
)
CURRENT_REQUEST_DECISION_POINTS = {
    "P1-04B": "provide exact selected profile, custody, rights, and distribution facts for the trusted external fixtures; comparison permission is already recorded",
    "P4B-08": "provide AMI rights, exact parameter compatibility, dynamic dependency closure, isolated vendor worker, and fresh-runtime evidence; S4P topology/port mapping is already observed",
    "P4B-09": "provide an authorized profile and fresh isolated runtime evidence for sipi ami run; silent fallback is prohibited",
    "P5-02": "provide the canonical R480 parameter JSON and authoritative MATLAB/agent-com oracle material, including the remaining warning and default-layout evidence",
    "P5-06": "provide current MATLAB oracle output and compare-matrix evidence for the required COM example, including full metric/checkpoint alignment",
}
CURRENT_REQUEST_NON_CLAIMS = {
    "no_owner_decision_items_remain_in_the_current_request",
    "external_asset_oracle_authorization_is_not_product_implementation_acceptance",
    "current_request_does_not_rewrite_owner_input_request_v1",
}
CURRENT_REQUEST_GATES = {
    "P1-04B": [
        "tools/verify_p1_04b_legacy_fixture_boundary.py",
        "tools/verify_p1_legacy_fixture_required_profile_facts.py",
        "tools/verify_p1_04b_comparison_permission_reconciliation.py",
    ],
    "P4B-08": [
        "tools/verify_p4b_ads_pcie_gen5_dual_ami_asset_preflight.py",
        "tools/verify_p4b_ads_pcie_gen5_dual_ami_runtime_preflight.py",
        "tools/verify_p4b_08_s4p_observation.py",
        "tools/verify_p4b_08b_s4p_ami_matrix_preflight.py",
        "tools/verify_p4b_08c_ads_netlist_topology_semantic_response.py",
    ],
    "P4B-09": [
        "tools/verify_p4b_ads_pcie_gen5_dual_ami_asset_preflight.py",
        "tools/verify_p4b_ads_pcie_gen5_dual_ami_runtime_preflight.py",
    ],
    "P5-02": [
        "tools/verify_com_r480_acceptance.py",
        "tools/verify_p5_02e_canonical_parameter_reference.py",
        "tools/verify_p5_02f_parameter_json_draft.py",
        "tools/verify_p5_02g_canonical_json.py",
        "tools/verify_p5_02h_canonical_json_v2.py",
        "tools/verify_p5_02i_warning_observation.py",
        "tools/verify_p5_02j_value_consumption.py",
        "tools/verify_p5_02k_matlab_literal.py",
        "tools/verify_p5_02l_resolve_parameters.py",
        "tools/verify_p5_02m_warning_detector.py",
        "tools/verify_p5_02n_warning_report.py",
        "tools/verify_p5_02o_source_observed_mlse_warning_vocabulary_subset.py",
    ],
    "P5-06": [
        "tools/verify_release_capability_publication.py",
        "tools/verify_p5_06a_matlab_oracle_first_run.py",
        "tools/verify_p5_06b_oracle_metric_surface.py",
        "tools/verify_p5_06c_normalized_input_surface.py",
        "tools/verify_p5_06d_canonical_input_keys.py",
        "tools/verify_p5_06e_oracle_metric_reference.py",
        "tools/verify_p5_06f_com_chain_core.py",
        "tools/verify_p5_06g_oracle_chain_compare.py",
        "tools/verify_p5_r480_reference_custody_preflight.py",
        "tools/verify_p5_06_pinned_source_external_oracle_candidate_document.py",
    ],
}
CURRENT_LEDGER_IDS = {
    "P1-04B", "P2-06", "P3B-02", "P3C-02", "P3C-03", "P4A-01", "P4A-02", "P4A-03",
    "P4B-02", "P4B-08", "P4B-09", "P5-02", "P5-05", "P5-06", "P5-08", "P5-09",
    "P7-01", "P7-02", "P7-03", "P7-04", "P7-05", "P7-06", "P7-07", "P7-08", "P7-09",
}
RECONCILED_SEMANTICS_GATES = {
    "P3B-02": [
        "tools/verify_p3b_02_link_kernel_singleton.py",
        "tools/verify_p3_original_project_eye_jitter_semantics_observation.py",
        "tools/verify_owner_decision_reconciliation_v2.py",
    ],
    "P4A-01": [
        "tools/verify_p4a_ibis_example_rx_candidate_inventory.py",
        "tools/verify_p4a_01_required_profile_inventory.py",
        "tools/verify_owner_decision_reconciliation_v2.py",
    ],
}
HISTORICAL_REQUEST_SHA256 = "a38f3688b343ed83c1c79c3c32cf5f459c1ab99fbc7fef7f1cdc825fe792c677"
HISTORICAL_CHECKLIST_SHA256 = "9496cb5242a702903ee44ea7ad1d55dddbdda5153588aba6a83c37916df986c1"


class ReconciliationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReconciliationError(f"document_not_mapping:{path.name}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ReconciliationError(reason)


def _expected_recommendations() -> dict[str, dict[str, Any]]:
    return {
        "P3B-02": {
            "receiver_chain": ["RX CTLE", "RX FFE"],
            "stage_order": "RX CTLE->RX FFE",
            "stage_selection": "explicit_optional_per_simulation",
            "bypass": "explicit_per_stage",
            "auto_tuning": "prohibited",
            "silent_default": "prohibited",
            "v1_boundary": "bypass_only_unchanged",
            "future_extension": "additive_profile_only",
        },
        "P3B-04": {
            "current_public_profile": {
                "cdr": "none",
                "lock": "not_applicable",
                "reset": "not_applicable",
                "cancel": "not_applicable",
            },
            "ami_internal_cdr": "future_authenticated_route_only",
            "cdr_04b_core": "existing_core_not_clock_source",
        },
        "P3B-05": {
            "stimulus": "PRBS9",
            "seed_literal": "0x001",
            "seed_integer": 1,
            "injection_position": "TX",
            "time_warp": "caller_supplied_sample_unit",
            "shift_formula": "p=n+shift[n]",
            "interpolation": "linear",
            "random_number_generator": "prohibited",
            "amplitude_noise": "prohibited",
            "library_determinism": True,
            "external_tolerance_claim": False,
        },
        "P3C-01": {
            "profile": "selected_highloss_exact",
            "receiver": "none",
            "scope": "waveform_only",
            "included_observables": ["waveform"],
            "excluded_observables": ["eye", "TIE", "bathtub"],
            "closed_eye_fallback": "prohibited",
            "q_factor": "generic_or_future_receiver_capability_only",
            "db_tolerance_0_1": "generic_or_future_receiver_capability_only",
        },
        "P4A-01": {
            "ibis_version": 5.0,
            "file_path": "fixtures/ibis/as4c512m16md4v-053bin.ibs",
            "structural_inventory": "observed_structural_inventory_only",
            "inventory_ref": "docs/baselines/p4a-01-required-profile-inventory.v1.yaml",
            "inventory_exhaustiveness": "not_claimed",
            "model_selector": "not_selected",
            "corner": "not_selected",
            "behavior_selection": "delegated_to_P4A-02_and_P4A-03",
            "structural_inventory_is_not_behavior_selection": True,
            "guessing": "prohibited",
        },
    }


def _expected_non_claims() -> dict[str, set[str]]:
    return {
        "P3B-02": {
            "does_not_widen_owner_input_request_v1",
            "does_not_enable_automatic_tuning",
            "does_not_select_a_silent_default_stage",
            "does_not_claim_ctle_or_ffe_runtime_implementation",
        },
        "P3B-04": {
            "public_cdr_none_is_not_ami_internal_cdr_support",
            "cdr_04b_core_is_not_a_clock_source",
            "cdr_04b_core_is_not_public_profile_selection",
            "no_public_lock_reset_cancel_semantics_are_claimed",
        },
        "P3B-05": {
            "does_not_add_rng",
            "does_not_add_amplitude_noise",
            "does_not_make_an_external_tolerance_claim",
            "does_not_promote_receiver_or_jitter_acceptance",
        },
        "P3C-01": {
            "does_not_generalize_to_arbitrary_closed_eye_inputs",
            "does_not_claim_eye_observation",
            "does_not_claim_tie_observation",
            "does_not_claim_bathtub_or_ber_observation",
        },
        "P4A-01": {
            "does_not_guess_model_or_corner",
            "does_not_select_ibis_behavior",
            "does_not_promote_a_product_ibis_parser",
            "does_not_promote_p4a_02_or_p4a_03",
        },
    }


def _ledger_rows(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    _require(ledger.get("schema") == "sipi.plan-remaining-items.ledger.v1", "ledger_schema_invalid")
    _require(ledger.get("status") == "provisional", "ledger_status_invalid")
    rows = ledger.get("items")
    _require(isinstance(rows, list), "ledger_items_invalid")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        _require(isinstance(row, dict) and isinstance(row.get("id"), str), "ledger_row_invalid")
        _require(row["id"] not in result, f"ledger_duplicate:{row['id']}")
        result[row["id"]] = row
    _require(ledger.get("total_open") == len(result), "ledger_total_open_invalid")
    return result


def _require_plan_item_state(plan_text: str, item_id: str, *, checked: bool) -> None:
    pattern = rf"(?m)^- \[(?P<marker>[ xX])\] \*\*{re.escape(item_id)}\*\*"
    matches = list(re.finditer(pattern, plan_text))
    expected = "x" if checked else " "
    _require(
        len(matches) == 1 and matches[0].group("marker").lower() == expected,
        f"plan_item_state_invalid:{item_id}",
    )


def _validate_historical_inputs() -> None:
    _require(HISTORICAL_REQUEST.is_file(), "historical_request_missing")
    _require(HISTORICAL_CHECKLIST.is_file(), "historical_checklist_missing")
    _require(_sha256(HISTORICAL_REQUEST) == HISTORICAL_REQUEST_SHA256, "historical_request_changed")
    _require(_sha256(HISTORICAL_CHECKLIST) == HISTORICAL_CHECKLIST_SHA256, "historical_checklist_changed")


def validate_current_request(
    request: dict[str, Any] | None = None,
    *,
    ledger: dict[str, Any] | None = None,
    reconciliation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = _load(CURRENT_REQUEST) if request is None else request
    _require(set(request) == {
        "schema", "status", "purpose", "reconciliation_ref", "historical_v1_unchanged", "entries", "non_claims"
    }, "current_request_shape_invalid")
    _require(request.get("schema") == CURRENT_REQUEST_SCHEMA, "current_request_schema_invalid")
    _require(request.get("status") == "awaiting_external_asset_oracle", "current_request_status_invalid")
    _require(request.get("reconciliation_ref") == "docs/baselines/owner-decision-reconciliation.v2.yaml", "current_request_reconciliation_ref_invalid")
    _require(request.get("historical_v1_unchanged") is True, "current_request_history_flag_invalid")
    _require(request.get("purpose") == CURRENT_REQUEST_PURPOSE, "current_request_purpose_invalid")
    non_claims = request.get("non_claims")
    _require(
        isinstance(non_claims, list)
        and len(non_claims) == len(CURRENT_REQUEST_NON_CLAIMS)
        and set(non_claims) == CURRENT_REQUEST_NON_CLAIMS,
        "current_request_non_claims_invalid",
    )
    entries = request.get("entries")
    _require(isinstance(entries, list) and len(entries) == len(EXTERNAL_IDS), "current_request_entries_invalid")
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        _require(isinstance(entry, dict), "current_request_entry_invalid")
        _require(set(entry) == {"id", "kind", "blocker", "decision_point", "gate"}, "current_request_entry_shape_invalid")
        entry_id = entry.get("id")
        _require(isinstance(entry_id, str) and entry_id in EXTERNAL_IDS, f"current_request_entry_unknown:{entry_id}")
        _require(entry_id not in by_id, f"current_request_entry_duplicate:{entry_id}")
        _require(entry.get("kind") == EXTERNAL and entry.get("blocker") == EXTERNAL, f"current_request_entry_kind_invalid:{entry_id}")
        _require(
            entry.get("decision_point") == CURRENT_REQUEST_DECISION_POINTS[entry_id],
            f"current_request_decision_invalid:{entry_id}",
        )
        gates = entry.get("gate")
        _require(isinstance(gates, list) and gates and all(isinstance(gate, str) for gate in gates), f"current_request_gates_invalid:{entry_id}")
        _require(gates == CURRENT_REQUEST_GATES[entry_id], f"current_request_gate_policy_drift:{entry_id}")
        _require(all((ROOT / gate).is_file() for gate in gates), f"current_request_gate_missing:{entry_id}")
        by_id[entry_id] = entry
    _require(set(by_id) == set(EXTERNAL_IDS), "current_request_entry_set_invalid")

    ledger = _load(LEDGER) if ledger is None else ledger
    rows = _ledger_rows(ledger)
    _require({row_id for row_id, row in rows.items() if row.get("blocker") == EXTERNAL} == set(EXTERNAL_IDS), "current_external_blocker_set_invalid")
    _require(not any(row.get("blocker") == "owner_decision" for row in rows.values()), "resolved_owner_blocker_remains")
    for entry_id, entry in by_id.items():
        expected = rows[entry_id].get("gate")
        _require(entry["gate"] == expected, f"current_request_gate_drift:{entry_id}")
        _require(expected == CURRENT_REQUEST_GATES[entry_id], f"ledger_external_gate_policy_drift:{entry_id}")
    _require(not any(entry.get("id") in OWNER_IDS for entry in entries), "resolved_owner_in_current_request")
    if reconciliation is not None:
        _require(request["reconciliation_ref"] == "docs/baselines/owner-decision-reconciliation.v2.yaml", "request_reconciliation_mismatch")
    return {"valid": True, "entries": len(entries), "external_asset_oracle": len(entries), "owner_decision": 0}


def validate(
    document: dict[str, Any] | None = None,
    *,
    current_request: dict[str, Any] | None = None,
    ledger: dict[str, Any] | None = None,
    plan_text: str | None = None,
) -> dict[str, Any]:
    _validate_historical_inputs()
    document = _load(RECONCILIATION) if document is None else document
    _require(set(document) == {
        "schema", "status", "authority", "scope", "decisions", "non_claims", "ledger_ref", "current_request_ref", "audit_ref"
    }, "reconciliation_shape_invalid")
    _require(document.get("schema") == SCHEMA, "reconciliation_schema_invalid")
    _require(document.get("status") == "current_owner_decisions_reconciled_semantics_pending", "reconciliation_status_invalid")
    authority = document.get("authority")
    _require(isinstance(authority, dict), "authority_invalid")
    _require(authority.get("actor") == "user" and authority.get("decision_label") == "A", "authority_decision_invalid")
    _require(authority.get("recorded_at") == "2026-08-21", "authority_date_invalid")
    _require(set(authority) == {"actor", "recorded_at", "decision_label", "source"}, "authority_shape_invalid")
    source = authority.get("source")
    _require(isinstance(source, dict) and set(source) == {"owner_input_request_v1", "owner_decision_checklist_v1"}, "authority_source_invalid")
    for key, path, digest in (
        ("owner_input_request_v1", "docs/baselines/owner-input-request.v1.yaml", HISTORICAL_REQUEST_SHA256),
        ("owner_decision_checklist_v1", "docs/baselines/owner-decision-checklist.v1.md", HISTORICAL_CHECKLIST_SHA256),
    ):
        ref = source.get(key)
        _require(ref == {"path": path, "sha256": digest, "immutable": True}, f"authority_source_binding_invalid:{key}")
    scope = document.get("scope")
    _require(scope == {
        "current_request_contains_only_external_asset_oracle_blockers": True,
        "product_rust_semantics_changed": False,
        "historical_v1_documents_changed": False,
    }, "scope_promotion_or_drift")

    decisions = document.get("decisions")
    _require(isinstance(decisions, list) and len(decisions) == len(OWNER_IDS), "decisions_invalid")
    expected_recommendations = _expected_recommendations()
    expected_non_claims = _expected_non_claims()
    by_id: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        _require(isinstance(decision, dict), "decision_invalid")
        _require(set(decision) == {"id", "answer", "blocker_before", "blocker_after", "current_request", "recommendation", "non_claims"}, "decision_shape_invalid")
        decision_id = decision.get("id")
        _require(isinstance(decision_id, str) and decision_id in OWNER_IDS, f"decision_unknown:{decision_id}")
        _require(decision_id not in by_id, f"decision_duplicate:{decision_id}")
        _require(decision.get("answer") == "A", f"decision_answer_invalid:{decision_id}")
        _require(decision.get("blocker_before") == "owner_decision", f"decision_before_invalid:{decision_id}")
        expected_after = SEMANTICS if decision_id in {"P3B-02", "P4A-01"} else SCOPED_RESOLVED
        _require(decision.get("blocker_after") == expected_after, f"decision_after_invalid:{decision_id}")
        _require(decision.get("current_request") is False, f"decision_request_flag_invalid:{decision_id}")
        _require(decision.get("recommendation") == expected_recommendations[decision_id], f"decision_recommendation_invalid:{decision_id}")
        _require(set(decision.get("non_claims", [])) == expected_non_claims[decision_id], f"decision_non_claims_invalid:{decision_id}")
        by_id[decision_id] = decision
    _require(set(by_id) == set(OWNER_IDS), "decision_set_invalid")
    _require(set(document.get("non_claims", [])) == {
        "reconciled_owner_decisions_are_not_product_implementation_acceptance",
        "semantics_not_implemented_rows_remain_open",
        "external_asset_oracle_rows_remain_open",
        "historical_v1_documents_are_not_rewritten",
        "no_release_or_license_promotion",
    }, "reconciliation_non_claims_invalid")
    _require(document.get("ledger_ref") == "docs/baselines/plan-remaining-items-ledger.v1.yaml", "ledger_ref_invalid")
    _require(document.get("current_request_ref") == "docs/baselines/owner-input-request.v2.yaml", "current_request_ref_invalid")
    audit_ref = document.get("audit_ref")
    _require(audit_ref == "docs/baselines/audits/2026-08-21-owner-input-current-reconciliation-v2.md" and (ROOT / audit_ref).is_file(), "audit_ref_invalid")

    ledger = _load(LEDGER) if ledger is None else ledger
    rows = _ledger_rows(ledger)
    _require(set(rows) == CURRENT_LEDGER_IDS, "ledger_item_set_invalid")
    for item_id in ("P3B-02", "P4A-01"):
        row = rows.get(item_id)
        _require(row is not None and row.get("blocker") == SEMANTICS, f"ledger_reclassified_state_invalid:{item_id}")
        _require(row.get("gate") == RECONCILED_SEMANTICS_GATES[item_id], f"reconciliation_gate_policy_drift:{item_id}")
    for item_id in ("P3B-04", "P3B-05", "P3C-01"):
        _require(item_id not in rows, f"scoped_resolved_item_remains_open:{item_id}")
    _require(not any(row.get("blocker") == "owner_decision" for row in rows.values()), "ledger_owner_decision_class_remains")
    current_request = _load(CURRENT_REQUEST) if current_request is None else current_request
    validate_current_request(current_request, ledger=ledger, reconciliation=document)
    plan_text = PLAN.read_text(encoding="utf-8") if plan_text is None else plan_text
    marker = "Current owner-input reconciliation v2"
    _require(marker in plan_text, "plan_reconciliation_marker_missing")
    for item_id in OWNER_IDS:
        _require(f"{item_id}: owner decision A reconciled" in plan_text, f"plan_decision_marker_missing:{item_id}")
    for item_id in ("P3B-02", "P4A-01"):
        _require_plan_item_state(plan_text, item_id, checked=False)
    for item_id in ("P3B-04", "P3B-05", "P3C-01"):
        _require_plan_item_state(plan_text, item_id, checked=True)
    return {
        "schema": SCHEMA,
        "valid": True,
        "reconciled_owner_decisions": len(OWNER_IDS),
        "current_external_asset_oracle_blockers": len(EXTERNAL_IDS),
        "remaining_semantics_items": sum(row.get("blocker") == SEMANTICS for row in rows.values()),
    }


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        print(json.dumps(validate(), sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ReconciliationError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
