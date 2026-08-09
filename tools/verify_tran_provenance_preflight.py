"""Materialize and verify the P2-01 TRAN source/provenance preflight."""

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
SCHEMA = "sipi.tran-provenance-preflight.v1"
TARGET_PREFIX = "native/crates/sipi-circuit"
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "tran-provenance-preflight.v1.yaml"


class PreflightError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *arguments: str, text: bool = False) -> str | bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments], check=False, capture_output=True
    )
    if completed.returncode != 0:
        raise PreflightError("git_object_unavailable")
    return completed.stdout.decode("utf-8").strip() if text else completed.stdout


def git_text(root: Path, *arguments: str) -> str:
    return str(git(root, *arguments, text=True))


def blob_bytes(root: Path, commit: str, path: str) -> bytes:
    return bytes(git(root, "cat-file", "blob", f"{commit}:{path}"))


def tree_entries(root: Path, commit: str, prefix: str) -> dict[str, dict[str, str]]:
    data = bytes(git(root, "ls-tree", "-r", "-z", commit, "--", prefix))
    entries: dict[str, dict[str, str]] = {}
    for record in data.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split(" ", 2)
        path = raw_path.decode("utf-8")
        if kind != "blob" or not path.startswith(f"{prefix}/"):
            raise PreflightError("invalid_tree_entry")
        entries[path] = {"mode": mode, "oid": oid}
    return entries


def object_record(root: Path, commit: str, path: str, oid: str | None = None) -> dict[str, str]:
    content = blob_bytes(root, commit, path)
    return {
        "path": path,
        "git_blob": oid or git_text(root, "rev-parse", f"{commit}:{path}"),
        "content_sha256": sha256(content),
    }


def optional_object_record(root: Path, commit: str, path: str) -> dict[str, Any]:
    try:
        return {"status": "present", **object_record(root, commit, path)}
    except PreflightError:
        return {"status": "absent_at_commit", "path": path}


