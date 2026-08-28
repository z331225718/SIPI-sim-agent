"""Stage-1 custody and preparation gate for the PB-01/PB-02 matrix.

Formal replay is deliberately unavailable until this exact five-file harness is
introduced by one reviewed preparation commit.  The later evidence stage calls
the primitives here, but must not modify the preparation commit.
"""

from __future__ import annotations

import argparse
import ast
import io
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import stat
import subprocess
import tarfile
import tempfile
import threading
import time
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


PINNED_PARENT = "d44581ac8b10adbc8f803bb0292107ae3303e015"
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_FILES = 20_000
MAX_PROCESS_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_PB01_WIRE_BYTES = 256 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 120
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
PREP_PATHS = (
    "docs/baselines/pb-01-02-portable-matrix-inputs.v1.json",
    "tools/aggregate_pb_01_02_portable_matrix.py",
    "tools/run_pb_01_02_portable_matrix.py",
    "tools/test_verify_pb_01_02_portable_matrix.py",
    "tools/verify_pb_01_02_portable_matrix.py",
)
FORMAL_PATHS = (
    "docs/baselines/pb-01-02-portable-matrix-run-01.v1.json",
    "docs/baselines/pb-01-02-portable-matrix-run-02.v1.json",
    "docs/baselines/pb-01-02-portable-matrix-aggregate.v1.json",
    "docs/baselines/pb-01-02-portable-matrix.v1.yaml",
    "docs/baselines/audits/2026-08-27-pb-01-02-portable-matrix.md",
)
EXPECTED_CASE_IDS = (
    "pb01_nrz_analytic_line",
    "pb01_nrz_tx_ffe",
    "pb01_nrz_rx_dfe",
    "pb01_pam4_analytic_line",
    "pb01_duo_binary_analytic_line",
    "pb01_nrz_ctle",
    "pb02_nrz_impulse",
    "pb02_pam4_impulse",
    "pb02_duo_binary_impulse",
    "pb02_impulse_tx_rx_equalization",
    "pb02_impulse_analytic_ctle",
    "pb02_impulse_jitter_bathtub_analysis",
)


class CustodyError(RuntimeError):
    """A filesystem or Git custody invariant failed."""


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _bounded_process(command: list[str], *, timeout: int, stdout_limit: int, stdout_fd: int | None = None) -> tuple[int, bytes, bytes]:
    child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout_fd if stdout_fd is not None else subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = bytearray(), bytearray()
    errors: list[str] = []
    failed = threading.Event()

    def drain(name: str, stream: Any, limit: int) -> None:
        total = 0
        while chunk := stream.read1(65536):
            total += len(chunk)
            if total > limit:
                errors.append(f"{name} exceeds capture budget")
                failed.set()
                return
            (stdout if name == "stdout" else stderr).extend(chunk)

    threads = [threading.Thread(target=drain, args=("stderr", child.stderr, MAX_PROCESS_CAPTURE_BYTES), daemon=True)]
    if stdout_fd is None:
        threads.append(threading.Thread(target=drain, args=("stdout", child.stdout, stdout_limit), daemon=True))
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout
    timed_out = False
    while child.poll() is None:
        if stdout_fd is not None and os.fstat(stdout_fd).st_size > stdout_limit:
            errors.append("stdout exceeds capture budget")
            failed.set()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            child.kill()
            break
        if failed.wait(min(0.05, remaining)):
            child.kill()
            break
    child.wait()
    if stdout_fd is not None and os.fstat(stdout_fd).st_size > stdout_limit:
        errors.append("stdout exceeds capture budget")
    for thread in threads:
        thread.join()
    if child.stdout is not None:
        child.stdout.close()
    child.stderr.close()
    if timed_out:
        raise subprocess.TimeoutExpired(command, timeout)
    if errors:
        raise CustodyError(errors[0])
    return child.returncode, bytes(stdout), bytes(stderr)


def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    returncode, stdout, stderr = _bounded_process(
        ["git", "-C", str(repo), *args], timeout=GIT_TIMEOUT_SECONDS, stdout_limit=MAX_FILE_BYTES
    )
    if returncode != 0:
        detail = stderr.decode("utf-8", "replace").strip()
        raise CustodyError(f"git {' '.join(args)} failed: {detail}")
    return stdout if binary else stdout.decode("utf-8", "strict").strip()


def _json_loads(payload: bytes | str) -> Any:
    def reject_constant(value: str) -> Any:
        raise CustodyError(f"non-finite JSON constant rejected: {value}")

    value = json.loads(payload, parse_constant=reject_constant)
    nodes = 0

    def close(item: Any, depth: int = 0) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > 1_000_000 or depth > 128:
            raise CustodyError("JSON structure budget exceeded")
        if item is None or type(item) in (bool, int, str):
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise CustodyError("non-finite JSON number rejected")
            return
        if type(item) is list:
            for child in item:
                close(child, depth + 1)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                close(child, depth + 1)
            return
        raise CustodyError("unsupported JSON value type")

    close(value)
    return value


def safe_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise CustodyError("path must be a non-empty string without NUL")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or windows.root:
        raise CustodyError(f"absolute/anchored path rejected: {value!r}")
    if "\\" in value or any(part in ("", ".", "..") for part in posix.parts):
        raise CustodyError(f"non-canonical relative path rejected: {value!r}")
    return posix.as_posix()


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return (int(info.st_dev), int(info.st_ino), int(info.st_size), int(info.st_mtime_ns))


def _checked_root(root: Path) -> Path:
    original = root.absolute()
    for component in (*reversed(original.parents), original):
        info = os.lstat(component)
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise CustodyError("custody root has a link/reparse ancestor")
    info = os.lstat(original)
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise CustodyError("custody root must be a regular, non-link directory")
    resolved = original.resolve(strict=True)
    return resolved


def _checked_target(root: Path, relative: str, *, require_nlink_one: bool = True) -> tuple[Path, os.stat_result]:
    root_resolved = _checked_root(root)
    relative = safe_relative(relative)
    current = root_resolved
    for part in PurePosixPath(relative).parts:
        current = current / part
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise CustodyError(f"link/reparse component rejected: {relative}")
    resolved = current.resolve(strict=True)
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise CustodyError(f"path escaped custody root: {relative}")
    info = os.lstat(current)
    if not stat.S_ISREG(info.st_mode) or int(info.st_nlink) < 1 or require_nlink_one and int(info.st_nlink) != 1:
        raise CustodyError(f"file must be regular/non-link/nlink1: {relative}")
    return current, info


