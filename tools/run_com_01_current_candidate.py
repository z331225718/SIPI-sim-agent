"""Run the current COM-01 config-validation leaf from immutable archives.

This is an additive evidence runner.  It compares the pinned Agent-COM
configuration entry point with the Rust direct port, but never publishes raw
configuration values and never closes a migration or release gate.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import io
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import ModuleType
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.com-01.current-candidate-replay.v1"
OPEN_STATUS = "scoped_current_candidate_observed"
CANDIDATE_COMMIT = "bc882d2e5a19c2a844bacc485ede5b874e8f9c37"
CANDIDATE_TREE = "d87cfecea77ccd670073a6c069658e6b4e8c3137"
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
CRATE_RELATIVE = Path("crates/sipi-agent-com-direct")
CORPUS_RELATIVE = Path("docs/baselines/com-01-direct-port-corpus.v1.json")
SEMANTIC_RUNNER_RELATIVE = Path("tools/run_com_01_direct_oracle.py")
FIXTURE_RELATIVE = Path(
    "matlab_src/config_com_ieee8023_93a=3ck_SA_120g_C2M_tp1a_08_17_2022.xlsx"
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PATH_LEAK = re.compile(r"(?i)(?:^|[\s=(\[\{\"'])" r"(?:[a-z]:[\\/]|\\\\|/|file://|\.\.?[\\/])")
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 128 * 1024 * 1024
SHARED_HELPER_SCHEMA = "sipi.com-current.shared-custody.v1"
ENVIRONMENT_SCOPE = "environment_local_scoped_no_canonical_pe_strategy"
COM01_BINARY_BASENAME = (
    "sipi-com-direct-config-validate.exe"
    if os.name == "nt"
    else "sipi-com-direct-config-validate"
)
COM01_SCENARIO_CONTRACT = {
    "xlsx_json_default_r480": ("passed", None, "structured"),
    "xlsx_text_default_r480": ("passed", None, "text"),
    "xlsx_materialized_json_default": ("values_equal_fingerprint_drift", None, "materialized"),
    "xlsx_experimental_corrected_profile": ("passed", None, "structured"),
    "xlsx_custom_standard_reader": ("passed", None, "structured"),
    "csv_package_warning_json_loader": ("passed", None, "structured"),
    "xlsx_custom_fix_config_defaults": ("passed", None, "structured"),
    "mutually_exclusive_json_modes": ("error_code_match", "argument_error", "error"),
    "custom_profile_without_selector": ("error_code_match", "profile_error", "error"),
    "reader_without_custom_profile": ("error_code_match", "profile_error", "error"),
    "unknown_fix_id": ("error_code_match", "profile_error", "error"),
    "duplicate_override": ("error_code_match", "override_error", "error"),
    "unsupported_extension": ("error_code_match", "unsupported_path", "error"),
    "missing_config_path": ("error_code_match", "input_error", "error"),
}
COM01_STRUCTURED_OBSERVATIONS = {
    "xlsx_json_default_r480": ("r480", 0, (), "36b6ee0f4f461eb051d539e7ab7a8187b0789a24c00409b8824391d43c8cb558"),
    "xlsx_experimental_corrected_profile": ("experimental_corrected", 0, (), "8859c9fec939865d8a8566ca8e4ae4edf7af77b5d438fc21462547d261e050ed"),
    "xlsx_custom_standard_reader": ("custom", 0, (), "e529b4d32331ad759fcedab142d720fdc05e323df373f46cae2b5f9c6d5f79ca"),
    "csv_package_warning_json_loader": ("r480", 2, ("R480-PKG-DUP-NAME",), "afb7a6522d8434f0414cfe9514b77e192d856241ac42e447bdc8de86f7d5380c"),
    "xlsx_custom_fix_config_defaults": ("custom", 0, (), "e529b4d32331ad759fcedab142d720fdc05e323df373f46cae2b5f9c6d5f79ca"),
}
COM01_TEXT_OBSERVATION = (
    (47, "cc05aa6efa7f46a138d4b7a2f0588833376705bd3051da206b07126dbc4a4c49"),
    (46, "a7e4fa38f3a9ffc563554f0e9a4bbcbbe04d6fab79c087e46b3e73494710246d"),
)
COM01_MATERIALIZED_OBSERVATION = (
    ("9305ec5f61f31bfb35dec92c91ecd886a0680a1180e58531da5bf9bc1f14f7b6", "d6963c122533d58273e4ebf3224bade1dc38b040f740c1cd92d4c9727e4483dc"),
    ("9d5ce30e6d90812ea7edfc9212c531a4b400194af70ead78cc38ffea40b47c45", "2d0791ee45451a46093e3318c16d3c3b3797ef3fecb687fa56db84aaa8ef7532"),
)
COM01_ERROR_OBSERVATIONS = {
    "mutually_exclusive_json_modes": (2, "argument_error", (352, "6fe5385e6fd305bcf65f3b304bb5ee5300130ee3a9d4a03a1a037b9af6d2c1cd"), (83, "453347a91d36495bb9503edf090a6d98708fa598419364acf925ebb8ff829981")),
    "custom_profile_without_selector": (3, "profile_error", (48, "e22fa7fa3eb52750550139863c6aa50ce11338db4962e8f0ac7eccc46d72b35d"), (73, "68ef45e782996207b6540473941b2c5abf20834b785fb7c4a7328f8991695c2d")),
    "reader_without_custom_profile": (3, "profile_error", (48, "c37b3783341ce92a647cc6d4ffb4ab45db336d630fdbef3f03d1c55484d63664"), (73, "cbbc66e5863fdce6dad8286c40a258a4a11c5f424936fc761ce93b4d0f209dcf")),
    "unknown_fix_id": (3, "profile_error", (46, "a7317acd974e3697355d20e3c8438862b65b1e05c38de99601261b49a59f4f6f"), (71, "0ec9d59d9ca5a450c18d7ad0bfae2c890b0e5c56ec8698c42b9243567a02942a")),
    "duplicate_override": (2, "override_error", (25, "9000af808d3e8756b97db7055bc43c8e36b01500e4dd496ccf69cdb92539042b"), (42, "5639a9c691cf89c521b858e7f5bc9a22f60e9ebc8f9e7e5fd52a5c86050562bf")),
    "unsupported_extension": (3, "unsupported_path", (57, "7641b44ff04b2981cfb4b8921bcdbf7dcabf7196c28497713f4766bf15fc7939"), (77, "d50de239486fea93403c92f358f401aeef425cbbb556eb08fa3766b3041dbe61")),
    "missing_config_path": (3, "input_error", (36, "1164003c5460dd444bc3298cdd23eaadfa1e89f17cf04011f4ebfc9332314e70"), (50, "ce54f932b6857dc591230c5e62be94dc2020cef26f018bd65b80d38671e3dc7c")),
}
COM01_ROUTING_CONTRACT = {
    "xlsx_json_default_r480": ("primary_xlsx", "json"),
    "xlsx_text_default_r480": ("primary_xlsx", "text"),
    "xlsx_materialized_json_default": ("primary_xlsx", "materialized_json"),
    "xlsx_experimental_corrected_profile": ("primary_xlsx", "json"),
    "xlsx_custom_standard_reader": ("primary_xlsx", "json"),
    "csv_package_warning_json_loader": ("package_warning_csv", "json"),
    "xlsx_custom_fix_config_defaults": ("primary_xlsx", "json"),
    "mutually_exclusive_json_modes": ("primary_xlsx", "json_and_materialized_json"),
    "custom_profile_without_selector": ("primary_xlsx", "json"),
    "reader_without_custom_profile": ("primary_xlsx", "json"),
    "unknown_fix_id": ("primary_xlsx", "json"),
    "duplicate_override": ("primary_xlsx", "json"),
    "unsupported_extension": ("unsupported_text", "json"),
    "missing_config_path": ("missing_xlsx", "json"),
}
UPSTREAM_ENV_CLEARED_KEYS = (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "PYTHONBREAKPOINT",
    "PYTHONINSPECT",
    "PYTHONWARNINGS",
    "PYTHONSAFEPATH",
    "PYTHONEXECUTABLE",
    "PYTHONUTF8",
    "PYTHONIOENCODING",
    "PYTHONHASHSEED",
    "PYTHONMALLOC",
    "PYTHONPROFILEIMPORTTIME",
    "VIRTUAL_ENV",
    "UV_PROJECT_ENVIRONMENT",
    "UV_PYTHON",
    "UV_PYTHON_DOWNLOADS",
    "UV_INDEX_URL",
    "UV_EXTRA_INDEX_URL",
    "UV_NO_INDEX",
    "UV_LINK_MODE",
    "UV_CACHE_DIR",
    "PIP_CONFIG_FILE",
    "PIP_INDEX_URL",
    "PIP_EXTRA_INDEX_URL",
    "PIP_FIND_LINKS",
    "PIP_REQUIRE_VIRTUALENV",
    "PIP_NO_INDEX",
    "CONDA_PREFIX",
    "CONDA_DEFAULT_ENV",
    "CONDA_PYTHON_EXE",
)
BUILD_ENV_CLEARED_KEYS = (
    "RUSTFLAGS",
    "CARGO_ENCODED_RUSTFLAGS",
    "RUSTC_WRAPPER",
    "RUSTC_WORKSPACE_WRAPPER",
    "CARGO_BUILD_RUSTC",
    "CARGO_BUILD_RUSTC_WRAPPER",
    "CARGO_BUILD_RUSTDOC",
    "RUSTDOCFLAGS",
    "CARGO_BUILD_TARGET",
    "RUSTUP_TOOLCHAIN",
    "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER",
    "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_RUSTFLAGS",
    "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_RUSTDOCFLAGS",
    "CARGO_BUILD_JOBS",
    "CARGO_BUILD_PIPELINING",
    "RUSTC_BOOTSTRAP",
    "CARGO_BUILD_RUSTFLAGS",
    "CARGO_BUILD_RUSTDOCFLAGS",
    "CARGO_CONFIG",
    "CC",
    "CXX",
    "CL",
    "LINK",
    "LIB",
    "INCLUDE",
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _hex(value: Any) -> bool:
    return type(value) is str and HEX64.fullmatch(value) is not None


def _git(root: Path, *args: str, raw: bool = False) -> bytes | str:
    completed = _popen_bounded(
        ["git", "-c", "core.autocrlf=false", "-C", str(root), *args],
        cwd=root,
        env=None,
        timeout=120,
        max_stdout=MAX_ARCHIVE_BYTES,
        max_stderr=MAX_CAPTURE_BYTES,
    )
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(completed.returncode, completed.args, completed.stdout, completed.stderr)
    return completed.stdout if raw else completed.stdout.decode("ascii").strip()


def _archive(root: Path, revision: str) -> bytes:
    completed = _popen_bounded(
        ["git", "-c", "core.autocrlf=false", "-C", str(root), "archive", "--format=tar", revision],
        cwd=root,
        env=None,
        timeout=120,
        max_stdout=MAX_ARCHIVE_BYTES,
        max_stderr=MAX_CAPTURE_BYTES,
    )
    if completed.returncode != 0:
        raise RuntimeError("git archive failed")
    if len(completed.stdout) > MAX_ARCHIVE_BYTES or len(completed.stderr) > MAX_CAPTURE_BYTES:
        raise RuntimeError("git archive output exceeds bound")
    return completed.stdout


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400)
    except (OSError, ValueError):
        return True


def _regular_identity(path: Path) -> tuple[int, int, int, int]:
    if _is_reparse(path):
        raise RuntimeError("path is a symlink or reparse point")
    value = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        raise RuntimeError("path is not a singly-linked regular file")
    return (value.st_dev, value.st_ino, value.st_size, value.st_nlink)


def _popen_bounded(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None,
    timeout: int,
    max_stdout: int,
    max_stderr: int,
) -> subprocess.CompletedProcess[bytes]:
    """Drain both pipes concurrently and kill on the first byte/time violation."""
    if timeout <= 0 or max_stdout < 0 or max_stderr < 0:
        raise ValueError("subprocess bounds must be positive")
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None and process.stderr is not None
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": max_stdout, "stderr": max_stderr}
    overflow = threading.Event()

    def drain(name: str, stream: Any) -> None:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                return
            buffer = buffers[name]
            remaining = limits[name] - len(buffer)
            if len(chunk) > remaining:
                if remaining > 0:
                    buffer.extend(chunk[:remaining])
                overflow.set()
                return
            buffer.extend(chunk)

    threads = [
        threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout
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
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        for thread in threads:
            thread.join(timeout=10)
        for stream in (process.stdout, process.stderr):
            stream.close()
    if any(thread.is_alive() for thread in threads):
        raise RuntimeError("subprocess drain thread did not terminate")
    if timed_out:
        raise subprocess.TimeoutExpired(command, timeout)
    if overflow.is_set():
        raise RuntimeError("subprocess capture exceeds bound")
    return subprocess.CompletedProcess(command, process.returncode, bytes(buffers["stdout"]), bytes(buffers["stderr"]))


def _bounded_run(
    command: list[str], *, cwd: Path, env: dict[str, str] | None, timeout: int
) -> subprocess.CompletedProcess[bytes]:
    return _popen_bounded(
        command,
        cwd=cwd,
        env=env,
        timeout=timeout,
        max_stdout=MAX_CAPTURE_BYTES,
        max_stderr=MAX_CAPTURE_BYTES,
    )


def _raw_absolute(path: Path) -> Path:
    if ".." in path.parts:
        raise RuntimeError("output path contains parent traversal")
    return path if path.is_absolute() else Path.cwd() / path


def _reject_raw_reparse_components(path: Path) -> None:
    """Check lexical path components before any resolve can erase a junction."""
    raw = _raw_absolute(path)
    anchor = Path(raw.anchor)
    cursor = anchor
    if os.path.lexists(cursor) and _is_reparse(cursor):
        raise RuntimeError("output path anchor is a symlink or reparse point")
    for part in raw.relative_to(anchor).parts:
        cursor /= part
        if not os.path.lexists(cursor):
            break
        cursor.lstat()
        if _is_reparse(cursor):
            raise RuntimeError("output path has a raw symlink/reparse component")


def _atomic_json_create(path: Path, value: Any, *, output_root: Path) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if len(payload) > MAX_REPORT_BYTES:
        raise RuntimeError("JSON output exceeds bound")
    if not path.name or path.name in {".", ".."}:
        raise RuntimeError("output filename is unsafe")
    raw_path = _raw_absolute(path)
    raw_root = _raw_absolute(output_root)
    raw_parent = raw_path.parent
    if raw_parent != raw_root and raw_root not in raw_parent.parents:
        raise RuntimeError("output path lexically escapes its declared root")
    _reject_raw_reparse_components(raw_root)
    _reject_raw_reparse_components(raw_parent)
    if os.path.lexists(raw_path):
        _reject_raw_reparse_components(raw_path)
    if not raw_parent.exists() or not raw_parent.is_dir():
        raise RuntimeError("output parent must already exist")
    root = raw_root.resolve(strict=True)
    parent = raw_parent.resolve(strict=True)
    if parent != root and root not in parent.parents:
        raise RuntimeError("output path escapes its declared root")
    cursor = parent
    while True:
        if _is_reparse(cursor):
            raise RuntimeError("output path has a reparse-point ancestor")
        if cursor == root:
            break
        if cursor.parent == cursor:
            raise RuntimeError("output root containment failed")
        cursor = cursor.parent
    resolved_path = parent / raw_path.name
    if resolved_path.exists() or resolved_path.is_symlink():
        raise FileExistsError("output already exists")
    temporary = resolved_path.with_name(f".{resolved_path.name}.{secrets.token_hex(16)}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _regular_identity(temporary)
        os.link(temporary, resolved_path)
        temporary.unlink()
        if _bounded_file(resolved_path, MAX_REPORT_BYTES) != (len(payload), _sha256(payload)):
            raise RuntimeError("published output identity drift")
    finally:
        if temporary.exists():
            temporary.unlink()


def _extract_archive(payload: bytes, destination: Path) -> None:
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise RuntimeError("archive exceeds bound")
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    seen: set[str] = set()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for member in archive.getmembers():
            raw = member.name.replace("\\", "/")
            path = PurePosixPath(raw)
            if (
                not raw
                or path.is_absolute()
                or not path.parts
                or any(part in ("", ".", "..") for part in path.parts)
                or ":" in path.parts[0]
                or member.issym()
                or member.islnk()
                or not (member.isfile() or member.isdir())
            ):
                raise RuntimeError(f"archive member is not admitted: {member.name}")
            normalized = path.as_posix()
            if normalized in seen:
                raise RuntimeError("duplicate archive member")
            seen.add(normalized)
            if member.isfile() and (member.size < 0 or member.size > MAX_ARCHIVE_MEMBER_BYTES):
                raise RuntimeError("archive member exceeds bound")
            total += max(member.size, 0)
            if total > MAX_ARCHIVE_BYTES:
                raise RuntimeError("archive expanded bytes exceed bound")
            target = (destination / Path(*path.parts)).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"archive path escapes destination: {member.name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError("archive member payload missing")
            content = source.read(member.size + 1)
            if len(content) != member.size:
                raise RuntimeError("archive member size drift")
            with target.open("xb") as output:
                output.write(content)
            _regular_identity(target)


def _materialize(root: Path, revision: str, destination: Path) -> dict[str, Any]:
    payload = _archive(root, revision)
    _extract_archive(payload, destination)
    resolved = str(_git(root, "rev-parse", f"{revision}^{{commit}}"))
    tree = str(_git(root, "rev-parse", f"{resolved}^{{tree}}"))
    return {
        "commit": resolved,
        "tree": tree,
        "archive": {
            "bytes": len(payload),
            "sha256": _sha256(payload),
            "command": "git -c core.autocrlf=false archive --format=tar <revision>",
            "path_redacted": True,
        },
    }


def _git_inventory(root: Path, revision: str, prefixes: Iterable[Path]) -> dict[str, Any]:
    """Recompute selected source identity directly from the pinned Git object."""
    with tempfile.TemporaryDirectory(prefix="sipi-com-git-inventory-") as directory:
        extracted = Path(directory) / "archive"
        _extract_archive(_archive(root, revision), extracted)
        return _inventory(extracted, prefixes)


def _git_blob_receipt(root: Path, revision: str, relative: Path) -> dict[str, Any]:
    raw = relative.as_posix()
    payload = _git(root, "show", f"{revision}:{raw}", raw=True)
    assert isinstance(payload, bytes)
    if len(payload) > MAX_FILE_BYTES:
        raise RuntimeError("Git blob exceeds bound")
    return {"path": raw, "bytes": len(payload), "sha256": _sha256(payload)}


def _harness_receipt(repo: Path, revision: str, files: Iterable[Path]) -> dict[str, Any]:
    commit = str(_git(repo, "rev-parse", f"{revision}^{{commit}}"))
    tree = str(_git(repo, "rev-parse", f"{commit}^{{tree}}"))
    receipts = [_git_blob_receipt(repo, commit, path) for path in files]
    for receipt in receipts:
        live = _safe_file(repo, Path(receipt["path"]))
        size, sha = _bounded_file(live)
        if (size, sha) != (receipt["bytes"], receipt["sha256"]):
            raise RuntimeError("executing harness differs from pinned harness commit")
    return {
        "commit": commit,
        "tree": tree,
        "files": receipts,
        "shared_helper_schema": SHARED_HELPER_SCHEMA,
    }


def _safe_file(root: Path, relative: Path) -> Path:
    raw = os.fspath(relative)
    host = Path(raw)
    posix = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if (
        not raw
        or "\x00" in raw
        or host.is_absolute()
        or bool(host.anchor)
        or posix.is_absolute()
        or bool(posix.anchor)
        or windows.is_absolute()
        or bool(windows.anchor)
        or bool(windows.drive)
        or ".." in re.split(r"[\\/]", raw)
    ):
        raise RuntimeError("archive-relative path is unsafe")
    base = root.resolve()
    unresolved = root / relative
    cursor = unresolved
    while True:
        if cursor.exists() and _is_reparse(cursor):
            raise RuntimeError("archive-relative path crosses a reparse point")
        if cursor == root:
            break
        if cursor.parent == cursor:
            raise RuntimeError("archive-relative path escaped its root")
        cursor = cursor.parent
    path = unresolved.resolve()
    if path == base or base not in path.parents or not path.is_file():
        raise RuntimeError(f"archive-relative file is missing or escaped: {relative.as_posix()}")
    _regular_identity(path)
    return path


def _bounded_file(path: Path, maximum: int = MAX_FILE_BYTES) -> tuple[int, str]:
    identity = _regular_identity(path)
    before = path.stat()
    if before.st_size < 0 or before.st_size > maximum:
        raise RuntimeError("file exceeds bounded size")
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while True:
            block = stream.read(min(1024 * 1024, maximum - size + 1))
            if not block:
                break
            size += len(block)
            if size > maximum:
                raise RuntimeError("file exceeds bounded size")
            hasher.update(block)
    after = path.stat()
    if size != before.st_size or after.st_size != before.st_size or _regular_identity(path) != identity:
        raise RuntimeError("file changed while hashing")
    return size, hasher.hexdigest()


def _bounded_cargo_source(
    path: Path, target_root: Path, maximum: int = 512 * 1024 * 1024
) -> dict[str, Any]:
    """Admit Cargo's standard hardlinked artifact only inside its target root."""
    _reject_raw_reparse_components(target_root)
    _reject_raw_reparse_components(path.parent)
    root = target_root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    if resolved == root or root not in resolved.parents or _is_reparse(path):
        raise RuntimeError("Cargo artifact escaped target root or is reparse-backed")
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink < 1:
        raise RuntimeError("Cargo artifact is not a regular file")
    if before.st_size < 0 or before.st_size > maximum:
        raise RuntimeError("Cargo artifact exceeds bounded size")
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while True:
            block = stream.read(min(1024 * 1024, maximum - size + 1))
            if not block:
                break
            size += len(block)
            if size > maximum:
                raise RuntimeError("Cargo artifact exceeds bounded size")
            hasher.update(block)
    after = path.stat(follow_symlinks=False)
    identity = (before.st_dev, before.st_ino, before.st_size, before.st_nlink)
    if (after.st_dev, after.st_ino, after.st_size, after.st_nlink) != identity or size != before.st_size:
        raise RuntimeError("Cargo artifact changed while hashing")
    return {
        "basename": path.name,
        "bytes": size,
        "sha256": hasher.hexdigest(),
        "nlink": before.st_nlink,
        "path_redacted": True,
    }


