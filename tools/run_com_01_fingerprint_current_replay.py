"""Run one archive-bound COM-01 materialized-fingerprint replay.

This lane is intentionally narrower than the historical COM-01 corpus.  It
executes the real 120G XLSX materialized-json scenario, keeps the complete
parameter/option/consumption/warning payload in process only, and emits only
bounded hashes and exactness facts.  The candidate archive is fixed at the
fingerprint-fix commit; the older e74 custody helpers are admitted by raw Git
blob identity before they are imported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.com-01.fingerprint-current-replay.v1"
STATUS = "scoped_exact_materialized_fingerprint_replay"
AGGREGATE_SCHEMA = "sipi.com-01.fingerprint-current-replay.aggregate.v1"

CANDIDATE_COMMIT = "ef9f651839be98142eb4a54b9aa161e471d23a0c"
CANDIDATE_TREE = "338336fcd29d4151f87257f6ac54b0c843a9996a"
# The prep commit is created on the then-current integration head.  The
# candidate remains an ancestor, but is not required to be its direct parent.
PREP_PARENT_COMMIT = "dadc9720d932f2e71886700d9112a12cd2a027d5"
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"

CUSTODY_COMMIT = "e74e10d2933b1ddbc73f7da1a7785ca15ba49e09"
CUSTODY_TREE = "2e49b25641439d29110747edde157eb232d1250c"
CUSTODY_FILES = {
    "tools/run_com_01_current_candidate.py": "e64e3dbd5d98e00a7136dc2e533a374d0c9e0077",
    "tools/aggregate_com_01_current_candidate.py": "d07fbd804d8348042fb422a9b0376eec0c11693a",
    "tools/verify_com_01_current_candidate.py": "f9698adc980704bc7ff6cb250fc6928189cdcde7",
    "tools/test_verify_com_01_current_candidate.py": "99bc4c4296a52fde9ba261ee36792c6d26ad89d2",
}

CRATE_RELATIVE = Path("crates/sipi-agent-com-direct")
FIXTURE_RELATIVE = Path(
    "matlab_src/config_com_ieee8023_93a=3ck_SA_120g_C2M_tp1a_08_17_2022.xlsx"
)
FIXTURE_BYTES = 63311
FIXTURE_SHA256 = "f2c4c92f9549e720fff2843df6dc861aca7a503d59b2208898c2b67fa6fc0fc9"
EXPECTED_FINGERPRINT = "d6963c122533d58273e4ebf3224bade1dc38b040f740c1cd92d4c9727e4483dc"
EXPECTED_PARAMETER_COUNT = 148
EXPECTED_OPTION_COUNT = 90
EXPECTED_WARNING_COUNT = 0
RAW_BINARY_POLICY = "raw_sha256_bound_per_replay_no_canonical_pe_strategy"
CANDIDATE_ARCHIVE_BYTES = 53166080
CANDIDATE_ARCHIVE_SHA256 = "160d92bf28ef619b2fe3d2f14f055ea0320e1ddcf2f32f927ef6449f5fb06544"
CANDIDATE_INVENTORY = {"file_count": 22, "total_bytes": 1630466, "sha256": "19dbff925c2c1d48a6f36d22e30d0122fa67aed77dc6a9c02a883753599d843e"}
CANDIDATE_CARGO_LOCK_SHA256 = "7bb650c602f7fe9f74930580380e399089014924e16576bc72c3b82764136a7f"
CANDIDATE_SOURCE_DATE_EPOCH = "1787795490"
UPSTREAM_ARCHIVE_BYTES = 43694080
UPSTREAM_ARCHIVE_SHA256 = "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf"
UPSTREAM_INVENTORY = {"file_count": 70, "total_bytes": 1006648, "sha256": "1cd0366c0d1cb7e14678ccfc5671918d6a36f8f993896aa2b4729fec487b621e"}
UPSTREAM_SOURCE_INVENTORY = {"file_count": 67, "total_bytes": 872082, "sha256": "dbacf2e869bd2d0f00dd65f41a86d357d6abcffce0d81ad69b9421e6e45372b4"}
UPSTREAM_INIT_BYTES = 1719
UPSTREAM_INIT_SHA256 = "0608729cb58b26107264c005cb362f713635783cca01f70967ecf0fa8253a0e0"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_HARNESS_FILE_BYTES = 4 * 1024 * 1024
MAX_READ_CHUNK = 1024 * 1024
GIT_TIMEOUT_SECONDS = 30
MAX_GIT_STDOUT_BYTES = 32 * 1024 * 1024
MAX_GIT_STDERR_BYTES = MAX_CAPTURE_BYTES
GIT_EXECUTABLE = shutil.which("git")
CONSUMPTION_KEYS = (
    "implemented",
    "report_only",
    "unimplemented",
    "obsolete",
    "unverified",
    "summary",
)
CONSUMPTION_OPTIONAL_KEYS = (
    "materialization_provenance",
    "source_field_trace",
    "source_order_default_consumption",
    "unverified_mutability",
)
DOCUMENT_KEYS = (
    "schema_version",
    "execution",
    "config",
    "materialized_fingerprint",
    "materialized",
    "warnings",
    "config_consumption",
)
MATERIALIZED_KEYS = ("parameters", "options")
FORMAL_ARTIFACT_PREFIXES = (
    "docs/baselines/com-01-fingerprint-current-replay",
    "docs/baselines/audits/2026-08-27-com-01-fingerprint-current-replay",
)
NON_CLAIMS = (
    "no_complete_com_parity",
    "no_global_migration_row_close",
    "no_product_capability_promotion",
    "no_release_readiness",
    "no_configuration_value_payloads_committed",
    "no_S_parameter_fit",
    "channel_impulse_only_policy_unchanged",
    "no_canonical_pe_or_bit_reproducibility",
)
HARNESS_FILES = (
    "tools/run_com_01_fingerprint_current_replay.py",
    "tools/aggregate_com_01_fingerprint_current_replay.py",
    "tools/verify_com_01_fingerprint_current_replay.py",
    "tools/test_verify_com_01_fingerprint_current_replay.py",
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _finite_json(value: Any) -> None:
    if value is None or type(value) in (bool, int, str):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise RuntimeError("JSON contains NaN or Infinity")
        return
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise RuntimeError("JSON object key is not a string")
        for item in value.values():
            _finite_json(item)
        return
    if type(value) is list:
        for item in value:
            _finite_json(item)
        return
    raise RuntimeError(f"unsupported JSON value type: {type(value).__name__}")


def _git_executable_identity() -> dict[str, Any]:
    if GIT_EXECUTABLE is None:
        raise RuntimeError("fixed Git executable is unavailable")
    path = Path(GIT_EXECUTABLE)
    payload = _read_bounded_regular(path, 256 * 1024 * 1024, require_nlink=False)
    metadata = path.stat(follow_symlinks=False)
    return {"basename": path.name, "bytes": len(payload), "sha256": _sha256(payload), "nlink": metadata.st_nlink, "path_redacted": True}


def _git(root: Path, *args: str, raw: bool = False) -> bytes | str:
    if GIT_EXECUTABLE is None:
        raise RuntimeError("fixed Git executable is unavailable")
    command = [GIT_EXECUTABLE, "-c", "core.autocrlf=false", "-C", str(root), *args]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None and process.stderr is not None
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": MAX_GIT_STDOUT_BYTES, "stderr": MAX_GIT_STDERR_BYTES}
    overflow = threading.Event()

    def drain(name: str, stream: Any) -> None:
        while True:
            chunk = stream.read(MAX_READ_CHUNK)
            if not chunk:
                return
            remaining = limits[name] - len(buffers[name])
            if len(chunk) > remaining:
                if remaining > 0:
                    buffers[name].extend(chunk[:remaining])
                overflow.set()
                return
            buffers[name].extend(chunk)

    threads = [threading.Thread(target=drain, args=(name, stream), daemon=True) for name, stream in (("stdout", process.stdout), ("stderr", process.stderr))]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + GIT_TIMEOUT_SECONDS
    timed_out = False
    try:
        while process.poll() is None:
            if overflow.is_set():
                process.kill()
                break
            if time.monotonic() >= deadline:
                timed_out = True
                process.kill()
                break
            time.sleep(0.01)
        process.wait()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        for stream in (process.stdout, process.stderr):
            stream.close()
        for thread in threads:
            thread.join(timeout=1)
    stdout = bytes(buffers["stdout"])
    stderr = bytes(buffers["stderr"])
    if timed_out:
        raise RuntimeError("git command exceeded timeout")
    if overflow.is_set():
        raise RuntimeError("git command output exceeded capture bound")
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, command, output=stdout, stderr=stderr)
    return stdout if raw else stdout.decode("ascii").strip()


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400)
    except (OSError, ValueError):
        return True


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_nlink,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _inode_identity(value: os.stat_result) -> tuple[int, int, int]:
    return (value.st_dev, value.st_ino, value.st_nlink)


def _structural_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (value.st_dev, value.st_ino, value.st_size, value.st_nlink)


def _regular_identity(path: Path, *, require_nlink: bool = True) -> tuple[int, int, int, int, int, int]:
    if _is_reparse(path):
        raise RuntimeError("path is a symlink or reparse point")
    value = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(value.st_mode) or value.st_nlink < 1 or (require_nlink and value.st_nlink != 1):
        raise RuntimeError("path is not an admitted regular file")
    return _stat_identity(value)


def _read_bounded_regular(path: Path, maximum: int, *, require_nlink: bool = True) -> bytes:
    """Read one regular file handle and reject replacement or growth while reading."""
    if maximum <= 0:
        raise ValueError("file bound must be positive")
    try:
        entry_before = path.stat(follow_symlinks=False)
    except OSError as error:
        raise RuntimeError("regular file could not be inspected") from error
    if _is_reparse(path) or not stat.S_ISREG(entry_before.st_mode) or entry_before.st_nlink < 1 or (require_nlink and entry_before.st_nlink != 1):
        raise RuntimeError("path is not an admitted regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RuntimeError("regular file could not be opened") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink < 1 or (require_nlink and before.st_nlink != 1):
            raise RuntimeError("opened path is not an admitted regular file")
        if _is_reparse(path) or _structural_identity(entry_before) != _structural_identity(before):
            raise RuntimeError("opened path is a symlink or reparse point")
        identity = _stat_identity(before)
        if before.st_size < 0 or before.st_size > maximum:
            raise RuntimeError("file exceeds bounded size")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(MAX_READ_CHUNK, maximum - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > maximum:
                raise RuntimeError("file exceeds bounded size")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        try:
            entry_after = path.stat(follow_symlinks=False)
        except OSError as error:
            raise RuntimeError("file disappeared while reading") from error
        if _is_reparse(path) or _stat_identity(after) != identity or _structural_identity(entry_after) != _structural_identity(after) or size != before.st_size:
            raise RuntimeError("file changed while reading")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _absolute_lexical(path: Path) -> Path:
    value = Path(path)
    if not value.is_absolute():
        value = Path.cwd() / value
    if ".." in value.parts:
        raise RuntimeError("path contains parent traversal")
    return value


def _validate_directory_root(root: Path) -> Path:
    raw = _absolute_lexical(root)
    if raw == Path(raw.anchor) or not raw.name:
        raise RuntimeError("output root is not a concrete directory")
    cursor = raw
    while True:
        try:
            metadata = cursor.stat(follow_symlinks=False)
        except OSError as error:
            raise RuntimeError("output root ancestor is missing") from error
        if _is_reparse(cursor) or not stat.S_ISDIR(metadata.st_mode) or metadata.st_nlink < 1:
            raise RuntimeError("output root has an unsafe ancestor")
        if cursor == Path(cursor.anchor):
            break
        parent = cursor.parent
        if parent == cursor:
            raise RuntimeError("output root ancestry failed")
        cursor = parent
    return raw


def _output_target(path: Path, output_root: Path) -> tuple[Path, Path]:
    root = _validate_directory_root(output_root)
    target = _absolute_lexical(path)
    if target.parent != root or not target.name or target.name in {".", ".."}:
        raise RuntimeError("output must be a direct child of its fixed root")
    if os.path.lexists(target):
        raise FileExistsError("output already exists")
    return root, target


def _atomic_json_create(path: Path, value: Any, *, output_root: Path) -> bytes:
    _finite_json(value)
    payload = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False).encode("ascii") + b"\n"
    if len(payload) > MAX_REPORT_BYTES:
        raise RuntimeError("JSON output exceeds bound")
    _, target = _output_target(path, output_root)
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags, 0o600)
    identity: tuple[int, int, int] | None = None
    def rollback() -> None:
        if identity is None:
            return
        try:
            current = target.stat(follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError as error:
            raise RuntimeError("output cleanup identity could not be checked") from error
        if _inode_identity(current) != identity:
            raise RuntimeError("output cleanup refused after inode identity changed")
        try:
            target.unlink()
        except OSError as error:
            raise RuntimeError("output cleanup failed") from error

    try:
        before = os.fstat(descriptor)
        identity = _inode_identity(before)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or _is_reparse(target):
            raise RuntimeError("created output is not a singly-linked regular file")
        view = memoryview(payload)
        written = 0
        while written < len(payload):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise RuntimeError("JSON output write made no progress")
            written += count
        os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        readback = bytearray()
        while True:
            chunk = os.read(descriptor, min(MAX_READ_CHUNK, MAX_REPORT_BYTES - len(readback) + 1))
            if not chunk:
                break
            readback.extend(chunk)
            if len(readback) > MAX_REPORT_BYTES:
                raise RuntimeError("JSON readback exceeds bound")
        after = os.fstat(descriptor)
        if _inode_identity(after) != identity or after.st_size != len(payload) or bytes(readback) != payload:
            raise RuntimeError("JSON output changed during write/readback")
    except BaseException as error:
        close_error: OSError | None = None
        try:
            os.close(descriptor)
        except OSError as candidate:
            close_error = candidate
        try:
            rollback()
        except RuntimeError as cleanup_error:
            raise cleanup_error from error
        if close_error is not None:
            raise RuntimeError("output close failed") from close_error
        raise
    else:
        try:
            os.close(descriptor)
        except OSError as error:
            try:
                rollback()
            except RuntimeError as cleanup_error:
                raise cleanup_error from error
            raise RuntimeError("output close failed") from error
    try:
        if _read_bounded_regular(target, MAX_REPORT_BYTES) != payload:
            raise RuntimeError("published JSON readback drift")
    except BaseException as error:
        try:
            rollback()
        except RuntimeError as cleanup_error:
            raise cleanup_error from error
        raise
    return payload


def _git_exists(root: Path, expression: str) -> bool:
    try:
        _git(root, "cat-file", "-e", expression)
    except (subprocess.CalledProcessError, RuntimeError):
        return False
    return True


def _git_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    try:
        _git(root, "merge-base", "--is-ancestor", ancestor, descendant)
    except subprocess.CalledProcessError as error:
        if error.returncode == 1:
            return False
        raise
    return True


def _load_custody(root: Path) -> Any:
    """Admit e74 from a Git blob and execute only the staged bytes."""
    root = _validate_directory_root(root)
    if _git(root, "rev-parse", f"{CUSTODY_COMMIT}^{{tree}}") != CUSTODY_TREE:
        raise RuntimeError("e74 custody tree drift")
    relative = "tools/run_com_01_current_candidate.py"
    helper_path = root / relative
    if str(_git(root, "rev-parse", f"{CUSTODY_COMMIT}:{relative}")) != CUSTODY_FILES[relative]:
        raise RuntimeError("e74 custody helper blob drift")
    raw = bytes(_git(root, "show", f"{CUSTODY_COMMIT}:{relative}", raw=True))
    live = _read_bounded_regular(helper_path, MAX_HARNESS_FILE_BYTES)
    if _sha256(raw) != _sha256(live) or len(raw) != len(live):
        raise RuntimeError("live e74 custody helper differs from its raw Git blob")
    module = ModuleType("com01_e74_custody")
    module.__file__ = str(helper_path)
    module.__package__ = None
    exec(compile(raw, str(helper_path), "exec"), module.__dict__, module.__dict__)
    module._git = _git
    # The helper's source-derived ROOT must point at this checked repository,
    # not at a temporary staging location or the caller's working directory.
    module.ROOT = root

    def staged_bounded_file(path: Path, maximum: int = module.MAX_FILE_BYTES) -> tuple[int, str]:
        payload = _read_bounded_regular(path, maximum)
        return len(payload), _sha256(payload)

    # Keep e74's inventory/source/tool receipts on the same descriptor-backed
    # reader used to admit the helper itself.
    module._bounded_file = staged_bounded_file
    return module


def _raw_receipt(root: Path, commit: str, relative: str) -> dict[str, Any]:
    payload = bytes(_git(root, "show", f"{commit}:{relative}", raw=True))
    if not payload or len(payload) > MAX_HARNESS_FILE_BYTES:
        raise RuntimeError(f"Git blob exceeds bounded receipt: {relative}")
    return {
        "path": relative,
        "git_blob_sha1": str(_git(root, "rev-parse", f"{commit}:{relative}")),
        "bytes": len(payload),
        "content_sha256": _sha256(payload),
    }


def _custody_receipt(root: Path) -> dict[str, Any]:
    files = []
    for relative, expected_blob in CUSTODY_FILES.items():
        receipt = _raw_receipt(root, CUSTODY_COMMIT, relative)
        if receipt["git_blob_sha1"] != expected_blob:
            raise RuntimeError(f"e74 custody blob drift: {relative}")
        live = _read_bounded_regular(root / relative, MAX_HARNESS_FILE_BYTES)
        if len(live) != receipt["bytes"] or _sha256(live) != receipt["content_sha256"]:
            raise RuntimeError(f"live custody file drift: {relative}")
        files.append(receipt)
    return {"commit": CUSTODY_COMMIT, "tree": CUSTODY_TREE, "files": files}


def _harness_receipt(custody: Any, root: Path, prep_commit: str | None) -> dict[str, Any]:
    if not isinstance(prep_commit, str) or HEX40.fullmatch(prep_commit) is None:
        raise RuntimeError("prep commit must be a full lowercase Git SHA-1")
    commit = str(custody._git(root, "rev-parse", f"{prep_commit}^{{commit}}"))
    if commit != prep_commit:
        raise RuntimeError("prep commit identity drift")
    parents = str(custody._git(root, "rev-list", "--parents", "-n", "1", commit)).split()
    if parents != [commit, PREP_PARENT_COMMIT]:
        raise RuntimeError("prep commit parent is not the pinned integration head")
    if not _git_ancestor(root, CANDIDATE_COMMIT, commit):
        raise RuntimeError("candidate commit is not an ancestor of prep")
    candidate_changes = str(custody._git(root, "diff", "--name-only", f"{CANDIDATE_COMMIT}..{commit}", "--", CRATE_RELATIVE.as_posix())).splitlines()
    if candidate_changes:
        raise RuntimeError("candidate COM production paths changed after candidate")
    tree = str(custody._git(root, "rev-parse", f"{commit}^{{tree}}"))
    changed = str(custody._git(root, "diff-tree", "--no-commit-id", "--no-renames", "--name-status", "-r", f"{commit}^", commit)).splitlines()
    expected_changes = [f"A\t{relative}" for relative in HARNESS_FILES]
    if sorted(changed) != sorted(expected_changes):
        raise RuntimeError("prep commit must introduce exactly the four fingerprint tools")
    if any(_git_exists(root, f"{commit}^:{relative}") for relative in HARNESS_FILES):
        raise RuntimeError("prep tools must be first introductions")
    all_paths = str(custody._git(root, "ls-tree", "-r", "--name-only", commit)).splitlines()
    if any(any(path.startswith(prefix) for prefix in FORMAL_ARTIFACT_PREFIXES) for path in all_paths):
        raise RuntimeError("formal fingerprint artifacts must be absent from prep")
    files = []
    for relative in HARNESS_FILES:
        try:
            receipt = _raw_receipt(root, commit, relative)
        except subprocess.CalledProcessError as error:
            raise RuntimeError("harness prep files must be committed before replay") from error
        live = _read_bounded_regular(root / relative, MAX_HARNESS_FILE_BYTES)
        if len(live) != receipt["bytes"] or _sha256(live) != receipt["content_sha256"]:
            raise RuntimeError(f"harness source changed after commit: {relative}")
        files.append(receipt)
    return {
        "prep_commit": commit,
        "prep_parent": PREP_PARENT_COMMIT,
        "prep_tree": tree,
        "changed_paths": list(HARNESS_FILES),
        "first_introduction": True,
        "formal_artifacts_absent": True,
        "files": files,
        "shared_custody": _custody_receipt(root),
        "source_mode": "raw_git_blob_bound_before_execution",
    }


def _canonical(value: Any) -> bytes:
    _finite_json(value)
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _semantic_numbers(value: Any) -> Any:
    """Match Python numeric equality while retaining bool as a distinct type."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return {"__number__": repr(float(value))}
    if isinstance(value, float):
        return {"__number__": repr(value)}
    if isinstance(value, dict):
        return {str(key): _semantic_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_semantic_numbers(item) for item in value]
    return value


