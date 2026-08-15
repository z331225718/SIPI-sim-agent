"""Verify the hash-only P7 compiled-license structural normalization evidence."""
from __future__ import annotations
import argparse, hashlib, json
import stat
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/baselines/p7-compiled-license-metadata-normalization-evidence.v1.yaml"
SCHEMA = "sipi.p7-compiled-license-metadata-normalization-evidence.v1"
REPORT_SCHEMA = "sipi.p7-compiled-license-metadata-normalization.v1"
EXPECTED_GATES = {
    "compiled_license_metadata_structurally_normalized": True,
    "unresolved_categories_observed": True,
    "dependency_snapshot_ready": False,
    "dependencies_approved": False,
    "notices_approved": False,
    "first_party_approved": False,
    "release_sbom": False,
    "release_ready": False,
    "promotion_status": "blocked",
}
EXPECTED_NON_CLAIMS = [
    "license_concluded_NOASSERTION",
    "notice_requirement_not_evaluated",
    "not_an_spdx_or_cyclonedx_sbom",
    "not_a_notice_or_legal_compatibility_decision",
    "not_a_dependency_or_first_party_approval",
]
EXPECTED_CATEGORY_COUNTS = {
    "declared_string_unparsed": 73,
    "license_file_declared": 0,
    "workspace_inherited_declared_unresolved": 0,
    "metadata_absent": 0,
    "conflicting_or_unbound": 13,
}


class EvidenceError(RuntimeError):
    pass


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hex(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise EvidenceError("digest_invalid")
    return value


def load() -> dict:
    try:
        value = yaml.safe_load(DOCUMENT.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise EvidenceError("document_invalid") from error
    if not isinstance(value, dict):
        raise EvidenceError("document_invalid")
    return value


def _reference(value: object, input_reference: bool) -> dict:
    expected_keys = {"sha256", "bytes", "package_set_sha256"} if input_reference else {"sha256", "bytes"}
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise EvidenceError("reference_invalid")
    _hex(value.get("sha256"))
    if input_reference:
        _hex(value.get("package_set_sha256"))
    if not isinstance(value.get("bytes"), int) or value["bytes"] <= 0:
        raise EvidenceError("reference_invalid")
    return value


def validate(document: dict) -> None:
    expected_keys = {"schema", "kind", "input", "external_report", "result", "gates", "non_claims"}
    if set(document) != expected_keys or document.get("schema") != SCHEMA or document.get("kind") != "external_structural_metadata_observation_not_license_decision":
        raise EvidenceError("schema_invalid")
    _reference(document.get("input"), input_reference=True)
    _reference(document.get("external_report"), input_reference=False)

    result = document.get("result")
    expected_result_keys = {"record_count", "category_counts", "normalized_records_sha256", "unresolved_set_sha256"}
    if not isinstance(result, dict) or set(result) != expected_result_keys or result.get("record_count") != 86:
        raise EvidenceError("result_invalid")
    _hex(result.get("normalized_records_sha256"))
    _hex(result.get("unresolved_set_sha256"))
    if result.get("category_counts") != EXPECTED_CATEGORY_COUNTS:
        raise EvidenceError("result_invalid")
    if document.get("gates") != EXPECTED_GATES or document.get("non_claims") != EXPECTED_NON_CLAIMS:
        raise EvidenceError("gates_invalid")


def verify_report(document: dict, path: Path) -> None:
    resolved = path.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise EvidenceError("external_report_required")
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
            raise EvidenceError("external_report_invalid")
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise EvidenceError("external_report_invalid") from error
    if before.st_size != len(raw) or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise EvidenceError("external_report_changed")
    reference = _reference(document["external_report"], input_reference=False)
    if len(raw) != reference["bytes"] or sha256(raw) != reference["sha256"]:
        raise EvidenceError("external_report_identity_mismatch")
    try:
        report = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError("external_report_invalid") from error
    expected_report_keys = {"schema", "status", "input", "result", "gates", "non_claims"}
    if not isinstance(report, dict) or set(report) != expected_report_keys or report.get("schema") != REPORT_SCHEMA:
        raise EvidenceError("external_report_binding_invalid")
    if report.get("status") != "compiled_license_metadata_structurally_normalized_not_concluded":
        raise EvidenceError("external_report_binding_invalid")
    if report.get("input") != document["input"] or report.get("result") != document["result"]:
        raise EvidenceError("external_report_binding_invalid")
    if report.get("gates") != EXPECTED_GATES or report.get("non_claims") != EXPECTED_NON_CLAIMS:
        raise EvidenceError("external_report_binding_invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    try:
        document = load()
        validate(document)
        if arguments.report:
            verify_report(document, arguments.report)
        print(json.dumps({"schema": SCHEMA, "valid": True, "external_report_verified": arguments.report is not None}, sort_keys=True))
        return 0
    except EvidenceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
