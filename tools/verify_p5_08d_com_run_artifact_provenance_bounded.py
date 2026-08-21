# -*- coding: utf-8 -*-
"""Verify the bounded P5-08d COM artifact projection document.

This is a static document gate. It binds the checked-in schema, exact source
hashes, bounded I/O policy, fixture digests, and non-claims. It does not turn
an external MATLAB run or a dirty checkout into authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p5-08d-com-run-artifact-provenance-bounded.v1.yaml"
AUDIT = ROOT / "docs" / "baselines" / "audits" / "2026-08-21-p5-com-source-gap-and-run-conformance.md"
SOURCE = ROOT / "crates" / "sipi-com" / "src" / "com_run_artifact_provenance_v1.rs"
CARGO_MANIFEST = ROOT / "crates" / "sipi-com" / "Cargo.toml"
SCHEMA = "sipi.p5-08d.com-run-artifact-provenance-bounded.v1"
POLICY = "sipi.p5-08d.com-run-artifact-provenance-v1.bounded"
REQUEST_SCHEMA = "sipi.com.run-request.v1"
REPORT_SCHEMA = "sipi.artifact-report.v1"
EXPECTED_SOURCE_SHA256 = "a58270e247a36f22ec768378d586f4b14ba4c6492a203fb1d8dfdecc352ef41a"
EXPECTED_SOURCE_BLOB_OID_SHA1 = "092af3b18e123435c483a1a203d91b1a9f53ce40"
EXPECTED_CARGO_MANIFEST_SHA256 = "c3c46cbb3d216bd1dc7fb8d14cab1485e2d347bcccf5e2be5f9ee939147edf0f"
EXPECTED_CARGO_MANIFEST_BLOB_OID_SHA1 = "df13187de19adb0004822fa26c565c50b1e790af"
EXPECTED_READER_BLOB = "794fbecd0465bc73f33dd0264755b45b9f23366b"
EXPECTED_PRODUCT_BASE_COMMIT = "b6071779d8164e685d15ddf45c19dcb6b2553c78"
EXPECTED_PRODUCT_BASE_TREE = "5f4859d40e9cfedb4445c0cc17e3bd4b1dfecdaa"
EXPECTED_BOUNDS = {
    "request_max_bytes": 65536,
    "maximum_manifest_bytes": 65536,
    "maximum_entry_count": 64,
    "maximum_total_payload_bytes": 16777216,
    "maximum_report_bytes": 16384,
    "policy_note": "exact_io_budgets_not_com_metric_tolerances",
}
EXPECTED_FIXTURE = {
    "artifact_id": "result-1",
    "payload_path": "report.json",
    "payload_bytes": 14,
    "payload_sha256": "23bd670b3ff114c2eeec2ce27fd6def314530f33f6a46b2c4fb05964628bba9b",
    "manifest_sha256": "dc44cc8d5ded60f3cbcf4c1b85c57fdc3e6d0b902cc5569e4a91d11f48c7d89c",
    "report_sha256": "2422c29429d48db15cf3ddb6dbba681457a367cb0c21dc0e0bb43ed2407f96f0",
}
EXPECTED_NON_CLAIMS = [
    "local_verified_metadata_only",
    "no_hostile_writer_safety",
    "no_ownership_signature_or_external_origin",
    "not_com_execution",
    "not_profile_selection",
    "not_matlab_oracle_provenance",
    "not_generator_input_config_provenance",
    "not_payload_to_com_pipeline",
    "not_checkpoint_alignment",
    "not_mlse_der_cdr_semantics",
    "not_metric_tolerance",
    "not_acceptance",
    "not_release",
]
ABSOLUTE_PATH = re.compile(r"(?:/(?:(?:home|Users|tmp|var)/)|\\\\|(?<![A-Za-z])[A-Za-z]:[\\/])")


class EvidenceError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvidenceError("document_not_mapping")
    return value


def canonical_git_object(path: Path, root: Path, expected_oid: str) -> tuple[str, str]:
    relative = path.relative_to(root).as_posix()
    try:
        oid = subprocess.run(
            ["git", "-C", str(root), "hash-object", f"--path={relative}", str(path)],
            check=True,
            capture_output=True,
            text=True,
            encoding="ascii",
        ).stdout.strip()
        content = subprocess.run(
            ["git", "-C", str(root), "cat-file", "blob", expected_oid],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise EvidenceError("canonical_git_object_unavailable") from error
    return oid, hashlib.sha256(content).hexdigest()


def validate(root: Path = ROOT) -> dict[str, Any]:
    evidence_path = EVIDENCE
    source_path = root / SOURCE.relative_to(ROOT)
    cargo_manifest_path = root / CARGO_MANIFEST.relative_to(ROOT)
    evidence = load_yaml(evidence_path)
    for document_path in (evidence_path, AUDIT):
        if ABSOLUTE_PATH.search(document_path.read_text(encoding="utf-8")):
            raise EvidenceError("absolute_path_in_evidence_or_audit")
    if evidence.get("schema") != SCHEMA:
        raise EvidenceError("schema_drift")
    if evidence.get("status") != "bounded_local_artifact_report_observed":
        raise EvidenceError("status_overclaim_or_drift")
    if evidence.get("policy") != POLICY:
        raise EvidenceError("policy_drift")
    if evidence.get("request_schema") != REQUEST_SCHEMA or evidence.get("report_schema") != REPORT_SCHEMA:
        raise EvidenceError("schema_binding_drift")

    implementation = evidence.get("implementation")
    if not isinstance(implementation, dict):
        raise EvidenceError("implementation_missing")
    if implementation.get("source_path") != "crates/sipi-com/src/com_run_artifact_provenance_v1.rs":
        raise EvidenceError("source_path_drift")
    if implementation.get("source_git_blob_oid_sha1") != EXPECTED_SOURCE_BLOB_OID_SHA1:
        raise EvidenceError("source_blob_document_drift")
    if implementation.get("source_content_sha256") != EXPECTED_SOURCE_SHA256:
        raise EvidenceError("source_hash_document_drift")
    if implementation.get("cargo_manifest_git_blob_oid_sha1") != EXPECTED_CARGO_MANIFEST_BLOB_OID_SHA1:
        raise EvidenceError("cargo_manifest_blob_document_drift")
    if implementation.get("cargo_manifest_content_sha256") != EXPECTED_CARGO_MANIFEST_SHA256:
        raise EvidenceError("cargo_manifest_hash_document_drift")
    if implementation.get("product_base_commit") != EXPECTED_PRODUCT_BASE_COMMIT:
        raise EvidenceError("product_base_commit_drift")
    if implementation.get("product_base_tree") != EXPECTED_PRODUCT_BASE_TREE:
        raise EvidenceError("product_base_tree_drift")
    if implementation.get("artifact_reader_dependency") != "crates/sipi-artifacts/src/lib.rs":
        raise EvidenceError("reader_path_drift")
    if implementation.get("artifact_reader_base_blob") != EXPECTED_READER_BLOB:
        raise EvidenceError("reader_object_drift")
    if canonical_git_object(source_path, root, EXPECTED_SOURCE_BLOB_OID_SHA1) != (
        EXPECTED_SOURCE_BLOB_OID_SHA1,
        EXPECTED_SOURCE_SHA256,
    ):
        raise EvidenceError("source_hash_drift")
    if canonical_git_object(cargo_manifest_path, root, EXPECTED_CARGO_MANIFEST_BLOB_OID_SHA1) != (
        EXPECTED_CARGO_MANIFEST_BLOB_OID_SHA1,
        EXPECTED_CARGO_MANIFEST_SHA256,
    ):
        raise EvidenceError("cargo_manifest_hash_drift")
    if implementation.get("source_status") != "canonical_git_object_identity_bound_base_commit_is_lineage_not_acceptance":
        raise EvidenceError("source_authority_overclaim")

    bounded = evidence.get("bounded_read_policy")
    if bounded != EXPECTED_BOUNDS:
        raise EvidenceError("bounded_policy_drift")
    if evidence.get("fixture") != EXPECTED_FIXTURE:
        raise EvidenceError("fixture_digest_drift")
    observed = evidence.get("observed")
    expected_observed = {
        "binding_parse": "passed",
        "bounded_report_projection": "passed",
        "missing_root": "rejected_as_artifact_not_verified",
        "tampered_payload": "rejected_as_artifact_not_verified",
        "legacy_run_result_wire": "unchanged",
        "external_matlab_oracle_execution": "not_performed",
    }
    if observed != expected_observed:
        raise EvidenceError("observed_behavior_drift")
    if evidence.get("non_claims") != EXPECTED_NON_CLAIMS:
        raise EvidenceError("non_claim_drift")

    source = source_path.read_text(encoding="utf-8")
    required_tokens = (
        "pub fn parse_com_run_artifact_binding_v1",
        "pub fn inspect_com_run_artifact_provenance_v1",
        "COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1: usize = 65_536",
        "COM_RUN_ARTIFACT_MAX_MANIFEST_BYTES_V1: u64 = 65_536",
        "COM_RUN_ARTIFACT_MAX_ENTRY_COUNT_V1: usize = 64",
        "COM_RUN_ARTIFACT_MAX_TOTAL_PAYLOAD_BYTES_V1: u64 = 16 * 1024 * 1024",
        "COM_RUN_ARTIFACT_MAX_REPORT_BYTES_V1: usize = 16_384",
        "ArtifactReportPolicyV1::try_new",
        ".inspect_verified_v1(",
        "COM_RUN_REQUEST_SCHEMA_V1",
    )
    if any(token not in source for token in required_tokens):
        raise EvidenceError("implementation_token_drift")
    serialized = json.dumps(evidence, sort_keys=True)
    if "authoritative" in serialized or "release_ready" in serialized:
        raise EvidenceError("authority_keyword_overclaim")
    return {"valid": True, "schema": SCHEMA}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        print(json.dumps(validate(ROOT), sort_keys=True))
        return 0
    except EvidenceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
