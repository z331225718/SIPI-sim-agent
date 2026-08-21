"""Verify the fail-closed P3C-02 current semantics boundary record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-02-current-semantics-gap.v1.yaml"
AUDIT_PATH = "docs/baselines/audits/2026-08-21-p3c-02-current-semantics-gap.md"
AUDIT_SHA256 = "92cd9ad28049331a17390b227de2857598a7de34918c67af7d35378f0fd09746"
OWNER = ROOT / "docs" / "baselines" / "owner-decision-reconciliation.v2.yaml"
OWNER_SHA256 = "4e9109e3adde405f3c6529bd6d09f27828a0cc56959eeb024b5600865bbba1f0"
CORE = ROOT / "docs" / "baselines" / "p3c-prbs9-metric-core.v2.yaml"
CORE_SHA256 = "4cd55eee3897b3705e25e1c7e0e5f1e5090efb0b8689b0bb8837f6252c036c13"
SOURCE_OBSERVATION = ROOT / "docs" / "baselines" / "p3-original-project-eye-jitter-semantics-observation.v1.yaml"
SOURCE_OBSERVATION_SHA256 = "d5d28e855865db033b3678ad3bf7e63f6fd1073a81dede8aadb9d70cdcae1a66"
SCHEMA = "sipi.p3c-02.current-semantics-gap.v1"


class P3C02GapError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise P3C02GapError(message)


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    _expect(isinstance(value, dict), "document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    evidence = _load(EVIDENCE)
    _expect(evidence.get("schema") == SCHEMA, "schema_invalid")
    _expect(evidence.get("status") == "p3c_02_semantic_boundary_observed_not_closed", "status_invalid")

    scope = evidence.get("scope")
    _expect(isinstance(scope, dict), "scope_missing")
    for key, expected in {
        "work_item": "P3C-02",
        "basis": "current_owner_reconciliation_and_product_contracts",
        "product_rust_changed_for_this_record": False,
        "external_runtime_invoked": False,
        "external_reference_bound": False,
        "historical_evidence_rewritten": False,
        "acceptance_or_release_promoted": False,
    }.items():
        _expect(scope.get(key) == expected, f"scope_{key}_drift")

    owner = evidence.get("owner_scope")
    _expect(isinstance(owner, dict), "owner_scope_missing")
    _expect(owner.get("path") == "docs/baselines/owner-decision-reconciliation.v2.yaml", "owner_path_drift")
    _expect(owner.get("sha256") == OWNER_SHA256, "owner_hash_drift")
    _expect(
        owner.get("profile") == "selected_highloss_exact"
        and owner.get("receiver") == "none"
        and owner.get("scope") == "waveform_only"
        and owner.get("included_observables") == ["waveform"]
        and owner.get("excluded_observables") == ["eye", "TIE", "bathtub"]
        and owner.get("closed_eye_fallback") == "prohibited",
        "owner_boundary_drift",
    )

    core = evidence.get("current_product_contract")
    _expect(isinstance(core, dict), "product_contract_missing")
    _expect(core.get("path") == "docs/baselines/p3c-prbs9-metric-core.v2.yaml", "core_path_drift")
    _expect(core.get("sha256") == CORE_SHA256, "core_hash_drift")
    _expect(
        core.get("status") == "product_owned_strict_grid_waveform_eye_tie_core_specified_not_profile_accepted",
        "core_status_drift",
    )
    _expect(core.get("fixed_eye_rules") == {
        "phase": "sample_index_modulo_32",
        "partition": "frozen_prbs9_current_ui",
        "opening": "min_high_minus_max_low",
        "width": "contiguous_positive_bins_containing_center_times_dt",
        "wraparound": "prohibited",
        "interpolation": "prohibited",
    }, "fixed_eye_rules_drift")
    admission = core.get("admission")
    _expect(
        admission == {
            "external_reference_binding": "not_evaluated",
            "accepted_receiver": False,
            "acceptance_ready": False,
            "release_ledger_promoted": False,
        },
        "core_admission_drift",
    )

    source = evidence.get("original_source_observation")
    _expect(isinstance(source, dict), "source_observation_missing")
    _expect(source.get("path") == "docs/baselines/p3-original-project-eye-jitter-semantics-observation.v1.yaml", "source_path_drift")
    _expect(source.get("sha256") == SOURCE_OBSERVATION_SHA256, "source_hash_drift")
    _expect(source.get("source_semantics_are_not_owner_profile") is True, "source_non_authority_guard_missing")
    _expect(source.get("decision_surface", {}).get("p3c_02_eye_folding_bins") == "pending_owner_decision", "source_decision_drift")
    _expect(source.get("source_port_admitted") is False, "source_port_admitted")

    gap = evidence.get("gap")
    _expect(isinstance(gap, dict) and gap.get("status") == "unresolved", "gap_status_invalid")
    _expect(
        gap.get("blockers") == [
            "current_selected_profile_excludes_eye_tie_bathtub",
            "generic_com_eye_folding_and_bin_contract_not_selected",
            "accepted_receiver_stage_missing",
            "external_reference_binding_missing",
        ],
        "gap_blockers_drift",
    )
    _expect(
        gap.get("prohibited_shortcuts") == [
            "infer_product_semantics_from_pybert_or_agent_com_source_names",
            "treat_waveform_only_metric_core_as_com_bathtub_acceptance",
            "add_alignment_gain_dc_polarity_or_tolerance_relaxation",
        ],
        "shortcut_guard_drift",
    )

    _expect(evidence.get("audit") == {"path": AUDIT_PATH, "sha256": AUDIT_SHA256}, "audit_binding_drift")
    audit = root / AUDIT_PATH
    _expect(audit.is_file() and _sha256(audit) == AUDIT_SHA256, "audit_hash_invalid")
    _expect(_sha256(root / OWNER.relative_to(ROOT)) == OWNER_SHA256, "owner_file_hash_invalid")
    _expect(_sha256(root / CORE.relative_to(ROOT)) == CORE_SHA256, "core_file_hash_invalid")
    _expect(_sha256(root / SOURCE_OBSERVATION.relative_to(ROOT)) == SOURCE_OBSERVATION_SHA256, "source_file_hash_invalid")

    claims = set(evidence.get("non_claims", []))
    for required in {
        "not_a_receiver_implementation",
        "not_a_bathtub_estimator_selection",
        "not_a_new_eye_folding_or_bin_api",
        "not_external_oracle_evidence",
        "not_com_parity",
        "not_acceptance_evidence",
        "not_release_evidence",
    }:
        _expect(required in claims, f"non_claim_missing:{required}")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": evidence["status"],
        "blocker_count": len(gap["blockers"]),
        "source_port_admitted": source["source_port_admitted"],
        "acceptance_ready": admission["acceptance_ready"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
    except (OSError, UnicodeError, yaml.YAMLError, P3C02GapError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
