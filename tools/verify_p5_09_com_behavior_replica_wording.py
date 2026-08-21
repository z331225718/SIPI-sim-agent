"""Verify the narrow P5-09 behavior-replica wording contract."""

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
SPEC = ROOT / "docs/baselines/p5-09-com-behavior-replica-wording-contract.v1.yaml"
EVIDENCE = ROOT / "docs/baselines/p5-09-com-behavior-replica-wording-evidence.v1.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p5-09-com-behavior-replica-wording.md"

SPEC_SCHEMA = "sipi.p5-09.com-behavior-replica-wording-contract.v1"
EVIDENCE_SCHEMA = "sipi.p5-09.com-behavior-replica-wording-evidence.v1"
CONTRACT_REF = "docs/baselines/p5-09-com-behavior-replica-wording-contract.v1.yaml"
CONTRACT_SHA256 = "86c0b001624ce17bdc48c7d2f04063f232d3f64a61b8963c3f88087923e4c6a6"
AUDIT_REF = "docs/baselines/audits/2026-08-21-p5-09-com-behavior-replica-wording.md"
AUDIT_SHA256 = "fabdb5a79db5bca5038dcc735a1569bf097b6ab6fbbd5d72475a15cf763954eb"
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
EXPECTED_HASHES = {
    "com_r480_acceptance": ("docs/baselines/com-r480-acceptance.v1.yaml", "e90fca0d14968a04e09df90cd8bd4fcc7f749abfa07ad2b4b29dc297351ef03b"),
    "com_publication": ("docs/baselines/release-capability-publication.v1.yaml", "3e99b86e33b71b3496e8598ad27356b29e5c5cf9cfef75db5235492ddba4a6ce"),
    "com_run_admission": ("docs/baselines/p5-08a-com-run-admission-stage.v1.yaml", "bb8b0af330ae014c23137c4cebee5a3976a8b6e8a421f0e20b08be3f8ea2c799"),
    "com_run_execution": ("docs/baselines/p5-08b-com-run-execution-stage.v1.yaml", "d5fa3e67b85a31ccb5142d2f50124117c42fa6deced51b440acb1bbb1d3d8d14"),
    "com_run_artifact": ("docs/baselines/p5-08d-com-run-artifact-provenance-bounded.v1.yaml", "b6d3b865289eb05589cc2ede971fe268af4947473f200719d0903881f4ee5398"),
    "com_r480_reference_custody": ("docs/baselines/p5-r480-reference-custody-preflight.v1.yaml", "9819bd5b01120808f0b38191a2b9dbbf2925c9b6e19e59a9e13caa1ed1f4730b"),
}
EXPECTED_ROLES = {
    "com_r480_acceptance": "selected_profile_and_external_oracle_boundary",
    "com_publication": "current_com_command_publication_boundary",
    "com_run_admission": "admission_is_not_full_runtime",
    "com_run_execution": "bounded_execution_slice_not_full_stack",
    "com_run_artifact": "local_metadata_report_only",
    "com_r480_reference_custody": "external_oracle_metrics_and_runtime_blockers",
}
EXPECTED_WORDING = {
    "report_title": "COM R4.80 behavior-replica wording candidate",
    "report_claim": "Candidate wording for the selected COM R4.80 behavior profile; no completed behavioral replication is claimed.",
    "report_disclaimer": "Wording candidate only; this is not IEEE official certification.",
    "capability_label": "behavior_replica_candidate",
    "capability_description": "Candidate wording for the selected COM R4.80 behavior profile; implementation and external comparison remain blocked.",
    "capability_disclaimer": "Not an IEEE official certification, standards-compliant result, reference implementation, conformance result, validated result, approved result, qualified result, equivalent result, matching result, passing result, or completed behavioral replication.",
    "external_oracle": "External oracle comparison remains blocked.",
    "metrics": "Full metric, checkpoint, and tolerance evidence remains blocked.",
    "runtime": "Full COM runtime, artifact, and provenance workflow remains blocked.",
}
EXPECTED_POSITIVE_FIELDS = [
    "report_title",
    "report_claim",
    "capability_label",
    "capability_description",
    "external_oracle",
    "metrics",
    "runtime",
]