def _field_hash(value: Any) -> str:
    return _sha256(_canonical(_semantic_numbers(value)))


def _typed_canonical(value: Any) -> Any:
    if value is None:
        return {"type": "null"}
    if type(value) is bool:
        return {"type": "bool", "value": value}
    if type(value) is int:
        return {"type": "number", "value": repr(float(value))}
    if type(value) is float:
        if not math.isfinite(value):
            raise RuntimeError("JSON contains NaN or Infinity")
        return {"type": "number", "value": repr(value)}
    if type(value) is str:
        return {"type": "str", "value": value}
    if type(value) is list:
        return {"type": "list", "value": [_typed_canonical(item) for item in value]}
    if type(value) is dict:
        return {"type": "dict", "value": [[key, _typed_canonical(value[key])] for key in sorted(value)]}
    raise RuntimeError("unsupported JSON value type")


def _typed_field_hash(value: Any) -> str:
    return _sha256(_canonical(_typed_canonical(value)))


def _key_hash(value: Any) -> str:
    return _sha256(_canonical(sorted(value))) if isinstance(value, dict) else ""


def _unique_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise RuntimeError("materialized-json contains duplicate keys")
        result[key] = value
    return result


def _commit_tree(root: Path, revision: str) -> tuple[str, str]:
    commit = str(_git(root, "rev-parse", f"{revision}^{{commit}}"))
    tree = str(_git(root, "rev-parse", f"{commit}^{{tree}}"))
    return commit, tree