def dependency_tables(document: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    result: list[tuple[str, dict[str, Any]]] = []
    for name, value in document.items():
        if name in {"dependencies", "build-dependencies", "dev-dependencies"} and isinstance(value, dict):
            result.append((name, value))
        elif isinstance(value, dict):
            result.extend(dependency_tables(value))
    return result


def direct_dependencies(content: bytes) -> list[dict[str, Any]]:
    document = tomllib.loads(content.decode("utf-8"))
    dependencies: list[dict[str, Any]] = []
    for kind, table in dependency_tables(document):
        for name, requested in sorted(table.items()):
            if isinstance(requested, str):
                source = {"version": requested}
            elif isinstance(requested, dict):
                source = {key: requested[key] for key in sorted(requested) if key in {"version", "path", "git", "registry", "package", "features", "default-features"}}
            else:
                raise PreflightError("cargo_dependency_invalid")
            dependencies.append({"kind": kind, "name": name, "requested": source})
    return sorted(dependencies, key=lambda item: (item["kind"], item["name"]))


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


def classify_file(path: str) -> str:
    suffix = PurePosixPath(path).suffix
    if suffix == ".rs":
        return "rust_source" if "/tests/" not in path and "/fixtures/" not in path else "test"
    if suffix in {".toml", ".lock"}:
        return "manifest"
    if suffix == ".md":
        return "doc"
    if suffix in {".ami", ".ibs"}:
        return "asset"
    return "build" if path.endswith("build.rs") else "unknown"


def materialize_manifest(target_root: Path, source_root: Path, source_commit: str) -> dict[str, Any]:
    target_commit = git_text(target_root, "rev-parse", "HEAD")
    target_tree = git_text(target_root, "rev-parse", "HEAD^{tree}")
    source_commit = git_text(source_root, "rev-parse", source_commit)
    source_tree = git_text(source_root, "rev-parse", f"{source_commit}^{{tree}}")
    origin = git_text(source_root, "remote", "get-url", "origin")
    target_entries = tree_entries(target_root, target_commit, TARGET_PREFIX)
    source_entries = tree_entries(source_root, source_commit, TARGET_PREFIX)
    license_evidence = optional_object_record(source_root, source_commit, "LICENSE")
    notice_evidence = optional_object_record(source_root, source_commit, "NOTICE")
    entries = []
    for path, metadata in sorted(target_entries.items()):
        target = object_record(target_root, target_commit, path, metadata["oid"])
        source = source_entries.get(path)
        if source is not None:
            source_record = object_record(source_root, source_commit, path, source["oid"])
            if source_record["content_sha256"] == target["content_sha256"]:
                entries.append(
                    {
                        "target": target,
                        "file_kind": classify_file(path),
                        "boundary_class": "quarantine",
                        "assessment": "direct_mit_exact",
                        "relationship": "byte_identical",
                        "source": source_record,
                        "license_evidence": license_evidence,
                    }
                )
                continue
        entries.append(
            {
                "target": target,
                "file_kind": classify_file(path),
                "boundary_class": "quarantine",
                "assessment": "unknown",
                "reason": "source_path_absent_at_anchor" if not source_entries else "no_exact_source_evidence",
            }
        )
    cargo_toml = object_record(target_root, target_commit, f"{TARGET_PREFIX}/Cargo.toml", target_entries[f"{TARGET_PREFIX}/Cargo.toml"]["oid"])
    cargo_lock = object_record(target_root, target_commit, f"{TARGET_PREFIX}/Cargo.lock", target_entries[f"{TARGET_PREFIX}/Cargo.lock"]["oid"])
    return {
        "schema": SCHEMA,
        "status": "preflight",
        "target": {"commit": target_commit, "tree": target_tree, "object_format": "sha1", "prefix": TARGET_PREFIX},
        "source": {
            "canonical_origin": origin,
            "origin_sha256": sha256(origin.encode("utf-8")),
            "commit": source_commit,
            "tree": source_tree,
            "object_format": "sha1",
            "license_evidence": license_evidence,
            "notice_evidence": notice_evidence,
            "native_tree_status": "present" if source_entries else "absent_at_commit",
        },
        "cargo": {
            "target_toml": cargo_toml,
            "target_lock": cargo_lock,
            "direct_dependencies": direct_dependencies(blob_bytes(target_root, target_commit, cargo_toml["path"])),
            "lock_packages": lock_packages(blob_bytes(target_root, target_commit, cargo_lock["path"])),
            "source_cargo_status": "present" if source_entries else "absent_at_commit",
        },
        "entries": entries,
        "unresolved_actions": [
            "No quarantine entry is promoted by this preflight.",
            "Dependency license, NOTICE, SBOM, and distribution decisions remain pending P0-06 review.",
            "No TRAN profile, solver, numerical equivalence, or release conclusion follows from object identity.",
        ],
    }


def verify_manifest(target_root: Path, source_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "preflight":
        raise PreflightError("manifest_schema_invalid")
    target = manifest.get("target")
    source = manifest.get("source")
    cargo = manifest.get("cargo")
    entries = manifest.get("entries")
    if not all(isinstance(value, dict) for value in (target, source, cargo)) or not isinstance(entries, list):
        raise PreflightError("manifest_shape_invalid")
    target_commit = target.get("commit")
    source_commit = source.get("commit")
    if target_commit != git_text(target_root, "rev-parse", str(target_commit)) or target.get("tree") != git_text(target_root, "rev-parse", f"{target_commit}^{{tree}}"):
        raise PreflightError("target_anchor_mismatch")
    if source_commit != git_text(source_root, "rev-parse", str(source_commit)) or source.get("tree") != git_text(source_root, "rev-parse", f"{source_commit}^{{tree}}"):
        raise PreflightError("source_anchor_mismatch")
    origin = git_text(source_root, "remote", "get-url", "origin")
    if source.get("origin_sha256") != sha256(origin.encode("utf-8")) or source.get("canonical_origin") != origin:
        raise PreflightError("source_origin_mismatch")
    expected = tree_entries(target_root, str(target_commit), TARGET_PREFIX)
    seen: set[str] = set()
    exact_count = 0
    unknown_count = 0
    source_tree = tree_entries(source_root, str(source_commit), TARGET_PREFIX)
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("target"), dict):
            raise PreflightError("entry_invalid")
        record = entry["target"]
        path = record.get("path")
        if not isinstance(path, str) or path in seen or path not in expected:
            raise PreflightError("entry_set_mismatch")
        seen.add(path)
        actual = object_record(target_root, str(target_commit), path, expected[path]["oid"])
        if actual != record or entry.get("boundary_class") != "quarantine":
            raise PreflightError("target_object_mismatch")
        if entry.get("assessment") == "direct_mit_exact":
            source_record = entry.get("source")
            if not isinstance(source_record, dict) or source_tree.get(path) is None:
                raise PreflightError("exact_source_missing")
            actual_source = object_record(source_root, str(source_commit), path, source_tree[path]["oid"])
            if actual_source != source_record or source_record["content_sha256"] != record["content_sha256"]:
                raise PreflightError("exact_source_mismatch")
            if entry.get("relationship") != "byte_identical" or entry.get("license_evidence") != source.get("license_evidence"):
                raise PreflightError("exact_evidence_invalid")
            exact_count += 1
        elif entry.get("assessment") == "unknown":
            if entry.get("reason") not in {"source_path_absent_at_anchor", "no_exact_source_evidence", "missing_clean_room_attestation"}:
                raise PreflightError("unknown_reason_invalid")
            unknown_count += 1
        else:
            raise PreflightError("assessment_invalid")
    if set(expected) != seen:
        raise PreflightError("entry_set_mismatch")
    expected_cargo = materialize_manifest(target_root, source_root, str(source_commit))["cargo"]
    if cargo != expected_cargo:
        raise PreflightError("cargo_audit_mismatch")
    if source.get("license_evidence") != optional_object_record(source_root, str(source_commit), "LICENSE"):
        raise PreflightError("license_evidence_mismatch")
    if source.get("notice_evidence") != optional_object_record(source_root, str(source_commit), "NOTICE"):
        raise PreflightError("notice_evidence_mismatch")
    return {
        "schema": SCHEMA,
        "status": "preflight_passed",
        "target_commit": target_commit,
        "source_commit": source_commit,
        "path_count": len(entries),
        "direct_mit_exact_count": exact_count,
        "unknown_count": unknown_count,
        "license_status": source["license_evidence"]["status"],
        "notice_status": source["notice_evidence"]["status"],
        "source_native_tree_status": source["native_tree_status"],
        "non_claims": ["No promotion, legal conclusion, TRAN capability, numerical parity, or release conclusion."],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.write_manifest:
            manifest = materialize_manifest(ROOT, arguments.source_root, arguments.source_commit)
            arguments.manifest.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        else:
            manifest = yaml.safe_load(arguments.manifest.read_text(encoding="utf-8"))
        report = verify_manifest(ROOT, arguments.source_root, manifest)
    except (OSError, yaml.YAMLError, PreflightError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if arguments.report:
        arguments.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["status"] == "preflight_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
