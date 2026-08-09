"""Materialize and fail-close the current native Rust candidate source map."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.rust-candidate-source-map.v1"
KINDS = {"rust_source", "test", "build", "manifest", "doc", "generated", "asset"}
ASSESSMENTS = {"unknown", "direct_mit", "clean_room"}


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def _safe_path(value: object) -> bool:
    return isinstance(value, str) and bool(value) and "\\" not in value and not value.startswith("/") and not (len(value) >= 2 and value[0].isalpha() and value[1] == ":") and ".." not in value.split("/")


def _file_kind(path: str) -> str:
    if path.endswith("build.rs"):
        return "build"
    if path.endswith(".rs"):
        return "test" if "/tests/" in path else "rust_source"
    if path.endswith(("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "engine.lock")) or path.endswith((".toml", ".lock")):
        return "manifest"
    if path.endswith(("README.md", ".md")):
        return "doc"
    if "/fixtures/" in path:
        return "asset"
    return "asset"


def _native_git_entries(root: Path) -> dict[str, dict]:
    listing = subprocess.run(["git", "-C", str(root), "ls-files", "-s", "--", "native"], check=True, capture_output=True, text=True).stdout.splitlines()
    entries: dict[str, dict] = {}
    for line in listing:
        metadata, path = line.split("\t", 1)
        _mode, blob, _stage = metadata.split()
        payload = subprocess.run(["git", "-C", str(root), "cat-file", "blob", blob], check=True, capture_output=True).stdout
        entries[path] = {
            "path": path,
            "tracked_git_blob": {"algorithm": "sha1", "oid": blob},
            "content_sha256": hashlib.sha256(payload).hexdigest(),
            "file_kind": _file_kind(path),
            "boundary_class": "quarantine",
            "assessment": "unknown",
            "evidence_status": "pending",
            "direct_mit_sources": [],
            "clean_room_evidence": [],
            "notes": "No promotion: exact direct-MIT or strict clean-room evidence has not been recorded.",
        }
    return entries


def _load(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("pyyaml is unavailable")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("source map must be a YAML object")
    return document


def verify_document(document: object, root: Path = ROOT) -> dict:
    blockers: list[str] = []
    if not _exact(document, {"schema", "status", "boundary_ref", "inventory", "non_claims"}):
        return {"valid": False, "blockers": ["source map has unknown or missing top-level fields"]}
    if document["schema"] != SCHEMA or document["status"] != "provisional":
        return {"valid": False, "blockers": ["source map schema or status mismatch"]}
    boundary = document["boundary_ref"]
    if not _exact(boundary, {"path", "sha256", "status"}) or not _safe_path(boundary.get("path")) or boundary.get("status") != "provisional":
        blockers.append("boundary_ref is invalid")
    else:
        path = root / boundary["path"]
        if not path.is_file() or not _hex(boundary["sha256"], 64) or hashlib.sha256(path.read_bytes()).hexdigest() != boundary["sha256"]:
            blockers.append("boundary_ref hash mismatch")
    expected = _native_git_entries(root)
    inventory = document["inventory"]
    if not _exact(inventory, {"source", "entries"}) or inventory.get("source") != "git_ls_files_native" or not isinstance(inventory.get("entries"), dict):
        blockers.append("inventory is invalid")
        entries = {}
    else:
        entries = inventory["entries"]
        if entries != expected:
            blockers.append("inventory entries do not match current native Git objects")
    for path, entry in entries.items():
        keys = {"path", "tracked_git_blob", "content_sha256", "file_kind", "boundary_class", "assessment", "evidence_status", "direct_mit_sources", "clean_room_evidence", "notes"}
        if not _safe_path(path) or not _exact(entry, keys):
            blockers.append(f"{path}: entry is invalid")
            continue
        if entry["boundary_class"] != "quarantine" or entry["assessment"] not in ASSESSMENTS or entry["file_kind"] not in KINDS or not _hex(entry["content_sha256"], 64):
            blockers.append(f"{path}: classification is invalid")
        if not _exact(entry["tracked_git_blob"], {"algorithm", "oid"}) or entry["tracked_git_blob"].get("algorithm") != "sha1" or not _hex(entry["tracked_git_blob"].get("oid"), 40):
            blockers.append(f"{path}: Git blob is invalid")
        if entry["assessment"] == "unknown" and (entry["evidence_status"] != "pending" or entry["direct_mit_sources"] or entry["clean_room_evidence"]):
            blockers.append(f"{path}: unknown assessment cannot claim promotion evidence")
        if not isinstance(entry["notes"], str) or not entry["notes"]:
            blockers.append(f"{path}: notes are required")
    if not isinstance(document["non_claims"], list) or not document["non_claims"] or not all(isinstance(item, str) and item for item in document["non_claims"]):
        blockers.append("non_claims must be a non-empty string list")
    return {"valid": not blockers, "native_entry_count": len(expected), "unknown_count": sum(item.get("assessment") == "unknown" for item in entries.values()), "blockers": blockers}


def write_inventory(path: Path, root: Path) -> None:
    document = _load(path)
    document["inventory"] = {"source": "git_ls_files_native", "entries": _native_git_entries(root)}
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, default=ROOT / "rust-candidate-source-map.v1.yaml")
    parser.add_argument("--write-inventory", action="store_true")
    args = parser.parse_args()
    try:
        if args.write_inventory:
            write_inventory(args.map, ROOT)
        report = verify_document(_load(args.map))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
