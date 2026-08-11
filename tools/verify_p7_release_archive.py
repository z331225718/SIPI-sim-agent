"""Bounded, no-extract admission scan for a provisional external ZIP archive."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import struct
import sys
from typing import Any
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.release-archive-report.v1"
POLICY_SCHEMA = "sipi.release-archive-policy.v1"
COMPOSITION_SCHEMA = "sipi.release-composition-preflight.v1"
MODES = {"observe", "release-gate"}
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_ENTRIES = 16
MAX_ENTRY_BYTES = 24 * 1024 * 1024
MAX_TOTAL_BYTES = 28 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


class ArchiveError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_digest(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ArchiveError("digest_invalid")
    return value


def safe_oid(value: object) -> str:
    if isinstance(value, str) and len(value) in {40, 64}:
        if all(char in "0123456789abcdef" for char in value):
            return value
    raise ArchiveError("digest_invalid")


def safe_dll_name(value: object) -> str:
    if not isinstance(value, str) or not value or not value.endswith(".dll"):
        raise ArchiveError("composition_report_invalid")
    normalized = value.lower()
    if any(not (char.isascii() and (char.isalnum() or char in "._-")) for char in normalized):
        raise ArchiveError("composition_report_invalid")
    return normalized


def require_external(path: Path, root: Path) -> Path:
    candidate = path.absolute()
    resolved = candidate.resolve()
    workspace = root.resolve()
    if resolved == workspace or workspace in resolved.parents:
        raise ArchiveError("external_path_required")
    return candidate


def read_regular_external(path: Path, root: Path) -> bytes:
    path = require_external(path, root)
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ArchiveError("external_input_unavailable") from error
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ArchiveError("external_input_not_regular")
    if metadata.st_size <= 0 or metadata.st_size > MAX_ARCHIVE_BYTES:
        raise ArchiveError("archive_size_rejected")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ArchiveError("external_input_unavailable") from error
    if len(data) != metadata.st_size:
        raise ArchiveError("archive_changed_during_read")
    return data


def load_json(path: Path, root: Path) -> tuple[dict[str, Any], str]:
    data = read_regular_external(path, root)
    try:
        document = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ArchiveError("external_json_invalid") from error
    if not isinstance(document, dict):
        raise ArchiveError("external_json_invalid")
    return document, sha256_bytes(data)


def parse_policy(document: object) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ArchiveError("archive_policy_invalid")
    expected = {
        "schema",
        "max_archive_bytes",
        "max_entries",
        "max_entry_bytes",
        "max_total_uncompressed_bytes",
        "max_compression_ratio",
        "entries",
    }
    if set(document) != expected or document.get("schema") != POLICY_SCHEMA:
        raise ArchiveError("archive_policy_invalid")
    limits = {
        "max_archive_bytes": MAX_ARCHIVE_BYTES,
        "max_entries": MAX_ENTRIES,
        "max_entry_bytes": MAX_ENTRY_BYTES,
        "max_total_uncompressed_bytes": MAX_TOTAL_BYTES,
        "max_compression_ratio": MAX_COMPRESSION_RATIO,
    }
    for field, maximum in limits.items():
        value = document.get(field)
        if not isinstance(value, int) or value <= 0 or value > maximum:
            raise ArchiveError("archive_policy_invalid")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) != 2:
        raise ArchiveError("archive_policy_invalid")
    parsed: dict[str, dict[str, str]] = {}
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"path", "role", "required", "digest_source"}:
            raise ArchiveError("archive_policy_invalid")
        path = item["path"]
        role = item["role"]
        required = item["required"]
        source = item["digest_source"]
        if not isinstance(path, str) or not path.isascii() or not path:
            raise ArchiveError("archive_policy_invalid")
        if not isinstance(role, str) or not isinstance(source, str) or required is not True:
            raise ArchiveError("archive_policy_invalid")
        parsed[path] = {"role": role, "digest_source": source}
    if set(parsed) != {"sipi.exe", "LICENSE"}:
        raise ArchiveError("archive_policy_invalid")
    if parsed["sipi.exe"] != {"role": "main_executable", "digest_source": "composition_stage"}:
        raise ArchiveError("archive_policy_invalid")
    if parsed["LICENSE"] != {"role": "mit_license", "digest_source": "source_tree"}:
        raise ArchiveError("archive_policy_invalid")
    return {**document, "entry_map": parsed}


def parse_composition(document: object) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ArchiveError("composition_report_invalid")
    expected = {
        "schema",
        "evidence_status",
        "promotion_status",
        "source_build",
        "dependency_inventory",
        "notice_license_gaps",
        "static_pe",
        "limitations",
    }
    if set(document) != expected or document.get("schema") != COMPOSITION_SCHEMA:
        raise ArchiveError("composition_report_invalid")
    if document.get("promotion_status") != "blocked" or document.get("evidence_status") not in {"complete", "incomplete"}:
        raise ArchiveError("composition_report_invalid")
    source = document.get("source_build")
    if not isinstance(source, dict) or set(source) != {
        "commit",
        "tree",
        "target",
        "cargo_lock_sha256",
        "toolchain_sha256",
        "twin_report_sha256",
        "staged_binary_sha256",
        "staged_binary_bytes",
    }:
        raise ArchiveError("composition_report_invalid")
    if source.get("target") != "x86_64-pc-windows-msvc" or not isinstance(source.get("staged_binary_bytes"), int) or source["staged_binary_bytes"] <= 0:
        raise ArchiveError("composition_report_invalid")
    safe_oid(source.get("commit"))
    safe_oid(source.get("tree"))
    for key in ("cargo_lock_sha256", "toolchain_sha256", "twin_report_sha256", "staged_binary_sha256"):
        safe_digest(source.get(key))
    static_pe = document.get("static_pe")
    if not isinstance(static_pe, dict) or set(static_pe) != {
        "layout_report_sha256",
        "machine",
        "normal_imports",
        "delay_imports",
        "dynamic_load_closure",
        "runtime_dependency_closure",
    } or static_pe.get("machine") != "amd64":
        raise ArchiveError("composition_report_invalid")
    safe_digest(static_pe.get("layout_report_sha256"))
    imports = static_pe.get("normal_imports")
    if not isinstance(imports, list) or not imports or imports != sorted({safe_dll_name(value) for value in imports}):
        raise ArchiveError("composition_report_invalid")
    if static_pe.get("delay_imports") != "not_present_in_layout_observation":
        raise ArchiveError("composition_report_invalid")
    if static_pe.get("dynamic_load_closure") != "not_assessed" or static_pe.get("runtime_dependency_closure") != "not_assessed":
        raise ArchiveError("composition_report_invalid")
    return source | {"evidence_status": document["evidence_status"]}


def source_license_sha256(root: Path, source: dict[str, Any]) -> str:
    if git_text(root, "rev-parse", "HEAD") != source["commit"] or git_text(root, "rev-parse", "HEAD^{tree}") != source["tree"]:
        raise ArchiveError("source_composition_identity_mismatch")
    boundary = load_product_boundary(root)
    license_entry = boundary.get("inventory", {}).get("entries", {}).get("LICENSE")
    if license_entry != {
        "rule": "product-governance",
        "class": "product_candidate",
        "license": "MIT",
        "provenance": "project_authored",
        "distribution": "product",
    }:
        raise ArchiveError("license_boundary_not_accepted")
    return sha256_bytes(archived_member(root, source["commit"], "LICENSE"))


def load_product_boundary(root: Path) -> dict[str, Any]:
    verifier_path = root / "tools" / "verify_product_boundary.py"
    specification = importlib.util.spec_from_file_location("product_boundary", verifier_path)
    if specification is None or specification.loader is None:
        raise ArchiveError("product_boundary_unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    try:
        document = module._load_document(root / "product-boundary.v1.yaml")
        report = module.verify_document(document, module.tracked_paths(root))
    except (OSError, RuntimeError) as error:
        raise ArchiveError("product_boundary_unavailable") from error
    if not report.get("valid") or report.get("status") != "provisional":
        raise ArchiveError("product_boundary_invalid")
    return document


def git_text(root: Path, *arguments: str) -> str:
    completed = __import__("subprocess").run(
        ["git", "-C", str(root), *arguments], capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise ArchiveError("git_identity_unavailable")
    try:
        return completed.stdout.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise ArchiveError("git_identity_unavailable") from error


def archived_member(root: Path, commit: str, path: str) -> bytes:
    completed = __import__("subprocess").run(
        ["git", "-C", str(root), "archive", "--format=tar", commit, path], capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise ArchiveError("source_archive_unavailable")
    try:
        import tarfile

        with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as bundle:
            members = bundle.getmembers()
            if len(members) != 1 or not members[0].isfile() or members[0].name != path:
                raise ArchiveError("source_archive_invalid")
            stream = bundle.extractfile(members[0])
            if stream is None:
                raise ArchiveError("source_archive_invalid")
            return stream.read()
    except (OSError, tarfile.TarError) as error:
        raise ArchiveError("source_archive_unavailable") from error


def safe_name(name: str) -> str:
    if not name or not name.isascii() or any(ord(char) < 0x20 for char in name):
        raise ArchiveError("archive_entry_name_unsafe")
    if "/" in name or "\\" in name or ":" in name or name in {".", ".."}:
        raise ArchiveError("archive_entry_name_unsafe")
    if name != name.strip() or name.endswith("."):
        raise ArchiveError("archive_entry_name_unsafe")
    return name


def validate_zip_container(data: bytes, maximum_entries: int) -> None:
    if len(data) < 22 or data[-22:-18] != b"PK\x05\x06":
        raise ArchiveError("archive_container_rejected")
    _, disk, central_disk, entries_on_disk, entries, central_size, central_offset, comment_size = struct.unpack(
        "<4sHHHHIIH", data[-22:]
    )
    if comment_size != 0 or disk != 0 or central_disk != 0 or entries_on_disk != entries:
        raise ArchiveError("archive_container_rejected")
    if entries > maximum_entries or central_size == 0xFFFFFFFF or central_offset == 0xFFFFFFFF:
        raise ArchiveError("archive_container_rejected")
    if central_offset + central_size > len(data) - 22 or (len(data) >= 42 and data[-42:-38] == b"PK\x06\x07"):
        raise ArchiveError("archive_container_rejected")


def scan_zip(data: bytes, policy: dict[str, Any], expected_binary: str, expected_license: str) -> list[dict[str, Any]]:
    if len(data) > policy["max_archive_bytes"] or not zipfile.is_zipfile(io.BytesIO(data)):
        raise ArchiveError("archive_invalid")
    validate_zip_container(data, policy["max_entries"])
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as bundle:
            if bundle.comment:
                raise ArchiveError("archive_comment_rejected")
            infos = bundle.infolist()
            if not infos or len(infos) > policy["max_entries"]:
                raise ArchiveError("archive_entry_count_rejected")
            seen: set[str] = set()
            entries: list[dict[str, Any]] = []
            total = 0
            for info in infos:
                name = safe_name(info.filename)
                folded = name.lower()
                if folded in seen:
                    raise ArchiveError("archive_entry_duplicate")
                seen.add(folded)
                if name not in policy["entry_map"]:
                    raise ArchiveError("archive_entry_not_allowed")
                if info.is_dir() or info.flag_bits & 0x09 or info.extra or info.extract_version > 20:
                    raise ArchiveError("archive_entry_feature_rejected")
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    raise ArchiveError("archive_entry_feature_rejected")
                mode = (info.external_attr >> 16) & 0o777777
                if info.create_system == 3 and mode and not stat.S_ISREG(mode):
                    raise ArchiveError("archive_entry_feature_rejected")
                if info.file_size < 0 or info.file_size > policy["max_entry_bytes"]:
                    raise ArchiveError("archive_entry_size_rejected")
                total += info.file_size
                if total > policy["max_total_uncompressed_bytes"]:
                    raise ArchiveError("archive_total_size_rejected")
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > policy["max_compression_ratio"]:
                    raise ArchiveError("archive_compression_ratio_rejected")
                with bundle.open(info, "r") as stream:
                    digest = hashlib.sha256()
                    count = 0
                    while chunk := stream.read(64 * 1024):
                        count += len(chunk)
                        if count > policy["max_entry_bytes"]:
                            raise ArchiveError("archive_entry_size_rejected")
                        digest.update(chunk)
                if count != info.file_size:
                    raise ArchiveError("archive_entry_size_rejected")
                content_sha256 = digest.hexdigest()
                expected = expected_binary if name == "sipi.exe" else expected_license
                if content_sha256 != expected:
                    raise ArchiveError("archive_entry_identity_mismatch")
                entries.append({
                    "role": policy["entry_map"][name]["role"],
                    "bytes": count,
                    "content_sha256": content_sha256,
                })
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        if isinstance(error, ArchiveError):
            raise
        raise ArchiveError("archive_read_rejected") from error
    if len(entries) != len(policy["entry_map"]):
        raise ArchiveError("archive_required_entry_missing")
    return sorted(entries, key=lambda entry: entry["role"])


def build_report(root: Path, archive_path: Path, composition_path: Path, policy_path: Path) -> dict[str, Any]:
    archive = read_regular_external(archive_path, root)
    policy_document, policy_sha256 = load_json(policy_path, root)
    composition_document, composition_sha256 = load_json(composition_path, root)
    policy = parse_policy(policy_document)
    composition = parse_composition(composition_document)
    license_sha256 = source_license_sha256(root, composition)
    entries = scan_zip(archive, policy, composition["staged_binary_sha256"], license_sha256)
    return {
        "schema": SCHEMA,
        "structural_admission": "conformant",
        "composition_evidence_status": composition["evidence_status"],
        "promotion_status": "blocked",
        "archive_sha256": sha256_bytes(archive),
        "archive_bytes": len(archive),
        "policy_sha256": policy_sha256,
        "composition_report_sha256": composition_sha256,
        "source_commit": composition["commit"],
        "entries": entries,
        "static_pe_binding": "same_executable_bytes_as_composition_stage",
        "limitations": [
            "provisional archive-admission evidence only",
            "not a release archive approval, SBOM, authorized NOTICE, license compatibility determination, or signature verification",
            "same executable bytes inherit only the prior static PE observation; dynamic-load and runtime dependency closure remain not assessed",
        ],
    }


def write_new_external_report(path: Path, root: Path, report: dict[str, Any]) -> None:
    path = require_external(path, root)
    if path.exists() or path.is_symlink():
        raise ArchiveError("report_already_exists")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as output:
            output.write(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
    except OSError as error:
        raise ArchiveError("report_write_failed") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--composition-report", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--mode", choices=sorted(MODES), default="release-gate")
    arguments = parser.parse_args()
    try:
        report = build_report(ROOT, arguments.archive, arguments.composition_report, arguments.policy)
        write_new_external_report(arguments.report, ROOT, report)
    except ArchiveError as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if arguments.mode == "observe" else 2


if __name__ == "__main__":
    raise SystemExit(main())
