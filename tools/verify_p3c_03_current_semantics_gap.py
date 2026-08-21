"""Verify the fail-closed P3C-03 required compare-surface gap record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-03-current-semantics-gap.v1.yaml"
AUDIT_PATH = "docs/baselines/audits/2026-08-21-p3c-03-current-semantics-gap.md"
AUDIT_SHA256 = "9a615d0cc6813b0f98bd3a8fc2d5f08729361a8c4fdfe4ec16d2482a388a962f"
REQUIRED = ROOT / "docs" / "baselines" / "p5-06k-required-com-compare-contract-gap.v1.yaml"
REQUIRED_SHA256 = "6bf07e6265176569ceee8a5250bf3012fe47881d4c982a6edc8fb59ce65c91d9"
C4_SOURCE = ROOT / "crates" / "sipi-compare" / "src" / "c4_metric_profile_v1.rs"
COMPARE_SOURCE = ROOT / "crates" / "sipi-compare" / "src" / "metric_compare_v1.rs"
PUBLICATION = ROOT / "docs" / "baselines" / "release-capability-publication.v1.yaml"
SCHEMA = "sipi.p3c-03.current-semantics-gap.v1"
C4_POLICY = "sipi.p3c-03c.c4-profile.v1.com-icn-erl-1pct"
REFERENCE_HASHES = {
    "docs/baselines/p5-06k-required-com-compare-contract-gap.v1.yaml": "6bf07e6265176569ceee8a5250bf3012fe47881d4c982a6edc8fb59ce65c91d9",
    "docs/baselines/release-capability-publication.v1.yaml": "3e99b86e33b71b3496e8598ad27356b29e5c5cf9cfef75db5235492ddba4a6ce",
    "crates/sipi-compare/src/c4_metric_profile_v1.rs": "193da6f9d33f1a987abd20f7b4ed43107de43a8ccfc5f4d3bd9bf1269c29a5c2",
    "crates/sipi-compare/src/metric_compare_v1.rs": "7f286ec6ca97173cc456d546e7f53c9f05db8d859640daaef9fcea8f3a1a7e14",
}


class P3C03GapError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise P3C03GapError(message)


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    _expect(isinstance(value, dict), "document_not_mapping")
    return value


def validate(root: Path = ROOT) -> dict[str, Any]:
    evidence = _load(EVIDENCE)
    _expect(evidence.get("schema") == SCHEMA, "schema_invalid")
    _expect(evidence.get("status") == "p3c_03_required_compare_surface_gap_observed_not_closed", "status_invalid")

    scope = evidence.get("scope")
    _expect(isinstance(scope, dict), "scope_missing")
    for key, expected in {
        "work_item": "P3C-03",
        "basis": "current_product_profile_and_pinned_required_contract_gap",
        "product_rust_change_in_scope": "exact_candidate_surface_rejection_only",
        "external_runtime_invoked": False,
        "product_vs_oracle_compare_executed": False,
        "historical_evidence_rewritten": False,
        "acceptance_or_release_promoted": False,
    }.items():
        _expect(scope.get(key) == expected, f"scope_{key}_drift")

    c4 = evidence.get("current_c4_surface")
    _expect(isinstance(c4, dict), "c4_surface_missing")
    _expect(c4.get("profile_policy") == C4_POLICY, "c4_policy_drift")
    _expect(c4.get("metrics") == [
        {"name": "COM_dB", "unit": "db"},
        {"name": "ICN_mV", "unit": "mv"},
        {"name": "ERL", "unit": "db"},
    ], "c4_metrics_drift")
    _expect(c4.get("relative_tolerance") == 0.01, "c4_tolerance_drift")
    _expect(c4.get("reference_binding") == "caller_supplied_finite_reference", "c4_reference_drift")
    compare = c4.get("compare_engine")
    _expect(
        compare == {
            "path": "crates/sipi-compare/src/metric_compare_v1.rs",
            "candidate_surface": "exact_profile_names",
            "unknown_candidate_metrics": "rejected",
            "missing_candidate_metrics": "rejected",
        },
        "compare_surface_drift",
    )

    required = evidence.get("required_contract")
    _expect(isinstance(required, dict), "required_contract_missing")
    _expect(required.get("evidence_path") == "docs/baselines/p5-06k-required-com-compare-contract-gap.v1.yaml", "required_path_drift")
    _expect(required.get("evidence_sha256") == REQUIRED_SHA256, "required_hash_drift")
    _expect(required.get("required_metrics") == [
        {"id": "com_db", "source_aliases": ["COM_dB"], "status": "alias_observed_value_observed_tolerance_missing"},
        {"id": "erl_db", "source_aliases": ["ERL"], "status": "alias_observed_value_observed_tolerance_missing"},
        {"id": "td_iln_db", "source_aliases": ["TD_ILN"], "status": "legacy_alias_only_value_and_tolerance_missing"},
    ], "required_metrics_drift")
    _expect(required.get("c4_substitution_guard") == {
        "current_c4_metric": "ICN_mV",
        "required_metric": "td_iln_db",
        "substitution_allowed": False,
    }, "substitution_guard_drift")
    _expect(required.get("unresolved") == {
        "source_input_provenance": True,
        "checkpoint_alignment": True,
        "required_metric_tolerance": True,
        "authoritative_reference_artifact": True,
    }, "required_gap_drift")

    publication = evidence.get("publication_boundary")
    _expect(isinstance(publication, dict), "publication_boundary_missing")
    _expect(publication.get("path") == "docs/baselines/release-capability-publication.v1.yaml", "publication_path_drift")
    _expect(publication.get("compare_acceptance_state") == "specified", "publication_state_drift")
    _expect(publication.get("blockers") == [
        "caller_supplied_alignment_and_semantic_binding",
        "metric_profile_semantics_not_implemented",
    ], "publication_blockers_drift")
    _expect(publication.get("external_oracle") is False, "publication_oracle_promoted")

    references = evidence.get("references")
    _expect(
        references == [{"path": path, "sha256": digest} for path, digest in REFERENCE_HASHES.items()],
        "reference_inventory_drift",
    )

    gap = evidence.get("gap")
    _expect(isinstance(gap, dict) and gap.get("status") == "unresolved", "gap_status_invalid")
    _expect(gap.get("blockers") == [
        "current_c4_surface_is_not_the_required_com_td_iln_contract",
        "td_iln_value_and_tolerance_missing",
        "input_and_checkpoint_alignment_missing",
        "authoritative_reference_artifact_missing",
    ], "gap_blockers_drift")
    _expect(gap.get("prohibited_shortcuts") == [
        "alias_icn_as_td_iln",
        "relax_alignment_or_tolerance_to_force_a_match",
        "use_historical_source_drift_as_current_evidence",
        "promote_c4_profile_to_com_acceptance",
    ], "shortcut_guard_drift")

    c4_source = C4_SOURCE.read_text(encoding="utf-8")
    _expect("pub const C4_METRICS" in c4_source and '[("COM_dB", "db"), ("ICN_mV", "mv"), ("ERL", "db")]' in c4_source, "c4_source_drift")
    _expect(C4_POLICY in c4_source, "c4_policy_source_missing")
    compare_source = COMPARE_SOURCE.read_text(encoding="utf-8")
    _expect("UnknownCandidateMetric" in compare_source and "contains_key" in compare_source, "exact_candidate_guard_missing")
    _expect("pub fn compare_metric_profile_v1" in compare_source, "compare_entry_missing")

    required_document = _load(REQUIRED)
    _expect(required_document.get("schema") == "sipi.p5-06k.required-com-compare-contract-gap.v1", "required_document_schema_drift")
    _expect(required_document.get("status") == "required_com_compare_contract_gap_observed_not_closed", "required_document_status_drift")

    for relative, expected_hash in REFERENCE_HASHES.items():
        path = root / relative
        _expect(path.is_file(), f"reference_missing:{relative}")
        _expect(_sha256(path) == expected_hash, f"reference_hash_invalid:{relative}")

    publication_document = _load(PUBLICATION)
    compare_row = next((row for row in publication_document.get("rows", []) if row.get("id") == "compare"), None)
    _expect(isinstance(compare_row, dict), "publication_compare_row_missing")
    _expect(compare_row.get("acceptance_state") == "specified", "publication_compare_row_state_drift")
    _expect(compare_row.get("external_oracle") is False, "publication_compare_row_oracle_promoted")
    _expect("metric_profile_semantics_not_implemented" in compare_row.get("blockers", []), "publication_compare_row_blocker_missing")

    _expect(evidence.get("audit") == {"path": AUDIT_PATH, "sha256": AUDIT_SHA256}, "audit_binding_drift")
    audit = root / AUDIT_PATH
    _expect(audit.is_file() and _sha256(audit) == AUDIT_SHA256, "audit_hash_invalid")

    claims = set(evidence.get("non_claims", []))
    for required_claim in {
        "not_td_iln_implementation",
        "not_product_vs_oracle_compare",
        "not_com_parity",
        "not_acceptance_evidence",
        "not_release_evidence",
    }:
        _expect(required_claim in claims, f"non_claim_missing:{required_claim}")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": evidence["status"],
        "current_c4_metric_count": len(c4["metrics"]),
        "required_metric_count": len(required["required_metrics"]),
        "td_iln_substitution_allowed": required["c4_substitution_guard"]["substitution_allowed"],
        "acceptance_state": publication["compare_acceptance_state"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
    except (OSError, UnicodeError, yaml.YAMLError, P3C03GapError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
