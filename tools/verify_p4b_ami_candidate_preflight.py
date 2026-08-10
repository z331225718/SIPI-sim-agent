"""Verify the quarantine-only P4B-01a AMI candidate preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tomllib
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.ami-candidate-quarantine-preflight.v1"
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "ami-candidate-quarantine-preflight.v1.yaml"
SOURCE_MAP = ROOT / "rust-candidate-source-map.v1.yaml"

AMI_PREFIX = "native/crates/sipi-ami"
CARRIER_PATHS = (
    "native/crates/sipi-circuit/Cargo.lock",
    "native/crates/sipi-circuit/Cargo.toml",
    "native/crates/sipi-circuit/src/ami_host_candidate.rs",
    "native/crates/sipi-circuit/src/main.rs",
    "native/crates/sipi-circuit/tests/ami_host_candidate.rs",
    "native/crates/sipi-circuit/tests/fixtures/ami_host_stub/Cargo.lock",
    "native/crates/sipi-circuit/tests/fixtures/ami_host_stub/Cargo.toml",
    "native/crates/sipi-circuit/tests/fixtures/ami_host_stub/src/lib.rs",
)
FORBIDDEN_SUFFIXES = {".dll", ".ami", ".ibs", ".whl", ".exe", ".pdb"}


class PreflightError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *arguments: str, text: bool = False) -> str | bytes:
    completed = subprocess.run(["git", "-C", str(root), *arguments], check=False, capture_output=True)
    if completed.returncode != 0:
        raise PreflightError("git_object_unavailable")
    return completed.stdout.decode("utf-8").strip() if text else completed.stdout


def git_text(root: Path, *arguments: str) -> str:
    return str(git(root, *arguments, text=True))


def blob_bytes(root: Path, commit: str, path: str) -> bytes:
    return bytes(git(root, "cat-file", "blob", f"{commit}:{path}"))


def object_record(root: Path, commit: str, path: str) -> dict[str, str]:
    content = blob_bytes(root, commit, path)
    return {
        "path": path,
        "git_blob": git_text(root, "rev-parse", f"{commit}:{path}"),
        "content_sha256": sha256(content),
    }


def target_paths(root: Path, commit: str) -> list[str]:
    ami_paths = git_text(root, "ls-tree", "-r", "--name-only", commit, "--", AMI_PREFIX).splitlines()
    paths = sorted([*ami_paths, *CARRIER_PATHS])
    if len(paths) != len(set(paths)) or not ami_paths:
        raise PreflightError("target_path_set_invalid")
    for path in paths:
        if not path.startswith("native/") or PurePosixPath(path).suffix.lower() in FORBIDDEN_SUFFIXES:
            raise PreflightError("forbidden_target_path")
        blob_bytes(root, commit, path)
    return paths


def path_role(path: str) -> str:
    roles = {
        f"{AMI_PREFIX}/Cargo.lock": "locked_dependency_manifest",
        f"{AMI_PREFIX}/Cargo.toml": "crate_manifest",
        f"{AMI_PREFIX}/README.md": "candidate_documentation",
        f"{AMI_PREFIX}/src/ami.rs": "candidate_parameter_module",
        f"{AMI_PREFIX}/src/contract.rs": "candidate_contract_module",
        f"{AMI_PREFIX}/src/host.rs": "candidate_dynamic_loader_module",
        f"{AMI_PREFIX}/src/lib.rs": "candidate_crate_root",
        "native/crates/sipi-circuit/Cargo.lock": "carrier_locked_dependency_manifest",
        "native/crates/sipi-circuit/Cargo.toml": "carrier_crate_manifest",
        "native/crates/sipi-circuit/src/ami_host_candidate.rs": "candidate_cli_transport_module",
        "native/crates/sipi-circuit/src/main.rs": "candidate_cli_dispatch_module",
        "native/crates/sipi-circuit/tests/ami_host_candidate.rs": "candidate_transport_test",
        "native/crates/sipi-circuit/tests/fixtures/ami_host_stub/Cargo.lock": "synthetic_stub_locked_manifest",
        "native/crates/sipi-circuit/tests/fixtures/ami_host_stub/Cargo.toml": "synthetic_stub_manifest",
        "native/crates/sipi-circuit/tests/fixtures/ami_host_stub/src/lib.rs": "synthetic_abi_stub_source",
    }
    try:
        return roles[path]
    except KeyError as error:
        raise PreflightError("unclassified_target_path") from error


def lock_packages(content: bytes) -> list[dict[str, Any]]:
    document = tomllib.loads(content.decode("utf-8"))
    packages = document.get("package")
    if not isinstance(packages, list):
        raise PreflightError("cargo_lock_invalid")
    result = []
    for package in packages:
        if not isinstance(package, dict) or not isinstance(package.get("name"), str) or not isinstance(package.get("version"), str):
            raise PreflightError("cargo_lock_invalid")
        result.append({key: package.get(key) for key in ("name", "version", "source", "checksum")})
    return sorted(result, key=lambda item: (item["name"], item["version"], item["source"] or ""))


def direct_dependencies(content: bytes) -> list[dict[str, Any]]:
    document = tomllib.loads(content.decode("utf-8"))
    dependencies = document.get("dependencies", {})
    if not isinstance(dependencies, dict):
        raise PreflightError("cargo_dependency_invalid")
    result = []
    for name, requested in sorted(dependencies.items()):
        if isinstance(requested, str):
            recorded: dict[str, Any] = {"version": requested}
        elif isinstance(requested, dict):
            recorded = {key: requested[key] for key in sorted(requested) if key in {"version", "path", "git", "registry", "package", "features", "default-features"}}
        else:
            raise PreflightError("cargo_dependency_invalid")
        if not recorded:
            raise PreflightError("cargo_dependency_invalid")
        result.append({"name": name, "requested": recorded})
    return result


def source_map_entries(root: Path) -> dict[str, dict[str, Any]]:
    document = yaml.safe_load((root / "rust-candidate-source-map.v1.yaml").read_text(encoding="utf-8"))
    inventory = document.get("inventory") if isinstance(document, dict) else None
    entries = inventory.get("entries") if isinstance(inventory, dict) else None
    if not isinstance(entries, dict):
        raise PreflightError("source_map_invalid")
    result: dict[str, dict[str, Any]] = {}
    for path, entry in entries.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise PreflightError("source_map_invalid")
        if path != entry["path"]:
            raise PreflightError("source_map_invalid")
        result[path] = entry
    return result


def materialize_manifest(root: Path) -> dict[str, Any]:
    commit = git_text(root, "rev-parse", "HEAD")
    tree = git_text(root, "rev-parse", f"{commit}^{{tree}}")
    paths = target_paths(root, commit)
    map_entries = source_map_entries(root)
    entries = []
    for path in paths:
        source_map = map_entries.get(path)
        if not isinstance(source_map, dict):
            raise PreflightError("source_map_entry_missing")
        entries.append({
            "target": object_record(root, commit, path),
            "path_role": path_role(path),
            "source_map": {
                "boundary_class": source_map.get("boundary_class"),
                "assessment": source_map.get("assessment"),
            },
        })
    crates = []
    for name, prefix in (("sipi-ami", AMI_PREFIX), ("agent-spice-sim-carrier", "native/crates/sipi-circuit")):
        toml_path = f"{prefix}/Cargo.toml"
        lock_path = f"{prefix}/Cargo.lock"
        crates.append({
            "id": name,
            "manifest": object_record(root, commit, toml_path),
            "lock": object_record(root, commit, lock_path),
            "direct_dependencies": direct_dependencies(blob_bytes(root, commit, toml_path)),
            "locked_packages": lock_packages(blob_bytes(root, commit, lock_path)),
            "license_notice_status": "pending_p0_06_review",
        })
    return {
        "schema": SCHEMA,
        "status": "quarantine_preflight",
        "promotion_eligible": False,
        "target": {"commit": commit, "tree": tree, "object_format": "sha1"},
        "entries": entries,
        "dependency_closures": crates,
        "observed_exposures": [
            {"path": f"{AMI_PREFIX}/src/host.rs", "category": "dynamic_loader", "identifier": "AmiDll"},
            {"path": f"{AMI_PREFIX}/src/host.rs", "category": "host_lifecycle", "identifier": "AmiModel"},
            {"path": "native/crates/sipi-circuit/src/ami_host_candidate.rs", "category": "candidate_cli_transport", "identifier": "ami-host-candidate"},
            {"path": "native/crates/sipi-circuit/src/ami_host_candidate.rs", "category": "host_lifecycle", "identifier": "Init_GetWave_Close"},
        ],
        "standards": [
            {"title": "IBIS Specification", "version": "6.1", "source_url": "https://ibis.org/ver6.1/ver6_1.pdf", "status": "public_reference_not_implementation_material"},
            {"title": "IBIS Algorithmic Modeling Interface", "version": "5.1", "source_url": "https://www.ibis.org/editorial_wip/IBIS_Section_10_rc02.pdf", "status": "public_reference_not_implementation_material"},
        ],
        "non_claims": [
            "This record does not promote any source, dependency, route, or asset.",
            "This record does not establish host runtime behavior or a release conclusion.",
            "This record does not include vendor assets, build outputs, or source excerpts.",
        ],
    }


def safe_path(path: Any) -> bool:
    return isinstance(path, str) and path.startswith("native/") and ".." not in PurePosixPath(path).parts and not Path(path).is_absolute()


def verify_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "quarantine_preflight" or manifest.get("promotion_eligible") is not False:
        raise PreflightError("manifest_status_invalid")
    target = manifest.get("target")
    entries = manifest.get("entries")
    closures = manifest.get("dependency_closures")
    exposures = manifest.get("observed_exposures")
    standards = manifest.get("standards")
    if not isinstance(target, dict) or not isinstance(entries, list) or not isinstance(closures, list) or not isinstance(exposures, list) or not isinstance(standards, list):
        raise PreflightError("manifest_shape_invalid")
    commit = target.get("commit")
    if not isinstance(commit, str) or target.get("tree") != git_text(root, "rev-parse", f"{commit}^{{tree}}"):
        raise PreflightError("target_anchor_mismatch")
    paths = target_paths(root, commit)
    source_map = source_map_entries(root)
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("target"), dict):
            raise PreflightError("entry_invalid")
        record = entry["target"]
        path = record.get("path")
        if not safe_path(path) or path not in paths or path in seen:
            raise PreflightError("entry_set_mismatch")
        if PurePosixPath(path).suffix.lower() in FORBIDDEN_SUFFIXES or path_role(path) != entry.get("path_role"):
            raise PreflightError("entry_role_invalid")
        if record != object_record(root, commit, path):
            raise PreflightError("target_object_mismatch")
        mapped = source_map.get(path)
        if not isinstance(mapped, dict) or entry.get("source_map") != {"boundary_class": "quarantine", "assessment": "unknown"} or mapped.get("boundary_class") != "quarantine" or mapped.get("assessment") != "unknown":
            raise PreflightError("quarantine_mapping_invalid")
        seen.add(path)
    if set(paths) != seen:
        raise PreflightError("entry_set_mismatch")
    expected = materialize_manifest(root)["dependency_closures"]
    if closures != expected or any(item.get("license_notice_status") != "pending_p0_06_review" for item in closures if isinstance(item, dict)):
        raise PreflightError("dependency_closure_mismatch")
    valid_exposures = {(f"{AMI_PREFIX}/src/host.rs", "dynamic_loader", "AmiDll"), (f"{AMI_PREFIX}/src/host.rs", "host_lifecycle", "AmiModel"), ("native/crates/sipi-circuit/src/ami_host_candidate.rs", "candidate_cli_transport", "ami-host-candidate"), ("native/crates/sipi-circuit/src/ami_host_candidate.rs", "host_lifecycle", "Init_GetWave_Close")}
    observed = {(item.get("path"), item.get("category"), item.get("identifier")) for item in exposures if isinstance(item, dict)}
    if observed != valid_exposures or any(not safe_path(path) for path, _, _ in observed):
        raise PreflightError("exposure_invalid")
    for standard in standards:
        if not isinstance(standard, dict) or standard.get("status") != "public_reference_not_implementation_material" or not isinstance(standard.get("source_url"), str) or not standard["source_url"].startswith("https://"):
            raise PreflightError("standard_invalid")
    if not isinstance(manifest.get("non_claims"), list) or len(manifest["non_claims"]) < 3:
        raise PreflightError("non_claims_invalid")
    return {
        "schema": SCHEMA,
        "status": "quarantine_preflight_passed",
        "target_commit": commit,
        "path_count": len(paths),
        "dependency_package_count": sum(len(item["locked_packages"]) for item in closures),
        "promotion_eligible": False,
        "non_claims": ["No product promotion, runtime assertion, or release conclusion."],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    try:
        manifest = materialize_manifest(ROOT) if arguments.write_manifest else yaml.safe_load(arguments.manifest.read_text(encoding="utf-8"))
        if arguments.write_manifest:
            arguments.manifest.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        report = verify_manifest(ROOT, manifest)
    except (OSError, yaml.YAMLError, PreflightError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if arguments.report:
        arguments.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["status"] == "quarantine_preflight_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
