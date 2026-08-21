"""Verify P5-09 retirement of candidate wording and binding to a real report."""

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
SPEC = ROOT / "docs/baselines/p5-09b-com-behavior-replica-wording-retirement.v1.yaml"
EVIDENCE = ROOT / "docs/baselines/p5-09b-com-behavior-replica-wording-retirement-evidence.v1.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p5-09b-com-behavior-replica-wording-retirement.md"

SPEC_SCHEMA = "sipi.p5-09b.com-behavior-replica-wording-retirement.v1"
EVIDENCE_SCHEMA = "sipi.p5-09b.com-behavior-replica-wording-retirement-evidence.v1"
CONTRACT_REF = "docs/baselines/p5-09b-com-behavior-replica-wording-retirement.v1.yaml"
CONTRACT_SHA256 = "fcae054d3284258dbda9246bb1ac7f989263da24525f5c1843998e31b8776a13"
AUDIT_REF = "docs/baselines/audits/2026-08-21-p5-09b-com-behavior-replica-wording-retirement.md"
AUDIT_SHA256 = "5e86013966157d626f3e40922dd804397ff0fd8edbad7cf18e6ca499cd1f9ed7"
EXPECTED_PATTERNS = [
    r"(?i)\bieee[- ]certified\b",
    r"(?i)\bcertified\b",
    r"(?i)\bcertification\b",
    r"(?i)\bofficial\b",
    r"(?i)\bofficial(?:\s+ieee)?\s+certification\b",
    r"(?i)\bieee(?:[/\s-]+)?standards?[- ]compliant\b",
    r"(?i)\bstandards?[- ]compliant\b",
    r"(?i)\bvalidated\b",
    r"(?i)\bapproved\b",
    r"(?i)\bqualified\b",
    r"(?i)\bequivalent\b",
    r"(?i)\bmatch(?:es|ed|ing)?\b",
    r"(?i)\bpass(?:es|ed|ing)?\b",
    r"(?i)\breference\s+implementation\b",
    r"(?i)\bparity\b",
    r"(?i)\bconformance\b",
    r"(?i)\brelease(?:[- ]ready)?\b",
    r"(?i)\baccept(?:ed|ance)\b",
    r"(?i)\bbehavioral\s+replication\s+of\b",
]
EXPECTED_POSITIVE_FIELDS = [
    "report_title",
    "report_claim",
    "capability_label",
    "capability_description",
    "external_oracle",
    "metrics",
    "runtime",
]
EXPECTED_WORDING = {
    "report_title": "COM bounded artifact execution report",
    "report_claim": "Product-owned bounded payload execution completed; no external equivalence is asserted.",
    "report_disclaimer": "This report is not IEEE official certification, a reference implementation, or an external COM comparison result.",
    "capability_label": "bounded_artifact_execution",
    "capability_description": "Consumes one verified local pulse artifact and publishes one verified local COM result artifact.",
    "capability_disclaimer": "This capability does not establish behavioral replication, standards compliance, conformance, external equivalence, product acceptance, or release readiness.",
    "external_oracle": "External oracle comparison remains blocked.",
    "metrics": "Full metric, checkpoint, and tolerance evidence remains blocked.",
    "runtime": "Bounded local pulse-to-result artifact execution is implemented.",
}
EXPECTED_BINDINGS = {
    "product_report_contract": (
        "docs/baselines/p5-08e-com-run-artifact-execution.v1.yaml",
        "baeb4de8cf0698505ce622eaee2fbea1a0051bcff8e6ab889f6e129a6a4a9379",
        "actual_bounded_execution_report_contract",
    ),
    "product_report_source": (
        "crates/sipi-com/src/com_run_artifact_execution_v1.rs",
        "02cd2a051dad54b39aabd4d1643f9a3a1b40bd2553522da7faf3ce4aed4b3e48",
        "actual_product_report_consumer",
    ),
    "com_r480_acceptance": (
        "docs/baselines/com-r480-acceptance.v1.yaml",
        "e90fca0d14968a04e09df90cd8bd4fcc7f749abfa07ad2b4b29dc297351ef03b",
        "external_oracle_and_acceptance_boundary",
    ),
    "com_publication": (
        "docs/baselines/release-capability-publication.v1.yaml",
        "29ba106b461043a3fbd2714c6201dbe01131bfb2a37a6942f1ed7ea7a7f7b1a2",
        "public_com_command_remains_unavailable",
    ),
    "com_r480_reference_custody": (
        "docs/baselines/p5-r480-reference-custody-preflight.v1.yaml",
        "9819bd5b01120808f0b38191a2b9dbbf2925c9b6e19e59a9e13caa1ed1f4730b",
        "external_oracle_metric_and_tolerance_blockers",
    ),
}


