"""Verify the additive current/historical evidence reconciliation inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/evidence-currentness-reconciliation.v1.yaml"
SCHEMA = "sipi.evidence-currentness-reconciliation.v1"
CLASSIFICATIONS = {"current", "historical", "source_drift", "external_input_missing", "implementation_failure"}
STATES = {"current", "historical"}
DOMAINS = {"P2", "P3", "P4", "P5", "P7"}
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{8,40}")


class ReconciliationError(ValueError):
    pass


def _load(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ReconciliationError("reconciliation_document_invalid") from error


def _relative_file(path: object, label: str) -> Path:
    if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts or "\\" in path:
        raise ReconciliationError(f"{label}_path_invalid")
    candidate = ROOT / path
    if not candidate.is_file():
        raise ReconciliationError(f"{label}_missing")
    return candidate


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_expected(expected: object, classification: str) -> None:
    if not isinstance(expected, dict) or set(expected) not in ({"exit_code", "stdout_contains"}, {"exit_code", "stderr_contains"}):
        raise ReconciliationError("expected_shape_invalid")
    if not isinstance(expected.get("exit_code"), int) or expected["exit_code"] not in {0, 1, 2}:
        raise ReconciliationError("expected_exit_code_invalid")
    markers = [key for key in ("stdout_contains", "stderr_contains") if key in expected]
    if len(markers) != 1 or not isinstance(expected[markers[0]], str) or not expected[markers[0]]:
        raise ReconciliationError("expected_marker_invalid")
    if classification == "source_drift" and "source_drift" not in expected[markers[0]]:
        raise ReconciliationError("source_drift_marker_missing")
    if classification == "implementation_failure" and expected["exit_code"] == 0:
        raise ReconciliationError("implementation_failure_must_fail")


def verify_document(document: object) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != {"schema", "baseline_commit", "scope", "policy", "reconciliation", "truth_table"}:
        raise ReconciliationError("document_schema_invalid")
    if document.get("schema") != SCHEMA or not isinstance(document.get("baseline_commit"), str) or not COMMIT.fullmatch(document["baseline_commit"]):
        raise ReconciliationError("document_identity_invalid")
    if document.get("scope") != ["P2", "P3", "P4", "P5", "P7"]:
        raise ReconciliationError("document_scope_invalid")
    policy = document.get("policy")
    expected_policy = {
        "historical_evidence_immutable": True,
        "additive_successors_only": True,
        "external_replay_required_for_current": True,
        "frozen_tolerances_unchanged": True,
        "release_promotion_unchanged": True,
        "external_assets_repacked": False,
        "allowed_classifications": sorted(CLASSIFICATIONS),
    }
    if policy != expected_policy:
        raise ReconciliationError("policy_invalid")
    reconciliation = document.get("reconciliation")
    expected_reconciliation = {
        "disposition": "p2_p3a_current_successors_replayed_other_classifications_unchanged",
        "historical_records_rewritten": False,
        "new_current_successors": ["p2-tran-current-v5", "p3a-channel-current-v9"],
        "source_drift_replay_performed": True,
        "release_gate_promoted": False,
    }
    if reconciliation != expected_reconciliation:
        raise ReconciliationError("reconciliation_policy_invalid")
    rows = document.get("truth_table")
    if not isinstance(rows, list) or not rows:
        raise ReconciliationError("truth_table_invalid")
    ids: set[str] = set()
    counts = {classification: 0 for classification in sorted(CLASSIFICATIONS)}
    for row in rows:
        expected_keys = {"id", "domain", "evidence", "verifier", "evidence_state", "classification", "evidence_sha256", "verifier_sha256", "expected", "release_claim", "note"}
        if not isinstance(row, dict) or set(row) != expected_keys:
            raise ReconciliationError("truth_table_row_shape_invalid")
        row_id = row["id"]
        if not isinstance(row_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", row_id) or row_id in ids:
            raise ReconciliationError("truth_table_row_id_invalid")
        ids.add(row_id)
        if row["domain"] not in DOMAINS or row["evidence_state"] not in STATES or row["classification"] not in CLASSIFICATIONS:
            raise ReconciliationError("truth_table_row_classification_invalid")
        if not isinstance(row["release_claim"], bool) or row["release_claim"]:
            raise ReconciliationError("truth_table_release_claim_invalid")
        evidence = _relative_file(row["evidence"], "evidence")
        verifier = _relative_file(row["verifier"], "verifier")
        if not SHA256.fullmatch(row["evidence_sha256"]) or _sha256(evidence) != row["evidence_sha256"]:
            raise ReconciliationError(f"evidence_hash_mismatch:{row_id}")
        if not SHA256.fullmatch(row["verifier_sha256"]) or _sha256(verifier) != row["verifier_sha256"]:
            raise ReconciliationError(f"verifier_hash_mismatch:{row_id}")
        if row["classification"] == "current" and row["evidence_state"] != "current":
            raise ReconciliationError("current_state_mismatch")
        if row["classification"] in {"source_drift", "historical", "implementation_failure"} and row["evidence_state"] != "historical":
            raise ReconciliationError("historical_state_mismatch")
        _validate_expected(row["expected"], row["classification"])
        counts[row["classification"]] += 1
    return {"valid": True, "record_count": len(rows), "classification_counts": counts}


def verify_runtime(document: dict[str, Any], timeout_seconds: float = 30.0) -> dict[str, Any]:
    rows = document["truth_table"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        verifier = ROOT / row["verifier"]
        completed = subprocess.run(
            [sys.executable, "-B", str(verifier)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=timeout_seconds,
        )
        expected = row["expected"]
        assert isinstance(expected, dict)
        marker_key = "stdout_contains" if "stdout_contains" in expected else "stderr_contains"
        stream = completed.stdout if marker_key == "stdout_contains" else completed.stderr
        if completed.returncode != expected["exit_code"] or expected[marker_key] not in stream:
            raise ReconciliationError(f"runtime_mismatch:{row['id']}")
    return {"valid": True, "executed": len(rows)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT)
    parser.add_argument("--no-runtime", action="store_true")
    arguments = parser.parse_args()
    try:
        document = _load(arguments.baseline)
        result = verify_document(document)
        if not arguments.no_runtime:
            runtime = verify_runtime(document)
            result.update(runtime)
    except (OSError, ReconciliationError, subprocess.SubprocessError, yaml.YAMLError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps({"schema": SCHEMA, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
