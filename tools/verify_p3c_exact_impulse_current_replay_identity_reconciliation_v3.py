"""Verify additive P3C replay source-identity reconciliation v3."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/baselines/p3c-exact-impulse-current-replay-identity-reconciliation.v3.yaml"
SCHEMA = "sipi.p3c-exact-impulse-current-replay-identity-reconciliation.v3"


class ReconciliationError(RuntimeError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReconciliationError("document_invalid")
    return value


def _git_blob(commit: str, path: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{commit}:{path}"],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ReconciliationError("git_blob_unavailable") from error


def validate(document: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "schema", "kind", "recorded_at", "historical_records", "clean_archive_commit",
        "source_identity_observations", "identity_result", "gates", "non_claims", "audit_ref",
    }
    if set(document) != expected or document.get("schema") != SCHEMA:
        raise ReconciliationError("document_schema_invalid")
    records = document.get("historical_records")
    if not isinstance(records, dict) or set(records) != {"preparation", "blocked_v1", "recovered_v2"}:
        raise ReconciliationError("historical_records_invalid")
    for record in records.values():
        if not isinstance(record, dict) or set(record) != {"path", "sha256", "rewritten"} or record["rewritten"] is not False:
            raise ReconciliationError("historical_records_invalid")
        if _sha((ROOT / record["path"]).read_bytes()) != record["sha256"]:
            raise ReconciliationError("historical_record_rewritten")

    commit = document.get("clean_archive_commit")
    observations = document.get("source_identity_observations")
    if not isinstance(observations, dict) or len(observations) != 7:
        raise ReconciliationError("source_inventory_invalid")
    for path, identity in observations.items():
        if not isinstance(identity, dict) or set(identity) != {"recorded_checkout_sha256", "canonical_git_blob_sha256"}:
            raise ReconciliationError("source_identity_invalid")
        raw = _git_blob(commit, path)
        if _sha(raw) != identity["canonical_git_blob_sha256"]:
            raise ReconciliationError("canonical_source_identity_invalid")
        if identity["recorded_checkout_sha256"] == identity["canonical_git_blob_sha256"]:
            raise ReconciliationError("historical_exact_identity_claim_invalid")
        transformed = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        if _sha(transformed) != identity["recorded_checkout_sha256"]:
            raise ReconciliationError("eol_diagnostic_invalid")

    if document.get("identity_result") != {
        "exact_matches": 0,
        "eol_transform_matches": 7,
        "replay_report_inherited_as_canonical_archive_evidence": False,
        "historical_numeric_result_status": "forensic_observation_only_not_current_exact_replay",
    }:
        raise ReconciliationError("identity_result_invalid")
    if document.get("gates") != {
        "historical_identity_inconsistency_recorded": True,
        "current_exact_replay_verified": False,
        "candidate_waveform_accepted": False,
        "receiver_accepted": False,
        "release_ready": False,
        "promotion_status": "blocked",
    }:
        raise ReconciliationError("gates_invalid")
    if set(document.get("non_claims", [])) != {
        "eol_equivalence_is_not_exact_source_identity",
        "historical_report_does_not_prove_canonical_archive_execution",
        "historical_numeric_summary_is_forensic_only",
        "no_root_cause_or_policy_change_is_authorized",
    }:
        raise ReconciliationError("non_claims_invalid")
    if not (ROOT / str(document.get("audit_ref", ""))).is_file():
        raise ReconciliationError("audit_missing")
    return {"valid": True, "exact_matches": 0, "release_ready": False}


def main() -> int:
    try:
        result = validate(_load(DOCUMENT))
        print(json.dumps({"schema": SCHEMA, **result}, sort_keys=True))
        return 0
    except (OSError, yaml.YAMLError, ReconciliationError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
