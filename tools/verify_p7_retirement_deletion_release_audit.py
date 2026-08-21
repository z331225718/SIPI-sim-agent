"""Verify the read-only P7-08/P7-09 retirement and release audit.

The audit binds the owner-approved P7-08 map/strategy/record and the P7-09
hash-only history registry to the live Git tracked tree.  It records a
canonical empty deletion-ready set: the audit is complete, but execution is
blocked by required-profile, same-batch, legal/release, and fresh-machine
gates.  This module only reads files and ``git ls-files``; it never deletes a
path, removes a gate, or changes a release state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p7-retirement-deletion-release-audit.v1.yaml"
AUDIT = ROOT / "docs" / "baselines" / "audits" / "2026-08-21-p7-retirement-deletion-release-audit.md"
MAP = ROOT / "docs" / "baselines" / "p7-08-path-scoped-replacement-map.v1.yaml"
STRATEGY = ROOT / "docs" / "baselines" / "p7-08-drift-gate-retirement-strategy.v1.yaml"
APPROVAL = ROOT / "docs" / "baselines" / "p7-08-retirement-approval-record.v1.yaml"
REGISTRY = ROOT / "docs" / "baselines" / "external-history-citations.v1.yaml"
ACCEPTANCE_PROFILES = ROOT / "acceptance-profiles.v1.yaml"
PUBLICATION = ROOT / "docs" / "baselines" / "release-capability-publication.v1.yaml"
LICENSE_OBSERVATION = ROOT / "docs" / "baselines" / "p7-current-candidate-build-license-material-observation-evidence.v1.yaml"
CANDIDATE_AUDIT = ROOT / "docs" / "baselines" / "audits" / "2026-08-15-p7-current-candidate-chain-observation.md"
SCHEMA = "sipi.p7.retirement-deletion-release-audit.v1"

SOURCE_PATHS = {
    "audit_record": "docs/baselines/audits/2026-08-21-p7-retirement-deletion-release-audit.md",
    "replacement_map": "docs/baselines/p7-08-path-scoped-replacement-map.v1.yaml",
    "drift_gate_strategy": "docs/baselines/p7-08-drift-gate-retirement-strategy.v1.yaml",
    "retirement_approval": "docs/baselines/p7-08-retirement-approval-record.v1.yaml",
    "external_history_registry": "docs/baselines/external-history-citations.v1.yaml",
    "acceptance_profiles": "acceptance-profiles.v1.yaml",
    "release_publication": "docs/baselines/release-capability-publication.v1.yaml",
    "license_observation": "docs/baselines/p7-current-candidate-build-license-material-observation-evidence.v1.yaml",
    "candidate_chain_audit": "docs/baselines/audits/2026-08-15-p7-current-candidate-chain-observation.md",
}

EXPECTED_BLOCKERS = {
    "required_profile_acceptance_incomplete",
    "same_batch_drift_gate_removal_pending",
    "license_notice_pending",
    "fresh_machine_evidence_missing",
    "uncertified_domain_profiles",
    "release_promotion_blocked",
}

EXPECTED_GATE_STATE = {
    "per_path_replacement_mapping": "satisfied",
    "owner_retirement_approval": "satisfied",
    "required_profile_accepted": "pending",
    "same_batch_drift_gate_removal": "pending",
    "release_license_fresh_machine_gates": "pending",
}

PATH_ROW_FIELDS = {
    "id", "path_prefix", "tracked_file_count", "tracked_path_set_sha256",
    "classification", "replacement_status", "disposition", "evidence_state",
    "required_profile_state", "release_state", "legal_state", "fresh_machine_state",
    "ready_for_deletion",
}


class AuditError(RuntimeError):
    """Raised when the audit evidence is stale, incomplete, or promoted."""


def _load_document(path: Path) -> dict[str, Any]:
    try:
        if yaml is None:
            raise AuditError("pyyaml_unavailable")
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except AuditError:
        raise
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise AuditError(f"document_read_failed:{path}") from error
    if not isinstance(value, dict):
        raise AuditError(f"document_not_mapping:{path}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AuditError(f"json_read_failed:{path}") from error
    if not isinstance(value, dict):
        raise AuditError(f"json_not_mapping:{path}")
    return value


def sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, IOError) as error:
        raise AuditError(f"source_read_failed:{path}") from error


def _tracked_paths(prefix: str, root: Path = ROOT) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--", prefix],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=60,
        )
    except (OSError, UnicodeDecodeError, subprocess.TimeoutExpired) as error:
        raise AuditError("git_ls_files_failed") from error
    if completed.returncode != 0:
        raise AuditError("git_ls_files_failed")
    return sorted(line for line in completed.stdout.splitlines() if line.strip())


def tracked_path_set_sha256(prefix: str, root: Path = ROOT) -> str:
    paths = _tracked_paths(prefix, root)
    return hashlib.sha256(("\n".join(paths) + "\n").encode("utf-8")).hexdigest()


def _module(name: str):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools import verify_external_history_citations
    from tools import verify_p7_08_drift_gate_retirement_strategy
    from tools import verify_p7_08_path_scoped_replacement_map
    from tools import verify_p7_08_retirement_approval_record
    return {
        "history": verify_external_history_citations,
        "strategy": verify_p7_08_drift_gate_retirement_strategy,
        "map": verify_p7_08_path_scoped_replacement_map,
        "approval": verify_p7_08_retirement_approval_record,
    }[name]


def _source_bindings(document: dict[str, Any]) -> dict[str, Any]:
    bindings = document.get("source_bindings")
    if not isinstance(bindings, dict) or set(bindings) != set(SOURCE_PATHS):
        raise AuditError("source_bindings_shape_invalid")
    for name, relative in SOURCE_PATHS.items():
        binding = bindings.get(name)
        if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
            raise AuditError(f"source_binding_shape_invalid:{name}")
        if binding["path"] != relative or binding["sha256"] != sha256_file(ROOT / relative):
            raise AuditError(f"source_binding_mismatch:{name}")
    return bindings


def _validate_release_gate_facts(document: dict[str, Any]) -> None:
    facts = document.get("release_gate_facts")
    if not isinstance(facts, dict) or set(facts) != {
        "required_profile_accepted", "release_ready", "promotion_status",
        "license_notice_clearance", "fresh_machine_certification", "legal_clearance",
    }:
        raise AuditError("release_gate_facts_shape_invalid")
    if facts != {
        "required_profile_accepted": False,
        "release_ready": False,
        "promotion_status": "blocked",
        "license_notice_clearance": False,
        "fresh_machine_certification": False,
        "legal_clearance": False,
    }:
        raise AuditError("release_gate_facts_promoted_or_drifted")

    profiles = _load_document(ACCEPTANCE_PROFILES)
    required = [
        item for item in profiles.get("profiles", [])
        if isinstance(item, dict) and isinstance(item.get("acceptance"), dict)
        and item["acceptance"].get("required_by")
    ]
    statuses = {item["id"]: item["acceptance"].get("status") for item in required}
    if statuses != {
        "channel-s2p-channel-16ghz-3db-v1": "required_accepted_matched_kernel_cli_e2e_only",
        "channel-rfm-block-2-current-drive-v1": "required_delegated_policy_agreement_not_lock_accepted",
        "com-r480-envelope-v1": "required_pending_authoritative_reference",
    }:
        raise AuditError("required_profile_status_drift")

    publication = _load_json(PUBLICATION)
    if publication.get("schema") != "sipi.release-capability-publication.v1":
        raise AuditError("release_publication_schema_invalid")
    if publication.get("release_ready") is not False or publication.get("promotion_status") != "blocked":
        raise AuditError("release_publication_promoted")
    if not {"license_notice_pending", "fresh_machine_evidence_missing", "uncertified_domain_profiles"}.issubset(
        set(publication.get("global_blockers", []))
    ):
        raise AuditError("release_publication_blockers_drifted")

    license_observation = _load_document(LICENSE_OBSERVATION)
    gates = license_observation.get("gates")
    if not isinstance(gates, dict) or gates.get("release_ready") is not False or gates.get("promotion_status") != "blocked":
        raise AuditError("license_observation_promoted")
    if any(gates.get(key) is not False for key in (
        "dependency_snapshot_ready", "dependencies_approved", "notices_approved",
        "first_party_approved", "release_sbom",
    )):
        raise AuditError("license_observation_gate_drifted")

    candidate_audit = CANDIDATE_AUDIT.read_text(encoding="utf-8")
    for token in ("fresh-machine", "license", "release", "blocked"):
        if token not in candidate_audit.lower():
            raise AuditError("candidate_audit_token_missing")


def validate(document: dict[str, Any] | None = None, root: Path = ROOT) -> dict[str, Any]:
    """Validate the static evidence and every current tracked map prefix."""
    document = _load_document(EVIDENCE) if document is None else document
    required = {
        "schema", "status", "audit_ref", "source_bindings", "blockers", "gate_state",
        "release_gate_facts", "canonical_sets", "path_assessments", "drift_gate_audit",
        "external_history_audit", "execution_state", "non_claims",
    }
    if set(document) != required or document.get("schema") != SCHEMA:
        raise AuditError("evidence_schema_invalid")
    if document.get("status") != "audit_complete_execution_blocked_by_release_gates":
        raise AuditError("audit_status_invalid")
    if document.get("audit_ref") != "docs/baselines/audits/2026-08-21-p7-retirement-deletion-release-audit.md" or not AUDIT.is_file():
        raise AuditError("audit_ref_invalid")
    _source_bindings(document)
    blockers = document.get("blockers")
    if not isinstance(blockers, list) or len(blockers) != len(set(blockers)) or set(blockers) != EXPECTED_BLOCKERS:
        raise AuditError("blockers_invalid")
    if document.get("gate_state") != EXPECTED_GATE_STATE:
        raise AuditError("gate_state_invalid")
    _validate_release_gate_facts(document)

    modules = {name: _module(name) for name in ("map", "strategy", "approval", "history")}
    map_document = modules["map"].load_json(MAP)
    strategy_document = modules["strategy"].load_json(STRATEGY)
    try:
        modules["map"].validate(map_document, root)
        modules["strategy"].validate(strategy_document, root)
        modules["approval"].validate(root)
        modules["history"].validate(modules["history"].load(REGISTRY), root)
    except Exception as error:
        if isinstance(error, AuditError):
            raise
        raise AuditError("bound_p7_source_invalid") from error

    execution = document.get("execution_state")
    if execution != {
        "path_deletion_performed": False,
        "drift_gate_removed": False,
        "release_admitted": False,
    }:
        raise AuditError("execution_promoted_or_mutating")
    if document.get("non_claims") != [
        "not_a_path_deletion",
        "not_a_drift_gate_removal",
        "not_a_required_profile_acceptance",
        "not_a_license_or_notice_clearance",
        "not_a_fresh_machine_certification",
        "not_a_release_approval_or_promotion",
    ]:
        raise AuditError("non_claims_invalid")

    entries = map_document.get("entries")
    if not isinstance(entries, list) or not entries:
        raise AuditError("map_entries_missing")
    expected_by_id = {entry["id"]: entry for entry in entries}
    rows = document.get("path_assessments")
    row_ids = [row.get("id") for row in rows] if isinstance(rows, list) else []
    if not isinstance(rows, list) or len(rows) != len(expected_by_id) or len(row_ids) != len(set(row_ids)) or set(row_ids) != set(expected_by_id):
        raise AuditError("path_assessment_coverage_invalid")
    fixture_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != PATH_ROW_FIELDS:
            raise AuditError("path_assessment_schema_invalid")
        entry = expected_by_id.get(row["id"])
        if entry is None:
            raise AuditError("path_assessment_unknown_id")
        for key in ("path_prefix", "tracked_file_count", "classification", "replacement_status", "disposition"):
            if row[key] != entry[key]:
                raise AuditError(f"path_assessment_map_drift:{key}")
        if row["tracked_path_set_sha256"] != tracked_path_set_sha256(entry["path_prefix"], root):
            raise AuditError("tracked_path_set_drift")
        if row["evidence_state"] != "map_strategy_approval_bound" or row["ready_for_deletion"] is not False:
            raise AuditError("path_assessment_promotion")
        is_fixture = entry["disposition"] == "retain_test_fixture"
        expected_state = "not_applicable_retained_fixture" if is_fixture else "blocked"
        if any(row[key] != expected_state for key in ("required_profile_state", "release_state", "legal_state", "fresh_machine_state")):
            raise AuditError("path_assessment_gate_state_invalid")
        if is_fixture:
            fixture_ids.add(row["id"])

    canonical = document.get("canonical_sets")
    if not isinstance(canonical, dict) or set(canonical) != {
        "ready_for_deletion", "not_ready_for_deletion", "retained_non_candidates",
        "ready_for_gate_removal", "not_ready_for_gate_removal", "registry_audit_ready",
        "registry_promotion_blocked",
    }:
        raise AuditError("canonical_sets_shape_invalid")
    map_ids = set(expected_by_id)
    if canonical["ready_for_deletion"] != [] or len(canonical["not_ready_for_deletion"]) != len(map_ids) or len(set(canonical["not_ready_for_deletion"])) != len(map_ids) or set(canonical["not_ready_for_deletion"]) != map_ids:
        raise AuditError("canonical_deletion_sets_invalid")
    if len(canonical["retained_non_candidates"]) != len(fixture_ids) or len(set(canonical["retained_non_candidates"])) != len(fixture_ids) or set(canonical["retained_non_candidates"]) != fixture_ids:
        raise AuditError("canonical_retained_set_invalid")

    strategy_entries = strategy_document.get("entries")
    if not isinstance(strategy_entries, list) or not strategy_entries:
        raise AuditError("strategy_entries_missing")
    strategy_ids = {entry["id"] for entry in strategy_entries}
    drift = document.get("drift_gate_audit")
    if not isinstance(drift, dict) or set(drift) != {"gate_count", "ready_for_removal", "not_ready_for_removal", "all_dispositions"}:
        raise AuditError("drift_gate_audit_shape_invalid")
    if drift["gate_count"] != len(strategy_entries) or drift["ready_for_removal"] != [] or len(drift["not_ready_for_removal"]) != len(strategy_ids) or len(set(drift["not_ready_for_removal"])) != len(strategy_ids) or set(drift["not_ready_for_removal"]) != strategy_ids or drift["all_dispositions"] != ["retain_gate_awaiting_approval"]:
        raise AuditError("drift_gate_audit_promotion_or_drift")
    if canonical["ready_for_gate_removal"] != [] or len(canonical["not_ready_for_gate_removal"]) != len(strategy_ids) or len(set(canonical["not_ready_for_gate_removal"])) != len(strategy_ids) or set(canonical["not_ready_for_gate_removal"]) != strategy_ids:
        raise AuditError("canonical_gate_sets_invalid")

    registry = modules["history"].load(REGISTRY)
    registry_ids = {entry["id"] for entry in registry.get("entries", [])}
    history = document.get("external_history_audit")
    if not isinstance(history, dict) or set(history) != {"registry_count", "audit_ready", "promotion_blocked", "product_material_status"}:
        raise AuditError("external_history_audit_shape_invalid")
    if history["registry_count"] != len(registry_ids) or len(history["audit_ready"]) != len(registry_ids) or len(set(history["audit_ready"])) != len(registry_ids) or set(history["audit_ready"]) != registry_ids or history["promotion_blocked"] is not True or history["product_material_status"] != "prohibited":
        raise AuditError("external_history_audit_promotion_or_drift")
    if len(canonical["registry_audit_ready"]) != len(registry_ids) or len(set(canonical["registry_audit_ready"])) != len(registry_ids) or len(canonical["registry_promotion_blocked"]) != len(registry_ids) or len(set(canonical["registry_promotion_blocked"])) != len(registry_ids) or set(canonical["registry_audit_ready"]) != registry_ids or set(canonical["registry_promotion_blocked"]) != registry_ids:
        raise AuditError("canonical_registry_sets_invalid")

    return {
        "schema": SCHEMA,
        "valid": True,
        "path_count": len(map_ids),
        "gate_count": len(strategy_ids),
        "registry_count": len(registry_ids),
        "ready_for_deletion": 0,
        "execution_status": document["status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    arguments = parser.parse_args()
    try:
        document = _load_document(arguments.evidence)
        print(json.dumps(validate(document), sort_keys=True))
        return 0
    except (AuditError, OSError, UnicodeDecodeError, ValueError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
