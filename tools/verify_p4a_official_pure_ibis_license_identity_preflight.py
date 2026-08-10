"""Verify the fail-closed P4A external pure-IBIS identity and custody record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4a-official-pure-ibis-license-identity-preflight.v1"
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "p4a-official-pure-ibis-license-identity-preflight.v1.yaml"
URL = "https://ibis.org/xml/sample1/sample1%28original%29.ibs"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PreflightError(RuntimeError):
    pass


def _exact_keys(value: object, keys: set[str], reason: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PreflightError(reason)
    return value


def _reject_path_or_content(value: Any) -> None:
    if isinstance(value, str):
        if value.startswith("https://"):
            return
        if re.search(r"(?:[A-Za-z]:[\\/]|file:|\.{2}[\\/])", value):
            raise PreflightError("unsafe_path_or_uri")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"asset", "bytes", "content", "local_path", "temporary_path", "tracked_path", "license_text", "notice_text"}:
                raise PreflightError("asset_material_or_path_recorded")
            _reject_path_or_content(item)
    elif isinstance(value, list):
        for item in value:
            _reject_path_or_content(item)


def _tracked_paths(root: Path) -> Iterable[Path]:
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=False)
    if result.returncode != 0:
        raise PreflightError("tracked_file_inventory_unavailable")
    for raw_path in result.stdout.split(b"\0"):
        if raw_path:
            yield root / raw_path.decode("utf-8", errors="strict")


def _tracked_digest_present(paths: Iterable[Path], expected: str) -> bool:
    return any(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected for path in paths)


def validate_manifest(document: object, *, root: Path = ROOT) -> dict[str, Any]:
    value = _exact_keys(document, {"schema", "status", "promotion_eligible", "profile_candidate_id", "authorization_anchor", "retrieval", "transport", "identity", "legal_observation", "classification", "custody", "non_claims"}, "manifest_shape_invalid")
    _reject_path_or_content(value)
    if value["schema"] != SCHEMA or value["status"] != "external_identity_observed_cleanup_pending" or value["promotion_eligible"] is not False:
        raise PreflightError("manifest_status_invalid")
    if value["profile_candidate_id"] != "ibis-org-sample1-original-ibs" or value["authorization_anchor"] != "user_authorization_external_license_identity_review_2026-08-10":
        raise PreflightError("candidate_or_authorization_invalid")

    retrieval = _exact_keys(value["retrieval"], {"canonical_url", "retrieved_at_utc", "retriever"}, "retrieval_shape_invalid")
    if retrieval != {"canonical_url": URL, "retrieved_at_utc": "2026-08-10T14:47:49Z", "retriever": "curl-8.19.0-windows"}:
        raise PreflightError("retrieval_invalid")
    transport = _exact_keys(value["transport"], {"approved_hosts", "redirect_chain", "final_url", "final_host", "final_status", "content_type", "etag", "last_modified_utc"}, "transport_shape_invalid")
    expected_transport = {"approved_hosts": ["ibis.org"], "redirect_chain": [], "final_url": URL, "final_host": "ibis.org", "final_status": 200, "content_type": "not_observed", "etag": "not_observed", "last_modified_utc": "2001-12-05T19:27:36Z"}
    if transport != expected_transport:
        raise PreflightError("transport_invalid")
    identity = _exact_keys(value["identity"], {"byte_length", "content_sha256", "materialized_outside_worktree", "tracked_asset_present"}, "identity_shape_invalid")
    if identity != {"byte_length": 406532, "content_sha256": "46c53a49a31dea27769f0dddddadea72f03f1f956fb8e60aeaa24f83a7201b95", "materialized_outside_worktree": True, "tracked_asset_present": False} or not SHA256.fullmatch(identity["content_sha256"]):
        raise PreflightError("identity_invalid")
    if _tracked_digest_present(_tracked_paths(root), identity["content_sha256"]):
        raise PreflightError("tracked_asset_digest_present")

    legal = _exact_keys(value["legal_observation"], {"copyright_marker", "license_marker", "notice_marker", "external_license_notice_evidence", "rights_status", "retrieval_authorized", "reuse_or_distribution_authorized"}, "legal_observation_shape_invalid")
    expected_legal = {
        "copyright_marker": {"status": "present", "count": 1, "line_spans": [[8, 8]], "text_sha256": "aaef10d794458d9d42205729536c2d6f90b4e25a4c3d863a5562cb1c4724b5f6"},
        "license_marker": {"status": "absent", "count": 0, "line_spans": [], "text_sha256": None},
        "notice_marker": {"status": "absent", "count": 0, "line_spans": [], "text_sha256": None},
        "external_license_notice_evidence": "absent",
        "rights_status": "unverified",
        "retrieval_authorized": True,
        "reuse_or_distribution_authorized": False,
    }
    if legal != expected_legal:
        raise PreflightError("legal_observation_invalid")
    classification = _exact_keys(value["classification"], {"boundary", "required", "product_asset", "parser_fixture", "oracle_runnable", "release_input", "selection_eligibility"}, "classification_shape_invalid")
    if classification != {"boundary": "external_only", "required": False, "product_asset": False, "parser_fixture": False, "oracle_runnable": False, "release_input": False, "selection_eligibility": "blocked_license_and_custody"}:
        raise PreflightError("classification_invalid")
    custody = _exact_keys(value["custody"], {"materialization_id", "cleanup_status", "source_hash_written_to_git_blob", "temporary_asset_path_recorded"}, "custody_shape_invalid")
    if custody != {"materialization_id": "external-ibis-sample1-20260810-1", "cleanup_status": "not_completed_execution_policy_blocked", "source_hash_written_to_git_blob": False, "temporary_asset_path_recorded": False}:
        raise PreflightError("custody_invalid")
    if not isinstance(value["non_claims"], list) or len(value["non_claims"]) != 4 or not all(isinstance(item, str) and item for item in value["non_claims"]):
        raise PreflightError("non_claims_invalid")
    return {"schema": SCHEMA, "status": value["status"], "candidate_id": value["profile_candidate_id"], "rights_status": legal["rights_status"], "selection_eligibility": classification["selection_eligibility"], "promotion_eligible": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        document = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
        report = validate_manifest(document)
    except (OSError, UnicodeError, yaml.YAMLError, PreflightError, TypeError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if args.report:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["status"] == "external_identity_observed_cleanup_pending" else 2


if __name__ == "__main__":
    raise SystemExit(main())
