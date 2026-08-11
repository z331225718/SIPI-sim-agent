"""Verify a non-release anchor for bounded P7 provisional evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ANCHOR = ROOT / "docs" / "baselines" / "p7-evidence-anchor.v1.yaml"
SCHEMA = "sipi.p7-evidence-anchor.v1"
EVALUATION_SCHEMA = "sipi.p7-fixed-tran-candidate-performance-evaluation.v1"
REQUIRED_BLOCKERS = {
    "license_notice_pending",
    "fresh_machine_evidence_missing",
    "uncertified_domain_profiles",
}
EVIDENCE_FIELDS = {
    "policy_sha256",
    "twin_report_sha256",
    "composition_report_sha256",
    "archive_report_sha256",
    "install_report_sha256",
    "candidate_observation_sha256",
    "candidate_evaluation_sha256",
}


class AnchorError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        document = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AnchorError("invalid_json") from error
    if not isinstance(document, dict):
        raise AnchorError("invalid_json")
    return document, raw


def hex_digest(value: object, length: int = 64) -> str:
    if not isinstance(value, str) or len(value) != length or any(character not in "0123456789abcdef" for character in value):
        raise AnchorError("invalid_digest")
    return value


def safe_audit_ref(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("docs/baselines/audits/"):
        raise AnchorError("audit_reference_invalid")
    if not value.endswith(".md") or "\\" in value or ":" in value or "\0" in value:
        raise AnchorError("audit_reference_invalid")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise AnchorError("audit_reference_invalid")
    return value


def git_text(*arguments: str) -> str:
    try:
        completed = subprocess.run(["git", "-C", str(ROOT), *arguments], check=True, capture_output=True)
        return completed.stdout.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise AnchorError("git_object_unavailable") from error


def validate(anchor: dict[str, Any], root: Path = ROOT) -> None:
    expected = {
        "schema", "kind", "record_commit", "candidate_source_commit", "candidate_tree",
        "candidate_cargo_lock_sha256", "candidate_toolchain_sha256", "candidate_executable_sha256",
        "evidence", "global_blockers", "audit_ref", "promotion_status", "release_candidate", "non_claims",
    }
    if set(anchor) != expected or anchor.get("schema") != SCHEMA or anchor.get("kind") != "evidence_anchor_not_release":
        raise AnchorError("anchor_schema_invalid")
    record_commit = hex_digest(anchor.get("record_commit"), 40)
    candidate_commit = hex_digest(anchor.get("candidate_source_commit"), 40)
    candidate_tree = hex_digest(anchor.get("candidate_tree"), 40)
    for field in ("candidate_cargo_lock_sha256", "candidate_toolchain_sha256", "candidate_executable_sha256"):
        hex_digest(anchor.get(field))
    evidence = anchor.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS:
        raise AnchorError("evidence_schema_invalid")
    for value in evidence.values():
        hex_digest(value)
    blockers = anchor.get("global_blockers")
    if (
        not isinstance(blockers, list)
        or len(blockers) != len(set(blockers))
        or any(not isinstance(blocker, str) or not blocker for blocker in blockers)
        or not REQUIRED_BLOCKERS.issubset(blockers)
    ):
        raise AnchorError("global_blockers_invalid")
    audit_ref = safe_audit_ref(anchor.get("audit_ref"))
    if not (root / audit_ref).is_file():
        raise AnchorError("audit_reference_unavailable")
    non_claims = anchor.get("non_claims")
    if not isinstance(non_claims, list) or not non_claims or any(not isinstance(item, str) or not item for item in non_claims):
        raise AnchorError("non_claims_invalid")
    if anchor.get("promotion_status") != "blocked" or anchor.get("release_candidate") is not False:
        raise AnchorError("promotion_state_invalid")
    if record_commit == candidate_commit:
        raise AnchorError("record_candidate_not_distinct")
    if git_text("cat-file", "-t", record_commit) != "commit" or git_text("cat-file", "-t", candidate_commit) != "commit":
        raise AnchorError("git_object_invalid")
    if git_text("rev-parse", f"{candidate_commit}^{{tree}}") != candidate_tree:
        raise AnchorError("candidate_tree_mismatch")


def verify_external_evaluation(anchor: dict[str, Any], path: Path) -> None:
    resolved = path.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise AnchorError("external_evaluation_required")
    document, raw = load_json(path)
    if sha256_bytes(raw) != anchor["evidence"]["candidate_evaluation_sha256"]:
        raise AnchorError("evaluation_digest_mismatch")
    expected = {
        "schema", "status", "promotion_status", "policy_sha256", "observation_sha256", "candidate_chain",
        "observed_medians", "thresholds", "threshold_verdict", "limitations",
    }
    if set(document) != expected or document.get("schema") != EVALUATION_SCHEMA:
        raise AnchorError("evaluation_schema_invalid")
    if document.get("status") not in {"within_policy", "over_limit"} or document.get("promotion_status") != "blocked":
        raise AnchorError("evaluation_promotion_invalid")
    if document.get("policy_sha256") != anchor["evidence"]["policy_sha256"] or document.get("observation_sha256") != anchor["evidence"]["candidate_observation_sha256"]:
        raise AnchorError("evaluation_identity_mismatch")
    chain = document.get("candidate_chain")
    if not isinstance(chain, dict):
        raise AnchorError("evaluation_chain_invalid")
    mappings = {
        "commit": "candidate_source_commit",
        "tree": "candidate_tree",
        "cargo_lock_sha256": "candidate_cargo_lock_sha256",
        "toolchain_sha256": "candidate_toolchain_sha256",
        "executable_sha256": "candidate_executable_sha256",
        "twin_report_sha256": "twin_report_sha256",
        "composition_report_sha256": "composition_report_sha256",
        "archive_report_sha256": "archive_report_sha256",
        "install_report_sha256": "install_report_sha256",
    }
    for report_field, anchor_field in mappings.items():
        expected_value = anchor["evidence"].get(anchor_field, anchor.get(anchor_field))
        if chain.get(report_field) != expected_value:
            raise AnchorError("evaluation_chain_mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchor", type=Path, default=ANCHOR)
    parser.add_argument("--evaluation-report", type=Path)
    arguments = parser.parse_args()
    try:
        anchor, raw = load_json(arguments.anchor)
        validate(anchor)
        if arguments.evaluation_report is not None:
            verify_external_evaluation(anchor, arguments.evaluation_report)
        print(json.dumps({"schema": SCHEMA, "valid": True, "anchor_sha256": sha256_bytes(raw)}, sort_keys=True))
        return 0
    except AnchorError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
