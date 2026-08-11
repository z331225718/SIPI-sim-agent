"""Assemble provisional release-composition and static-PE evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tomllib
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.release-composition-preflight.v1"
TWIN_SCHEMA = "sipi.p7-windows-twin-build-report.v1"
LAYOUT_SCHEMA = "sipi.release-layout-report.v1"
MODES = {"observe", "release-gate"}


class PreflightError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def require_external(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    workspace = root.resolve()
    if resolved == workspace or workspace in resolved.parents:
        raise PreflightError("external_path_required")
    return resolved


def safe_hex(value: object, length: int) -> str:
    if not isinstance(value, str) or len(value) != length or any(char not in "0123456789abcdef" for char in value):
        raise PreflightError("digest_invalid")
    return value


def safe_digest(value: object) -> str:
    return safe_hex(value, 64)


def safe_git_oid(value: object) -> str:
    if isinstance(value, str) and len(value) in {40, 64}:
        return safe_hex(value, len(value))
    raise PreflightError("digest_invalid")


def safe_dll_name(value: object) -> str:
    if not isinstance(value, str) or not value or "/" in value or "\\" in value:
        raise PreflightError("layout_import_invalid")
    normalized = value.lower()
    if not normalized.endswith(".dll") or any(not (char.isascii() and (char.isalnum() or char in "._-")) for char in normalized):
        raise PreflightError("layout_import_invalid")
    return normalized


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PreflightError("evidence_json_unavailable") from error
    if not isinstance(value, dict):
        raise PreflightError("evidence_json_invalid")
    return value


def git_bytes(root: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise PreflightError("git_identity_unavailable") from error
    return completed.stdout


def git_text(root: Path, *arguments: str) -> str:
    return git_bytes(root, *arguments).decode("ascii").strip()


def archived_member(root: Path, commit: str, path: str) -> bytes:
    archive = git_bytes(root, "archive", "--format=tar", commit, path)
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
            member = bundle.getmember(path)
            if not member.isfile() or member.issym() or member.islnk():
                raise PreflightError("locked_input_archive_invalid")
            source = bundle.extractfile(member)
            if source is None:
                raise PreflightError("locked_input_archive_invalid")
            return source.read()
    except (tarfile.TarError, KeyError) as error:
        raise PreflightError("locked_input_archive_unavailable") from error


def parse_twin_report(document: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema",
        "status",
        "commit",
        "tree",
        "lock_sha256",
        "toolchain_sha256",
        "rustflags_sha256",
        "target",
        "build_a",
        "build_b",
        "comparison",
        "limitations",
    }
    if set(document) != required or document.get("schema") != TWIN_SCHEMA:
        raise PreflightError("twin_report_schema_invalid")
    if document.get("status") != "identical" or document.get("target") != "x86_64-pc-windows-msvc":
        raise PreflightError("twin_identity_not_accepted")
    for key in ("commit", "tree"):
        safe_git_oid(document.get(key))
    for key in ("lock_sha256", "toolchain_sha256", "rustflags_sha256"):
        safe_digest(document.get(key))
    first = document["build_a"]
    second = document["build_b"]
    expected_build = {"binary_bytes", "binary_sha256", "cargo_version_sha256", "rustc_version_sha256"}
    if not isinstance(first, dict) or not isinstance(second, dict) or set(first) != expected_build or set(second) != expected_build:
        raise PreflightError("twin_report_build_invalid")
    for build in (first, second):
        if not isinstance(build["binary_bytes"], int) or build["binary_bytes"] <= 0:
            raise PreflightError("twin_report_build_invalid")
        for key in ("binary_sha256", "cargo_version_sha256", "rustc_version_sha256"):
            safe_digest(build[key])
    if first["binary_bytes"] != second["binary_bytes"] or first["binary_sha256"] != second["binary_sha256"]:
        raise PreflightError("twin_identity_not_accepted")
    if document.get("comparison") != {"size_match": True, "digest_match": True}:
        raise PreflightError("twin_identity_not_accepted")
    return {"commit": document["commit"], "tree": document["tree"], "lock_sha256": document["lock_sha256"], "toolchain_sha256": document["toolchain_sha256"], "binary_bytes": first["binary_bytes"], "binary_sha256": first["binary_sha256"]}


def parse_layout_report(document: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema",
        "status",
        "policySha256",
        "inventorySha256",
        "executableSha256",
        "executableBytes",
        "machine",
        "normalImports",
        "delayImportDirectoryPresent",
        "smoke",
        "limitations",
    }
    if set(document) != required or document.get("schema") != LAYOUT_SCHEMA:
        raise PreflightError("layout_report_schema_invalid")
    if document.get("status") != "layout_conformant" or document.get("machine") != "amd64":
        raise PreflightError("layout_observation_not_accepted")
    if document.get("delayImportDirectoryPresent") is not False:
        raise PreflightError("delay_import_observed")
    for key in ("policySha256", "inventorySha256", "executableSha256"):
        safe_digest(document.get(key))
    if not isinstance(document.get("executableBytes"), int) or document["executableBytes"] <= 0:
        raise PreflightError("layout_report_schema_invalid")
    imports = document.get("normalImports")
    if not isinstance(imports, list) or not imports:
        raise PreflightError("layout_report_schema_invalid")
    return {"report_sha256": None, "binary_sha256": document["executableSha256"], "binary_bytes": document["executableBytes"], "normal_imports": sorted({safe_dll_name(value) for value in imports})}


def release_manifest_status(root: Path) -> dict[str, Any]:
    verifier_path = root / "tools" / "verify_release_license_preflight.py"
    specification = importlib.util.spec_from_file_location("release_license_preflight", verifier_path)
    if specification is None or specification.loader is None:
        raise PreflightError("license_preflight_unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    try:
        document = module._load(root / "license-manifest.v2.yaml")
        report = module.verify_document(document, root=root)
    except (OSError, RuntimeError) as error:
        raise PreflightError("license_preflight_unavailable") from error
    if not report.get("valid") or report.get("status") not in {"provisional", "strict"}:
        raise PreflightError("license_preflight_invalid")
    dependencies = document["release_inputs"]["dependencies"]
    notices = {item["dependency"]: item["status"] for item in document["release_inputs"]["notices"]}
    by_component = {
        item["component"]: {
            "id": item["id"],
            "declared_license": item["declared_spdx"],
            "review_status": item["status"],
            "notice_status": notices[item["id"]],
        }
        for item in dependencies
    }
    return {"manifest_sha256": sha256_file(root / "license-manifest.v2.yaml"), "status": report["status"], "components": by_component}


def source_kind(source: object) -> str:
    if source is None:
        return "workspace"
    if not isinstance(source, str):
        raise PreflightError("lock_source_invalid")
    if source.startswith("registry+"):
        return "registry"
    if source.startswith("git+"):
        return "git"
    return "other"


def locked_inventory(lock_bytes: bytes, declared: dict[str, dict[str, str]]) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        document = tomllib.loads(lock_bytes.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise PreflightError("cargo_lock_unavailable") from error
    packages = document.get("package")
    if not isinstance(packages, list) or not packages:
        raise PreflightError("cargo_lock_invalid")
    inventory: list[dict[str, Any]] = []
    gaps: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for package in packages:
        if not isinstance(package, dict):
            raise PreflightError("cargo_lock_invalid")
        name = package.get("name")
        version = package.get("version")
        kind = source_kind(package.get("source"))
        if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
            raise PreflightError("cargo_lock_invalid")
        key = (name, version, kind)
        if key in seen:
            raise PreflightError("cargo_lock_duplicate_package")
        seen.add(key)
        checksum = package.get("checksum")
        if checksum is not None:
            safe_digest(checksum)
        declaration = declared.get(name)
        item: dict[str, Any] = {
            "package": name,
            "version": version,
            "source_kind": kind,
            "checksum_sha256": checksum,
            "manifest_dependency_id": declaration["id"] if declaration else None,
            "declared_license": declaration["declared_license"] if declaration else "unclassified",
            "review_status": declaration["review_status"] if declaration else "unclassified",
            "notice_status": declaration["notice_status"] if declaration else "unclassified",
        }
        inventory.append(item)
        if declaration is None:
            gaps.append(f"unclassified_locked_package:{name}@{version}")
        elif declaration["review_status"] != "approved" or declaration["notice_status"] not in {"approved", "not_required"}:
            gaps.append(f"pending_manifest_review:{declaration['id']}")
    return sorted(inventory, key=lambda item: (item["package"], item["version"], item["source_kind"])), sorted(set(gaps))


def build_report(root: Path, stage: Path, twin_path: Path, layout_path: Path) -> dict[str, Any]:
    stage = require_external(stage, root)
    twin_path = require_external(twin_path, root)
    layout_path = require_external(layout_path, root)
    executable = stage / "sipi.exe"
    if not stage.is_dir() or not executable.is_file():
        raise PreflightError("stage_executable_unavailable")
    twin = parse_twin_report(load_json(twin_path))
    layout = parse_layout_report(load_json(layout_path))
    layout["report_sha256"] = sha256_file(layout_path)
    binary_sha256 = sha256_file(executable)
    binary_bytes = executable.stat().st_size
    if binary_sha256 != twin["binary_sha256"] or binary_bytes != twin["binary_bytes"]:
        raise PreflightError("stage_twin_identity_mismatch")
    if binary_sha256 != layout["binary_sha256"] or binary_bytes != layout["binary_bytes"]:
        raise PreflightError("stage_layout_identity_mismatch")
    if git_text(root, "rev-parse", "HEAD") != twin["commit"] or git_text(root, "rev-parse", "HEAD^{tree}") != twin["tree"]:
        raise PreflightError("source_twin_identity_mismatch")
    lock_bytes = archived_member(root, twin["commit"], "Cargo.lock")
    toolchain_bytes = archived_member(root, twin["commit"], "rust-toolchain.toml")
    if sha256_bytes(lock_bytes) != twin["lock_sha256"] or sha256_bytes(toolchain_bytes) != twin["toolchain_sha256"]:
        raise PreflightError("locked_input_identity_mismatch")
    license_status = release_manifest_status(root)
    inventory, gaps = locked_inventory(lock_bytes, license_status["components"])
    if license_status["status"] != "strict":
        gaps.append("license_manifest_not_strict")
    return {
        "schema": SCHEMA,
        "evidence_status": "complete" if not gaps else "incomplete",
        "promotion_status": "blocked",
        "source_build": {
            "commit": twin["commit"],
            "tree": twin["tree"],
            "target": "x86_64-pc-windows-msvc",
            "cargo_lock_sha256": twin["lock_sha256"],
            "toolchain_sha256": twin["toolchain_sha256"],
            "twin_report_sha256": sha256_file(twin_path),
            "staged_binary_sha256": binary_sha256,
            "staged_binary_bytes": binary_bytes,
        },
        "dependency_inventory": inventory,
        "notice_license_gaps": gaps,
        "static_pe": {
            "layout_report_sha256": layout["report_sha256"],
            "machine": "amd64",
            "normal_imports": layout["normal_imports"],
            "delay_imports": "not_present_in_layout_observation",
            "dynamic_load_closure": "not_assessed",
            "runtime_dependency_closure": "not_assessed",
        },
        "limitations": [
            "provisional composition evidence only",
            "not an SPDX or CycloneDX SBOM, authorized NOTICE, license compatibility determination, or release approval",
            "static normal-import observation does not prove dynamic or runtime dependency closure",
        ],
    }


def write_new_external_report(path: Path, root: Path, report: dict[str, Any]) -> None:
    path = require_external(path, root)
    if path.exists():
        raise PreflightError("report_already_exists")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as output:
            output.write(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
    except OSError as error:
        raise PreflightError("report_write_failed") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--twin-report", type=Path, required=True)
    parser.add_argument("--layout-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--mode", choices=sorted(MODES), default="release-gate")
    arguments = parser.parse_args()
    try:
        report = build_report(ROOT, arguments.stage, arguments.twin_report, arguments.layout_report)
        write_new_external_report(arguments.report, ROOT, report)
    except PreflightError as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if arguments.mode == "observe" else 2


if __name__ == "__main__":
    raise SystemExit(main())