def _parse_json(stdout: bytes) -> dict[str, Any]:
    text = stdout.decode("utf-8", errors="strict")
    try:
        value = json.loads(text, object_pairs_hook=_unique_json_pairs, parse_constant=lambda value: (_ for _ in ()).throw(RuntimeError(f"invalid JSON constant: {value}")))
        _finite_json(value)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line, object_pairs_hook=_unique_json_pairs, parse_constant=lambda value: (_ for _ in ()).throw(RuntimeError(f"invalid JSON constant: {value}")))
            _finite_json(value)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError("materialized-json command did not emit a JSON object")


def _payload(document: dict[str, Any]) -> dict[str, Any]:
    _finite_json(document)
    if set(document) != set(DOCUMENT_KEYS):
        raise RuntimeError("materialized document keys are not the fixed complete projection")
    execution = document["execution"]
    config = document["config"]
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise RuntimeError("materialized schema version drift")
    if (
        not isinstance(execution, dict)
        or set(execution) != {"performed", "runtime_reads"}
        or type(execution["performed"]) is not bool
        or execution["performed"] is not False
        or execution["runtime_reads"] != "not_run"
    ):
        raise RuntimeError("materialized execution projection drift")
    if (
        not isinstance(config, dict)
        or set(config) != {"path", "sha256", "profile"}
        or not isinstance(config["path"], str)
        or not isinstance(config["sha256"], str)
        or HEX64.fullmatch(config["sha256"]) is None
        or config["profile"] != "r480"
    ):
        raise RuntimeError("materialized config projection drift")
    materialized = document.get("materialized")
    consumption = document.get("config_consumption")
    warnings = document.get("warnings")
    if (
        not isinstance(materialized, dict)
        or set(materialized) != set(MATERIALIZED_KEYS)
        or not isinstance(consumption, dict)
        or not isinstance(warnings, list)
        or any(type(item) is not str for item in warnings)
    ):
        raise RuntimeError("materialized payload shape drift")
    parameters = materialized.get("parameters")
    options = materialized.get("options")
    if not isinstance(parameters, dict) or not isinstance(options, dict):
        raise RuntimeError("materialized parameter/option maps are missing")
    allowed_consumption = set(CONSUMPTION_KEYS) | set(CONSUMPTION_OPTIONAL_KEYS)
    if any(key not in consumption for key in CONSUMPTION_KEYS) or set(consumption) - allowed_consumption:
        raise RuntimeError("consumption projection is not the pinned complete projection")
    ordered_consumption = {
        key: consumption[key]
        for key in (*CONSUMPTION_KEYS, *CONSUMPTION_OPTIONAL_KEYS)
        if key in consumption
    }
    return {
        "schema_version": document["schema_version"],
        "execution": {"performed": execution["performed"], "runtime_reads": execution["runtime_reads"]},
        "config": {"profile": config["profile"], "sha256": config["sha256"]},
        "materialized_fingerprint": document.get("materialized_fingerprint"),
        "config_sha256": config["sha256"],
        "parameters": parameters,
        "options": options,
        "consumption": ordered_consumption,
        "warnings": warnings,
    }