class P509Error(RuntimeError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise P509Error(reason)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise P509Error(f"load_failed:{path}") from error
    _require(isinstance(value, dict), f"document_not_mapping:{path}")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise P509Error(f"read_failed:{path}") from error


def _positive_wording(spec: dict[str, Any]) -> dict[str, str]:
    wording = spec.get("wording")
    rules = spec.get("policy_rules")
    _require(isinstance(wording, dict) and isinstance(rules, dict), "wording_policy_invalid")
    _require(rules.get("positive_claim_fields") == EXPECTED_POSITIVE_FIELDS, "positive_claim_field_set_invalid")
    result: dict[str, str] = {}
    for field in EXPECTED_POSITIVE_FIELDS:
        value = wording.get(field)
        _require(isinstance(value, str) and value, f"wording_field_invalid:{field}")
        result[field] = value
    return result


def validate_spec(spec: dict[str, Any]) -> None:
    _require(
        set(spec)
        == {
            "schema",
            "status",
            "predecessor",
            "policy",
            "scope",
            "consumer",
            "wording",
            "policy_rules",
            "non_claims",
            "evidence_ref",
            "audit_ref",
        },
        "spec_shape_invalid",
    )
    _require(spec.get("schema") == SPEC_SCHEMA, "spec_schema_invalid")
    _require(spec.get("predecessor") == {
        "contract_path": "docs/baselines/p5-09-com-behavior-replica-wording-contract.v1.yaml",
        "contract_sha256": "86c0b001624ce17bdc48c7d2f04063f232d3f64a61b8963c3f88087923e4c6a6",
        "evidence_path": "docs/baselines/p5-09-com-behavior-replica-wording-evidence.v1.yaml",
        "evidence_sha256": "49052cd182693372a75d792664f21b9279abd88c40bc09f180a0f6249e3ef697",
        "unchanged": True,
    }, "predecessor_binding_invalid")
    _require(_sha256(ROOT / spec["predecessor"]["contract_path"]) == spec["predecessor"]["contract_sha256"], "predecessor_contract_hash_drift")
    _require(_sha256(ROOT / spec["predecessor"]["evidence_path"]) == spec["predecessor"]["evidence_sha256"], "predecessor_evidence_hash_drift")
    _require(spec.get("status") == "candidate_wording_retired_product_report_bound", "spec_status_invalid")
    _require(spec.get("policy") == "sipi.p5-09.behavior-replica-not-ieee-certification.v1", "spec_policy_invalid")
    _require(
        spec.get("scope")
        == {
            "domain": "com",
            "profile_id": "com-r480-envelope-v1",
            "closure": "superseded",
            "closure_boundary": "bounded_artifact_execution_report_only",
            "product_behavior_replica": "retired_unpublished_candidate",
            "behavioral_replication": "not_claimed",
            "product_capability": "bounded_artifact_execution_only",
            "external_oracle": "blocked",
            "metrics": "blocked",
            "runtime": "bounded_local_artifact_execution",
            "product_acceptance": False,
            "promotion": False,
        },
        "spec_scope_invalid",
    )
    _require(
        spec.get("consumer")
        == {
            "path": "crates/sipi-com/src/com_run_artifact_execution_v1.rs",
            "symbol": "ComRunArtifactExecutionReportV1",
            "producer": "execute_com_run_artifact_v1",
            "semantics_status": "product_owned_bounded_execution_complete",
            "behavioral_replication_status": "not_claimed",
            "external_acceptance_status": "blocked_missing_authoritative_reference",
        },
        "consumer_binding_invalid",
    )
    wording = _positive_wording(spec)
    _require(spec.get("wording") == EXPECTED_WORDING, "wording_not_canonical")
    rules = spec["policy_rules"]
    _require(rules.get("forbidden_positive_patterns") == EXPECTED_PATTERNS, "forbidden_pattern_policy_invalid")
    _require(rules.get("disclaimer_fields") == ["report_disclaimer", "capability_disclaimer"], "disclaimer_field_policy_invalid")
    for field, value in wording.items():
        for pattern in EXPECTED_PATTERNS:
            _require(re.search(pattern, value) is None, f"forbidden_positive_wording:{field}")
    _require(
        spec.get("non_claims")
        == [
            "retired_candidate_is_not_product_wording",
            "not_behavioral_replication_claim",
            "bounded_execution_is_not_external_equivalence",
            "not_ieee_official_certification",
            "not_reference_implementation",
            "not_conformance_result",
            "not_external_oracle_result",
            "not_full_metric_checkpoint_tolerance",
            "not_public_com_run_cli_admission",
            "not_product_acceptance",
            "not_promotion",
        ],
        "spec_non_claims_invalid",
    )
    _require(spec.get("evidence_ref") == "docs/baselines/p5-09b-com-behavior-replica-wording-retirement-evidence.v1.yaml", "spec_evidence_ref_invalid")
    _require(spec.get("audit_ref") == AUDIT_REF, "spec_audit_ref_invalid")


def _binding_map(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    bindings = evidence.get("bindings")
    _require(isinstance(bindings, list), "evidence_bindings_invalid")
    result = {
        binding.get("id"): binding
        for binding in bindings
        if isinstance(binding, dict) and isinstance(binding.get("id"), str)
    }
    _require(len(result) == len(bindings), "evidence_binding_duplicate_or_invalid")
    _require(set(result) == set(EXPECTED_BINDINGS), "evidence_binding_set_invalid")
    return result


def _check_bindings(bindings: dict[str, dict[str, Any]]) -> None:
    for binding_id, (relative, digest, role) in EXPECTED_BINDINGS.items():
        _require(
            bindings[binding_id]
            == {"id": binding_id, "path": relative, "sha256": digest, "role": role},
            f"evidence_binding_metadata_invalid:{binding_id}",
        )
        path = ROOT / relative
        _require(path.is_file(), f"bound_material_missing:{binding_id}")
        _require(_sha256(path) == digest, f"bound_material_hash_drift:{binding_id}")


def _check_bound_material() -> None:
    product = _load(ROOT / EXPECTED_BINDINGS["product_report_contract"][0])
    _require(
        product.get("status")
        == "bounded_library_composition_implemented_external_acceptance_blocked",
        "product_report_contract_status_invalid",
    )
    _require(
        product.get("report")
        == {
            "semantics": "product_owned_bounded_execution_complete",
            "behavioral_replication": "not_claimed",
            "external_acceptance": "blocked_missing_authoritative_reference",
            "product_acceptance": False,
            "promotion": False,
        },
        "product_report_scope_invalid",
    )
    source = (ROOT / EXPECTED_BINDINGS["product_report_source"][0]).read_text(encoding="utf-8")
    for token in (
        "pub struct ComRunArtifactExecutionReportV1",
        "pub fn execute_com_run_artifact_v1",
        "pub const fn semantics_status",
        "pub const fn behavioral_replication_status",
        "pub const fn external_acceptance_status",
        "product_owned_bounded_execution_complete",
        "blocked_missing_authoritative_reference",
        "CAPABILITY_LABEL",
        "REPORT_CLAIM",
        "REPORT_DISCLAIMER",
        "CAPABILITY_DESCRIPTION",
        "CAPABILITY_DISCLAIMER",
        "EXTERNAL_ORACLE_STATEMENT",
        "METRICS_STATEMENT",
        "RUNTIME_STATEMENT",
        '"capability_label": CAPABILITY_LABEL',
        '"report_claim": REPORT_CLAIM',
        '"report_disclaimer": REPORT_DISCLAIMER',
    ):
        _require(token in source, f"product_report_consumer_missing:{token}")

    acceptance = _load(ROOT / EXPECTED_BINDINGS["com_r480_acceptance"][0])
    _require(acceptance.get("authoritative_reference", {}).get("status") == "missing", "authoritative_reference_not_blocked")
    _require(acceptance.get("comparison", {}).get("product_self_comparison") == "forbidden", "product_self_comparison_not_forbidden")

    publication = _load(ROOT / EXPECTED_BINDINGS["com_publication"][0])
    rows = publication.get("rows")
    _require(isinstance(rows, list), "publication_rows_invalid")
    com_rows = [row for row in rows if isinstance(row, dict) and row.get("command_id") == "com.run"]
    _require(
        len(com_rows) == 1
        and {
            key: com_rows[0].get(key)
            for key in ("domain", "product_surface", "acceptance_state", "external_oracle", "blockers", "non_claims")
        }
        == {
            "domain": "com",
            "product_surface": "unavailable",
            "acceptance_state": "blocked",
            "external_oracle": True,
            "blockers": ["authoritative_reference_missing"],
            "non_claims": ["no_com_solver_or_oracle_workflow"],
        },
        "publication_com_row_invalid",
    )

    custody = _load(ROOT / EXPECTED_BINDINGS["com_r480_reference_custody"][0])
    admission = custody.get("admission", {})
    _require(admission.get("status") == "blocked", "custody_admission_status_invalid")
    _require(admission.get("t14_full_compare_matrix_admitted") is False, "full_compare_matrix_admitted")


def validate_evidence(evidence: dict[str, Any]) -> None:
    _require(
        set(evidence)
        == {
            "schema",
            "status",
            "contract_ref",
            "contract",
            "audit",
            "bindings",
            "expected_scope",
            "expected_publication_row",
            "non_claims",
        },
        "evidence_shape_invalid",
    )
    _require(evidence.get("schema") == EVIDENCE_SCHEMA, "evidence_schema_invalid")
    _require(evidence.get("status") == "retired_candidate_bound_to_product_report", "evidence_status_invalid")
    _require(evidence.get("contract_ref") == CONTRACT_REF, "evidence_contract_ref_invalid")
    _require(evidence.get("contract") == {"path": CONTRACT_REF, "sha256": CONTRACT_SHA256}, "evidence_contract_binding_invalid")
    _require(_sha256(ROOT / CONTRACT_REF) == CONTRACT_SHA256, "contract_hash_drift")
    _require(evidence.get("audit") == {"path": AUDIT_REF, "sha256": AUDIT_SHA256}, "evidence_audit_binding_invalid")
    _require(_sha256(AUDIT) == AUDIT_SHA256, "audit_hash_drift")
    _check_bindings(_binding_map(evidence))
    _check_bound_material()
    _require(
        evidence.get("expected_scope")
        == {
            "closure": "superseded",
            "retired_candidate": "behavior_replica_candidate",
            "product_capability": "bounded_artifact_execution_only",
            "product_report_symbol": "ComRunArtifactExecutionReportV1",
            "semantics_status": "product_owned_bounded_execution_complete",
            "behavioral_replication": "not_claimed",
            "external_acceptance": "blocked_missing_authoritative_reference",
            "product_acceptance": False,
            "promotion": False,
        },
        "evidence_scope_invalid",
    )
    _require(
        evidence.get("expected_publication_row")
        == {
            "command_id": "com.run",
            "domain": "com",
            "product_surface": "unavailable",
            "acceptance_state": "blocked",
            "external_oracle": True,
            "blockers": ["authoritative_reference_missing"],
            "non_claims": ["no_com_solver_or_oracle_workflow"],
        },
        "evidence_publication_expectation_invalid",
    )
    _require(
        evidence.get("non_claims")
        == [
            "retired_candidate_was_never_product_capability",
            "bounded_execution_does_not_claim_behavioral_replication",
            "external_oracle_remains_blocked",
            "full_metrics_and_tolerances_remain_blocked",
            "public_com_run_remains_unavailable",
            "no_ieee_certification_or_official_conformance_claim",
            "no_reference_implementation_claim",
            "no_product_acceptance_or_promotion",
        ],
        "evidence_non_claims_invalid",
    )


def validate_audit(path: Path = AUDIT) -> None:
    _require(path.is_file(), "audit_missing")
    _require(_sha256(path) == AUDIT_SHA256, "audit_hash_drift")
    text = path.read_text(encoding="utf-8").lower()
    for marker in (
        "wording retirement audit",
        "behavior_replica_candidate",
        "comrunartifactexecutionreportv1",
        "bounded_artifact_execution",
        "product_owned_bounded_execution_complete",
        "not_claimed",
        "blocked_missing_authoritative_reference",
        "not promoted",
    ):
        _require(marker in text, f"audit_marker_missing:{marker}")


def validate(root: Path = ROOT) -> dict[str, Any]:
    del root
    spec = _load(SPEC)
    evidence = _load(EVIDENCE)
    validate_spec(spec)
    validate_evidence(evidence)
    validate_audit()
    return {
        "schema": SPEC_SCHEMA,
        "valid": True,
        "closure": "superseded",
        "wording_scope": "retired_unpublished_candidate",
        "behavioral_replication": "not_claimed",
        "product_capability": "bounded_artifact_execution_only",
        "external_oracle": "blocked",
        "metrics": "blocked",
        "runtime": "bounded_local_artifact_execution",
        "product_acceptance": False,
        "promotion": False,
    }


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        print(json.dumps(validate(), sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, yaml.YAMLError, P509Error) as error:
        print(json.dumps({"schema": SPEC_SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
