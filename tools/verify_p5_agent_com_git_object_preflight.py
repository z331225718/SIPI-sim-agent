"""Materialize and verify the external-only P5 agent-com Git-object preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p5.agent-com-git-object-preflight.v1"
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "p5-agent-com-git-object-preflight.v1.yaml"
CANONICAL_ORIGIN = "https://github.com/z331225718/agent-com.git"
LICENSE_PATH = "LICENSE"
NOTICE_PATH = "NOTICE"
WORKBOOK_SUFFIXES = {".xls", ".xlsx", ".xlsm", ".ods"}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".mat", ".zip", ".npz", ".npy"}


class PreflightError(RuntimeError):
    pass


def _git(root: Path, *arguments: str, text: bool = False) -> str | bytes:
    completed = subprocess.run(["git", "-C", str(root), *arguments], check=False, capture_output=True)
    if completed.returncode:
        raise PreflightError("git_object_unavailable")
    return completed.stdout.decode("utf-8").strip() if text else completed.stdout


def _git_text(root: Path, *arguments: str) -> str:
    return str(_git(root, *arguments, text=True))


def _safe_path(path: object) -> bool:
    if not isinstance(path, str) or not path or "\\" in path or path.startswith("/"):
        return False
    return ".." not in PurePosixPath(path).parts


def _source_identity(root: Path) -> dict[str, str]:
    if _git_text(root, "config", "--get", "remote.origin.url") != CANONICAL_ORIGIN:
        raise PreflightError("canonical_origin_mismatch")
    if _git_text(root, "rev-parse", "--show-object-format") != "sha1":
        raise PreflightError("object_format_mismatch")
    if _git_text(root, "status", "--porcelain"):
        raise PreflightError("source_worktree_not_clean")
    commit = _git_text(root, "rev-parse", "HEAD")
    return {
        "canonical_origin": CANONICAL_ORIGIN,
        "commit": commit,
        "tree": _git_text(root, "rev-parse", f"{commit}^{{tree}}"),
        "object_format": "sha1",
    }


def _tree_entries(root: Path, commit: str) -> list[dict[str, Any]]:
    raw = bytes(_git(root, "ls-tree", "-r", "-z", "-l", commit))
    entries: list[dict[str, Any]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", maxsplit=1)
        mode, kind, oid, raw_size = metadata.decode("ascii").split(maxsplit=3)
        path = raw_path.decode("utf-8")
        if not _safe_path(path):
            raise PreflightError("unsafe_source_path")
        if mode == "160000" or kind == "commit":
            entries.append({
                "path": path,
                "git_kind": "gitlink",
                "git_oid": oid,
                "byte_length": None,
                "content_sha256": None,
                "path_class": "unresolved_gitlink",
                "material_role": "quarantine",
                "license_evidence_status": "unresolved_gitlink",
                "action": "external_only_unresolved",
            })
            continue
        if mode != "100644" or kind != "blob" or raw_size == "-":
            raise PreflightError("unsupported_tree_entry")
        content = bytes(_git(root, "cat-file", "blob", f"{commit}:{path}"))
        if content.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
            path_class, role, evidence, action = (
                "unresolved_lfs_pointer",
                "quarantine",
                "unresolved_lfs_pointer",
                "external_only_unresolved",
            )
        else:
            path_class, role, evidence, action = _classify(path)
        entries.append({
            "path": path,
            "git_kind": "blob",
            "git_oid": oid,
            "byte_length": len(content),
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "path_class": path_class,
            "material_role": role,
            "license_evidence_status": evidence,
            "action": action,
        })
    if not entries or len({entry["path"] for entry in entries}) != len(entries):
        raise PreflightError("tree_coverage_invalid")
    return sorted(entries, key=lambda entry: entry["path"])


def _classify(path: str) -> tuple[str, str, str, str]:
    suffix = PurePosixPath(path).suffix.lower()
    if path == LICENSE_PATH:
        return "license_notice", "license_evidence", "root_mit_license_observed", "evidence_only"
    if path == "LICENSE-MANIFEST.md":
        return "license_notice", "license_evidence", "license_manifest_observed_not_dispositive", "evidence_only"
    if path.startswith("matlab_src/"):
        return "matlab_source", "oracle_only", "root_mit_observed_not_promoted", "external_only"
    if suffix in WORKBOOK_SUFFIXES:
        return "workbook_binary", "quarantine", "path_requires_asset_review", "external_only"
    if path.startswith(("fixtures/", "benchmarks/", "artifacts/")) or suffix in BINARY_SUFFIXES:
        return "data_fixture", "oracle_only", "path_requires_asset_review", "external_only"
    if path.startswith("src/") and suffix == ".py":
        return "source_code", "potential_mit_input", "root_mit_observed_not_promoted", "quarantine_review"
    if path.startswith(("tests/", "tools/")) and suffix == ".py":
        return "test_or_tool_source", "potential_mit_input", "root_mit_observed_not_promoted", "quarantine_review"
    if path.startswith("docs/") or suffix in {".md", ".html"}:
        return "documentation", "quarantine", "root_mit_observed_not_dispositive", "external_only"
    if path.startswith(".github/") or suffix in {".toml", ".lock", ".yml", ".yaml", ".json", ".txt"}:
        return "build_or_metadata", "quarantine", "root_mit_observed_not_dispositive", "external_only"
    return "unknown", "quarantine", "path_requires_review", "external_only"


def materialize_manifest(source_root: Path) -> dict[str, Any]:
    target = _source_identity(source_root)
    entries = _tree_entries(source_root, target["commit"])
    license_entry = next((entry for entry in entries if entry["path"] == LICENSE_PATH), None)
    if license_entry is None:
        raise PreflightError("root_license_missing")
    if b"MIT License" not in bytes(_git(source_root, "cat-file", "blob", f"{target['commit']}:{LICENSE_PATH}")):
        raise PreflightError("root_mit_license_not_observed")
    if any(entry["path"] == NOTICE_PATH for entry in entries):
        raise PreflightError("notice_presence_requires_explicit_review")
    return {
        "schema": SCHEMA,
        "status": "git_object_preflight",
        "promotion_eligible": False,
        "target": target,
        "license_evidence": {
            "root_license": {
            "path": license_entry["path"],
            "git_blob": license_entry["git_oid"],
            "content_sha256": license_entry["content_sha256"],
                "observed_spdx": "MIT",
            },
            "notice": {"status": "absent_at_commit", "path": NOTICE_PATH},
        },
        "entries": entries,
        "non_claims": [
            "The root MIT license is evidence only and does not promote any path to product or release input.",
            "MATLAB, data, workbooks, benchmarks, and external oracle materials remain external-only or quarantine.",
            "This record does not execute COM, MATLAB, workbooks, fixtures, or an oracle.",
        ],
    }


def _require_keys(value: object, keys: set[str], reason: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PreflightError(reason)
    return value


def verify_manifest(source_root: Path, manifest: object) -> dict[str, Any]:
    value = _require_keys(manifest, {"schema", "status", "promotion_eligible", "target", "license_evidence", "entries", "non_claims"}, "manifest_shape_invalid")
    if value["schema"] != SCHEMA or value["status"] != "git_object_preflight" or value["promotion_eligible"] is not False:
        raise PreflightError("manifest_status_invalid")
    expected = materialize_manifest(source_root)
    if value["target"] != expected["target"] or value["license_evidence"] != expected["license_evidence"]:
        raise PreflightError("target_or_license_anchor_mismatch")
    if value["entries"] != expected["entries"]:
        raise PreflightError("entry_coverage_or_identity_mismatch")
    if not isinstance(value["non_claims"], list) or len(value["non_claims"]) != 3 or not all(isinstance(item, str) and item for item in value["non_claims"]):
        raise PreflightError("non_claims_invalid")
    if any(entry["material_role"] == "product_input" or entry["action"] == "release_input" for entry in value["entries"]):
        raise PreflightError("forbidden_promotion")
    counts: dict[str, int] = {}
    for entry in value["entries"]:
        counts[entry["path_class"]] = counts.get(entry["path_class"], 0) + 1
    return {
        "schema": SCHEMA,
        "status": "git_object_preflight_passed",
        "target_commit": value["target"]["commit"],
        "path_count": len(value["entries"]),
        "path_class_counts": counts,
        "promotion_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.write_manifest:
            manifest = materialize_manifest(arguments.source_root)
            arguments.manifest.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=False), encoding="utf-8")
        else:
            manifest = yaml.safe_load(arguments.manifest.read_text(encoding="utf-8"))
        report = verify_manifest(arguments.source_root, manifest)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError, PreflightError, subprocess.SubprocessError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if arguments.report:
        arguments.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["status"] == "git_object_preflight_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
