"""Read-only recovery audit for the pinned scikit-rf AS-03 source.

The AS-03 oracle names a Git commit and tree, but the candidate repository does
not contain that Git database.  This tool searches local Git repositories and
local Python/uv package material without downloading or importing anything.  A
wheel or an extracted uv archive may prove that the three source leaves have
the expected bytes; it does not prove that the pinned Git commit and tree are
available.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Iterable, Iterator, Sequence


SCHEMA = "sipi.as03-skrf-custody-recovery.v1"
PINNED_VERSION = "2.0.1"
PINNED_COMMIT = "bd651e923cac6020de49a096e1d7e9b5f949f884"
PINNED_TREE = "e01dc798d1ba119357cc41e96802ac9aca83b9bc"
PINNED_SOURCES: dict[str, dict[str, object]] = {
    "skrf/network.py": {
        "blob": "be5a55e367628b888a39376b693e7a5368df45a9",
        "bytes": 291611,
        "sha256": "62d5bd5434eb4f2bb6fef2262dd02fac828f93b9742f7c900920fbf313c8b759",
    },
    "skrf/mathFunctions.py": {
        "blob": "ad356cd00d90799ed483d4efeff83bcffeb3674f",
        "bytes": 32637,
        "sha256": "7ff864b104b672ddcbd06b5fe7c6d6806040827b2d156732948d58a671010462",
    },
    "skrf/constants.py": {
        "blob": "2064f8b734e449f214c63f7977d83031483c10ff",
        "bytes": 5529,
        "sha256": "be3da422ceefb438b335f0e8dc0b8789a63bf2c6da2eec9ed7adbd52d7acfdf5",
    },
}
DIST_INFO = "scikit_rf-2.0.1.dist-info"
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_GIT_OUTPUT_BYTES = 128 * 1024 * 1024
MAX_WALK_ENTRIES = 1_000_000
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
WHEEL_NAME = re.compile(r"^scikit[-_]rf[-_]2\.0\.1(?:[-_.].*)?\.(?:whl|zip|tar|gz|bz2)$", re.IGNORECASE)
UV_HTTP_NAME = re.compile(r"^2\.0\.1-py3-none-any\.http$", re.IGNORECASE)
PRUNED_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".tox",
        "__pycache__",
        "node_modules",
        "target",
    }
)


class AuditError(RuntimeError):
    """Raised when a local audit input is malformed or exceeds its bound."""


def _normalise(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def _regular(path: Path, label: str, maximum: int = MAX_FILE_BYTES) -> bytes:
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise AuditError(f"{label} is not a regular file")
        if info.st_size > maximum:
            raise AuditError(f"{label} exceeds the byte bound")
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                chunks.append(chunk)
        payload = b"".join(chunks)
        if len(payload) != info.st_size:
            raise AuditError(f"{label} changed while being read")
        return payload
    except OSError as error:
        raise AuditError(f"cannot read {label}") from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git_blob_sha1(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _walk_files(root: Path) -> Iterator[Path]:
    """Walk without following links and without descending into build trees."""

    if not root.is_dir():
        return
    count = 0
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories[:] = [
            name
            for name in directories
            if name.lower() not in PRUNED_DIR_NAMES
            and not (Path(current) / name).is_symlink()
        ]
        for name in files:
            path = Path(current) / name
            if path.is_symlink():
                continue
            count += 1
            if count > MAX_WALK_ENTRIES:
                raise AuditError(f"scan root exceeds {MAX_WALK_ENTRIES} files")
            yield path


def _walk_directories(root: Path) -> Iterator[Path]:
    if not root.is_dir():
        return
    count = 0
    for current, directories, _files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        if (current_path / ".git").is_dir() or (current_path / ".git").is_file():
            yield current_path
        directories[:] = [
            name
            for name in directories
            if name.lower() not in PRUNED_DIR_NAMES
            and not (current_path / name).is_symlink()
        ]
        count += len(directories)
        if count > MAX_WALK_ENTRIES:
            raise AuditError(f"scan root exceeds directory bound")


def _run_git(repo: Path, args: Sequence[str], *, maximum: int = MAX_GIT_OUTPUT_BYTES) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-C", str(repo), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or len(result.stdout) > maximum:
        return None
    return result.stdout


def _git_text(repo: Path, args: Sequence[str]) -> str | None:
    payload = _run_git(repo, args)
    if payload is None:
        return None
    try:
        return payload.decode("utf-8", "strict").strip()
    except UnicodeDecodeError:
        return None


def _git_object_type(repo: Path, object_id: str) -> str | None:
    value = _git_text(repo, ["cat-file", "-t", object_id])
    return value if value in {"blob", "tree", "commit", "tag"} else None


def _git_path_hits(repo: Path) -> dict[str, object]:
    payload = _run_git(repo, ["rev-list", "--objects", "--all", "--reflog"])
    if payload is None:
        return {"available": False, "path_count": 0, "target_path_hits": []}
    hits: list[str] = []
    path_count = 0
    for raw in payload.splitlines():
        parts = raw.split(maxsplit=1)
        if len(parts) != 2:
            continue
        path_count += 1
        relative = parts[1].decode("utf-8", "replace")
        lowered = relative.lower()
        if any(name.lower() in lowered for name in PINNED_SOURCES) or "scikit-rf" in lowered or "scikit_rf" in lowered:
            hits.append(relative)
    return {"available": True, "path_count": path_count, "target_path_hits": sorted(set(hits))}


def _git_object_stats(repo: Path) -> dict[str, object]:
    payload = _run_git(repo, ["cat-file", "--batch-all-objects", "--batch-check"])
    if payload is None:
        return {"available": False, "object_count": 0, "counts": {}, "pinned_object_presence": {}}
    counts: dict[str, int] = {}
    object_count = 0
    for raw in payload.splitlines():
        parts = raw.split()
        if len(parts) != 3:
            continue
        object_id, kind, _size = parts
        object_count += 1
        name = kind.decode("ascii", "replace")
        counts[name] = counts.get(name, 0) + 1
    pinned = {
        "commit": any(
            raw.split()[0] == PINNED_COMMIT.encode("ascii")
            for raw in payload.splitlines()
            if len(raw.split()) == 3
        ),
        "tree": any(
            raw.split()[0] == PINNED_TREE.encode("ascii")
            for raw in payload.splitlines()
            if len(raw.split()) == 3
        ),
    }
    for relative, expected in PINNED_SOURCES.items():
        blob = str(expected["blob"])
        pinned[f"blob:{relative}"] = any(
            raw.split()[0].decode("ascii", "replace") == blob
            for raw in payload.splitlines()
            if len(raw.split()) == 3
        )
    return {
        "available": True,
        "object_count": object_count,
        "counts": counts,
        "pinned_object_presence": pinned,
    }


def git_inventory(repo: Path) -> dict[str, object]:
    """Inspect refs/reflogs and all Git objects without changing the repo."""

    repo = repo.resolve(strict=True)
    head = _git_text(repo, ["rev-parse", "HEAD^{commit}"])
    head_tree = _git_text(repo, ["rev-parse", "HEAD^{tree}"])
    commit_type = _git_object_type(repo, PINNED_COMMIT)
    tree_type = _git_object_type(repo, PINNED_TREE)
    exact_commit = commit_type == "commit"
    exact_tree = exact_commit and _git_text(repo, ["rev-parse", f"{PINNED_COMMIT}^{{tree}}"]) == PINNED_TREE
    leaves: dict[str, dict[str, object]] = {}
    for relative, expected in PINNED_SOURCES.items():
        object_id = _git_text(repo, ["rev-parse", f"{PINNED_COMMIT}:{relative}"]) if exact_commit else None
        size_text = _git_text(repo, ["cat-file", "-s", object_id]) if object_id else None
        leaves[relative] = {
            "object": object_id,
            "type": _git_object_type(repo, object_id) if object_id else None,
            "expected_blob": expected["blob"],
            "bytes": int(size_text) if size_text and size_text.isdigit() else None,
            "matches": exact_commit and object_id == expected["blob"] and size_text == str(expected["bytes"]),
        }
    path_hits = _git_path_hits(repo)
    object_stats = _git_object_stats(repo)
    return {
        "repo": _normalise(repo),
        "head": head,
        "head_tree": head_tree,
        "pinned_commit_type": commit_type,
        "pinned_tree_type": tree_type,
        "exact_pinned_commit": exact_commit,
        "exact_pinned_tree": exact_tree,
        "source_leaves_in_pinned_commit": leaves,
        "source_leaves_match": all(bool(item["matches"]) for item in leaves.values()),
        "refs_reflog": path_hits,
        "all_objects": object_stats,
    }


def discover_git_repositories(roots: Iterable[Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for root in roots:
        for candidate in _walk_directories(root.resolve()):
            key = _normalise(candidate).lower()
            found.setdefault(key, candidate)
    return [found[key] for key in sorted(found)]


def _package_root_for(path: Path, root: Path) -> Path | None:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    parts = relative.parts
    try:
        index = parts.index(DIST_INFO)
    except ValueError:
        return None
    if index == 0:
        return root
    return root.joinpath(*parts[:index])


def discover_package_roots(roots: Iterable[Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for root in roots:
        for path in _walk_files(root.resolve()):
            if path.name != "METADATA" or path.parent.name != DIST_INFO:
                continue
            candidate = _package_root_for(path, root.resolve())
            if candidate is not None and (candidate / "skrf").is_dir():
                found.setdefault(_normalise(candidate).lower(), candidate)
    return [found[key] for key in sorted(found)]


def _record_map(payload: bytes) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    try:
        rows = csv.reader(payload.decode("utf-8", "strict").splitlines())
        for row in rows:
            if len(row) != 3:
                continue
            relative, encoded, size = row
            normalized = relative.replace("\\", "/")
            digest: str | None = None
            if encoded.startswith("sha256="):
                try:
                    digest = base64.urlsafe_b64decode(encoded[7:] + "=").hex()
                except (ValueError, binascii.Error):
                    digest = None
            result[normalized] = {"digest": digest, "size": int(size) if size.isdigit() else None}
    except (UnicodeDecodeError, csv.Error):
        return {}
    return result


def package_inventory(package_root: Path) -> dict[str, object]:
    """Compare extracted wheel/uv source leaves against pinned Git leaf bytes."""

    package_root = package_root.resolve(strict=True)
    metadata_path = package_root / DIST_INFO / "METADATA"
    record_path = package_root / DIST_INFO / "RECORD"
    metadata = _regular(metadata_path, "scikit-rf METADATA").decode("utf-8", "replace")
    name = next((line.split(":", 1)[1].strip() for line in metadata.splitlines() if line.startswith("Name:")), None)
    version = next((line.split(":", 1)[1].strip() for line in metadata.splitlines() if line.startswith("Version:")), None)
    records = _record_map(_regular(record_path, "scikit-rf RECORD")) if record_path.is_file() else {}
    files: dict[str, dict[str, object]] = {}
    for relative, expected in PINNED_SOURCES.items():
        path = package_root / Path(relative)
        try:
            path.relative_to(package_root)
            payload = _regular(path, relative)
        except (AuditError, ValueError):
            files[relative] = {
                "present": False,
                "expected": expected,
                "record": records.get(relative),
            }
            continue
        actual_sha256 = _sha256(payload)
        actual = {
            "present": True,
            "bytes": len(payload),
            "sha256": actual_sha256,
            "git_blob_sha1": _git_blob_sha1(payload),
            "expected": expected,
            "bytes_match": len(payload) == expected["bytes"],
            "sha256_match": actual_sha256 == expected["sha256"],
            "blob_match": _git_blob_sha1(payload) == expected["blob"],
            "record": records.get(relative),
        }
        record = records.get(relative)
        actual["record_match"] = bool(
            record
            and record.get("digest") == actual_sha256
            and record.get("size") == len(payload)
        )
        files[relative] = actual
    source_match = all(
        bool(item.get("present"))
        and bool(item.get("bytes_match"))
        and bool(item.get("sha256_match"))
        and bool(item.get("blob_match"))
        for item in files.values()
    )
    return {
        "root": _normalise(package_root),
        "kind": "extracted_python_distribution",
        "metadata": {"name": name, "version": version, "version_match": name == "scikit-rf" and version == PINNED_VERSION},
        "source_leaves": files,
        "all_source_leaves_match": source_match and name == "scikit-rf" and version == PINNED_VERSION,
        "record_present": record_path.is_file(),
        "record_all_source_rows_match": all(bool(item.get("record_match")) for item in files.values()),
    }


def find_wheel_archives(roots: Iterable[Path]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for root in roots:
        for path in _walk_files(root.resolve()):
            is_wheel = WHEEL_NAME.fullmatch(path.name) is not None
            is_skrf_uv_metadata = UV_HTTP_NAME.fullmatch(path.name) is not None and path.parent.name.lower() == "scikit-rf"
            if not (is_wheel or is_skrf_uv_metadata):
                continue
            key = _normalise(path).lower()
            if key in seen:
                continue
            seen.add(key)
            payload = _regular(path, "wheel/cache metadata")
            record: dict[str, object] = {
                "path": _normalise(path),
                "name": path.name,
                "bytes": len(payload),
                "sha256": _sha256(payload),
                "kind": "wheel_archive" if path.suffix.lower() in {".whl", ".zip", ".gz", ".bz2", ".tar"} else "uv_http_cache_metadata",
            }
            if record["kind"] == "uv_http_cache_metadata":
                text = payload.decode("latin-1")
                matches = re.findall(r"(?i)(?:sha256|SHA256).{0,12}([0-9a-f]{64})", text)
                record["advertised_sha256"] = sorted(set(matches))
            records.append(record)
    return sorted(records, key=lambda item: str(item["path"]).lower())


def default_roots(workspace: Path) -> list[Path]:
    home = Path.home()
    candidates = [
        workspace,
        workspace.parent / "agent-spice",
        workspace.parent / "SIPI-m0-scratch",
        home / "AppData/Local/uv/cache",
        home / "AppData/Local/pip/cache",
    ]
    unique: dict[str, Path] = {}
    for candidate in candidates:
        if candidate.is_dir():
            unique.setdefault(_normalise(candidate).lower(), candidate)
    return [unique[key] for key in sorted(unique)]


def audit(roots: Iterable[Path]) -> dict[str, object]:
    roots = [Path(root).resolve(strict=True) for root in roots]
    repositories = [git_inventory(path) for path in discover_git_repositories(roots)]
    packages = [package_inventory(path) for path in discover_package_roots(roots)]
    archives = find_wheel_archives(roots)
    exact_git = any(
        bool(item["exact_pinned_commit"])
        and bool(item["exact_pinned_tree"])
        and bool(item["source_leaves_match"])
        for item in repositories
    )
    wheel_match = any(bool(item["all_source_leaves_match"]) for item in packages)
    if exact_git:
        status = "exact_pinned_git_custody_found"
    elif wheel_match:
        status = "partial_wheel_source_match_git_custody_missing"
    else:
        status = "pinned_skrf_custody_missing"
    return {
        "schema": SCHEMA,
        "version": 1,
        "status": status,
        "pinned": {
            "project": "scikit-rf",
            "version": PINNED_VERSION,
            "commit": PINNED_COMMIT,
            "tree": PINNED_TREE,
            "source_leaves": PINNED_SOURCES,
        },
        "scan": {"roots": [_normalise(root) for root in roots], "read_only": True, "network_used": False, "imports_used": False},
        "git_repositories": repositories,
        "package_trees": packages,
        "wheel_archives": archives,
        "assessment": {
            "complete_git_custody": exact_git,
            "offline_immutable_git_oracle": exact_git,
            "scoped_source_leaf_bytes_available": wheel_match or exact_git,
            "scoped_source_leaf_match_is_not_git_custody": True,
            "can_serve_scoped_offline_leaf_observation": wheel_match,
            "offline_runtime_execution_proven": False,
            "reason": (
                "Pinned commit/tree and every source leaf are available in a local Git database."
                if exact_git
                else "Extracted wheel/archive source leaves match the pinned leaf hashes, but no complete pinned Git commit/tree was found."
                if wheel_match
                else "Neither the pinned Git object nor matching extracted source leaves were found."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-root", action="append", type=Path, help="bounded local root; repeatable")
    parser.add_argument("--json-out", type=Path, help="write the JSON result to this local path")
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        roots = args.scan_root if args.scan_root else default_roots(args.workspace)
        result = audit(roots)
        payload = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(payload + "\n", encoding="utf-8", newline="\n")
        print(payload)
        return 0 if result["assessment"]["complete_git_custody"] else 1
    except (AuditError, OSError, ValueError) as error:
        print(f"AS-03 custody audit failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
