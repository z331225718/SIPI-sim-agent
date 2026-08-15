"""Observe Cargo license materials for the exact Windows candidate build closure.

This is a provenance collector, not a license classifier, SBOM generator, or
NOTICE decision tool. Its JSON output must be written outside the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p7-candidate-build-license-material-observation.v2"
TARGET = "x86_64-pc-windows-msvc"
MAX_CRATE_BYTES = 16 * 1024 * 1024
MAX_LICENSE_FILES_PER_PACKAGE = 64
MAX_LICENSE_BYTES_PER_PACKAGE = 2 * 1024 * 1024
MAX_BUILD_OUTPUT_BYTES = 64 * 1024 * 1024
LICENSE_PREFIXES = ("LICENSE", "COPYING", "NOTICE", "COPYRIGHT")


class ObservationError(RuntimeError):
    pass


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hex(value: object, length: int = 64) -> str:
    if not isinstance(value, str) or len(value) != length or any(char not in "0123456789abcdef" for char in value):
        raise ObservationError("invalid_digest")
    return value


def _external(path: Path) -> bool:
    resolved = path.resolve()
    return resolved != ROOT and ROOT not in resolved.parents


def _run(
    arguments: list[str], *, cwd: Path | None = None, failure: str = "command_failed"
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(arguments, cwd=cwd, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise ObservationError(failure) from error


def _git_text(repository: Path, *arguments: str) -> str:
    try:
        return _run(["git", "-C", str(repository), *arguments]).stdout.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise ObservationError("candidate_identity_invalid") from error


def _archive_member(repository: Path, commit: str, path: str) -> bytes:
    payload = _run(["git", "-C", str(repository), "archive", "--format=tar", commit, path]).stdout
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
            member = archive.getmember(path)
            if not member.isfile() or member.issym() or member.islnk():
                raise ObservationError("candidate_archive_invalid")
            stream = archive.extractfile(member)
            if stream is None:
                raise ObservationError("candidate_archive_invalid")
            return stream.read()
    except (tarfile.TarError, KeyError) as error:
        raise ObservationError("candidate_archive_invalid") from error


def _safe_extract(payload: bytes, destination: Path) -> None:
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
            for member in archive.getmembers():
                pure = PurePosixPath(member.name)
                if pure.is_absolute() or ".." in pure.parts or member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                    raise ObservationError("candidate_archive_invalid")
            archive.extractall(destination, filter="data")
    except (tarfile.TarError, OSError) as error:
        raise ObservationError("candidate_archive_invalid") from error


def _load_lock(source_root: Path) -> tuple[list[dict[str, Any]], str]:
    raw = (source_root / "Cargo.lock").read_bytes()
    try:
        parsed = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ObservationError("candidate_lock_invalid") from error
    packages = parsed.get("package")
    if not isinstance(packages, list):
        raise ObservationError("candidate_lock_invalid")
    return packages, sha256(raw)


def _cargo_build_artifacts(cargo: str, source_root: Path, target_root: Path) -> tuple[dict[str, Path], str]:
    completed = _run(
        [
            cargo, "build", "--package", "sipi-cli", "--release", "--locked", "--offline",
            "--target", TARGET, "--target-dir", str(target_root), "--message-format=json-render-diagnostics",
        ],
        cwd=source_root,
        failure="cargo_build_failed",
    )
    if len(completed.stdout) > MAX_BUILD_OUTPUT_BYTES:
        raise ObservationError("build_output_budget_exceeded")
    package_manifests: dict[str, Path] = {}
    for line in completed.stdout.splitlines():
        try:
            message = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ObservationError("cargo_message_invalid") from error
        if not isinstance(message, dict):
            raise ObservationError("cargo_message_invalid")
        if message.get("reason") == "compiler-artifact":
            package_id = message.get("package_id")
            manifest_path = message.get("manifest_path")
            if not isinstance(package_id, str) or not package_id or not isinstance(manifest_path, str) or not manifest_path:
                raise ObservationError("cargo_message_invalid")
            path = Path(manifest_path)
            previous = package_manifests.setdefault(package_id, path)
            if previous != path:
                raise ObservationError("compiler_artifact_manifest_ambiguous")
    if not package_manifests:
        raise ObservationError("build_closure_empty")
    return package_manifests, sha256(completed.stderr)


def _candidate_boundary(source_root: Path) -> dict[str, Any]:
    if yaml is None:
        raise ObservationError("pyyaml_unavailable")
    try:
        boundary = yaml.safe_load((source_root / "product-boundary.v1.yaml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ObservationError("candidate_boundary_invalid") from error
    inventory = boundary.get("inventory") if isinstance(boundary, dict) else None
    entries = inventory.get("entries") if isinstance(inventory, dict) else None
    if not isinstance(entries, dict):
        raise ObservationError("candidate_boundary_invalid")
    return entries


def _literal_license(manifest: bytes) -> tuple[str | None, str | None]:
    try:
        package = tomllib.loads(manifest.decode("utf-8")).get("package")
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ObservationError("package_manifest_invalid") from error
    if not isinstance(package, dict):
        raise ObservationError("package_manifest_invalid")
    license_value = package.get("license")
    license_file = package.get("license-file")
    if license_value == {"workspace": True}:
        license_value = None
    if license_file == {"workspace": True}:
        license_file = None
    if license_value is not None and not isinstance(license_value, str):
        raise ObservationError("package_manifest_invalid")
    if license_file is not None and not isinstance(license_file, str):
        raise ObservationError("package_manifest_invalid")
    return license_value, license_file


def _license_candidates(members: list[tarfile.TarInfo]) -> list[tarfile.TarInfo]:
    result: list[tarfile.TarInfo] = []
    for member in members:
        pure = PurePosixPath(member.name)
        if pure.is_absolute() or ".." in pure.parts or member.issym() or member.islnk() or not member.isfile():
            raise ObservationError("crate_archive_unsafe")
        basename = pure.name.upper()
        if basename.startswith(LICENSE_PREFIXES):
            result.append(member)
    if len(result) > MAX_LICENSE_FILES_PER_PACKAGE:
        raise ObservationError("license_material_budget_exceeded")
    return sorted(result, key=lambda item: item.name)


def _registry_material(cache_root: Path, package: dict[str, Any], lock: dict[tuple[str, str, str], dict[str, Any]]) -> dict[str, Any]:
    name = package["name"]
    version = package["version"]
    source = package["source"]
    lock_entry = lock.get((name, version, source))
    if lock_entry is None or not isinstance(lock_entry.get("checksum"), str):
        raise ObservationError("compiled_package_not_in_lock")
    checksum = _hex(lock_entry["checksum"])
    candidates = list(cache_root.glob(f"*/{name}-{version}.crate"))
    if len(candidates) != 1:
        raise ObservationError("compiled_registry_archive_missing")
    archive_path = candidates[0]
    if archive_path.is_symlink() or not archive_path.is_file() or archive_path.stat().st_size <= 0 or archive_path.stat().st_size > MAX_CRATE_BYTES:
        raise ObservationError("compiled_registry_archive_missing")
    payload = archive_path.read_bytes()
    if sha256(payload) != checksum:
        raise ObservationError("registry_archive_checksum_mismatch")
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            members = archive.getmembers()
            manifests = [member for member in members if PurePosixPath(member.name).name == "Cargo.toml" and member.isfile()]
            if len(manifests) != 1:
                raise ObservationError("crate_manifest_ambiguous")
            manifest_stream = archive.extractfile(manifests[0])
            if manifest_stream is None:
                raise ObservationError("crate_manifest_ambiguous")
            manifest = manifest_stream.read()
            literal_license, literal_license_file = _literal_license(manifest)
            materials = []
            total = 0
            prefix = PurePosixPath(manifests[0].name).parent
            for member in _license_candidates(members):
                stream = archive.extractfile(member)
                if stream is None:
                    raise ObservationError("crate_archive_unsafe")
                content = stream.read()
                total += len(content)
                if total > MAX_LICENSE_BYTES_PER_PACKAGE:
                    raise ObservationError("license_material_budget_exceeded")
                relative = PurePosixPath(member.name).relative_to(prefix).as_posix()
                materials.append({"path": relative, "sha256": sha256(content), "bytes": len(content)})
    except (tarfile.TarError, ValueError) as error:
        raise ObservationError("crate_archive_invalid") from error
    return {
        "identity": f"registry:{name}@{version}#{checksum}", "kind": "registry", "name": name,
        "version": version, "cargo_lock_checksum": checksum, "manifest_sha256": sha256(manifest),
        "literal_license": literal_license, "literal_license_file": literal_license_file,
        "license_materials": materials, "license_concluded": "NOASSERTION", "notice_requirement": "not_evaluated",
    }


def _workspace_material(source_root: Path, manifest_path: Path, boundary: dict[str, Any]) -> dict[str, Any]:
    try:
        relative_manifest = manifest_path.relative_to(source_root).as_posix()
        manifest = manifest_path.read_bytes()
    except (OSError, ValueError) as error:
        raise ObservationError("workspace_manifest_invalid") from error
    literal_license, literal_license_file = _literal_license(manifest)
    try:
        package = tomllib.loads(manifest.decode("utf-8")).get("package")
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ObservationError("workspace_manifest_invalid") from error
    if not isinstance(package, dict) or not isinstance(package.get("name"), str) or not isinstance(package.get("version"), str):
        raise ObservationError("workspace_manifest_invalid")
    boundary_entry = boundary.get(relative_manifest)
    if not isinstance(boundary_entry, dict):
        raise ObservationError("workspace_boundary_class_missing")
    required = {"rule", "class", "license", "provenance", "distribution"}
    if set(boundary_entry) != required:
        raise ObservationError("workspace_boundary_class_missing")
    return {
        "identity": f"workspace:{package['name']}@{package['version']}#{sha256(manifest)}", "kind": "workspace",
        "name": package["name"], "version": package["version"], "manifest_path": relative_manifest,
        "manifest_sha256": sha256(manifest), "literal_license": literal_license,
        "literal_license_file": literal_license_file, "boundary_class": boundary_entry,
        "license_materials": [], "license_concluded": "NOASSERTION", "notice_requirement": "not_evaluated",
    }


def _inside(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve(strict=True)
        root_resolved = root.resolve(strict=True)
    except OSError as error:
        raise ObservationError("compiler_artifact_manifest_invalid") from error
    return resolved != root_resolved and root_resolved in resolved.parents


def _registry_locator(
    manifest_path: Path, registry_source_root: Path, lock: dict[tuple[str, str], list[dict[str, Any]]]
) -> dict[str, Any]:
    if manifest_path.is_symlink() or not manifest_path.is_file() or not _inside(manifest_path, registry_source_root):
        raise ObservationError("compiler_artifact_manifest_outside_custody")
    try:
        manifest = manifest_path.read_bytes()
        package = tomllib.loads(manifest.decode("utf-8")).get("package")
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ObservationError("compiler_artifact_manifest_invalid") from error
    if not isinstance(package, dict) or not isinstance(package.get("name"), str) or not isinstance(package.get("version"), str):
        raise ObservationError("compiler_artifact_manifest_invalid")
    entries = lock.get((package["name"], package["version"]), [])
    if len(entries) != 1:
        raise ObservationError("compiled_registry_lock_ambiguous")
    entry = entries[0]
    source = entry.get("source")
    if not isinstance(source, str) or not source.startswith("registry+"):
        raise ObservationError("compiled_package_source_unsupported")
    return {"name": package["name"], "version": package["version"], "source": source}


def _one_build(cargo: str, source_root: Path, target_root: Path, cache_root: Path, registry_source_root: Path) -> dict[str, Any]:
    lock_entries, lock_sha = _load_lock(source_root)
    lock: dict[tuple[str, str, str], dict[str, Any]] = {}
    lock_by_name_version: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entry in lock_entries:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(key), str) for key in ("name", "version")):
            raise ObservationError("candidate_lock_invalid")
        source = entry.get("source")
        if isinstance(source, str):
            lock[(entry["name"], entry["version"], source)] = entry
            lock_by_name_version.setdefault((entry["name"], entry["version"]), []).append(entry)
    package_manifests, stderr_sha = _cargo_build_artifacts(cargo, source_root, target_root)
    boundary = _candidate_boundary(source_root)
    materials: list[dict[str, Any]] = []
    for package_id, manifest_path in sorted(package_manifests.items()):
        if _inside(manifest_path, source_root):
            materials.append(_workspace_material(source_root, manifest_path, boundary))
        else:
            registry_package = _registry_locator(manifest_path, registry_source_root, lock_by_name_version)
            materials.append(_registry_material(cache_root, registry_package, lock))
    if len({item["identity"] for item in materials}) != len(materials):
        raise ObservationError("canonical_package_identity_duplicate")
    canonical = json.dumps(materials, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"lock_sha256": lock_sha, "build_stderr_sha256": stderr_sha, "packages": materials, "package_set_sha256": sha256(canonical)}


def _rejected_report(
    *,
    commit: str,
    tree: str,
    lock_sha256: str,
    toolchain_sha256: str,
    cargo_version_sha256: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "selected_windows_build_license_material_rejected",
        "candidate": {
            "commit": commit,
            "tree": tree,
            "cargo_lock_sha256": lock_sha256,
            "toolchain_sha256": toolchain_sha256,
        },
        "build": {
            "cargo_version_sha256": cargo_version_sha256,
            "target": TARGET,
            "release": True,
            "locked": True,
            "offline": True,
            "fresh_builds": 2,
            "rejection_stage": "build_closure",
            "rejection_reason": reason,
        },
        "gates": {
            "selected_windows_build_package_set_observed": False,
            "license_declared_metadata_observed": False,
            "dependency_snapshot_ready": False,
            "dependencies_approved": False,
            "notices_approved": False,
            "first_party_approved": False,
            "release_sbom": False,
            "release_ready": False,
            "promotion_status": "blocked",
        },
        "non_claims": [
            "offline_build_closure_not_observed",
            "not_a_complete_cargo_lock_snapshot",
            "not_an_spdx_or_cyclonedx_sbom",
            "not_a_notice_or_legal_compatibility_decision",
            "not_a_first_party_promotion_or_release_approval",
        ],
    }


def observe(arguments: argparse.Namespace) -> dict[str, Any]:
    repository = arguments.repository.resolve()
    output = arguments.output.resolve()
    scratch_root = arguments.scratch_root.resolve()
    cache_root = arguments.cargo_home.resolve() / "registry" / "cache"
    registry_source_root = arguments.cargo_home.resolve() / "registry" / "src"
    if not _external(output) or output.exists() or not _external(scratch_root) or not repository.is_dir() or not cache_root.is_dir() or not registry_source_root.is_dir():
        raise ObservationError("external_custody_invalid")
    commit = _hex(arguments.candidate_commit, 40)
    tree = _git_text(repository, "rev-parse", f"{commit}^{{tree}}")
    if _git_text(repository, "cat-file", "-t", commit) != "commit":
        raise ObservationError("candidate_identity_invalid")
    archive = _run(
        ["git", "-C", str(repository), "archive", "--format=tar", commit],
        failure="candidate_archive_command_failed",
    ).stdout
    cargo_version = _run([arguments.cargo, "--version"], failure="cargo_unavailable").stdout
    toolchain = _archive_member(repository, commit, "rust-toolchain.toml")
    expected_lock_sha = sha256(_archive_member(repository, commit, "Cargo.lock"))
    scratch_root.mkdir(parents=True, exist_ok=False)
    try:
        runs = []
        rejected_reasons = []
        for label in ("a", "b"):
            source_root = scratch_root / f"source-{label}"
            target_root = scratch_root / f"target-{label}"
            source_root.mkdir()
            _safe_extract(archive, source_root)
            try:
                result = _one_build(arguments.cargo, source_root, target_root, cache_root, registry_source_root)
            except ObservationError as error:
                rejected_reasons.append(str(error))
                continue
            if result["lock_sha256"] != expected_lock_sha:
                raise ObservationError("candidate_lock_mismatch")
            runs.append(result)
        if rejected_reasons:
            if len(rejected_reasons) != 2 or len(set(rejected_reasons)) != 1:
                raise ObservationError("fresh_build_rejection_mismatch")
            report = _rejected_report(
                commit=commit,
                tree=tree,
                lock_sha256=expected_lock_sha,
                toolchain_sha256=sha256(toolchain),
                cargo_version_sha256=sha256(cargo_version),
                reason=rejected_reasons[0],
            )
            output.write_bytes(json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
            return report
        if runs[0]["package_set_sha256"] != runs[1]["package_set_sha256"] or runs[0]["packages"] != runs[1]["packages"]:
            raise ObservationError("fresh_build_closure_mismatch")
        package_counts = {
            "total": len(runs[0]["packages"]),
            "registry": sum(item["kind"] == "registry" for item in runs[0]["packages"]),
            "workspace": sum(item["kind"] == "workspace" for item in runs[0]["packages"]),
        }
        report = {
            "schema": SCHEMA,
            "status": "selected_windows_build_license_material_observed_not_concluded",
            "candidate": {"commit": commit, "tree": tree, "cargo_lock_sha256": expected_lock_sha, "toolchain_sha256": sha256(toolchain)},
            "build": {"cargo_version_sha256": sha256(cargo_version), "target": TARGET, "release": True, "locked": True, "offline": True, "fresh_builds": 2},
            "package_set": {"sha256": runs[0]["package_set_sha256"], "counts": package_counts, "build_a_stderr_sha256": runs[0]["build_stderr_sha256"], "build_b_stderr_sha256": runs[1]["build_stderr_sha256"], "packages": runs[0]["packages"]},
            "gates": {"selected_windows_build_package_set_observed": True, "license_declared_metadata_observed": True, "dependency_snapshot_ready": False, "dependencies_approved": False, "notices_approved": False, "first_party_approved": False, "release_sbom": False, "release_ready": False, "promotion_status": "blocked"},
            "non_claims": ["license_concluded_NOASSERTION", "notice_requirement_not_evaluated", "not_a_complete_cargo_lock_snapshot", "not_an_spdx_or_cyclonedx_sbom", "not_a_notice_or_legal_compatibility_decision", "not_a_first_party_promotion_or_release_approval"],
        }
        output.write_bytes(json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
        return report
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--cargo", required=True)
    parser.add_argument("--cargo-home", type=Path, required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        result = observe(arguments)
        output = {"schema": SCHEMA, "status": result["status"]}
        if "package_set" in result:
            output["package_set_sha256"] = result["package_set"]["sha256"]
        print(json.dumps(output, sort_keys=True))
        return 0
    except ObservationError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