def secure_read(root: Path, relative: str, limit: int = MAX_FILE_BYTES, *, require_nlink_one: bool = True) -> tuple[bytes, dict[str, Any]]:
    """Read once through one descriptor and prove pre/fd/post identity."""
    if type(limit) is not int or limit < 0:
        raise CustodyError("read limit must be a non-negative integer")
    target, pre = _checked_target(root, relative, require_nlink_one=require_nlink_one)
    if pre.st_size > limit:
        raise CustodyError(f"file exceeds read budget: {relative}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags)
    try:
        opened = os.fstat(fd)
        if _identity(opened) != _identity(pre) or int(opened.st_nlink) != int(pre.st_nlink):
            raise CustodyError(f"file changed before descriptor read: {relative}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise CustodyError(f"file exceeds read budget: {relative}")
        after_fd = os.fstat(fd)
    finally:
        os.close(fd)
    post = os.lstat(target)
    if _identity(pre) != _identity(after_fd) or _identity(pre) != _identity(post):
        raise CustodyError(f"file changed during read: {relative}")
    if stat.S_ISLNK(post.st_mode) or _is_reparse(post) or int(post.st_nlink) != int(pre.st_nlink) or require_nlink_one and int(post.st_nlink) != 1:
        raise CustodyError(f"post-read custody failed: {relative}")
    payload = b"".join(chunks)
    return payload, {
        "path": safe_relative(relative),
        "bytes": len(payload),
        "sha256": sha256(payload),
        "regular": True,
        "nonlink": True,
        "nlink": int(post.st_nlink),
        "single_handle_read": True,
        "pre_identity": list(_identity(pre)),
        "post_identity": list(_identity(post)),
    }


def _ensure_output_parent(root: Path, relative: str) -> tuple[Path, Path]:
    root_resolved = _checked_root(root)
    relative = safe_relative(relative)
    if len(PurePosixPath(relative).parts) != 1:
        raise CustodyError("output must be a direct child of its tight output root")
    target = root_resolved / PurePosixPath(relative)
    return root_resolved, target


def exclusive_write(root: Path, relative: str, payload: bytes, limit: int = MAX_FILE_BYTES, *, mode: int = 0o600) -> dict[str, Any]:
    """Create a bounded artifact once, then verify it by a fresh secure read."""
    if not isinstance(payload, bytes) or len(payload) > limit:
        raise CustodyError("output payload is not bytes or exceeds budget")
    root_resolved, target = _ensure_output_parent(root, relative)
    if os.path.lexists(target):
        raise CustodyError(f"refusing to overwrite output: {relative}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, mode)
    opened = os.fstat(fd)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise CustodyError("short output write")
            view = view[written:]
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        current = os.lstat(target) if os.path.lexists(target) else None
        if current is not None and (current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino):
            os.unlink(target)
        raise
    else:
        os.close(fd)
    try:
        readback, fact = secure_read(root_resolved, safe_relative(relative), limit)
        if readback != payload:
            raise CustodyError("output readback differs from supplied payload")
    except BaseException:
        current = os.lstat(target) if os.path.lexists(target) else None
        if current is not None and (current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino):
            os.unlink(target)
        raise
    fact.update({"exclusive_create": True, "pre_absent": True, "readback_equal": True})
    return fact


def load_corpus(payload: bytes) -> dict[str, Any]:
    try:
        value = _json_loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CustodyError(f"invalid corpus JSON: {error}") from error
    if type(value) is not dict or set(value) != {
        "schema", "version", "purpose", "base_fixtures", "pb01_cases", "pb02_cases", "excluded_branches"
    }:
        raise CustodyError("corpus top-level schema is not exact")
    if value["schema"] != "sipi.pb-01-02-portable-matrix-inputs.v1" or type(value["version"]) is not int or value["version"] != 1:
        raise CustodyError("corpus schema/version invalid")
    fixtures = value["base_fixtures"]
    if type(fixtures) is not dict or set(fixtures) != {"PB-01", "PB-02"}:
        raise CustodyError("base fixture map invalid")
    for fixture in fixtures.values():
        safe_relative(fixture)
    cases = value["pb01_cases"] + value["pb02_cases"]
    ids: list[str] = []
    for case in cases:
        if type(case) is not dict or set(case) != {"id", "branches", "patch"}:
            raise CustodyError("case schema is not exact")
        if type(case["id"]) is not str or type(case["branches"]) is not list or type(case["patch"]) is not dict:
            raise CustodyError("case field type invalid")
        if not case["branches"] or any(type(item) is not str or not item for item in case["branches"]):
            raise CustodyError("case branches invalid")
        ids.append(case["id"])
    if tuple(ids) != EXPECTED_CASE_IDS or len(ids) != len(set(ids)):
        raise CustodyError("case IDs are not the unique closed matrix")
    exclusions = value["excluded_branches"]
    if type(exclusions) is not list:
        raise CustodyError("excluded branches must be a list")
    seen: set[str] = set()
    for exclusion in exclusions:
        if type(exclusion) is not dict or set(exclusion) != {"id", "status", "reason"}:
            raise CustodyError("excluded branch schema is not exact")
        if any(type(exclusion[key]) is not str or not exclusion[key] for key in exclusion):
            raise CustodyError("excluded branch field type invalid")
        if exclusion["id"] in seen:
            raise CustodyError("duplicate excluded branch")
        seen.add(exclusion["id"])
    class_pickle = next((item for item in exclusions if item["id"] == "legacy.result.class_pickle"), None)
    if not class_pickle or class_pickle["status"] != "implemented_not_covered_by_matrix":
        raise CustodyError("class pickle must be described as implemented but outside this matrix")
    return value


def validate_prep_commit(
    repo: Path,
    commit: str,
    expected_parent: str = PINNED_PARENT,
    *,
    require_live: bool = True,
) -> dict[str, Any]:
    """Prove a one-parent, first-introduction, tools-and-corpus-only commit."""
    resolved = str(_git(repo, "rev-parse", f"{commit}^{{commit}}"))
    tree = str(_git(repo, "rev-parse", f"{resolved}^{{tree}}"))
    parent = str(_git(repo, "rev-parse", f"{resolved}^"))
    parents = str(_git(repo, "show", "-s", "--format=%P", resolved)).split()
    if len(parents) != 1 or parents[0] != expected_parent or parent != expected_parent:
        raise CustodyError("preparation commit is not the direct single-parent child")
    raw_changed = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", expected_parent, resolved, binary=True)
    assert isinstance(raw_changed, bytes)
    changed = tuple(sorted(item.decode("utf-8", "strict") for item in raw_changed.split(b"\0") if item))
    if changed != PREP_PATHS:
        raise CustodyError(f"preparation changed paths are not exact: {changed!r}")
    files: dict[str, Any] = {}
    repo_root = repo.resolve(strict=True)
    for relative in PREP_PATHS:
        old = _git(repo, "ls-tree", "-z", expected_parent, "--", relative, binary=True)
        assert isinstance(old, bytes)
        if old:
            raise CustodyError(f"preparation path was not first introduced: {relative}")
        object_type = str(_git(repo, "cat-file", "-t", f"{resolved}:{relative}"))
        if object_type != "blob":
            raise CustodyError(f"preparation path is not a blob: {relative}")
        blob = str(_git(repo, "rev-parse", f"{resolved}:{relative}"))
        size_text = str(_git(repo, "cat-file", "-s", blob))
        if not size_text.isascii() or not size_text.isdigit() or int(size_text) > MAX_FILE_BYTES:
            raise CustodyError(f"preparation blob exceeds budget: {relative}")
        payload = _git(repo, "cat-file", "blob", blob, binary=True)
        assert isinstance(payload, bytes)
        if len(payload) != int(size_text):
            raise CustodyError(f"preparation blob size drift: {relative}")
        fact: dict[str, Any] = {"blob": blob, "bytes": len(payload), "sha256": sha256(payload)}
        if require_live:
            live, live_fact = secure_read(repo_root, relative)
            if live != payload:
                raise CustodyError(f"live file differs from preparation blob: {relative}")
            fact["live"] = live_fact
        files[relative] = fact
    for relative in FORMAL_PATHS:
        exists = _git(repo, "ls-tree", "-z", resolved, "--", relative, binary=True)
        assert isinstance(exists, bytes)
        if exists:
            raise CustodyError(f"formal evidence present in preparation commit: {relative}")
    corpus_bytes, _ = secure_read(repo_root, PREP_PATHS[0]) if require_live else (bytes(_git(repo, "cat-file", "blob", files[PREP_PATHS[0]]["blob"], binary=True)), {})
    load_corpus(corpus_bytes)
    return {
        "commit": resolved,
        "tree": tree,
        "parent": expected_parent,
        "changed_paths": list(PREP_PATHS),
        "first_introduction": True,
        "formal_paths_absent": True,
        "files": files,
    }


def _fresh_child(parent: Path, name: str) -> Path:
    parent = _checked_root(parent)
    name = safe_relative(name)
    if len(PurePosixPath(name).parts) != 1:
        raise CustodyError("fresh directory must be a direct child")
    target = parent / name
    try:
        os.mkdir(target)
    except FileExistsError as error:
        raise CustodyError(f"fresh directory already exists: {name}") from error
    return target


def _external_absent_root(path: Path, repositories: tuple[Path, ...], label: str) -> Path:
    original = path.absolute()
    if os.path.lexists(original):
        raise CustodyError(f"{label} must be absent")
    parent = _checked_root(original.parent)
    proposed = parent / original.name
    for repository in repositories:
        repository = repository.resolve(strict=True)
        if proposed == repository or proposed in repository.parents or repository in proposed.parents:
            raise CustodyError(f"{label} must be outside source repositories")
    return proposed


def _archive_write(root: Path, relative: str, payload: bytes) -> dict[str, Any]:
    """Exclusive archive extraction write with component and readback checks."""
    root = _checked_root(root)
    relative = safe_relative(relative)
    target = root / PurePosixPath(relative)
    current = root
    for part in PurePosixPath(relative).parts[:-1]:
        current /= part
        if os.path.lexists(current):
            info = os.lstat(current)
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                raise CustodyError("archive parent is not a plain directory")
        else:
            os.mkdir(current)
    if os.path.lexists(target):
        raise CustodyError(f"duplicate archive output: {relative}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise CustodyError("short archive output write")
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    readback, fact = secure_read(root, relative, max(len(payload), 1))
    if readback != payload:
        raise CustodyError("archive output readback mismatch")
    return fact


def _capture_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    capture_root: Path,
    label: str,
    timeout: int,
    limit: int = MAX_PROCESS_CAPTURE_BYTES,
    stdin_payload: bytes | None = None,
) -> dict[str, Any]:
    """Run with stdout/stderr handles created exclusively inside a fresh root."""
    if type(timeout) is not int or timeout <= 0:
        raise CustodyError("timeout must be a positive integer")
    if stdin_payload is not None and len(stdin_payload) > MAX_PB01_WIRE_BYTES:
        raise CustodyError("process stdin exceeds the explicit PB-01 wire budget")
    stdout_name, stderr_name = f"{label}.stdout", f"{label}.stderr"
    root = _checked_root(capture_root)
    child = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE if stdin_payload is not None else subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    errors: list[str] = []

    def drain(name: str, stream: Any) -> None:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                return
            if len(buffers[name]) + len(chunk) > limit:
                errors.append(f"{name} exceeds capture budget")
                child.kill()
                return
            buffers[name].extend(chunk)

    threads = [threading.Thread(target=drain, args=("stdout", child.stdout), daemon=True), threading.Thread(target=drain, args=("stderr", child.stderr), daemon=True)]
    for thread in threads:
        thread.start()
    writer: threading.Thread | None = None
    if stdin_payload is not None:
        def write_stdin() -> None:
            try:
                assert child.stdin is not None
                child.stdin.write(stdin_payload)
                child.stdin.close()
            except BrokenPipeError:
                pass
        writer = threading.Thread(target=write_stdin, daemon=True)
        writer.start()
    try:
        child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
        raise
    for thread in threads:
        thread.join()
    if writer is not None:
        writer.join()
    if errors:
        raise CustodyError(errors[0])
    stdout = bytes(buffers["stdout"])
    stderr = bytes(buffers["stderr"])
    stdout_fact = exclusive_write(root, stdout_name, stdout, limit)
    stderr_fact = exclusive_write(root, stderr_name, stderr, limit)
    process = child
    return {"exit_code": process.returncode, "stdout": stdout, "stderr": stderr, "stdout_fact": stdout_fact, "stderr_fact": stderr_fact}


def _archive_bytes(repo: Path, commit: str, root: Path, label: str, timeout: int) -> tuple[bytes, dict[str, Any]]:
    listing = _git(repo, "ls-tree", "-rl", "-z", commit, binary=True)
    assert isinstance(listing, bytes)
    entries = [item for item in listing.split(b"\0") if item]
    if len(entries) > MAX_ARCHIVE_FILES or len(listing) > MAX_FILE_BYTES:
        raise CustodyError("Git tree inventory exceeds archive budget")
    total = 0
    for entry in entries:
        header = entry.split(b"\t", 1)[0].split()
        if len(header) != 4 or header[0] not in {b"100644", b"100755"} or header[1] != b"blob" or not header[3].isdigit():
            raise CustodyError("Git tree contains a non-blob or malformed entry")
        total += int(header[3])
    if total + (len(entries) + 2) * 1024 > MAX_ARCHIVE_BYTES:
        raise CustodyError("Git tree payload cannot fit the archive budget")
    archive_name = f"{label}.tar"
    root = _checked_root(root)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    archive_path = root / archive_name
    archive_fd = os.open(archive_path, flags, 0o600)
    opened = os.fstat(archive_fd)
    cleanup_identity = (int(opened.st_dev), int(opened.st_ino))
    try:
        returncode, _, error = _bounded_process(
            ["git", "-c", "core.autocrlf=false", "-C", str(repo), "archive", "--format=tar", commit],
            timeout=timeout,
            stdout_limit=MAX_ARCHIVE_BYTES,
            stdout_fd=archive_fd,
        )
        os.fsync(archive_fd)
        os.close(archive_fd)
        archive_fd = -1
        if returncode:
            raise CustodyError(f"git archive failed: {error.decode('utf-8', 'replace')}")
    except BaseException:
        if archive_fd >= 0:
            os.close(archive_fd)
        try:
            current = os.lstat(archive_path)
            if (int(current.st_dev), int(current.st_ino)) == cleanup_identity:
                os.unlink(archive_path)
        except FileNotFoundError:
            pass
        raise
    payload, fact = secure_read(root, archive_name, MAX_ARCHIVE_BYTES)
    return payload, fact


def materialize_archive(repo: Path, commit: str, destination_parent: Path, name: str, timeout: int) -> tuple[Path, dict[str, Any]]:
    """Materialize only regular Git archive members with bounded exclusive writes."""
    resolved = str(_git(repo, "rev-parse", f"{commit}^{{commit}}"))
    tree = str(_git(repo, "rev-parse", f"{resolved}^{{tree}}"))
    payload, archive_fact = _archive_bytes(repo, resolved, destination_parent, name, timeout)
    destination = _fresh_child(destination_parent, f"{name}-tree")
    seen: set[str] = set()
    total = 0
    count = 0
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for member in archive:
            relative = safe_relative(member.name.rstrip("/"))
            folded = relative.casefold()
            if folded in seen:
                raise CustodyError(f"duplicate/case-colliding archive member: {relative}")
            seen.add(folded)
            if member.isdir():
                current = destination
                for part in PurePosixPath(relative).parts:
                    current /= part
                    if not os.path.lexists(current):
                        os.mkdir(current)
                    info = os.lstat(current)
                    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                        raise CustodyError("archive directory custody failed")
                continue
            if not member.isfile() or member.issym() or member.islnk():
                raise CustodyError(f"archive member kind rejected: {relative}")
            stream = archive.extractfile(member)
            if stream is None:
                raise CustodyError("archive member has no payload")
            data = stream.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES or stream.read(1):
                raise CustodyError(f"archive member exceeds budget: {relative}")
            total += len(data)
            count += 1
            if total > MAX_ARCHIVE_BYTES or count > MAX_ARCHIVE_FILES:
                raise CustodyError("archive total budget exceeded")
            _archive_write(destination, relative, data)
    return destination, {"commit": resolved, "tree": tree, "archive_sha256": hashlib.sha256(payload).hexdigest(), "archive": archive_fact, "files": count, "bytes": total, "regular_only": True, "exclusive_materialization": True}


def _resolve_tool(value: str, role: str, version_args: list[str], capture_root: Path, timeout: int) -> tuple[Path, dict[str, Any]]:
    literal = Path(value)
    found = literal if literal.is_file() else Path(resolved) if (resolved := shutil.which(value)) else None
    if found is None:
        raise CustodyError(f"{role} executable cannot be resolved")
    original = found.absolute()
    info = os.lstat(original)
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info) or int(info.st_nlink) != 1:
        raise CustodyError(f"{role} executable is not regular/nonlink/nlink1")
    executable = original.resolve(strict=True)
    payload, file_custody = secure_read(executable.parent, executable.name, MAX_FILE_BYTES * 16)
    actual_version_args = ["/dump", "/headers", str(executable)] if role == "link" else version_args
    result = _capture_command([str(executable), *actual_version_args], cwd=capture_root, env=os.environ.copy(), capture_root=capture_root, label=f"tool-{role}", timeout=timeout)
    if result["exit_code"] != 0:
        raise CustodyError(f"{role} version command failed")
    return executable, {"role": role, "executable": executable.name, "file_sha256": hashlib.sha256(payload).hexdigest(), "version_sha256": hashlib.sha256(result["stdout"] + b"\0" + result["stderr"]).hexdigest(), "version_exit": 0, "path_redacted": True, "file_custody_pre": file_custody}


def _execution_env(rustc: Path, cargo: Path, linker: Path | None = None) -> dict[str, str]:
    allowed = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "ProgramData", "ProgramFiles", "ProgramFiles(x86)", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "INCLUDE", "LIB", "LIBPATH", "VCINSTALLDIR", "VSINSTALLDIR", "WindowsSdkDir", "WindowsSDKVersion", "VCToolsInstallDir", "UCRTVersion", "UniversalCRTSdkDir"}
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env["RUSTC"] = str(rustc)
    system32 = Path(env.get("SYSTEMROOT", env.get("WINDIR", r"C:\Windows"))) / "System32"
    path_entries = [str(cargo.parent), str(rustc.parent)]
    if linker is not None:
        path_entries.append(str(linker.parent))
        tools = linker.parents[3]
        sdk = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits" / "10"
        versions = sorted((sdk / "Lib").glob("*"), reverse=True)
        version = next((item.name for item in versions if (item / "um" / "x64" / "kernel32.lib").is_file() and (item / "ucrt" / "x64").is_dir()), None)
        if version is None or not (tools / "lib" / "x64").is_dir() or not (tools / "include").is_dir():
            raise CustodyError("explicit MSVC/Windows SDK environment cannot be resolved from linker")
        env["LIB"] = os.pathsep.join((str(tools / "lib" / "x64"), str(sdk / "Lib" / version / "um" / "x64"), str(sdk / "Lib" / version / "ucrt" / "x64")))
        env["INCLUDE"] = os.pathsep.join((str(tools / "include"), str(sdk / "Include" / version / "ucrt"), str(sdk / "Include" / version / "shared"), str(sdk / "Include" / version / "um"), str(sdk / "Include" / version / "winrt")))
    path_entries.append(str(system32))
    env["PATH"] = os.pathsep.join(path_entries)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["CARGO_NET_OFFLINE"] = "true"
    env["CARGO_HOME"] = os.environ.get("CARGO_HOME", str(Path.home() / ".cargo"))
    env["UV_CACHE_DIR"] = os.environ.get("UV_CACHE_DIR", str(Path(env.get("LOCALAPPDATA", Path.home())) / "uv" / "cache"))
    env["UV_LINK_MODE"] = "copy"
    env["UV_OFFLINE"] = "1"
    env["UV_NO_CONFIG"] = "1"
    return env


def _yaml_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if type(value) in (int, float):
        return repr(value)
    if isinstance(value, str):
        return value
    raise CustodyError("unsupported YAML scalar patch")


def _patch_pb01(payload: bytes, patch: dict[str, Any]) -> bytes:
    text = payload.decode("utf-8", "strict")
    if set(patch) - {"scalars", "replacements"}:
        raise CustodyError("unknown PB-01 patch operation")
    for key, value in patch.get("scalars", {}).items():
        if type(key) is not str or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is None:
            raise CustodyError("unsafe PB-01 scalar key")
        pattern = re.compile(rf"(?m)^({re.escape(key)}:\s*).*$")
        text, count = pattern.subn(rf"\g<1>{_yaml_scalar(value)}", text)
        if count != 1:
            raise CustodyError(f"PB-01 scalar patch count is not one: {key}")
    for replacement in patch.get("replacements", []):
        if type(replacement) is not dict or set(replacement) - {"from", "to", "count"}:
            raise CustodyError("PB-01 replacement schema invalid")
        old, new = replacement.get("from"), replacement.get("to")
        expected = replacement.get("count", 1)
        if type(old) is not str or type(new) is not str or type(expected) is not int or expected <= 0 or text.count(old) != expected:
            raise CustodyError("PB-01 replacement count invalid")
        text = text.replace(old, new)
    return text.encode("utf-8")


def _deep_merge(base: Any, patch: Any) -> Any:
    if isinstance(base, dict) and isinstance(patch, dict):
        result = dict(base)
        for key, value in patch.items():
            result[key] = _deep_merge(result.get(key), value)
        return result
    return patch


def _patch_pb02(payload: bytes, patch: dict[str, Any]) -> bytes:
    try:
        base = _json_loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CustodyError("PB-02 base fixture is invalid JSON") from error
    if type(base) is not dict:
        raise CustodyError("PB-02 fixture root must be an object")
    return json.dumps(_deep_merge(base, patch), indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _npy_summary(payload: bytes) -> dict[str, Any]:
    if len(payload) < 10 or payload[:6] != b"\x93NUMPY":
        raise CustodyError("NPZ member is not NPY")
    major = payload[6]
    if major == 1:
        length, offset, codec = int.from_bytes(payload[8:10], "little"), 10, "latin-1"
    elif major in (2, 3):
        length, offset, codec = int.from_bytes(payload[8:12], "little"), 12, "utf-8"
    else:
        raise CustodyError("unsupported NPY version")
    data_offset = offset + length
    if data_offset > len(payload):
        raise CustodyError("truncated NPY header")
    try:
        header = ast.literal_eval(payload[offset:data_offset].decode(codec).strip())
    except (SyntaxError, ValueError, UnicodeDecodeError) as error:
        raise CustodyError("invalid NPY header") from error
    if type(header) is not dict or type(header.get("descr")) is not str or type(header.get("shape")) is not tuple or type(header.get("fortran_order")) is not bool:
        raise CustodyError("NPY header schema invalid")
    shape = tuple(header["shape"])
    if any(type(item) is not int or item < 0 for item in shape):
        raise CustodyError("NPY shape invalid")
    raw = payload[data_offset:]
    if header["descr"] not in {"<f8", "|f8", ">f8"} or len(raw) != math.prod(shape) * 8:
        raise CustodyError("NPY payload is not exact float64")
    f64 = raw if header["descr"] != ">f8" else b"".join(raw[index:index + 8][::-1] for index in range(0, len(raw), 8))
    return {"dtype": header["descr"], "shape": list(shape), "fortran_order": header["fortran_order"], "count": math.prod(shape), "f64_sha256": hashlib.sha256(f64).hexdigest()}


def _npz_summary(payload: bytes) -> dict[str, Any]:
    members: dict[str, Any] = {}
    seen: set[str] = set()
    total_uncompressed = 0
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload), "r")
    except zipfile.BadZipFile as error:
        raise CustodyError("invalid NPZ") from error
    with archive:
        for info in archive.infolist():
            name = safe_relative(info.filename)
            folded = name.casefold()
            if info.is_dir() or not name.endswith(".npy") or folded in seen:
                raise CustodyError("NPZ member set contains a bad or duplicate member")
            seen.add(folded)
            if info.file_size > MAX_FILE_BYTES or info.compress_size > MAX_FILE_BYTES:
                raise CustodyError("NPZ member exceeds budget")
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_ARCHIVE_BYTES or len(seen) > len(PB02_MEMBERS):
                raise CustodyError("NPZ cumulative member budget exceeded")
            data = archive.read(info)
            members[name] = _npy_summary(data)
    if tuple(sorted(members)) != PB02_MEMBERS:
        raise CustodyError("NPZ logical member set is not the exact native contract")
    return {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "uncompressed_bytes": total_uncompressed, "logical_members": dict(sorted(members.items())), "logical_sha256": hashlib.sha256(json.dumps(members, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def _artifact_file(root: Path, relative: str, limit: int = MAX_FILE_BYTES) -> tuple[bytes | None, dict[str, Any]]:
    try:
        payload, fact = secure_read(root, relative, limit)
    except (FileNotFoundError, NotADirectoryError):
        return None, {"path": relative, "present": False}
    return payload, {**fact, "present": True, "pre_absent": True}


def _inventory(root: Path) -> dict[str, Any]:
    root = _checked_root(root)
    entries: list[dict[str, Any]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise CustodyError(f"source inventory contains a link: {relative}")
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode) or int(info.st_nlink) != 1:
            raise CustodyError(f"source inventory contains a non-regular file: {relative}")
        payload, fact = secure_read(root, relative)
        total += len(payload)
        if len(entries) >= MAX_ARCHIVE_FILES or total > MAX_ARCHIVE_BYTES:
            raise CustodyError("source inventory exceeds budget")
        entries.append({"path": relative, "bytes": fact["bytes"], "sha256": fact["sha256"]})
    return {"entries": len(entries), "bytes": total, "sha256": hashlib.sha256(_canonical_json(entries)).hexdigest()}


PB01_ARRAYS = ("chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h", "chnl_s", "tx_out_s", "ctle_out_s", "dfe_out_s", "chnl_p", "tx_out_p", "ctle_out_p", "dfe_out_p")
PB02_MEMBERS = (
    "channel_impulse_v_per_v.npy", "channel_output_v.npy", "ctle_output_v.npy",
    "rx_ffe_impulse_v_per_v.npy", "rx_filter_impulse_v_per_v.npy", "rx_input_v.npy",
    "rx_output_v.npy", "symbols_v.npy", "time_s.npy", "tx_channel_impulse_v_per_v.npy",
    "tx_waveform_v.npy",
)
PB01_EXTRACTOR = r'''
import io, json, math, pickle, sys
class Restricted(pickle.Unpickler):
    def find_class(self, module, name): raise pickle.UnpicklingError("candidate globals forbidden")
names=json.loads(sys.argv[3],parse_constant=lambda value:(_ for _ in ()).throw(ValueError(value)))
wire=sys.stdin.buffer.read(); split=int.from_bytes(wire[:8],"little")
candidate_payload=wire[8:8+split]; oracle_payload=wire[8+split:]
def arrays(data, candidate):
    obj=Restricted(io.BytesIO(data)).load() if candidate else pickle.loads(data)
    if hasattr(obj,"the_data"): return obj.the_data.arrays, {"kind":"PyBertData_class_pickle"}
    if isinstance(obj,dict) and isinstance(obj.get("arrays"),dict):
        return obj["arrays"], {"kind":"python_pickle_dict","schema":obj.get("schema"),"item_names":obj.get("item_names"),"array_keys":sorted(obj["arrays"])}
    return {}, {"kind":"unknown"}
left,left_schema=arrays(candidate_payload,True); right,right_schema=arrays(oracle_payload,False)
rows=[]; blockers=[]
for name in names:
    a=left.get(name); b=right.get(name)
    if a is None or b is None: blockers.append(name+":missing"); continue
    a=a.reshape(-1).tolist() if hasattr(a,"reshape") else list(a)
    b=b.reshape(-1).tolist() if hasattr(b,"reshape") else list(b)
    a=[float(x) for x in a]; b=[float(x) for x in b]
    if len(a)!=len(b) or not all(math.isfinite(x) for x in a+b): blockers.append(name+":length_or_finite"); continue
    residual=max((abs(x-y) for x,y in zip(a,b)),default=0.0); scale=max([1.0]+[abs(x) for x in a+b]); tolerance=1e-7+1e-6*scale
    passed=residual<=tolerance
    if not passed: blockers.append(name+":numeric_drift")
    rows.append({"name":name,"length":len(a),"max_abs":residual,"scale":scale,"tolerance":tolerance,"passed":passed})
print(json.dumps({"candidate_schema":left_schema,"oracle_schema":right_schema,"rows":rows,"blockers":blockers},sort_keys=True,separators=(",",":")))
'''
MODULE_PROBE = r'''
import json, numpy, scipy, pybert
print(json.dumps({name:{"file":module.__file__,"version":getattr(module,"__version__",None)} for name,module in (("pybert",pybert),("numpy",numpy),("scipy",scipy))},sort_keys=True,separators=(",",":")))
'''


def _process_fact(result: dict[str, Any]) -> dict[str, Any]:
    return {"exit_code": result["exit_code"], "stdout": result["stdout_fact"], "stderr": result["stderr_fact"]}


def _probe_oracle_runtime(upstream_root: Path, venv_root: Path, run_root: Path, uv: Path, cargo: Path, rustc: Path, linker: Path, timeout: int) -> dict[str, Any]:
    capture = _fresh_child(run_root, "oracle-runtime-capture")
    env = _execution_env(rustc, cargo, linker)
    env["CARGO_TARGET_DIR"] = str(run_root / "upstream-target")
    env["UV_PROJECT_ENVIRONMENT"] = str(venv_root)
    result = _capture_command([str(uv), "run", "--project", str(upstream_root), "--frozen", "--offline", "--no-editable", "--extra", "native", "python", "-c", MODULE_PROBE], cwd=upstream_root, env=env, capture_root=capture, label="module-probe", timeout=timeout)
    if result["exit_code"] != 0:
        raise CustodyError("pinned oracle module probe failed")
    try:
        payload = _json_loads(result["stdout"])
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CustodyError("oracle module probe output invalid") from error
    if type(payload) is not dict or set(payload) != {"pybert", "numpy", "scipy"}:
        raise CustodyError("oracle module probe set invalid")
    modules: dict[str, Any] = {}
    roots = {"archive": upstream_root.resolve(strict=True), "venv": venv_root.resolve(strict=True)}
    for name, item in payload.items():
        if type(item) is not dict or set(item) != {"file", "version"} or type(item["file"]) is not str or type(item["version"]) is not str:
            raise CustodyError("oracle module identity schema invalid")
        path = Path(item["file"]).resolve(strict=True)
        allowed = ("archive", "venv") if name == "pybert" else ("venv",)
        owner = next((role for role in allowed if path == roots[role] or roots[role] in path.parents), None)
        if owner is None:
            raise CustodyError(f"oracle module escaped clean archive/venv: {name}")
        relative = path.relative_to(roots[owner]).as_posix()
        _, fact = secure_read(roots[owner], relative, MAX_FILE_BYTES)
        modules[name] = {"owner": owner, "relative_path": relative, "version": item["version"], "file": fact}
    return {"process": _process_fact(result), "modules": modules, "clean_archive_or_venv_only": True, "host_pythonpath_absent": True, "host_virtual_env_absent": True, "uv_offline_frozen_no_config": True, "uv_link_mode_copy": True, "uv_cache_explicit_lock_bound": True, "host_uv_flags_cleared": True}


def _case_result(case_id: str, candidate: dict[str, Any], oracle: dict[str, Any], comparison: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    status = "passed" if candidate["exit_code"] == oracle["exit_code"] == 0 and not blockers else "blocked"
    return {"id": case_id, "status": status, "blockers": blockers, "comparison": {"candidate_process": _process_fact(candidate), "oracle_process": _process_fact(oracle), **comparison}}


def _build_candidate(candidate_root: Path, run_root: Path, cargo: Path, rustc: Path, linker: Path, timeout: int) -> tuple[Path, dict[str, Any]]:
    target = _fresh_child(run_root, "candidate-target")
    env = _execution_env(rustc, cargo, linker)
    env["CARGO_TARGET_DIR"] = str(target)
    capture = _fresh_child(run_root, "build-capture")
    result = _capture_command([str(cargo), "build", "--offline", "--manifest-path", str(candidate_root / "crates/sipi-pybert-direct/Cargo.toml"), "--release", "--locked"], cwd=candidate_root, env=env, capture_root=capture, label="cargo-build", timeout=timeout)
    binary = target / "release" / ("sipi-pybert-direct.exe" if os.name == "nt" else "sipi-pybert-direct")
    if result["exit_code"] != 0:
        raise CustodyError("candidate build failed")
    binary_payload, cargo_binary_fact = secure_read(binary.parent, binary.name, MAX_FILE_BYTES * 16, require_nlink_one=False)
    execution_root = _fresh_child(run_root, "candidate-exec")
    published_fact = exclusive_write(execution_root, binary.name, binary_payload, MAX_FILE_BYTES * 16, mode=0o700)
    published = execution_root / binary.name
    return published, {"process": _process_fact(result), "cargo_binary_source": cargo_binary_fact, "binary_pre": published_fact, "env": {"rustc_explicit": True, "rustc_wrappers_cleared": True, "cargo_target_external": True, "cargo_offline": True, "path_closed": True, "cargo_home_explicit": True, "cargo_config_and_flags_cleared": True, "cargo_cache_lock_bound": True}}


def _run_matrix_case(
    *, case: dict[str, Any], lane: str, base: bytes, run_root: Path, candidate_root: Path,
    upstream_root: Path, binary: Path, cargo: Path, rustc: Path, uv: Path, timeout: int,
    linker: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    case_id = case["id"]
    case_root = _fresh_child(run_root, case_id)
    candidate_capture = _fresh_child(case_root, "candidate-capture")
    oracle_capture = _fresh_child(case_root, "oracle-capture")
    payload = _patch_pb01(base, case["patch"]) if lane == "PB-01" else _patch_pb02(base, case["patch"])
    suffix = "yaml" if lane == "PB-01" else "json"
    input_fact = exclusive_write(case_root, f"input.{suffix}", payload)
    env = _execution_env(rustc, cargo, linker)
    env["CARGO_TARGET_DIR"] = str(run_root / "candidate-target")
    upstream_env = _execution_env(rustc, cargo, linker)
    upstream_env["CARGO_TARGET_DIR"] = str(run_root / "upstream-target")
    upstream_env["UV_PROJECT_ENVIRONMENT"] = str(run_root / "upstream-venv")
    input_path = case_root / f"input.{suffix}"
    blockers: list[str] = []
    artifacts: list[dict[str, Any]] = []
    if lane == "PB-01":
        candidate_result = case_root / "candidate.pybert_data"
        oracle_result = case_root / "oracle.pybert_data"
        if os.path.lexists(candidate_result) or os.path.lexists(oracle_result):
            raise CustodyError("legacy result path must be absent")
        candidate = _capture_command([str(binary), "sim", str(input_path), "--results", str(candidate_result)], cwd=candidate_root, env=env, capture_root=candidate_capture, label="candidate", timeout=timeout)
        oracle = _capture_command([str(uv), "run", "--project", str(upstream_root), "--frozen", "--offline", "--no-editable", "--extra", "native", "pybert", "sim", str(input_path), "--results", str(oracle_result)], cwd=upstream_root, env=upstream_env, capture_root=oracle_capture, label="oracle", timeout=timeout)
        candidate_bytes, candidate_fact = _artifact_file(case_root, candidate_result.name, MAX_ARCHIVE_BYTES)
        oracle_bytes, oracle_fact = _artifact_file(case_root, oracle_result.name, MAX_ARCHIVE_BYTES)
        artifacts.extend([{**candidate_fact, "role": "candidate", "kind": "legacy_result", "case_id": case_id}, {**oracle_fact, "role": "oracle", "kind": "legacy_result", "case_id": case_id}])
        comparison: dict[str, Any] = {"kind": "pb01_selected_numeric_arrays", "class_pickle_covered_by_matrix": False, "candidate_schema": None, "oracle_schema": None, "rows": [], "blockers": []}
        if candidate["exit_code"] == oracle["exit_code"] == 0 and candidate_bytes is not None and oracle_bytes is not None:
            extract_capture = _fresh_child(case_root, "extract-capture")
            wire = len(candidate_bytes).to_bytes(8, "little") + candidate_bytes + oracle_bytes
            extracted = _capture_command([str(uv), "run", "--project", str(upstream_root), "--frozen", "--offline", "--no-editable", "--extra", "native", "python", "-c", PB01_EXTRACTOR, "candidate-bytes", "oracle-bytes", json.dumps(PB01_ARRAYS)], cwd=upstream_root, env=upstream_env, capture_root=extract_capture, label="extract", timeout=timeout, stdin_payload=wire)
            if extracted["exit_code"]:
                blockers.append("pickle_selected_array_extraction_failed")
            else:
                try:
                    comparison.update(_json_loads(extracted["stdout"]))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    blockers.append("pickle_selected_array_extraction_invalid")
                blockers.extend(comparison.get("blockers", []))
        else:
            blockers.append("candidate_or_oracle_process_or_artifact_missing")
    else:
        candidate_output = case_root / "candidate-output"
        oracle_output = case_root / "oracle-output"
        if os.path.lexists(candidate_output) or os.path.lexists(oracle_output):
            raise CustodyError("native output root must be absent")
        candidate = _capture_command([str(binary), "sim-native", str(input_path), "--output-dir", str(candidate_output)], cwd=candidate_root, env=env, capture_root=candidate_capture, label="candidate", timeout=timeout)
        oracle = _capture_command([str(uv), "run", "--project", str(upstream_root), "--frozen", "--offline", "--no-editable", "--extra", "native", "pybert", "sim-native", str(input_path), "--output-dir", str(oracle_output)], cwd=upstream_root, env=upstream_env, capture_root=oracle_capture, label="oracle", timeout=timeout)
        comparison = {"kind": "pb02_complete_meta_and_logical_npz", "candidate": None, "oracle": None}
        summaries: dict[str, Any] = {}
        for role, output in (("candidate", candidate_output), ("oracle", oracle_output)):
            if not output.is_dir():
                blockers.append(f"{role}_output_missing")
                artifacts.extend(
                    [
                        {"path": "meta.json", "present": False, "role": role, "kind": "meta", "case_id": case_id},
                        {"path": "arrays.npz", "present": False, "role": role, "kind": "arrays", "case_id": case_id},
                    ]
                )
                continue
            meta, meta_fact = _artifact_file(output, "meta.json")
            arrays, arrays_fact = _artifact_file(output, "arrays.npz", MAX_ARCHIVE_BYTES)
            artifacts.extend([{**meta_fact, "role": role, "kind": "meta", "case_id": case_id}, {**arrays_fact, "role": role, "kind": "arrays", "case_id": case_id}])
            if meta is None or arrays is None:
                blockers.append(f"{role}_artifact_missing")
                continue
            try:
                meta_value = _normalize_metadata(_json_loads(meta))
                arrays_value = _npz_summary(arrays)
            except (UnicodeDecodeError, json.JSONDecodeError, CustodyError):
                blockers.append(f"{role}_artifact_invalid")
                continue
            summaries[role] = {"meta": _json_field_summary(meta_value), "arrays": arrays_value}
        if set(summaries) == {"candidate", "oracle"}:
            comparison["candidate"] = summaries["candidate"]
            comparison["oracle"] = summaries["oracle"]
            if summaries["candidate"]["meta"] != summaries["oracle"]["meta"]:
                blockers.append("complete_metadata_drift")
            if summaries["candidate"]["arrays"]["logical_members"] != summaries["oracle"]["arrays"]["logical_members"]:
                blockers.append("complete_array_payload_drift")
        if candidate["exit_code"] != oracle["exit_code"] or candidate["exit_code"] != 0:
            blockers.append("candidate_or_oracle_process_failed")
    if lane == "PB-01":
        comparison["blockers"] = sorted(set(blockers))
    input_after, input_post = secure_read(case_root, f"input.{suffix}")
    if input_after != payload or input_post["pre_identity"] != input_fact["pre_identity"]:
        raise CustodyError("case input changed during replay")
    return _case_result(case_id, candidate, oracle, comparison, sorted(set(blockers))), [{"case_id": case_id, "pre": input_fact, "post": input_post, "equal": True}], artifacts


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _normalize_metadata(value: Any, key: str | None = None) -> Any:
    if key in {"input_file", "source_file"}:
        if not isinstance(value, str):
            raise CustodyError(f"metadata path field {key} must be a string")
        return "<input-file>"
    if isinstance(value, dict):
        return {name: _normalize_metadata(item, name) for name, item in sorted(value.items())}
    if isinstance(value, list):
        return [_normalize_metadata(item) for item in value]
    if isinstance(value, str):
        windows, posix = PureWindowsPath(value), PurePosixPath(value)
        if windows.is_absolute() or windows.drive or posix.is_absolute():
            raise CustodyError(f"absolute string outside metadata path whitelist: {key}")
    return value


def _json_field_summary(value: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {}

    def visit(item: Any, path: str) -> None:
        if isinstance(item, dict):
            fields[path or "$object"] = {"type": "object", "keys": sorted(item)}
            for key, child in sorted(item.items()):
                visit(child, f"{path}.{key}" if path else key)
        elif isinstance(item, list):
            fields[path] = {"type": "array", "length": len(item), "sha256": hashlib.sha256(_canonical_json(item)).hexdigest()}
        elif item is None:
            fields[path] = {"type": "null", "value": None}
        elif type(item) is bool:
            fields[path] = {"type": "bool", "value": item}
        elif type(item) in (int, float):
            fields[path] = {"type": "number", "value": item}
        elif isinstance(item, str):
            fields[path] = {"type": "string", "value": item}
        else:
            raise CustodyError("metadata contains an unsupported JSON value")

    visit(value, "")
    return {"canonical_sha256": hashlib.sha256(_canonical_json(value)).hexdigest(), "fields": fields}


def run_replay(args: argparse.Namespace) -> dict[str, Any]:
    candidate_repo, upstream_repo = args.candidate_repo.resolve(strict=True), args.upstream_repo.resolve(strict=True)
    preparation = validate_prep_commit(candidate_repo, args.prep_commit, args.expected_parent)
    upstream_commit = str(_git(upstream_repo, "rev-parse", f"{args.upstream_commit}^{{commit}}"))
    upstream_tree = str(_git(upstream_repo, "rev-parse", f"{upstream_commit}^{{tree}}"))
    if (upstream_commit, upstream_tree) != (UPSTREAM_COMMIT, UPSTREAM_TREE):
        raise CustodyError("upstream source is not the pinned commit/tree")
    work_parent = _external_absent_root(args.work_parent, (candidate_repo, upstream_repo), "work root")
    os.mkdir(work_parent)
    run_root = _fresh_child(work_parent, args.run_id)
    custody: dict[str, Any] = {"archive_materialization": [], "inputs": [], "artifacts": [], "output": {"fresh_root": True, "exclusive_report": True}}
    candidate_root, candidate_source = materialize_archive(candidate_repo, preparation["commit"], run_root, "candidate-source", args.timeout_seconds)
    upstream_root, upstream_source = materialize_archive(upstream_repo, upstream_commit, run_root, "upstream-source", args.timeout_seconds)
    oracle_root, oracle_source = materialize_archive(upstream_repo, upstream_commit, run_root, "upstream-oracle", args.timeout_seconds)
    candidate_inventory_pre = _inventory(candidate_root)
    upstream_inventory_pre = _inventory(upstream_root)
    custody["archive_materialization"].extend(
        [
            {"role": "candidate", "archive_sha256": candidate_source["archive_sha256"], "fact": candidate_source["archive"]},
            {"role": "upstream_pristine", "archive_sha256": upstream_source["archive_sha256"], "fact": upstream_source["archive"]},
            {"role": "upstream_oracle", "archive_sha256": oracle_source["archive_sha256"], "fact": oracle_source["archive"]},
        ]
    )
    corpus_raw, corpus_live = secure_read(candidate_root, PREP_PATHS[0])
    corpus = load_corpus(corpus_raw)
    corpus_git = preparation["files"][PREP_PATHS[0]]
    if corpus_live["sha256"] != corpus_git["sha256"]:
        raise CustodyError("archived corpus differs from raw prep Git blob")
    tool_root = _fresh_child(run_root, "tool-capture")
    cargo, cargo_identity = _resolve_tool(args.cargo, "cargo", ["--version"], tool_root, args.timeout_seconds)
    rustc, rustc_identity = _resolve_tool(args.rustc, "rustc", ["-Vv"], tool_root, args.timeout_seconds)
    uv, uv_identity = _resolve_tool(args.uv, "uv", ["--version"], tool_root, args.timeout_seconds)
    linker, linker_identity = _resolve_tool(args.linker, "link", ["/?"], tool_root, args.timeout_seconds)
    _fresh_child(run_root, "upstream-target")
    upstream_venv = run_root / "upstream-venv"
    if os.path.lexists(upstream_venv):
        raise CustodyError("oracle venv must be absent before the frozen probe")
    oracle_runtime = _probe_oracle_runtime(oracle_root, upstream_venv, run_root, uv, cargo, rustc, linker, args.timeout_seconds)
    oracle_runtime["oracle_work_archive_sha256"] = oracle_source["archive_sha256"]
    oracle_runtime["oracle_work_started_clean"] = True
    binary, build = _build_candidate(candidate_root, run_root, cargo, rustc, linker, args.timeout_seconds)
    pb01_base, pb01_fact = secure_read(candidate_root, corpus["base_fixtures"]["PB-01"])
    pb02_base, pb02_fact = secure_read(candidate_root, corpus["base_fixtures"]["PB-02"])
    custody["inputs"].extend([{"lane": "PB-01", "pre": pb01_fact}, {"lane": "PB-02", "pre": pb02_fact}])
    cases: list[dict[str, Any]] = []
    for case in corpus["pb01_cases"]:
        result, inputs, artifacts = _run_matrix_case(case=case, lane="PB-01", base=pb01_base, run_root=run_root, candidate_root=candidate_root, upstream_root=oracle_root, binary=binary, cargo=cargo, rustc=rustc, uv=uv, linker=linker, timeout=args.timeout_seconds)
        cases.append(result); custody["inputs"].extend(inputs); custody["artifacts"].extend(artifacts)
    for case in corpus["pb02_cases"]:
        result, inputs, artifacts = _run_matrix_case(case=case, lane="PB-02", base=pb02_base, run_root=run_root, candidate_root=candidate_root, upstream_root=oracle_root, binary=binary, cargo=cargo, rustc=rustc, uv=uv, linker=linker, timeout=args.timeout_seconds)
        cases.append(result); custody["inputs"].extend(inputs); custody["artifacts"].extend(artifacts)
    live_after = validate_prep_commit(candidate_repo, preparation["commit"], args.expected_parent)
    if _canonical_json(preparation) != _canonical_json(live_after):
        raise CustodyError("preparation live/pre-post binding drifted")
    pb01_after, pb01_post = secure_read(candidate_root, corpus["base_fixtures"]["PB-01"])
    pb02_after, pb02_post = secure_read(candidate_root, corpus["base_fixtures"]["PB-02"])
    if pb01_after != pb01_base or pb02_after != pb02_base:
        raise CustodyError("base fixture changed during replay")
    custody["inputs"][0].update({"post": pb01_post, "equal": True})
    custody["inputs"][1].update({"post": pb02_post, "equal": True})
    candidate_inventory_post = _inventory(candidate_root)
    upstream_inventory_post = _inventory(upstream_root)
    if candidate_inventory_pre != candidate_inventory_post or upstream_inventory_pre != upstream_inventory_post:
        raise CustodyError("archive source inventory changed during replay")
    binary_after, binary_post = secure_read(binary.parent, binary.name, MAX_FILE_BYTES * 16)
    binary_pre_comparable = {key: value for key, value in build["binary_pre"].items() if key not in {"exclusive_create", "pre_absent", "readback_equal"}}
    if hashlib.sha256(binary_after).hexdigest() != build["binary_pre"]["sha256"] or binary_post != binary_pre_comparable:
        raise CustodyError("candidate binary changed during replay")
    build = {"process": build["process"], "cargo_binary_source": build["cargo_binary_source"], "binary": {"pre": build["binary_pre"], "post": binary_post, "equal": True}, "env": build["env"]}
    for executable, identity in ((cargo, cargo_identity), (rustc, rustc_identity), (uv, uv_identity), (linker, linker_identity)):
        payload_after, custody_after = secure_read(executable.parent, executable.name, MAX_FILE_BYTES * 16)
        if hashlib.sha256(payload_after).hexdigest() != identity["file_sha256"] or custody_after != identity["file_custody_pre"]:
            raise CustodyError(f"{identity['role']} executable changed during replay")
        identity["file_custody_post"] = custody_after
        identity["file_custody_equal"] = True
    report = {
        "schema": "sipi.pb-01-02-portable-matrix-report.v2", "version": 2,
        "run_id": args.run_id, "run_nonce": secrets.token_hex(32),
        "preparation": {
            "commit": preparation["commit"], "tree": preparation["tree"], "parent": preparation["parent"], "changed_paths": preparation["changed_paths"],
            "files": {path: {"blob": fact["blob"], "sha256": fact["sha256"], "bytes": fact["bytes"], "live_pre": fact["live"], "live_post": live_after["files"][path]["live"], "live_equal": True} for path, fact in preparation["files"].items()},
        },
        "corpus": {"path": PREP_PATHS[0], "blob": corpus_git["blob"], "sha256": corpus_git["sha256"], "bytes": corpus_git["bytes"]},
        "source": {
            "candidate": {**{key: candidate_source[key] for key in ("commit", "tree", "archive_sha256")}, "inventory_pre_sha256": candidate_inventory_pre["sha256"], "inventory_post_sha256": candidate_inventory_post["sha256"], "inventory_equal": True},
            "upstream": {**{key: upstream_source[key] for key in ("commit", "tree", "archive_sha256")}, "inventory_pre_sha256": upstream_inventory_pre["sha256"], "inventory_post_sha256": upstream_inventory_post["sha256"], "inventory_equal": True},
        },
        "toolchain": {"cargo": cargo_identity, "rustc": rustc_identity, "uv": uv_identity, "link": linker_identity}, "build": build, "oracle_runtime": oracle_runtime,
        "custody": custody, "cases": cases,
        "claims": {"global_branch_parity": False, "whole_payload_parity": False, "release_acceptance": False, "numeric_parity": False},
    }
    output_root = _external_absent_root(args.output_root, (candidate_repo, upstream_repo), "output root")
    if output_root == work_parent or output_root in work_parent.parents or work_parent in output_root.parents:
        raise CustodyError("output root must be separate from the replay work root")
    os.mkdir(output_root)
    payload = json.dumps(report, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    report_fact = exclusive_write(output_root, "report.json", payload, MAX_ARCHIVE_BYTES)
    return {"status": "passed_scoped" if all(case["status"] == "passed" for case in cases) else "scoped_matrix_blocked", "report_file": report_fact, "case_statuses": {case["id"]: case["status"] for case in cases}, "build_binary_sha256": build["binary"]["pre"]["sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-repo", "--repo", dest="candidate_repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--upstream-repo", type=Path, default=Path(r"C:\Users\z3312\code\Py-bert-agent"))
    parser.add_argument("--prep-commit", required=True)
    parser.add_argument("--expected-parent", default=PINNED_PARENT)
    parser.add_argument("--upstream-commit", default=UPSTREAM_COMMIT)
    parser.add_argument("--run-id")
    parser.add_argument("--work-parent", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--cargo", default=os.environ.get("CARGO", "cargo"))
    parser.add_argument("--rustc", default=os.environ.get("RUSTC", "rustc"))
    parser.add_argument("--uv", default=os.environ.get("UV", "uv"))
    parser.add_argument("--linker", default=os.environ.get("LINK", "link.exe"))
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--prep-only", action="store_true")
    parser.add_argument("--no-live", action="store_true")
    args = parser.parse_args()
    try:
        if args.prep_only:
            result = {"preparation": validate_prep_commit(args.candidate_repo, args.prep_commit, args.expected_parent, require_live=not args.no_live)}
        else:
            if not args.run_id or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", args.run_id) is None:
                raise CustodyError("replay requires one safe --run-id")
            if args.work_parent is None or args.output_root is None:
                raise CustodyError("replay requires --work-parent and --output-root")
            result = run_replay(args)
    except (CustodyError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"valid": True, "result": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