def _execution_copy_receipt(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    size, sha = _bounded_file(path, 512 * 1024 * 1024)
    receipt = {
        "basename": path.name,
        "bytes": size,
        "sha256": sha,
        "nlink": path.stat(follow_symlinks=False).st_nlink,
        "path_redacted": True,
    }
    if receipt["nlink"] != 1 or (receipt["bytes"], receipt["sha256"]) != (
        expected["bytes"],
        expected["sha256"],
    ):
        raise RuntimeError("execution copy identity does not match Cargo source")
    return receipt


def _copy_cargo_binary(
    source: Path, target_root: Path, execution_root: Path
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    source_receipt = _bounded_cargo_source(source, target_root)
    raw_target = _raw_absolute(target_root)
    raw_execution = _raw_absolute(execution_root)
    if raw_execution.parent != raw_target:
        raise RuntimeError("execution directory is not tightly rooted in Cargo target")
    _reject_raw_reparse_components(raw_target)
    if os.path.lexists(raw_execution):
        raise FileExistsError("execution directory already exists")
    execution_root.mkdir(parents=False, exist_ok=False)
    if _is_reparse(execution_root) or execution_root.resolve().parent != target_root.resolve():
        raise RuntimeError("execution directory materialization drift")
    destination = execution_root / source.name
    copied = 0
    with source.open("rb") as input_stream, destination.open("xb") as output_stream:
        while True:
            block = input_stream.read(1024 * 1024)
            if not block:
                break
            copied += len(block)
            if copied > source_receipt["bytes"]:
                raise RuntimeError("Cargo source changed while copying")
            output_stream.write(block)
        output_stream.flush()
        os.fsync(output_stream.fileno())
    if copied != source_receipt["bytes"]:
        raise RuntimeError("Cargo source changed while copying")
    if _bounded_cargo_source(source, target_root) != source_receipt:
        raise RuntimeError("Cargo source identity changed during copy")
    copy_receipt = _execution_copy_receipt(destination, source_receipt)
    return destination, source_receipt, copy_receipt


def _inventory(root: Path, prefixes: Iterable[Path]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for prefix in prefixes:
        path = root / prefix
        candidates = [path] if path.is_file() else sorted(path.rglob("*"))
        for item in candidates:
            if (
                not item.is_file()
                or "__pycache__" in item.parts
                or item.suffix in {".pyc", ".pyo"}
                or any(part.endswith(".egg-info") for part in item.parts)
            ):
                continue
            size, sha = _bounded_file(item)
            entries.append({"path": item.relative_to(root).as_posix(), "bytes": size, "sha256": sha})
    entries.sort(key=lambda item: item["path"])
    return {
        "file_count": len(entries),
        "total_bytes": sum(item["bytes"] for item in entries),
        "sha256": _sha256(_canonical(entries)),
    }


def _directory_inventory(root: Path) -> dict[str, Any]:
    if _is_reparse(root) or not root.is_dir():
        raise RuntimeError("cache root is missing or a reparse point")
    entries: list[dict[str, Any]] = []
    total = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in {"bin", "env"}:
            continue
        if path.is_dir():
            if _is_reparse(path):
                raise RuntimeError("cache inventory crosses a reparse point")
            continue
        size, sha = _bounded_file(path, MAX_FILE_BYTES)
        total += size
        if len(entries) >= 100_000 or total > 4 * 1024 * 1024 * 1024:
            raise RuntimeError("cache inventory exceeds bound")
        entries.append({"path": relative.as_posix(), "bytes": size, "sha256": sha})
    return {"basename": root.name, "path_redacted": True, "file_count": len(entries), "total_bytes": total, "sha256": _sha256(_canonical(entries))}


def _resolve(value: str | Path, role: str) -> Path:
    literal = Path(value)
    if literal.is_file():
        resolved = literal.resolve()
        _regular_identity(resolved)
        return resolved
    discovered = shutil.which(str(value))
    if discovered is None or not Path(discovered).is_file():
        raise RuntimeError(f"{role} executable cannot be resolved")
    resolved = Path(discovered).resolve()
    _regular_identity(resolved)
    return resolved


def _resolve_bootstrap(value: str | Path, role: str) -> Path:
    """Resolve only a rustup bootstrap proxy; it is never executed as evidence tool."""
    literal = Path(value)
    candidate = literal if literal.is_file() else Path(shutil.which(str(value)) or "")
    if not candidate.is_file() or _is_reparse(candidate):
        raise RuntimeError(f"{role} bootstrap executable cannot be resolved")
    return candidate.resolve()


def _tool_identity(path: Path, role: str, args: tuple[str, ...]) -> dict[str, Any]:
    result = _bounded_run([str(path), *args], cwd=path.parent, env=None, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"{role} version query failed")
    basename = path.name
    if not basename or "/" in basename or "\\" in basename:
        raise RuntimeError(f"{role} identity contains a path")
    size, file_sha = _bounded_file(path, 256 * 1024 * 1024)
    return {
        "role": role,
        "basename": basename,
        "file_bytes": size,
        "file_sha256": file_sha,
        "version_args": (
            ["-flavor", "link", "help"]
            if role == "linker" and args == ("-flavor", "link", "/?")
            else list(args)
        ),
        "version_exit": 0,
        "version_stdout_sha256": _sha256(result.stdout),
        "version_stderr_sha256": _sha256(result.stderr),
        "path_redacted": True,
    }


def _toolchain(cargo: str, python: str, uv: str) -> tuple[dict[str, Any], dict[str, Path]]:
    cargo_bootstrap = _resolve_bootstrap(cargo, "cargo")
    rustc_bootstrap = _resolve_bootstrap(cargo_bootstrap.with_name(f"rustc{cargo_bootstrap.suffix}"), "rustc")
    sysroot_result = _bounded_run([str(rustc_bootstrap), "--print", "sysroot"], cwd=rustc_bootstrap.parent, env=None, timeout=30)
    if sysroot_result.returncode != 0:
        raise RuntimeError("rustc sysroot query failed")
    sysroot = Path(sysroot_result.stdout.decode("utf-8").strip())
    cargo_path = _resolve(sysroot / "bin" / f"cargo{cargo_bootstrap.suffix}", "cargo")
    rustc_path = _resolve(sysroot / "bin" / f"rustc{cargo_bootstrap.suffix}", "rustc")
    python_path = _resolve(python, "python")
    uv_path = _resolve(uv, "uv")
    if os.name == "nt":
        linker_path = _resolve(sysroot / "lib" / "rustlib" / "x86_64-pc-windows-msvc" / "bin" / "rust-lld.exe", "linker")
        linker_args = ("-flavor", "link", "/?")
    else:
        linker_path = _resolve("cc", "linker")
        linker_args = ("--version",)
    cargo_home = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")).resolve()
    tools = {"cargo": cargo_path, "rustc": rustc_path, "python": python_path, "uv": uv_path, "linker": linker_path, "cargo_home": cargo_home}
    return (
        {
            role: _tool_identity(path, role, ("--version",))
            for role, path in tools.items()
            if role not in {"linker", "cargo_home"}
        } | {"linker": _tool_identity(linker_path, "linker", linker_args)},
        tools,
    )


def _cargo_dependency_cache_inventory(source_root: Path, tools: dict[str, Path], timeout: int) -> dict[str, Any]:
    environment = _clean_build_env(tools, source_root.parent / "cargo-metadata-target", source_root, "0")
    completed = _popen_bounded(
        [str(tools["cargo"]), "metadata", "--manifest-path", str(source_root / CRATE_RELATIVE / "Cargo.toml"), "--locked", "--offline", "--format-version", "1"],
        cwd=source_root,
        env=environment,
        timeout=timeout,
        max_stdout=32 * 1024 * 1024,
        max_stderr=MAX_CAPTURE_BYTES,
    )
    if completed.returncode != 0:
        raise RuntimeError("cargo metadata failed while binding dependency cache")
    try:
        metadata = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("cargo metadata output drift") from error
    packages = metadata.get("packages")
    if type(packages) is not list:
        raise RuntimeError("cargo metadata package list drift")
    cargo_home = tools["cargo_home"].resolve()
    receipts = []
    for package in packages:
        if type(package) is not dict or package.get("source") is None:
            continue
        manifest = Path(package.get("manifest_path", "")).resolve()
        if cargo_home not in manifest.parents:
            raise RuntimeError("resolved Cargo dependency escaped bound CARGO_HOME")
        package_root = manifest.parent
        inventory = _directory_inventory(package_root)
        receipts.append({"name": package.get("name"), "version": package.get("version"), "source": package.get("source"), "inventory": inventory})
    receipts.sort(key=lambda value: (str(value["name"]), str(value["version"]), str(value["source"])))
    return {
        "scope": "resolved_locked_dependency_sources",
        "path_redacted": True,
        "package_count": len(receipts),
        "file_count": sum(item["inventory"]["file_count"] for item in receipts),
        "total_bytes": sum(item["inventory"]["total_bytes"] for item in receipts),
        "sha256": _sha256(_canonical(receipts)),
    }


def _clean_build_env(
    tools: dict[str, Path], target: Path, source_root: Path, source_date_epoch: str
) -> dict[str, str]:
    environment = dict(os.environ)
    dynamic = tuple(
        key
        for key in environment
        if key.startswith("CARGO_TARGET_")
        and key.endswith(("_RUSTFLAGS", "_RUSTDOCFLAGS", "_LINKER"))
    )
    for key in (*BUILD_ENV_CLEARED_KEYS, *dynamic):
        environment.pop(key, None)
    environment.update(
        {
            "RUSTC": str(tools["rustc"]),
            "CARGO_TARGET_DIR": str(target),
            "CARGO_INCREMENTAL": "0",
            "SOURCE_DATE_EPOCH": source_date_epoch,
            "CARGO_NET_OFFLINE": "true",
            "CARGO_TERM_COLOR": "never",
            "CARGO_HOME": str(tools["cargo_home"]),
            "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER": str(tools["linker"]),
            "RUSTFLAGS": "-C link-arg=/Brepro --remap-path-prefix=" + str(source_root) + "=C:/sipi-candidate",
        }
    )
    return environment


def _normalized_log(payload: bytes) -> str:
    counts: Counter[str] = Counter()
    for line in payload.decode("utf-8", errors="replace").splitlines():
        text = line.strip().casefold()
        if text.startswith("compiling "):
            counts["compiling"] += 1
        elif text.startswith("finished "):
            counts["finished"] += 1
        elif text.startswith("warning"):
            counts["warning"] += 1
        elif text.startswith("error"):
            counts["error"] += 1
        elif text:
            counts["other"] += 1
    return json.dumps(counts, sort_keys=True, separators=(",", ":"))


def _build(
    source_root: Path,
    target: Path,
    tools: dict[str, Path],
    timeout: int,
    source_date_epoch: str,
) -> tuple[Path, Path, dict[str, Any]]:
    environment = _clean_build_env(tools, target, source_root, source_date_epoch)
    command = [
        str(tools["cargo"]),
        "build",
        "--manifest-path",
        str(source_root / CRATE_RELATIVE / "Cargo.toml"),
        "--bin",
        "sipi-com-direct-config-validate",
        "--release",
        "--locked",
        "--offline",
        "--config",
        "build.rustflags=[]",
        "--config",
        "build.rustdocflags=[]",
    ]
    completed = _bounded_run(command, cwd=source_root, env=environment, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError("candidate archive build failed")
    # CARGO_TARGET_DIR is normally outside source_root; resolve from the target itself.
    cargo_binary = target / "release" / "sipi-com-direct-config-validate"
    if os.name == "nt":
        cargo_binary = cargo_binary.with_suffix(".exe")
    if not cargo_binary.is_file():
        raise RuntimeError("candidate archive build did not produce config-validate")
    binary, cargo_source, binary_pre = _copy_cargo_binary(
        cargo_binary, target, target / "sipi-execution"
    )
    return binary, cargo_binary, {
        "command": "cargo build --manifest-path <candidate>/crates/sipi-agent-com-direct/Cargo.toml --bin sipi-com-direct-config-validate --release --locked --offline",
        "cargo_source_pre": cargo_source,
        "binary_pre": binary_pre,
        "stdout_sha256": _sha256(_normalized_log(completed.stdout).encode("ascii")),
        "stderr_sha256": _sha256(_normalized_log(completed.stderr).encode("ascii")),
        "log_policy": "stable_event_categories",
            "environment": {
            "cleared": list(BUILD_ENV_CLEARED_KEYS),
            "incremental": "0",
            "offline": True,
            "rustc_forced": True,
            "wrappers_cleared": True,
            "source_path_remapped": True,
                "target_is_independent": True,
                "cargo_home_policy": "host_cargo_home_retained_for_offline_dependency_cache",
                "native_linker_overrides_cleared": True,
                "linker_forced": True,
                "cargo_cache_bound_pre_post": True,
            },
    }


def _upstream_env() -> dict[str, str]:
    environment = dict(os.environ)
    for key in UPSTREAM_ENV_CLEARED_KEYS:
        environment.pop(key, None)
    for key in tuple(environment):
        if key == "VIRTUAL_ENV" or key.startswith("PYTHON"):
            environment.pop(key, None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["UV_NO_CONFIG"] = "1"
    environment["UV_OFFLINE"] = "1"
    environment["UV_PYTHON_DOWNLOADS"] = "never"
    environment["UV_LINK_MODE"] = "copy"
    return environment


def _uv_run(tools: dict[str, Path], root: Path, python: Path, script: str, args: list[str], timeout: int) -> subprocess.CompletedProcess[bytes]:
    command = [
        str(tools["uv"]),
        "run",
        "--frozen",
        "--offline",
        "--project",
        str(root),
        "--python",
        str(python),
        "python",
        "-c",
        script,
        *args,
    ]
    return _bounded_run(command, cwd=root, env=_upstream_env(), timeout=timeout)


def _source_receipt(root: Path) -> dict[str, Any]:
    package = root / "src" / "agent_com"
    files = []
    for path in sorted(package.rglob("*.py"), key=lambda item: item.as_posix()):
        size, sha = _bounded_file(path)
        files.append({"path": path.relative_to(root).as_posix(), "bytes": size, "sha256": sha})
    if not files:
        raise RuntimeError("upstream source package is empty")
    init = package / "__init__.py"
    init_size, init_sha = _bounded_file(init)
    return {
        "module_file": {
            "relative_path": "src/agent_com/__init__.py",
            "basename": "__init__.py",
            "bytes": init_size,
            "sha256": init_sha,
            "root_contained": True,
            "path_redacted": True,
        },
        "package_source_inventory": {
            "file_count": len(files),
            "total_bytes": sum(item["bytes"] for item in files),
            "sha256": _sha256(_canonical(files)),
        },
    }


def _probe_upstream(root: Path, tools: dict[str, Path], timeout: int, source: dict[str, Any]) -> dict[str, Any]:
    script = (
        "import agent_com, hashlib, json, numpy, openpyxl, pathlib, scipy, yaml\n"
        "root=pathlib.Path.cwd().resolve()\n"
        "mods={}\n"
        "for name,module in [('agent_com',agent_com),('numpy',numpy),('openpyxl',openpyxl),('scipy',scipy),('yaml',yaml)]:\n"
        " p=pathlib.Path(module.__file__).resolve(); rel=p.relative_to(root).as_posix()\n"
        " b=p.read_bytes(); mods[name]={'relative_path':rel,'basename':p.name,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}\n"
        "print(json.dumps({'modules':mods,'version':getattr(agent_com,'__version__',None)},sort_keys=True,separators=(',',':')))"
    )
    completed = _uv_run(tools, root, tools["python"], script, [], timeout)
    if completed.returncode != 0:
        raise RuntimeError("pinned Agent-COM uv runtime probe failed")
    lines = completed.stdout.decode("utf-8", errors="replace").splitlines()
    if not lines:
        raise RuntimeError("pinned Agent-COM uv runtime probe was empty")
    try:
        value = json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise RuntimeError("pinned Agent-COM uv runtime probe was not JSON") from error
    modules = value.get("modules")
    if not isinstance(modules, dict) or set(modules) != {"agent_com", "numpy", "openpyxl", "scipy", "yaml"}:
        raise RuntimeError("upstream module identity set drift")
    if modules["agent_com"].get("relative_path") != "src/agent_com/__init__.py":
        raise RuntimeError("Agent-COM import escaped the materialized archive")
    for name, identity in modules.items():
        relative = identity.get("relative_path")
        if not isinstance(relative, str) or not (
            relative == "src/agent_com/__init__.py" or relative.startswith(".venv/")
        ):
            raise RuntimeError(f"{name} import escaped the materialized project")
        path = _safe_file(root, Path(relative))
        size, sha = _bounded_file(path)
        if (identity.get("bytes"), identity.get("sha256")) != (size, sha):
            raise RuntimeError(f"{name} runtime module identity drift")
    stable_stdout = _canonical(value)
    stable_stderr = _normalized_log(completed.stderr).encode("ascii")
    return {
        "runtime": "executed_clean_archive_uv_frozen_offline",
        "command": "uv run --frozen --offline --project <clean-upstream> --python <pinned-python> python -c <probe>",
        "exit": 0,
        "stdout_bytes": len(stable_stdout),
        "stdout_sha256": _sha256(stable_stdout),
        "stderr_bytes": len(stable_stderr),
        "stderr_sha256": _sha256(stable_stderr),
        "source": source,
        "environment": {
            "cleared": list(UPSTREAM_ENV_CLEARED_KEYS),
            "pythonno_user_site": True,
            "uv_no_config": True,
            "project_venv": "materialized_inside_archive",
            "direct_python_fallback": False,
            "global_uv_cache": "required_path_redacted_environment_local",
            "uv_frozen": True,
            "uv_offline": True,
        },
        "modules": modules,
    }


def _derive_fixture(
    module_path: Path,
    upstream_root: Path,
    primary: Path,
    destination: Path,
    tools: dict[str, Path],
    timeout: int,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / "com-01-package-warning.csv"
    script = (
        "import importlib.util, pathlib, sys\n"
        "spec=importlib.util.spec_from_file_location('com01_fixture_helper', sys.argv[1])\n"
        "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)\n"
        "module.derive_package_warning_fixture(pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]), pathlib.Path(sys.argv[4]))\n"
    )
    completed = _uv_run(
        tools,
        upstream_root,
        tools["python"],
        script,
        [str(module_path), str(primary), str(upstream_root), str(destination)],
        timeout,
    )
    if completed.returncode != 0 or not output.is_file():
        diagnostic = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            "derived COM-01 package-warning fixture failed"
            + (f": {diagnostic[-240:]}" if diagnostic else "")
        )


def _load_semantic_runner(path: Path, corpus: Path, upstream_root: Path, candidate_root: Path, tools: dict[str, Path], timeout: int) -> ModuleType:
    name = f"com01_current_semantic_{secrets.token_hex(8)}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load archived COM-01 semantic runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CORPUS = corpus
    original_summary = module._artifact_summary

    def redacted_summary(value: Any, fixture: Path, stdout: str, stderr: str, error_category: str | None) -> dict[str, Any]:
        return original_summary(value, fixture, module._redact(stdout, fixture), module._redact(stderr, fixture), error_category)

    module._artifact_summary = redacted_summary

    def bounded_run(command: list[str], *, env: dict[str, str] | None = None) -> tuple[int, str, str]:
        del env
        if len(command) >= 3 and command[1:3] == ["-m", "agent_com.cli"]:
            completed = _uv_run(
                tools,
                upstream_root,
                tools["python"],
                "import runpy,sys; sys.argv=['agent_com.cli',*sys.argv[1:]]; runpy.run_module('agent_com.cli', run_name='__main__')",
                list(command[3:]),
                timeout,
            )
        else:
            completed = _bounded_run(command, cwd=candidate_root, env=None, timeout=timeout)
        return (
            completed.returncode,
            completed.stdout.decode("utf-8", errors="replace"),
            completed.stderr.decode("utf-8", errors="replace"),
        )

    module._run = bounded_run
    return module


def _run_scenarios(module: ModuleType, upstream_root: Path, candidate_root: Path, binary: Path, fixture: Path, scratch: Path, tools: dict[str, Path], timeout: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    corpus = module.load_corpus()
    package_fixture = scratch / "com-01-package-warning.csv"
    _derive_fixture(
        _safe_file(candidate_root, SEMANTIC_RUNNER_RELATIVE),
        upstream_root,
        fixture,
        scratch,
        tools,
        timeout,
    )
    fixtures = {"primary_xlsx": fixture, "package_warning_csv": package_fixture}
    scenarios = []
    for scenario in corpus["scenarios"]:
        role = scenario["fixture_role"]
        if role in fixtures:
            scenario_fixture = fixtures[role]
        elif role == "missing_xlsx":
            scenario_fixture = scratch / "missing.xlsx"
        elif role == "unsupported_text":
            scenario_fixture = scratch / "unsupported.txt"
            scenario_fixture.write_text("not a configuration", encoding="utf-8", newline="\n")
        else:
            raise RuntimeError(f"unknown COM-01 fixture role: {role}")
        scenarios.append(module.compare_scenario(scenario, scenario_fixture, upstream_root, binary))
    receipts = []
    for role, path in fixtures.items():
        size, sha = _bounded_file(path)
        receipts.append({"role": role, "basename": path.name, "extension": path.suffix, "bytes": size, "sha256": sha, "path_redacted": True})
    return scenarios, receipts


def _path_free(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _path_free(key)
            _path_free(item)
    elif isinstance(value, list):
        for item in value:
            _path_free(item)
    elif isinstance(value, str):
        normalized = value.replace("\\", "/")
        if PATH_LEAK.search(normalized) or normalized.startswith(("/", "../")) or "file://" in normalized.lower():
            raise ValueError("absolute path leaked into COM-01 report")


def _exact_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{label} exact schema drift")
    return value


def _exact_type(value: Any, expected: type, label: str) -> None:
    if type(value) is not expected:
        raise ValueError(f"{label} exact type drift")


def _validate_com01_scenarios(scenarios: Any) -> None:
    if type(scenarios) is not list or len(scenarios) != len(COM01_SCENARIO_CONTRACT):
        raise ValueError("COM-01 scenario list drift")
    if [item.get("id") for item in scenarios if type(item) is dict] != list(COM01_SCENARIO_CONTRACT):
        raise ValueError("COM-01 scenario order/id drift")
    scenario_keys = {
        "id", "fixture_role", "output", "oracle_exit", "candidate_exit",
        "oracle_error_category", "candidate_error_category", "oracle_summary",
        "candidate_summary", "value_match", "fingerprint_match", "difference_keys",
        "comparison",
    }
    structured_keys = {"options", "package_blocks", "parameters", "profile", "projection_sha256", "top_level_keys", "warnings"}
    materialized_keys = {"consumption_summary", "materialized", "materialized_fingerprint", "projection_sha256", "schema_version", "top_level_keys", "warnings"}
    error_keys = {"error_category", "stderr_bytes", "stderr_sha256", "stdout_bytes", "stdout_sha256"}
    text_keys = {"stdout_bytes", "stdout_sha256"}
    output_by_kind = {"structured": "json", "materialized": "materialized_json", "text": "text"}
    for scenario in scenarios:
        item = _exact_keys(scenario, scenario_keys, "COM-01 scenario")
        scenario_id = item["id"]
        comparison, category, summary_kind = COM01_SCENARIO_CONTRACT[scenario_id]
        expected_fixture_role, expected_route = COM01_ROUTING_CONTRACT[scenario_id]
        _exact_type(scenario_id, str, "COM-01 id")
        _exact_type(item["fixture_role"], str, "COM-01 fixture role")
        _exact_type(item["output"], str, "COM-01 output")
        _exact_type(item["oracle_exit"], int, "COM-01 oracle exit")
        _exact_type(item["candidate_exit"], int, "COM-01 candidate exit")
        _exact_type(item["value_match"], bool, "COM-01 value match")
        if summary_kind == "materialized":
            if item["fingerprint_match"] is not False:
                raise ValueError("COM-01 materialized fingerprint drift contract changed")
        elif item["fingerprint_match"] is not None:
            raise ValueError("COM-01 non-materialized fingerprint must be null")
        if type(item["difference_keys"]) is not list or any(type(key) is not str for key in item["difference_keys"]):
            raise ValueError("COM-01 difference key type drift")
        if item["comparison"] != comparison:
            raise ValueError(f"COM-01 comparison drift for {scenario_id}")
        if item["oracle_error_category"] != category or item["candidate_error_category"] != category:
            raise ValueError(f"COM-01 error category drift for {scenario_id}")
        if item["fixture_role"] != expected_fixture_role or item["output"] != expected_route:
            raise ValueError(f"COM-01 fixture/output routing drift for {scenario_id}")
        if summary_kind == "error":
            expected_keys = error_keys
        elif summary_kind == "text":
            expected_keys = text_keys
        elif summary_kind == "materialized":
            expected_keys = materialized_keys
        else:
            expected_keys = structured_keys
        _exact_keys(item["oracle_summary"], expected_keys, f"COM-01 oracle summary {scenario_id}")
        _exact_keys(item["candidate_summary"], expected_keys, f"COM-01 candidate summary {scenario_id}")
        for summary in (item["oracle_summary"], item["candidate_summary"]):
            if summary_kind == "structured":
                if any(type(summary[key]) is not int for key in ("options", "package_blocks", "parameters")) or type(summary["profile"]) is not str or not _hex(summary["projection_sha256"]):
                    raise ValueError("COM-01 structured summary type drift")
                if type(summary["top_level_keys"]) is not list or type(summary["warnings"]) is not list or any(type(value) is not str for value in (*summary["top_level_keys"], *summary["warnings"])):
                    raise ValueError("COM-01 structured summary list type drift")
            elif summary_kind == "text":
                if type(summary["stdout_bytes"]) is not int or not _hex(summary["stdout_sha256"]):
                    raise ValueError("COM-01 text summary type drift")
            elif summary_kind == "error":
                if summary["error_category"] != category or any(type(summary[key]) is not int for key in ("stderr_bytes", "stdout_bytes")) or not _hex(summary["stderr_sha256"]) or not _hex(summary["stdout_sha256"]):
                    raise ValueError("COM-01 error summary type drift")
            else:
                if type(summary["schema_version"]) is not int or not _hex(summary["projection_sha256"]) or not _hex(summary["materialized_fingerprint"]):
                    raise ValueError("COM-01 materialized summary scalar drift")
                materialized = _exact_keys(summary["materialized"], {"option_count", "option_keys_sha256", "parameter_count", "parameter_keys_sha256"}, "COM-01 materialized counts")
                if any(type(materialized[key]) is not int for key in ("option_count", "parameter_count")) or not _hex(materialized["option_keys_sha256"]) or not _hex(materialized["parameter_keys_sha256"]):
                    raise ValueError("COM-01 materialized count identity drift")
                consumption = _exact_keys(summary["consumption_summary"], {"status_counts", "total"}, "COM-01 consumption summary")
                statuses = _exact_keys(consumption["status_counts"], {"implemented", "obsolete", "report_only", "unimplemented", "unverified"}, "COM-01 consumption status counts")
                if type(consumption["total"]) is not int:
                    raise ValueError("COM-01 consumption total type drift")
                for counts in statuses.values():
                    counts = _exact_keys(counts, {"options", "parameters", "total"}, "COM-01 consumption status")
                    if any(type(counts[key]) is not int for key in counts):
                        raise ValueError("COM-01 consumption status type drift")
                if type(summary["top_level_keys"]) is not list or type(summary["warnings"]) is not list or any(type(value) is not str for value in (*summary["top_level_keys"], *summary["warnings"])):
                    raise ValueError("COM-01 materialized summary list type drift")
        expected_output = output_by_kind.get(summary_kind)
        if expected_output is not None and item["output"] != expected_output:
            raise ValueError(f"COM-01 output mode drift for {scenario_id}")
        if item["value_match"] is not True or item["difference_keys"] != [] or item["oracle_exit"] != item["candidate_exit"]:
            raise ValueError(f"COM-01 value/exit relation drift for {scenario_id}")
        if summary_kind == "structured":
            profile, package_blocks, warnings, projection = COM01_STRUCTURED_OBSERVATIONS[scenario_id]
            expected = {"options": 90, "package_blocks": package_blocks, "parameters": 148, "profile": profile, "projection_sha256": projection, "top_level_keys": ["config", "options", "package_blocks", "parameters", "profile", "warnings"], "warnings": list(warnings)}
            if item["oracle_exit"] != 0 or item["oracle_summary"] != expected or item["candidate_summary"] != expected:
                raise ValueError(f"COM-01 structured observation drift for {scenario_id}")
        elif summary_kind == "text":
            expected_oracle = {"stdout_bytes": COM01_TEXT_OBSERVATION[0][0], "stdout_sha256": COM01_TEXT_OBSERVATION[0][1]}
            expected_candidate = {"stdout_bytes": COM01_TEXT_OBSERVATION[1][0], "stdout_sha256": COM01_TEXT_OBSERVATION[1][1]}
            if item["oracle_exit"] != 0 or item["oracle_summary"] != expected_oracle or item["candidate_summary"] != expected_candidate:
                raise ValueError("COM-01 text observation drift")
        elif summary_kind == "materialized":
            common = {
                "consumption_summary": {"status_counts": {"implemented": {"options": 63, "parameters": 133, "total": 196}, "obsolete": {"options": 5, "parameters": 10, "total": 15}, "report_only": {"options": 21, "parameters": 5, "total": 26}, "unimplemented": {"options": 1, "parameters": 0, "total": 1}, "unverified": {"options": 0, "parameters": 0, "total": 0}}, "total": 238},
                "materialized": {"option_count": 90, "option_keys_sha256": "db2dcb5e7d9b32ee6d2c55e905fe22d28a744581c8c3a88757754b61cfbd0137", "parameter_count": 148, "parameter_keys_sha256": "0d5ac58e2807c5cda038371fcb4f3b689359a393fe0053c6f9773927227ad870"},
                "schema_version": 1,
                "top_level_keys": ["config", "config_consumption", "execution", "materialized", "materialized_fingerprint", "schema_version", "warnings"],
                "warnings": [],
            }
            expected_oracle = {**common, "projection_sha256": COM01_MATERIALIZED_OBSERVATION[0][0], "materialized_fingerprint": COM01_MATERIALIZED_OBSERVATION[0][1]}
            expected_candidate = {**common, "projection_sha256": COM01_MATERIALIZED_OBSERVATION[1][0], "materialized_fingerprint": COM01_MATERIALIZED_OBSERVATION[1][1]}
            if item["oracle_exit"] != 0 or item["oracle_summary"] != expected_oracle or item["candidate_summary"] != expected_candidate:
                raise ValueError("COM-01 materialized observation drift")
        else:
            exit_code, expected_category, oracle_error, candidate_error = COM01_ERROR_OBSERVATIONS[scenario_id]
            empty_sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            expected_oracle = {"error_category": expected_category, "stderr_bytes": oracle_error[0], "stderr_sha256": oracle_error[1], "stdout_bytes": 0, "stdout_sha256": empty_sha}
            expected_candidate = {"error_category": expected_category, "stderr_bytes": candidate_error[0], "stderr_sha256": candidate_error[1], "stdout_bytes": 0, "stdout_sha256": empty_sha}
            if item["oracle_exit"] != exit_code or item["oracle_summary"] != expected_oracle or item["candidate_summary"] != expected_candidate:
                raise ValueError(f"COM-01 error observation drift for {scenario_id}")


def _validate_archive(value: Any, label: str) -> None:
    item = _exact_keys(value, {"bytes", "sha256", "command", "path_redacted"}, label)
    _exact_type(item["bytes"], int, f"{label}.bytes")
    _exact_type(item["sha256"], str, f"{label}.sha256")
    if item["bytes"] <= 0 or not _hex(item["sha256"]) or item["path_redacted"] is not True:
        raise ValueError(f"{label} identity drift")


def _validate_inventory(value: Any, label: str) -> None:
    item = _exact_keys(value, {"file_count", "total_bytes", "sha256"}, label)
    for key in ("file_count", "total_bytes"):
        _exact_type(item[key], int, f"{label}.{key}")
        if item[key] <= 0:
            raise ValueError(f"{label}.{key} is not positive")
    if not _hex(item["sha256"]):
        raise ValueError(f"{label} digest drift")


def _validate_source_receipt(value: Any, label: str) -> None:
    item = _exact_keys(value, {"module_file", "package_source_inventory"}, label)
    module = _exact_keys(item["module_file"], {"relative_path", "basename", "bytes", "sha256", "root_contained", "path_redacted"}, f"{label}.module_file")
    if module["relative_path"] != "src/agent_com/__init__.py" or module["basename"] != "__init__.py" or type(module["bytes"]) is not int or module["bytes"] <= 0 or not _hex(module["sha256"]) or module["root_contained"] is not True or module["path_redacted"] is not True:
        raise ValueError(f"{label} module identity drift")
    _validate_inventory(item["package_source_inventory"], f"{label}.package_source_inventory")


def _validate_runtime(value: Any, label: str) -> None:
    runtime = _exact_keys(value, {"runtime", "command", "exit", "stdout_bytes", "stdout_sha256", "stderr_bytes", "stderr_sha256", "source", "environment", "modules"}, label)
    if runtime["runtime"] != "executed_clean_archive_uv_frozen_offline" or type(runtime["exit"]) is not int or runtime["exit"] != 0:
        raise ValueError(f"{label} execution identity drift")
    for key in ("stdout_bytes", "stderr_bytes"):
        if type(runtime[key]) is not int or runtime[key] < 0:
            raise ValueError(f"{label}.{key} type drift")
    if not _hex(runtime["stdout_sha256"]) or not _hex(runtime["stderr_sha256"]):
        raise ValueError(f"{label} output digest drift")
    _validate_source_receipt(runtime["source"], f"{label}.source")
    environment = _exact_keys(runtime["environment"], {"cleared", "direct_python_fallback", "project_venv", "pythonno_user_site", "uv_no_config", "global_uv_cache", "uv_frozen", "uv_offline"}, f"{label}.environment")
    if type(environment["cleared"]) is not list or any(type(key) is not str for key in environment["cleared"]):
        raise ValueError(f"{label} cleared env type drift")
    if any(environment[key] is not True for key in ("pythonno_user_site", "uv_no_config", "uv_frozen", "uv_offline")) or environment["direct_python_fallback"] is not False:
        raise ValueError(f"{label} environment policy drift")
    if environment["project_venv"] != "materialized_inside_archive" or environment["global_uv_cache"] != "required_path_redacted_environment_local":
        raise ValueError(f"{label} environment scope drift")
    modules = _exact_keys(runtime["modules"], {"agent_com", "numpy", "openpyxl", "scipy", "yaml"}, f"{label}.modules")
    for name, module in modules.items():
        module = _exact_keys(module, {"relative_path", "basename", "bytes", "sha256"}, f"{label}.modules.{name}")
        if type(module["relative_path"]) is not str or type(module["basename"]) is not str or type(module["bytes"]) is not int or module["bytes"] <= 0 or not _hex(module["sha256"]):
            raise ValueError(f"{label} module identity type drift")
        if name == "agent_com" and module["relative_path"] != "src/agent_com/__init__.py":
            raise ValueError(f"{label} Agent-COM module drift")
        if name != "agent_com" and not module["relative_path"].startswith(".venv/"):
            raise ValueError(f"{label} dependency module escaped project venv")


def _validate_toolchain(value: Any) -> None:
    item = _exact_keys(value, {"pre", "post", "stable"}, "toolchain")
    if item["stable"] is not True or item["pre"] != item["post"]:
        raise ValueError("toolchain pre/post drift")
    roles = _exact_keys(item["pre"], {"cargo", "rustc", "python", "uv", "linker", "cargo_cache"}, "toolchain.pre")
    identity_keys = {"role", "basename", "file_bytes", "file_sha256", "version_args", "version_exit", "version_stdout_sha256", "version_stderr_sha256", "path_redacted"}
    cache = _exact_keys(roles["cargo_cache"], {"scope", "path_redacted", "package_count", "file_count", "total_bytes", "sha256"}, "toolchain.cargo_cache")
    if cache["scope"] != "resolved_locked_dependency_sources" or cache["path_redacted"] is not True or any(type(cache[key]) is not int or cache[key] <= 0 for key in ("package_count", "file_count", "total_bytes")) or not _hex(cache["sha256"]):
        raise ValueError("cargo cache inventory drift")
    for role, identity in roles.items():
        if role == "cargo_cache":
            continue
        identity = _exact_keys(identity, identity_keys, f"toolchain.{role}")
        if identity["role"] != role or type(identity["basename"]) is not str or "/" in identity["basename"] or "\\" in identity["basename"]:
            raise ValueError("toolchain role/path drift")
        if type(identity["file_bytes"]) is not int or identity["file_bytes"] <= 0 or type(identity["version_exit"]) is not int or identity["version_exit"] != 0:
            raise ValueError("toolchain numeric identity drift")
        if type(identity["version_args"]) is not list or any(type(arg) is not str for arg in identity["version_args"]):
            raise ValueError("toolchain version args drift")
        expected_args = (
            ["-flavor", "link", "help"]
            if role == "linker" and identity["basename"].casefold() == "rust-lld.exe"
            else ["--version"]
        )
        if identity["version_args"] != expected_args:
            raise ValueError("toolchain version args binding drift")
        if not all(_hex(identity[key]) for key in ("file_sha256", "version_stdout_sha256", "version_stderr_sha256")) or identity["path_redacted"] is not True:
            raise ValueError("toolchain digest/path drift")


def _validate_harness_source(value: Any, expected_paths: set[str]) -> None:
    item = _exact_keys(value, {"commit", "tree", "files", "shared_helper_schema"}, "harness.source")
    if item["shared_helper_schema"] != SHARED_HELPER_SCHEMA or not re.fullmatch(r"[0-9a-f]{40}", item["commit"]) or not re.fullmatch(r"[0-9a-f]{40}", item["tree"]):
        raise ValueError("harness source revision drift")
    if type(item["files"]) is not list or {entry.get("path") for entry in item["files"] if type(entry) is dict} != expected_paths:
        raise ValueError("harness source file set drift")
    for entry in item["files"]:
        receipt = _exact_keys(entry, {"path", "bytes", "sha256"}, "harness source file")
        if type(receipt["path"]) is not str or type(receipt["bytes"]) is not int or receipt["bytes"] <= 0 or not _hex(receipt["sha256"]):
            raise ValueError("harness source file identity drift")


def _validate_com01_report(report: Any) -> None:
    root_keys = {"schema", "status", "work_item", "leaf", "run_id", "nonce", "candidate", "upstream", "toolchain", "harness", "fixtures", "outcomes", "values_aligned", "difference_scenario_ids", "scenarios", "blockers", "matched", "acceptance", "non_claims"}
    item = _exact_keys(report, root_keys, "COM-01 report")
    if (item["schema"], item["status"], item["work_item"], item["leaf"]) != (SCHEMA, OPEN_STATUS, "COM-01", "config-validate"):
        raise ValueError("COM-01 root identity drift")
    if not _hex(item["run_id"]) or not _hex(item["nonce"]) or item["run_id"] == item["nonce"]:
        raise ValueError("COM-01 replay identity drift")
    candidate = _exact_keys(item["candidate"], {"commit", "tree", "archive", "source_mode", "inventory", "cargo_lock_sha256", "source_date_epoch", "build"}, "COM-01 candidate")
    if candidate["commit"] != CANDIDATE_COMMIT or candidate["tree"] != CANDIDATE_TREE or candidate["source_mode"] != "git_archive_at_immutable_commit" or not _hex(candidate["cargo_lock_sha256"]) or type(candidate["source_date_epoch"]) is not str:
        raise ValueError("COM-01 candidate source binding drift")
    _validate_archive(candidate["archive"], "candidate.archive")
    _validate_inventory(candidate["inventory"], "candidate.inventory")
    build = _exact_keys(candidate["build"], {"command", "cargo_source_pre", "cargo_source_post", "cargo_source_stable", "binary_pre", "binary_post", "binary_stable", "copy_matches_source", "raw_binary_scope", "stdout_sha256", "stderr_sha256", "log_policy", "environment"}, "candidate.build")
    if type(build["command"]) is not str or build["log_policy"] != "stable_event_categories" or not _hex(build["stdout_sha256"]) or not _hex(build["stderr_sha256"]):
        raise ValueError("candidate build command/log receipt drift")
    for key in ("binary_pre", "binary_post"):
        binary = _exact_keys(build[key], {"basename", "bytes", "sha256", "nlink", "path_redacted"}, f"candidate.build.{key}")
        if binary["basename"] != COM01_BINARY_BASENAME or type(binary["bytes"]) is not int or binary["bytes"] <= 0 or not _hex(binary["sha256"]) or type(binary["nlink"]) is not int or binary["nlink"] != 1 or binary["path_redacted"] is not True:
            raise ValueError("candidate binary identity drift")
    for key in ("cargo_source_pre", "cargo_source_post"):
        source = _exact_keys(build[key], {"basename", "bytes", "sha256", "nlink", "path_redacted"}, f"candidate.build.{key}")
        if source["basename"] != COM01_BINARY_BASENAME or type(source["bytes"]) is not int or source["bytes"] <= 0 or not _hex(source["sha256"]) or type(source["nlink"]) is not int or source["nlink"] < 1 or source["path_redacted"] is not True:
            raise ValueError("candidate Cargo source identity drift")
    if build["binary_stable"] is not True or build["cargo_source_stable"] is not True or build["copy_matches_source"] is not True or build["binary_pre"] != build["binary_post"] or build["cargo_source_pre"] != build["cargo_source_post"] or (build["binary_post"]["basename"], build["binary_post"]["bytes"], build["binary_post"]["sha256"]) != (build["cargo_source_post"]["basename"], build["cargo_source_post"]["bytes"], build["cargo_source_post"]["sha256"]) or build["raw_binary_scope"] != ENVIRONMENT_SCOPE:
        raise ValueError("candidate binary custody drift")
    environment = _exact_keys(build["environment"], {"cleared", "incremental", "offline", "rustc_forced", "wrappers_cleared", "source_path_remapped", "target_is_independent", "cargo_home_policy", "native_linker_overrides_cleared", "linker_forced", "cargo_cache_bound_pre_post"}, "candidate.build.environment")
    if type(environment["cleared"]) is not list or any(type(key) is not str for key in environment["cleared"]):
        raise ValueError("candidate build cleared env type drift")
    if any(type(value) is not bool for key, value in environment.items() if key not in {"cleared", "incremental", "cargo_home_policy"}):
        raise ValueError("candidate build environment type drift")
    upstream = _exact_keys(item["upstream"], {"commit", "tree", "archive", "source_mode", "inventory", "source", "runtime", "uv_lock"}, "COM-01 upstream")
    if upstream["commit"] != UPSTREAM_COMMIT or upstream["tree"] != UPSTREAM_TREE or upstream["source_mode"] != "git_archive_at_immutable_commit":
        raise ValueError("COM-01 upstream source binding drift")
    _validate_archive(upstream["archive"], "upstream.archive")
    _validate_inventory(upstream["inventory"], "upstream.inventory")
    uv_lock = _exact_keys(upstream["uv_lock"], {"bytes", "sha256"}, "upstream.uv_lock")
    if type(uv_lock["bytes"]) is not int or uv_lock["bytes"] <= 0 or not _hex(uv_lock["sha256"]):
        raise ValueError("upstream uv.lock identity drift")
    _validate_source_receipt(upstream["source"], "upstream.source")
    _validate_runtime(upstream["runtime"], "upstream.runtime")
    _validate_toolchain(item["toolchain"])
    harness = _exact_keys(item["harness"], {"runner", "semantic_runner", "corpus", "scenario_count", "scenario_set_sha256", "archive_only_inputs", "report_policy", "timeout_seconds", "source", "shared_helper_schema"}, "COM-01 harness")
    _validate_harness_source(harness["source"], {"tools/run_com_01_current_candidate.py", "tools/aggregate_com_01_current_candidate.py", "tools/verify_com_01_current_candidate.py", "tools/test_verify_com_01_current_candidate.py"})
    if harness["runner"] != "tools/run_com_01_current_candidate.py" or harness["semantic_runner"] != "tools/run_com_01_direct_oracle.py" or harness["corpus"] != CORPUS_RELATIVE.as_posix() or not _hex(harness["scenario_set_sha256"]) or harness["archive_only_inputs"] is not True or type(harness["report_policy"]) is not str or harness["shared_helper_schema"] != SHARED_HELPER_SCHEMA or type(harness["scenario_count"]) is not int or harness["scenario_count"] != 14 or type(harness["timeout_seconds"]) is not int or harness["timeout_seconds"] <= 0:
        raise ValueError("COM-01 harness drift")
    if type(item["fixtures"]) is not list:
        raise ValueError("COM-01 fixtures type drift")
    for fixture in item["fixtures"]:
        fixture = _exact_keys(fixture, {"role", "basename", "extension", "bytes", "sha256", "path_redacted"}, "COM-01 fixture")
        if type(fixture["role"]) is not str or type(fixture["basename"]) is not str or type(fixture["extension"]) is not str or type(fixture["bytes"]) is not int or fixture["bytes"] <= 0 or not _hex(fixture["sha256"]) or fixture["path_redacted"] is not True:
            raise ValueError("COM-01 fixture receipt drift")
    _validate_com01_scenarios(item["scenarios"])
    if type(item["outcomes"]) is not dict or any(type(value) is not int for value in item["outcomes"].values()) or item["outcomes"] != {"error_code_match": 7, "passed": 6, "values_equal_fingerprint_drift": 1} or item["values_aligned"] is not True:
        raise ValueError("COM-01 outcome drift")
    for key in ("difference_scenario_ids", "blockers", "non_claims"):
        if type(item[key]) is not list or any(type(value) is not str for value in item[key]):
            raise ValueError(f"COM-01 {key} type drift")
    if item["matched"] is not False or item["acceptance"] is not False:
        raise ValueError("COM-01 acceptance overclaim")


def run(args: argparse.Namespace) -> dict[str, Any]:
    candidate_repo = args.candidate_repo.resolve()
    upstream_repo = args.upstream_repo.resolve()
    candidate_commit = str(_git(candidate_repo, "rev-parse", f"{args.candidate_commit}^{{commit}}"))
    candidate_tree = str(_git(candidate_repo, "rev-parse", f"{candidate_commit}^{{tree}}"))
    upstream_commit = str(_git(upstream_repo, "rev-parse", f"{args.upstream_commit}^{{commit}}"))
    upstream_tree = str(_git(upstream_repo, "rev-parse", f"{upstream_commit}^{{tree}}"))
    if (candidate_commit, candidate_tree) != (CANDIDATE_COMMIT, CANDIDATE_TREE):
        raise RuntimeError("candidate commit/tree is not the fixed business candidate")
    if (upstream_commit, upstream_tree) != (UPSTREAM_COMMIT, UPSTREAM_TREE):
        raise RuntimeError("upstream commit/tree is not the pinned Agent-COM revision")
    if not HEX64.fullmatch(args.run_id) or not HEX64.fullmatch(args.nonce) or args.run_id == args.nonce:
        raise RuntimeError("run_id and nonce must be distinct lowercase 64-hex values")
    toolchain_pre, tools = _toolchain(args.cargo, args.python, args.uv)
    if tools["python"] != Path(sys.executable).resolve():
        raise RuntimeError("replay Python identity must match the executing interpreter")
    source_date_epoch = str(_git(candidate_repo, "show", "-s", "--format=%ct", candidate_commit))
    harness_source = _harness_receipt(
        candidate_repo,
        args.harness_commit,
        (
            Path("tools/run_com_01_current_candidate.py"),
            Path("tools/aggregate_com_01_current_candidate.py"),
            Path("tools/verify_com_01_current_candidate.py"),
            Path("tools/test_verify_com_01_current_candidate.py"),
        ),
    )
    with tempfile.TemporaryDirectory(prefix="sipi-com-01-current-") as directory:
        run_root = Path(directory)
        candidate_root = run_root / "candidate"
        upstream_root = run_root / "upstream"
        target_root = run_root / "candidate-target"
        scratch = run_root / "scratch"
        target_root.mkdir()
        scratch.mkdir()
        candidate_info = _materialize(candidate_repo, candidate_commit, candidate_root)
        upstream_info = _materialize(upstream_repo, upstream_commit, upstream_root)
        toolchain_pre["cargo_cache"] = _cargo_dependency_cache_inventory(candidate_root, tools, args.timeout_seconds)
        candidate_inventory = _inventory(candidate_root, (CRATE_RELATIVE, CORPUS_RELATIVE, SEMANTIC_RUNNER_RELATIVE))
        upstream_inventory = _inventory(upstream_root, (Path("src/agent_com"), Path("schemas/r480-config.schema.yaml"), Path("schemas/behavior-presets.yaml"), FIXTURE_RELATIVE))
        if candidate_inventory != _git_inventory(candidate_repo, candidate_commit, (CRATE_RELATIVE, CORPUS_RELATIVE, SEMANTIC_RUNNER_RELATIVE)):
            raise RuntimeError("candidate inventory does not mechanically match Git")
        if upstream_inventory != _git_inventory(upstream_repo, upstream_commit, (Path("src/agent_com"), Path("schemas/r480-config.schema.yaml"), Path("schemas/behavior-presets.yaml"), FIXTURE_RELATIVE)):
            raise RuntimeError("upstream inventory does not mechanically match Git")
        fixture = _safe_file(upstream_root, FIXTURE_RELATIVE)
        corpus = _safe_file(candidate_root, CORPUS_RELATIVE)
        semantic_runner = _safe_file(candidate_root, SEMANTIC_RUNNER_RELATIVE)
        source_receipt = _source_receipt(upstream_root)
        runtime_probe = _probe_upstream(upstream_root, tools, args.timeout_seconds, source_receipt)
        module = _load_semantic_runner(
            semantic_runner,
            corpus,
            upstream_root,
            candidate_root,
            tools,
            args.timeout_seconds,
        )
        binary, cargo_binary, build = _build(
            candidate_root, target_root, tools, args.timeout_seconds, source_date_epoch
        )
        scenarios, fixtures = _run_scenarios(module, upstream_root, candidate_root, binary, fixture, scratch, tools, args.timeout_seconds)
        _validate_com01_scenarios(scenarios)
        binary_bytes, binary_sha = _bounded_file(binary, 512 * 1024 * 1024)
        build["binary_post"] = {
            "basename": binary.name, "bytes": binary_bytes, "sha256": binary_sha,
            "nlink": binary.stat(follow_symlinks=False).st_nlink,
            "path_redacted": True,
        }
        build["binary_stable"] = build["binary_pre"] == build["binary_post"]
        build["cargo_source_post"] = _bounded_cargo_source(cargo_binary, target_root)
        build["cargo_source_stable"] = build["cargo_source_pre"] == build["cargo_source_post"]
        build["copy_matches_source"] = (
            build["binary_post"]["bytes"], build["binary_post"]["sha256"]
        ) == (
            build["cargo_source_post"]["bytes"], build["cargo_source_post"]["sha256"]
        )
        build["raw_binary_scope"] = ENVIRONMENT_SCOPE
        if build["binary_stable"] is not True or build["cargo_source_stable"] is not True or build["copy_matches_source"] is not True:
            raise RuntimeError("candidate source/copy identity changed during replay")
        candidate_record = {
            **candidate_info,
            "source_mode": "git_archive_at_immutable_commit",
            "inventory": candidate_inventory,
            "cargo_lock_sha256": _sha256(_safe_file(candidate_root, CRATE_RELATIVE / "Cargo.lock").read_bytes()),
            "source_date_epoch": source_date_epoch,
            "build": build,
        }
        upstream_record = {
            **upstream_info,
            "source_mode": "git_archive_at_immutable_commit",
            "inventory": upstream_inventory,
            "source": source_receipt,
            "runtime": runtime_probe,
            "uv_lock": dict(zip(("bytes", "sha256"), _bounded_file(_safe_file(upstream_root, Path("uv.lock"))))),
        }
        harness = {
            "runner": "tools/run_com_01_current_candidate.py",
            "semantic_runner": "tools/run_com_01_direct_oracle.py",
            "corpus": CORPUS_RELATIVE.as_posix(),
            "scenario_count": len(scenarios),
            "scenario_set_sha256": module.scenario_set_sha256(json.loads(corpus.read_text(encoding="utf-8"))),
            "archive_only_inputs": True,
            "report_policy": "bounded_hashes_counts_error_categories_and_difference_keys_only",
            "timeout_seconds": args.timeout_seconds,
            "source": harness_source,
            "shared_helper_schema": SHARED_HELPER_SCHEMA,
        }
        post_candidate_inventory = _inventory(candidate_root, (CRATE_RELATIVE, CORPUS_RELATIVE, SEMANTIC_RUNNER_RELATIVE))
        post_upstream_inventory = _inventory(upstream_root, (Path("src/agent_com"), Path("schemas/r480-config.schema.yaml"), Path("schemas/behavior-presets.yaml"), FIXTURE_RELATIVE))
        if post_candidate_inventory != candidate_inventory or post_upstream_inventory != upstream_inventory:
            raise RuntimeError("archive source inventory changed during replay")
        toolchain_post, _ = _toolchain(args.cargo, args.python, args.uv)
        toolchain_post["cargo_cache"] = _cargo_dependency_cache_inventory(candidate_root, tools, args.timeout_seconds)
        if toolchain_post != toolchain_pre:
            raise RuntimeError("toolchain identity changed during replay")
    outcomes = dict(sorted(Counter(item.get("comparison") for item in scenarios).items()))
    mismatches = [item["id"] for item in scenarios if item.get("comparison") not in {"passed", "error_code_match", "values_equal_fingerprint_drift"}]
    values_aligned = not mismatches
    blockers = []
    if not values_aligned:
        blockers.append("candidate_semantic_difference_observed")
    if outcomes.get("values_equal_fingerprint_drift", 0):
        blockers.append("materialized_fingerprint_drift")
    result = {
        "schema": SCHEMA,
        "status": OPEN_STATUS,
        "work_item": "COM-01",
        "leaf": "config-validate",
        "run_id": args.run_id,
        "nonce": args.nonce,
        "candidate": candidate_record,
        "upstream": upstream_record,
        "toolchain": {"pre": toolchain_pre, "post": toolchain_post, "stable": True},
        "harness": harness,
        "fixtures": fixtures,
        "outcomes": outcomes,
        "values_aligned": values_aligned,
        "difference_scenario_ids": mismatches,
        "scenarios": scenarios,
        "blockers": sorted(set(blockers)),
        "matched": False,
        "acceptance": False,
        "non_claims": [
            "no_complete_com_parity",
            "no_global_migration_row_close",
            "no_product_capability_promotion",
            "no_release_readiness",
            "no_S_parameter_fit",
            "channel_impulse_only_policy_unchanged",
            "no_raw_configuration_values_in_evidence",
        ],
    }
    _validate_com01_report(result)
    _path_free(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--candidate-commit", default=CANDIDATE_COMMIT)
    parser.add_argument("--upstream-repo", type=Path, default=Path(r"C:\Users\z3312\code\COM"))
    parser.add_argument("--upstream-commit", default=UPSTREAM_COMMIT)
    parser.add_argument("--harness-commit", required=True)
    parser.add_argument("--cargo", default=str(Path.home() / ".cargo" / "bin" / "cargo.exe"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--run-id", default=secrets.token_hex(32))
    parser.add_argument("--nonce", default=secrets.token_hex(32))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("timeout must be positive")
    try:
        report = run(args)
        _atomic_json_create(args.report, report, output_root=args.report.parent)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "run_id": report["run_id"], "scenario_count": len(report["scenarios"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