class P509Error(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise P509Error(f"load_failed:{path}") from error
    if not isinstance(value, dict):
        raise P509Error(f"document_not_mapping:{path}")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise P509Error(f"read_failed:{path}") from error


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise P509Error(reason)


def _positive_wording(spec: dict[str, Any]) -> dict[str, str]:
    wording = spec.get("wording")
    rules = spec.get("policy_rules")
    _require(isinstance(wording, dict) and isinstance(rules, dict), "wording_policy_invalid")
    fields = rules.get("positive_claim_fields")
    _require(fields == EXPECTED_POSITIVE_FIELDS, "positive_claim_field_set_invalid")
    result: dict[str, str] = {}
    for field in fields:
        value = wording.get(field)
        _require(isinstance(value, str) and value, f"wording_field_invalid:{field}")
        result[field] = value
    return result


def validate_spec(spec: dict[str, Any]) -> None:
    _require(set(spec) == {"schema", "status", "policy", "scope", "wording", "policy_rules", "non_claims", "evidence_ref", "audit_ref"}, "spec_shape_invalid")
    _require(spec.get("schema") == SPEC_SCHEMA, "spec_schema_invalid")
    _require(spec.get("status") == "scoped_closed_wording_only", "spec_status_invalid")
    _require(spec.get("policy") == "sipi.p5-09.behavior-replica-not-ieee-certification.v1", "spec_policy_invalid")
    _require(spec.get("scope") == {
        "domain": "com",
        "profile_id": "com-r480-envelope-v1",
        "closure": "scoped",
        "closure_boundary": "report_and_capability_wording_candidate_only",
        "product_behavior_replica": "wording_candidate_only",
        "behavioral_replication": "not_claimed",
        "product_capability": "not_claimed",
        "external_oracle": "blocked",
        "metrics": "blocked",
        "runtime": "blocked",
        "product_acceptance": False,
        "promotion": False,
    }, "spec_scope_invalid")
    wording = _positive_wording(spec)
    _require(spec.get("wording") == EXPECTED_WORDING, "wording_not_canonical")
    rules = spec["policy_rules"]
    _require(rules.get("forbidden_positive_patterns") == EXPECTED_PATTERNS, "forbidden_pattern_policy_invalid")
    _require(rules.get("disclaimer_fields") == ["report_disclaimer", "capability_disclaimer"], "disclaimer_field_policy_invalid")
    for field, value in wording.items():
        for pattern in EXPECTED_PATTERNS:
            _require(re.search(pattern, value) is None, f"forbidden_positive_wording:{field}")
    _require(spec.get("non_claims") == [
        "not_behavioral_replication_claim",
        "wording_candidate_not_product_capability",
        "not_ieee_official_certification",
        "not_reference_implementation",
        "not_conformance_result",
        "not_external_oracle_result",
        "not_full_metric_checkpoint_tolerance",
        "not_full_com_runtime_or_provenance",
        "not_product_acceptance",
        "not_promotion",
    ], "spec_non_claims_invalid")
    _require(spec.get("evidence_ref") == "docs/baselines/p5-09-com-behavior-replica-wording-evidence.v1.yaml", "spec_evidence_ref_invalid")
    _require(spec.get("audit_ref") == "docs/baselines/audits/2026-08-21-p5-09-com-behavior-replica-wording.md", "spec_audit_ref_invalid")


def _binding_map(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    bindings = evidence.get("bindings")
    _require(isinstance(bindings, list), "evidence_bindings_invalid")
    result: dict[str, dict[str, Any]] = {}
    for binding in bindings:
        _require(isinstance(binding, dict) and isinstance(binding.get("id"), str), "evidence_binding_invalid")
        _require(binding["id"] not in result, f"evidence_binding_duplicate:{binding['id']}")
        result[binding["id"]] = binding
    _require(set(result) == set(EXPECTED_HASHES), "evidence_binding_set_invalid")
    return result


def _check_hash_bindings(bindings: dict[str, dict[str, Any]]) -> None:
    for binding_id, (relative, expected_hash) in EXPECTED_HASHES.items():
        binding = bindings[binding_id]
        _require(binding.get("path") == relative, f"evidence_path_invalid:{binding_id}")
        _require(binding.get("sha256") == expected_hash, f"evidence_declared_hash_invalid:{binding_id}")
        _require(binding.get("role") == EXPECTED_ROLES[binding_id], f"evidence_role_invalid:{binding_id}")
        path = ROOT / relative
        _require(path.is_file(), f"bound_material_missing:{binding_id}")
        _require(_sha256(path) == expected_hash, f"bound_material_hash_drift:{binding_id}")


def _check_bound_material(bindings: dict[str, dict[str, Any]]) -> None:
    acceptance = _load(ROOT / EXPECTED_HASHES["com_r480_acceptance"][0])
    _require(acceptance.get("schema") == "sipi.com.r480.acceptance.v1", "acceptance_schema_invalid")
    _require(acceptance.get("selection", {}).get("capability") == "com", "acceptance_capability_invalid")
    _require(acceptance.get("external_oracle", {}).get("role") == "external_comparison_observation_only", "acceptance_oracle_role_invalid")
    _require(acceptance.get("authoritative_reference", {}).get("status") == "missing", "authoritative_reference_not_blocked")
    comparison = acceptance.get("comparison", {})
    _require(comparison.get("status") == "blocked_missing_authoritative_reference", "comparison_status_invalid")
    _require(comparison.get("product_self_comparison") == "forbidden", "product_self_comparison_not_forbidden")

    publication = _load(ROOT / EXPECTED_HASHES["com_publication"][0])
    _require(publication.get("release_ready") is False and publication.get("promotion_status") == "blocked", "publication_promotion_state_invalid")
    rows = publication.get("rows")
    _require(isinstance(rows, list), "publication_rows_invalid")
    com_rows = [row for row in rows if isinstance(row, dict) and row.get("command_id") == "com.run"]
    _require(len(com_rows) == 1 and {
        key: com_rows[0].get(key)
        for key in ("domain", "product_surface", "acceptance_state", "external_oracle", "blockers", "non_claims")
    } == {
        "domain": "com",
        "product_surface": "unavailable",
        "acceptance_state": "blocked",
        "external_oracle": True,
        "blockers": ["authoritative_reference_missing"],
        "non_claims": ["no_com_solver_or_oracle_workflow"],
    }, "publication_com_row_invalid")

    admission = _load(ROOT / EXPECTED_HASHES["com_run_admission"][0]).get("admission", {})
    _require(admission.get("no_conformance_admission") is True, "admission_conformance_boundary_invalid")
    _require(admission.get("no_com_execution") is True and admission.get("product_runtime_invoked") is False, "admission_runtime_boundary_invalid")
    _require(admission.get("release_evidence") is False, "admission_promotion_boundary_invalid")

    execution = _load(ROOT / EXPECTED_HASHES["com_run_execution"][0]).get("admission", {})
    _require(execution.get("full_conformance_stack") is False, "execution_stack_boundary_invalid")
    _require(execution.get("release_evidence") is False, "execution_promotion_boundary_invalid")

    artifact = _load(ROOT / EXPECTED_HASHES["com_run_artifact"][0])
    _require(artifact.get("status") == "bounded_local_artifact_report_observed", "artifact_status_invalid")
    observed = artifact.get("observed", {})
    _require(observed.get("external_matlab_oracle_execution") == "not_performed", "artifact_oracle_boundary_invalid")
    _require({"not_com_execution", "not_acceptance", "not_release"} <= set(artifact.get("non_claims", [])), "artifact_non_claims_invalid")

    custody = _load(ROOT / EXPECTED_HASHES["com_r480_reference_custody"][0])
    _require(custody.get("status") == "reference_custody_vertical_preflight_recorded_blocked", "custody_status_invalid")
    scope = custody.get("scope", {})
    _require(scope.get("oracle") == "external_matlab_only", "custody_oracle_scope_invalid")
    _require(scope.get("product_self_comparison_as_oracle") == "forbidden", "custody_self_oracle_invalid")
    _require(scope.get("product_runtime_dependency") == "forbidden", "custody_runtime_scope_invalid")
    checkpoints = custody.get("checkpoints", {})
    _require(checkpoints.get("per_checkpoint_tolerance") == "missing", "checkpoint_tolerance_not_blocked")
    metrics = custody.get("metrics", {})
    _require(metrics.get("acceptance_metric_scope", {}).get("status") == "incomplete_scope_mismatch", "metric_scope_not_blocked")
    tolerance = custody.get("tolerance", {})
    _require(tolerance.get("status") == "incomplete_for_t14", "tolerance_status_invalid")
    _require(tolerance.get("full_matrix", {}).get("metric_tolerances") == "missing", "metric_tolerance_not_blocked")
    admission = custody.get("admission", {})
    _require(admission.get("t14_full_compare_matrix_admitted") is False, "full_compare_matrix_admitted")
    _require(admission.get("status") == "blocked", "custody_admission_status_invalid")
    required_blockers = {
        "intermediate_checkpoint_tolerances_missing",
        "full_metric_tolerance_and_alignment_policy_missing",
        "reference_artifact_payload_missing",
    }
    _require(required_blockers <= set(admission.get("blockers", [])), "custody_blocker_set_incomplete")


def validate_evidence(evidence: dict[str, Any]) -> None:
    _require(set(evidence) == {"schema", "status", "contract_ref", "contract", "audit", "bindings", "expected_scope", "expected_publication_row", "non_claims"}, "evidence_shape_invalid")
    _require(evidence.get("schema") == EVIDENCE_SCHEMA, "evidence_schema_invalid")
    _require(evidence.get("status") == "scoped_wording_contract_bound_blockers_observed", "evidence_status_invalid")
    _require(evidence.get("contract_ref") == CONTRACT_REF, "evidence_contract_ref_invalid")
    _require(evidence.get("contract") == {"path": CONTRACT_REF, "sha256": CONTRACT_SHA256}, "evidence_contract_binding_invalid")
    _require((ROOT / CONTRACT_REF).is_file(), "contract_missing")
    _require(_sha256(ROOT / CONTRACT_REF) == CONTRACT_SHA256, "contract_hash_drift")
    _require(evidence.get("audit") == {"path": AUDIT_REF, "sha256": AUDIT_SHA256}, "evidence_audit_binding_invalid")
    bindings = _binding_map(evidence)
    _check_hash_bindings(bindings)
    _check_bound_material(bindings)
    _require(evidence.get("expected_scope") == {
        "wording_scope": "candidate_only",
        "behavioral_replication": "not_claimed",
        "product_capability": "not_claimed",
        "external_oracle_status": "blocked_missing_authoritative_reference",
        "metrics_status": "full_metric_checkpoint_tolerance_blocked",
        "runtime_status": "full_runtime_artifact_provenance_blocked",
        "product_acceptance": False,
        "promotion": False,
    }, "evidence_scope_invalid")
    _require(evidence.get("expected_publication_row") == {
        "command_id": "com.run",
        "domain": "com",
        "product_surface": "unavailable",
        "acceptance_state": "blocked",
        "external_oracle": True,
        "blockers": ["authoritative_reference_missing"],
        "non_claims": ["no_com_solver_or_oracle_workflow"],
    }, "evidence_publication_expectation_invalid")
    _require(evidence.get("non_claims") == [
        "evidence_is_wording_scope_only",
        "no_behavioral_replication_claim",
        "wording_candidate_not_product_capability",
        "external_oracle_remains_blocked",
        "full_metrics_and_tolerances_remain_blocked",
        "full_runtime_and_provenance_remain_blocked",
        "no_ieee_certification_or_official_conformance_claim",
        "no_reference_implementation_claim",
        "no_product_acceptance_or_promotion",
    ], "evidence_non_claims_invalid")


def validate_audit(path: Path = AUDIT) -> None:
    _require(path.is_file(), "audit_missing")
    _require(_sha256(path) == AUDIT_SHA256, "audit_hash_drift")
    text = path.read_text(encoding="utf-8")
    for marker in (
        "# P5-09 COM Behavior-Replica Wording Audit",
        "Wording candidate only; this is not IEEE official certification.",
        "no completed behavioral replication is claimed",
        "candidate wording contract",
        "external oracle",
        "metric",
        "runtime",
        "standards-compliant",
        "validated",
        "approved",
        "qualified",
        "equivalent",
        "match/pass",
        "reference implementation",
        "conformance",
        "release",
    ):
        _require(marker.lower() in text.lower(), f"audit_marker_missing:{marker}")


def validate(root: Path = ROOT) -> dict[str, Any]:
    del root  # The committed paths are intentionally repository-root bound.
    spec = _load(SPEC)
    evidence = _load(EVIDENCE)
    validate_spec(spec)
    validate_evidence(evidence)
    validate_audit()
    return {
        "schema": SPEC_SCHEMA,
        "valid": True,
        "closure": "scoped_wording_only",
        "wording_scope": "candidate_only",
        "behavioral_replication": "not_claimed",
        "product_capability": "not_claimed",
        "external_oracle": "blocked",
        "metrics": "blocked",
        "runtime": "blocked",
        "product_acceptance": False,
        "promotion": False,
    }


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        print(json.dumps(validate(), sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, yaml.YAMLError, P509Error) as error:
        print(f'{{"schema":"{SPEC_SCHEMA}","valid":false,"reason":"{error}"}}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
