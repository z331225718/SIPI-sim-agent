"""Verify the additive P7 historical byte-identity correction."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/baselines/p7-license-notice-identity-inconsistency-reconciliation.v2.yaml"
SCHEMA = "sipi.p7-license-notice-identity-inconsistency-reconciliation.v2"


class IdentityReconciliationError(RuntimeError):
    pass


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _archive_bytes(commit: str, path: str) -> bytes:
    try:
        raw = subprocess.run(
            ["git", "-C", str(ROOT), "archive", "--format=tar", commit, path],
            check=True,
            capture_output=True,
        ).stdout
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            member = archive.getmember(path)
            if not member.isfile() or member.issym() or member.islnk():
                raise IdentityReconciliationError("git_object_invalid")
            stream = archive.extractfile(member)
            if stream is None:
                raise IdentityReconciliationError("git_object_invalid")
            return stream.read()
    except (OSError, subprocess.CalledProcessError, tarfile.TarError, KeyError) as error:
        raise IdentityReconciliationError("git_object_invalid") from error


def _load(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise IdentityReconciliationError("document_unavailable") from error
    if not isinstance(value, dict):
        raise IdentityReconciliationError("document_invalid")
    return value


def validate(document: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "schema", "kind", "recorded_at", "historical_records",
        "identity_observations", "currentness", "gates", "non_claims", "audit_ref",
    }
    if set(document) != expected or document.get("schema") != SCHEMA:
        raise IdentityReconciliationError("document_schema_invalid")
    if document.get("kind") != "additive_historical_identity_correction_not_currentness_or_legal_evidence":
        raise IdentityReconciliationError("document_kind_invalid")

    records = document.get("historical_records")
    if not isinstance(records, dict) or set(records) != {"reconciliation_v1", "build_evidence_v2"}:
        raise IdentityReconciliationError("historical_records_invalid")
    for record in records.values():
        if not isinstance(record, dict) or set(record) != {"path", "sha256", "rewritten"} or record["rewritten"] is not False:
            raise IdentityReconciliationError("historical_records_invalid")
        path = ROOT / record["path"]
        if _sha256(path.read_bytes()) != record["sha256"]:
            raise IdentityReconciliationError("historical_record_rewritten")

    observations = document.get("identity_observations")
    if not isinstance(observations, list) or len(observations) != 7:
        raise IdentityReconciliationError("identity_observations_invalid")
    seen: set[str] = set()
    for item in observations:
        required = {
            "id", "commit", "path", "recorded_sha256", "canonical_git_blob_sha256",
            "exact_match", "content_equivalent_under_eol_transform",
        }
        if not isinstance(item, dict) or set(item) != required or item["id"] in seen:
            raise IdentityReconciliationError("identity_observation_invalid")
        seen.add(item["id"])
        canonical = _archive_bytes(item["commit"], item["path"])
        if _sha256(canonical) != item["canonical_git_blob_sha256"]:
            raise IdentityReconciliationError("canonical_git_identity_invalid")
        if item["recorded_sha256"] == item["canonical_git_blob_sha256"] or item["exact_match"] is not False:
            raise IdentityReconciliationError("historical_exact_identity_claim_invalid")
        eol_equivalent = _sha256(canonical.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")) == item["recorded_sha256"]
        if item["content_equivalent_under_eol_transform"] is not eol_equivalent:
            raise IdentityReconciliationError("eol_diagnostic_invalid")

    if document.get("currentness") != {
        "state": "historical_identity_inconsistent_external_reports_missing",
        "historical_package_set_current": False,
        "historical_metadata_current": False,
        "current_build_replay": "not_observed",
    }:
        raise IdentityReconciliationError("currentness_invalid")
    if document.get("gates") != {
        "historical_identity_inconsistency_recorded": True,
        "historical_package_set_reconciled": False,
        "historical_declared_metadata_reconciled": False,
        "dependency_snapshot_ready": False,
        "dependencies_approved": False,
        "notices_approved": False,
        "first_party_approved": False,
        "release_sbom": False,
        "release_ready": False,
        "promotion_status": "blocked",
    }:
        raise IdentityReconciliationError("gates_invalid")
    required_non_claims = {
        "eol_equivalence_is_diagnostic_not_exact_identity",
        "recorded_checkout_digest_is_not_canonical_git_blob_identity",
        "historical_counts_are_not_current_package_members",
        "not_a_dependency_notice_or_first_party_approval",
        "not_release_ready",
    }
    if set(document.get("non_claims", [])) != required_non_claims:
        raise IdentityReconciliationError("non_claims_invalid")
    audit = ROOT / str(document.get("audit_ref", ""))
    if not audit.is_file():
        raise IdentityReconciliationError("audit_missing")
    return {"valid": True, "identity_observations": 7, "release_ready": False}


def main() -> int:
    try:
        result = validate(_load(DOCUMENT))
        print(json.dumps({"schema": SCHEMA, **result}, sort_keys=True))
        return 0
    except (OSError, IdentityReconciliationError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
