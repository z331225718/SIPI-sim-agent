"""Structurally normalize the hash-bound P7-07c package metadata report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INPUT_SCHEMA = "sipi.p7-candidate-build-license-material-observation.v2"
SCHEMA = "sipi.p7-compiled-license-metadata-normalization.v1"
EXPECTED_INPUT_SHA256 = "3a5da5b5ec1a64eb523eb1cd4d586156b9d326237d3615afe024078f3542bd29"
EXPECTED_INPUT_BYTES = 57976
EXPECTED_PACKAGE_SET = "ff34e43289a5ba721ac8f5487894d7afd64481f0e71a795ece822a1fe229e927"
EXPECTED_COUNTS = {"total": 86, "registry": 73, "workspace": 13}
MAX_BYTES = 128 * 1024


class NormalizationError(RuntimeError):
    pass


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _external(path: Path) -> bool:
    resolved = path.resolve()
    return resolved != ROOT and ROOT not in resolved.parents


def _read_external(path: Path) -> bytes:
    if not _external(path):
        raise NormalizationError("external_input_required")
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode) or not 0 < before.st_size <= MAX_BYTES:
            raise NormalizationError("external_input_invalid")
        raw = path.read_bytes(); after = path.lstat()
    except OSError as error:
        raise NormalizationError("external_input_invalid") from error
    if before.st_size != len(raw) or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise NormalizationError("external_input_changed_during_read")
    return raw


def _record(package: dict[str, Any]) -> dict[str, Any]:
    required = {"identity", "kind", "name", "version", "manifest_sha256", "literal_license", "literal_license_file", "license_materials", "license_concluded", "notice_requirement"}
    if not required <= set(package) or package.get("kind") not in {"registry", "workspace"}:
        raise NormalizationError("package_record_invalid")
    identity = package["identity"]
    literal = package["literal_license"]
    license_file = package["literal_license_file"]
    materials = package["license_materials"]
    if not isinstance(identity, str) or not isinstance(literal, (str, type(None))) or not isinstance(license_file, (str, type(None))) or not isinstance(materials, list):
        raise NormalizationError("package_record_invalid")
    material_paths = {item.get("path") for item in materials if isinstance(item, dict) and isinstance(item.get("path"), str)}
    if len(material_paths) != len(materials):
        raise NormalizationError("package_record_invalid")
    coverage_gap = license_file is not None and license_file not in material_paths
    if literal is not None:
        category = "declared_string_unparsed"
    elif license_file is not None:
        category = "license_file_declared"
    elif package["kind"] == "workspace":
        category = "conflicting_or_unbound"
    else:
        category = "metadata_absent"
    return {"identity": identity, "kind": package["kind"], "literal_license": literal, "literal_license_file": license_file, "category": category, "observer_material_coverage_gap": coverage_gap, "named_notice_material_observed": any(path.upper().startswith("NOTICE") for path in material_paths)}


def normalize(raw: bytes) -> dict[str, Any]:
    if len(raw) != EXPECTED_INPUT_BYTES or sha256(raw) != EXPECTED_INPUT_SHA256:
        raise NormalizationError("input_identity_mismatch")
    try:
        report = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NormalizationError("input_invalid") from error
    package_set = report.get("package_set") if isinstance(report, dict) else None
    if report.get("schema") != INPUT_SCHEMA or report.get("status") != "selected_windows_build_license_material_observed_not_concluded" or not isinstance(package_set, dict):
        raise NormalizationError("input_invalid")
    packages = package_set.get("packages")
    if package_set.get("sha256") != EXPECTED_PACKAGE_SET or package_set.get("counts") != EXPECTED_COUNTS or not isinstance(packages, list) or len(packages) != 86:
        raise NormalizationError("input_binding_invalid")
    records = sorted((_record(item) for item in packages if isinstance(item, dict)), key=lambda item: item["identity"])
    if len(records) != 86 or len({record["identity"] for record in records}) != 86:
        raise NormalizationError("package_identity_invalid")
    categories = {category: sum(record["category"] == category for record in records) for category in ("declared_string_unparsed", "license_file_declared", "workspace_inherited_declared_unresolved", "metadata_absent", "conflicting_or_unbound")}
    unresolved = sorted(record["identity"] for record in records if record["category"] in {"conflicting_or_unbound", "metadata_absent"} or record["observer_material_coverage_gap"])
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"schema": SCHEMA, "status": "compiled_license_metadata_structurally_normalized_not_concluded", "input": {"sha256": sha256(raw), "bytes": len(raw), "package_set_sha256": EXPECTED_PACKAGE_SET}, "result": {"record_count": len(records), "category_counts": categories, "normalized_records_sha256": sha256(canonical), "unresolved_set_sha256": sha256(json.dumps(unresolved, separators=(",", ":")).encode("utf-8"))}, "gates": {"compiled_license_metadata_structurally_normalized": True, "unresolved_categories_observed": True, "dependency_snapshot_ready": False, "dependencies_approved": False, "notices_approved": False, "first_party_approved": False, "release_sbom": False, "release_ready": False, "promotion_status": "blocked"}, "non_claims": ["license_concluded_NOASSERTION", "notice_requirement_not_evaluated", "not_an_spdx_or_cyclonedx_sbom", "not_a_notice_or_legal_compatibility_decision", "not_a_dependency_or_first_party_approval"]}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--input", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); arguments = parser.parse_args()
    try:
        if arguments.output.exists() or not _external(arguments.output): raise NormalizationError("external_output_required")
        result = normalize(_read_external(arguments.input)); arguments.output.write_bytes(json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
        print(json.dumps({"schema": SCHEMA, "status": result["status"]}, sort_keys=True)); return 0
    except NormalizationError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True)); return 2


if __name__ == "__main__":
    raise SystemExit(main())