def _payload_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    parameters = payload["parameters"]
    options = payload["options"]
    return {
        "projection_sha256": _typed_field_hash(payload),
        "materialized_fingerprint": payload["materialized_fingerprint"],
        "config_sha256": payload["config_sha256"],
        "parameters": {
            "count": len(parameters),
            "keys_sha256": _key_hash(parameters),
            "semantic_sha256": _field_hash(parameters),
        },
        "options": {
            "count": len(options),
            "keys_sha256": _key_hash(options),
            "semantic_sha256": _field_hash(options),
        },
        "consumption": {
            "keys": list(payload["consumption"]),
            "semantic_sha256": _typed_field_hash(payload["consumption"]),
            "common_sha256": _typed_field_hash({key: payload["consumption"][key] for key in CONSUMPTION_KEYS}),
            "oracle_only_sha256": _typed_field_hash({key: payload["consumption"][key] for key in CONSUMPTION_OPTIONAL_KEYS if key in payload["consumption"]}),
        },
        "warnings": {
            "count": len(payload["warnings"]),
            "semantic_sha256": _field_hash(payload["warnings"]),
        },
    }


def _exactness(oracle: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    # The Rust leaf currently emits the six stable status buckets; the pinned
    # Python oracle additionally emits source-derived metadata.  Preserve and
    # hash that complete oracle projection, while comparing the shared buckets
    # rather than silently discarding the oracle-only metadata.
    oracle_consumption = {key: oracle["consumption"][key] for key in CONSUMPTION_KEYS}
    candidate_consumption = {key: candidate["consumption"][key] for key in CONSUMPTION_KEYS}
    fields = {
        "materialized_fingerprint": oracle["materialized_fingerprint"] == candidate["materialized_fingerprint"] == EXPECTED_FINGERPRINT,
        "parameters": oracle["parameters"] == candidate["parameters"],
        "options": oracle["options"] == candidate["options"],
        "consumption": _typed_field_hash(oracle_consumption) == _typed_field_hash(candidate_consumption),
        "warnings": oracle["warnings"] == candidate["warnings"],
    }
    fields["all"] = all(fields.values())
    return fields


def _runtime_env(custody: Any, tools: dict[str, Path]) -> dict[str, str]:
    environment = dict(os.environ)
    for key in custody.BUILD_ENV_CLEARED_KEYS:
        environment.pop(key, None)
    environment.update(
        {
            "RUSTC": str(tools["rustc"]),
            "CARGO_NET_OFFLINE": "true",
            "CARGO_TERM_COLOR": "never",
            "CARGO_INCREMENTAL": "0",
        }
    )
    return environment


def _tool_identities(custody: Any, tools: dict[str, Path]) -> dict[str, dict[str, Any]]:
    """Re-query executable bytes and version output at the second boundary."""
    linker_args = ("-flavor", "link", "/?") if os.name == "nt" else ("--version",)
    arguments = {role: (("--version",) if role != "linker" else linker_args) for role in ("cargo", "rustc", "python", "uv")}
    arguments["linker"] = linker_args
    return {
        role: custody._tool_identity(tools[role], role, arguments[role])
        for role in ("cargo", "rustc", "python", "uv", "linker")
    }


def _git_source_receipt(custody: Any, root: Path, commit: str, source: dict[str, Any]) -> None:
    """Bind the runtime package receipt to the same pinned Git blobs."""
    names = str(custody._git(root, "ls-tree", "-r", "--name-only", commit, "--", "src/agent_com")).splitlines()
    python_names = [name for name in names if name.endswith(".py")]
    if not python_names:
        raise RuntimeError("pinned Agent-COM source package is empty")
    entries = []
    for relative in sorted(python_names):
        receipt = _raw_receipt(root, commit, relative)
        entries.append({"path": relative, "bytes": receipt["bytes"], "sha256": receipt["content_sha256"]})
    inventory = {
        "file_count": len(entries),
        "total_bytes": sum(item["bytes"] for item in entries),
        "sha256": _sha256(_canonical(entries)),
    }
    if source["package_source_inventory"] != inventory:
        raise RuntimeError("upstream source receipt does not match pinned Git blobs")
    init = next((item for item in entries if item["path"] == "src/agent_com/__init__.py"), None)
    if init is None or source["module_file"]["bytes"] != init["bytes"] or source["module_file"]["sha256"] != init["sha256"]:
        raise RuntimeError("upstream module receipt does not match pinned Git blob")


def _scenario(
    custody: Any,
    tools: dict[str, Path],
    upstream_root: Path,
    candidate_root: Path,
    binary: Path,
    fixture: Path,
    timeout: int,
) -> dict[str, Any]:
    args = ["config", "validate", str(fixture), "--profile", "r480", "--materialized-json"]
    script = "import runpy,sys; sys.argv=['agent_com.cli',*sys.argv[1:]]; runpy.run_module('agent_com.cli',run_name='__main__')"
    oracle_process = custody._uv_run(
        tools, upstream_root, tools["python"], script, args, timeout
    )
    candidate_process = custody._bounded_run(
        [str(binary), *args],
        cwd=candidate_root,
        env=_runtime_env(custody, tools),
        timeout=timeout,
    )
    if oracle_process.returncode != 0 or candidate_process.returncode != 0:
        raise RuntimeError("120G materialized-json scenario did not complete successfully")
    oracle = _payload(_parse_json(oracle_process.stdout))
    candidate = _payload(_parse_json(candidate_process.stdout))
    for label, payload in (("oracle", oracle), ("candidate", candidate)):
        if payload["config_sha256"] != FIXTURE_SHA256:
            raise RuntimeError(f"{label} configuration source identity drift")
        if len(payload["parameters"]) != EXPECTED_PARAMETER_COUNT or len(payload["options"]) != EXPECTED_OPTION_COUNT:
            raise RuntimeError(f"{label} materialized count drift")
        if len(payload["warnings"]) != EXPECTED_WARNING_COUNT:
            raise RuntimeError(f"{label} warning count drift")
    oracle_receipt = _payload_receipt(oracle)
    candidate_receipt = _payload_receipt(candidate)
    exact = _exactness(oracle, candidate)
    if not exact["all"]:
        raise RuntimeError("120G materialized payload is not exact")
    return {
        "id": "xlsx_materialized_json_default",
        "fixture_role": "primary_xlsx",
        "profile": "r480",
        "output": "materialized_json",
        "oracle": {"exit_code": oracle_process.returncode, "payload": oracle_receipt, "runtime": "uv_frozen_offline"},
        "candidate": {"exit_code": candidate_process.returncode, "payload": candidate_receipt, "runtime": "archive_binary_execution_copy"},
        "exact": exact,
        "comparison_mode": "parsed_json_semantic_numbers_with_exact_fingerprint",
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not HEX64.fullmatch(args.run_id):
        raise RuntimeError("run_id must be lowercase 64-hex")
    candidate_repo = _validate_directory_root(args.candidate_repo)
    git_identity_pre = _git_executable_identity()
    custody = _load_custody(candidate_repo)
    upstream_repo = _validate_directory_root(args.upstream_repo)
    candidate_commit, candidate_tree = _commit_tree(candidate_repo, args.candidate_commit)
    upstream_commit, upstream_tree = _commit_tree(upstream_repo, args.upstream_commit)
    if (candidate_commit, candidate_tree) != (CANDIDATE_COMMIT, CANDIDATE_TREE):
        raise RuntimeError("candidate commit/tree is not ef9 fingerprint preparation")
    if (upstream_commit, upstream_tree) != (UPSTREAM_COMMIT, UPSTREAM_TREE):
        raise RuntimeError("upstream commit/tree is not pinned")
    if Path(args.python).resolve() != Path(sys.executable).resolve():
        raise RuntimeError("--python must be the interpreter executing this replay")
    toolchain, tools = custody._toolchain(args.cargo, args.python, args.uv)
    toolchain["timeout_seconds"] = args.timeout_seconds
    tool_identities_pre = {role: dict(toolchain[role]) for role in ("cargo", "rustc", "python", "uv", "linker")}
    prep_commit = getattr(args, "prep_commit", None)
    if prep_commit is None:
        prep_commit = getattr(args, "harness_commit", None)
    harness = _harness_receipt(custody, candidate_repo, prep_commit)
    fresh_run_nonce = secrets.token_hex(32)
    source_date_epoch = str(custody._git(candidate_repo, "show", "-s", "--format=%ct", candidate_commit))
    with tempfile.TemporaryDirectory(prefix="com-01-fingerprint-current-") as directory:
        run_root = Path(directory)
        candidate_root = run_root / "candidate"
        upstream_root = run_root / "upstream"
        target_root = run_root / "candidate-target"
        target_root.mkdir()
        candidate_info = custody._materialize(candidate_repo, candidate_commit, candidate_root)
        upstream_info = custody._materialize(upstream_repo, upstream_commit, upstream_root)
        candidate_inventory = custody._inventory(candidate_root, (CRATE_RELATIVE,))
        if candidate_inventory != custody._git_inventory(candidate_repo, candidate_commit, (CRATE_RELATIVE,)):
            raise RuntimeError("candidate archive inventory does not match pinned Git")
        upstream_inventory = custody._inventory(
            upstream_root,
            (Path("src/agent_com"), Path("schemas/r480-config.schema.yaml"), Path("schemas/behavior-presets.yaml"), FIXTURE_RELATIVE),
        )
        if upstream_inventory != custody._git_inventory(
            upstream_repo,
            upstream_commit,
            (Path("src/agent_com"), Path("schemas/r480-config.schema.yaml"), Path("schemas/behavior-presets.yaml"), FIXTURE_RELATIVE),
        ):
            raise RuntimeError("upstream archive inventory does not match pinned Git")
        fixture = custody._safe_file(upstream_root, FIXTURE_RELATIVE)
        fixture_bytes, fixture_sha = custody._bounded_file(fixture)
        if (fixture_bytes, fixture_sha) != (FIXTURE_BYTES, FIXTURE_SHA256):
            raise RuntimeError("120G XLSX fixture identity drift")
        dependency_cache_pre = custody._cargo_dependency_cache_inventory(candidate_root, tools, args.timeout_seconds)
        source = custody._source_receipt(upstream_root)
        _git_source_receipt(custody, upstream_repo, upstream_commit, source)
        upstream_runtime = custody._probe_upstream(upstream_root, tools, args.timeout_seconds, source)
        upstream_runtime["environment"]["dependency_modules_scope"] = "environment_local_recheck_not_replay_artifact"
        binary, cargo_binary, build = custody._build(
            candidate_root, target_root, tools, args.timeout_seconds, source_date_epoch
        )
        build["binary_post"] = custody._execution_copy_receipt(binary, build["cargo_source_pre"])
        build["copy_matches_source"] = True
        build["raw_binary_scope"] = "execution_copy_only"
        candidate_post_inventory = custody._inventory(candidate_root, (CRATE_RELATIVE,))
        if candidate_post_inventory != candidate_inventory:
            raise RuntimeError("candidate archive changed during build")
        scenario = _scenario(
            custody, tools, upstream_root, candidate_root, binary, fixture, args.timeout_seconds
        )
        if custody._execution_copy_receipt(binary, build["cargo_source_pre"]) != build["binary_post"]:
            raise RuntimeError("execution copy changed during scenario")
        cargo_lock_path = custody._safe_file(candidate_root, CRATE_RELATIVE / "Cargo.lock")
        cargo_lock_bytes, cargo_lock_sha = custody._bounded_file(cargo_lock_path)
        cargo_lock_raw = bytes(_git(candidate_repo, "show", f"{candidate_commit}:{(CRATE_RELATIVE / 'Cargo.lock').as_posix()}", raw=True))
        if len(cargo_lock_raw) != cargo_lock_bytes or _sha256(cargo_lock_raw) != cargo_lock_sha:
            raise RuntimeError("Cargo.lock archive/Git identity drift")
        dependency_cache_post = custody._cargo_dependency_cache_inventory(candidate_root, tools, args.timeout_seconds)
        tool_identities_post = _tool_identities(custody, tools)
        git_identity_post = _git_executable_identity()
        if dependency_cache_pre != dependency_cache_post:
            raise RuntimeError("locked Cargo dependency cache changed during replay")
        if tool_identities_pre != tool_identities_post:
            raise RuntimeError("tool executable identity changed during replay")
        if git_identity_pre != git_identity_post:
            raise RuntimeError("Git executable identity changed during replay")
        build["dependency_cache_pre"] = dependency_cache_pre
        build["dependency_cache_post"] = dependency_cache_post
        build["dependency_cache_equal"] = dependency_cache_pre == dependency_cache_post
        build["tool_identities_pre"] = tool_identities_pre
        build["tool_identities_post"] = tool_identities_post
        build["tool_identities_equal"] = tool_identities_pre == tool_identities_post
        build["git_identity_pre"] = git_identity_pre
        build["git_identity_post"] = git_identity_post
        build["git_identity_equal"] = git_identity_pre == git_identity_post
        candidate_record = {
            **candidate_info,
            "source_mode": "git_archive_at_immutable_commit",
            "inventory": candidate_inventory,
            "cargo_lock_sha256": cargo_lock_sha,
            "source_date_epoch": source_date_epoch,
            "build": build,
            "cargo_binary_basename": cargo_binary.name,
        }
        upstream_record = {
            **upstream_info,
            "source_mode": "git_archive_at_immutable_commit",
            "inventory": upstream_inventory,
            "source": source,
            "runtime": upstream_runtime,
        }
        fixture_record = {
            "role": "primary_xlsx",
            "relative_path": FIXTURE_RELATIVE.as_posix(),
            "basename": FIXTURE_RELATIVE.name,
            "bytes": fixture_bytes,
            "sha256": fixture_sha,
            "path_redacted": True,
            "custody": "upstream_git_archive_only",
        }
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "work_item": "COM-01",
        "leaf": "config-validate",
        "run_id": args.run_id,
        "fresh_run_nonce": fresh_run_nonce,
        "source_mode": "git_archive_at_immutable_commit",
        "candidate": candidate_record,
        "upstream": upstream_record,
        "harness": harness,
        "toolchain": toolchain,
        "fixture": fixture_record,
        "scenario": scenario,
        "expected": {
            "materialized_fingerprint": EXPECTED_FINGERPRINT,
            "parameter_count": EXPECTED_PARAMETER_COUNT,
            "option_count": EXPECTED_OPTION_COUNT,
            "warning_count": EXPECTED_WARNING_COUNT,
        },
        "exact": scenario["exact"],
        "artifact_policy": "hash_counts_and_exactness_only_no_configuration_payloads",
        "acceptance": False,
        "non_claims": list(NON_CLAIMS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--candidate-commit", default=CANDIDATE_COMMIT)
    parser.add_argument("--prep-commit", "--harness-commit", dest="prep_commit", required=True)
    parser.add_argument("--upstream-repo", type=Path, default=Path(r"C:\Users\z3312\code\COM"))
    parser.add_argument("--upstream-commit", default=UPSTREAM_COMMIT)
    parser.add_argument("--cargo", default=str(Path.home() / ".cargo" / "bin" / "cargo.exe"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("timeout must be positive")
    try:
        report = run(args)
        # Validate with the sibling verifier before exposing the immutable
        # report, so no caller can publish a forged exactness shortcut.
        try:
            from .verify_com_01_fingerprint_current_replay import validate_report  # type: ignore[import-not-found]
        except ImportError:  # pragma: no cover - direct script execution
            from verify_com_01_fingerprint_current_replay import validate_report
        validate_report(report)
        _atomic_json_create(args.report, report, output_root=args.report.parent)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError, UnicodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "report": args.report.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
