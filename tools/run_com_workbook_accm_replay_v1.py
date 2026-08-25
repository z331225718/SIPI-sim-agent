"""Preparation runner for a pinned COM workbook/ACCM replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import struct
import tarfile
import tempfile
import threading
import tomllib
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

CANDIDATE_COMMIT = "2e18a6a27cf8abc0555e24e0346a54c4ea577baf"
CANDIDATE_TREE = "bfdc3e0ddd9bc76737528011e6dddc94c728f059"
CANDIDATE_ARCHIVE_SHA256 = "67b071cf9302d932ed2b974db3c7d82cb1e70c4b7f0dac276d788b88f1a64993"
CANDIDATE_ARCHIVE_BYTES = 44615680
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
SCHEMA = "sipi.com.workbook-accm-replay-prep.v4"
CANONICAL_ROOT_BASENAME = "com-workbook-accm-canonical-v4"
CANONICAL_LOCK_BASENAME = "com-workbook-accm-canonical-v4.lock"
FIXED_CARGO_HOME = Path("C:/sipi-cargo-home-v1")
CARGO_INVENTORY_COUNT = 7727
CARGO_INVENTORY_TOTAL_BYTES = 234108979
CARGO_INVENTORY_SHA256 = "d841c89ca7eef7018c6be0bf622cb55df079bd3cc39e7d15b9d802dd7f694c3f"
PE_EXPECTED = {"pe_offset": 120, "optional_header_offset": 144, "debug_directory_raw_pointer": 5888732, "machine": 0x8664, "optional_magic": 0x20B, "characteristics": 34, "debug_entries": 2, "codeview_rva": 5893908, "codeview_raw_pointer": 5888788, "codeview_bytes": 48, "repro_entries": 1, "canonical_sha256": "d6b133d9ca509c19c7ee112634d534b7d8b1c6e9d579255ff22de0ee46c56e87"}
PE_NORMALIZATION = [{"role": "coff_timestamp", "offset": 128, "bytes": 4}, {"role": "debug_timestamp", "offset": 5888736, "bytes": 4}, {"role": "rsds_guid", "offset": 5888792, "bytes": 16}, {"role": "debug_timestamp", "offset": 5888764, "bytes": 4}, {"role": "pe_checksum", "offset": 208, "bytes": 4}]
PE_SECTION_SHAPE = [(".text", 4096, 5494758, 1024, 5494784), (".rdata", 5500928, 753084, 5495808, 753152), (".data", 6254592, 5480, 6248960, 4096), (".pdata", 6262784, 95892, 6253056, 96256), (".tls", 6361088, 113, 6349312, 512), (".reloc", 6365184, 7876, 6349824, 8192)]
RUN_TIMEOUT_S = 180
BUILD_TIMEOUT_S = 900
IDENTITY_TIMEOUT_S = 15
MAX_RESULT_BYTES = 64 * 1024 * 1024
MAX_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_IDENTITY_FILE_BYTES = 256 * 1024 * 1024
RESULT_KEYS = {"schema_version", "source_revision", "profile", "cases", "provenance", "warnings", "timings_s", "input_manifest", "report_manifest"}
FIXTURES = {
    "workbook": {"path": "matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx", "git_blob_sha1": "22b633b6092b4b0de0ca89273515329b362eabae", "bytes": 67087, "sha256": "e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925"},
    "s4p": {"path": "fixtures/synthetic/kappa_asymmetric_reflective_10db_at_26p56ghz.s4p", "git_blob_sha1": "a1fe8618043b31f63dfb24454ac1d296000010c0", "bytes": 6457063, "sha256": "3a563543ba664fcc04c1ac5603ad305cb0b1d110c3d9020727444b1c3fd2d0ec"},
}
SOURCE_PATHS = ("src/agent_com/api.py", "src/agent_com/_orchestration.py", "src/agent_com/network/package.py", "src/agent_com/network/two_port.py", "src/agent_com/signal/fd_to_td.py", "src/agent_com/equalization/search.py")
NATIVE_ENV_KEYS = ("PATH", "LIB", "LIBPATH", "INCLUDE", "VCINSTALLDIR", "VCToolsInstallDir", "WindowsSdkDir", "WindowsSDKVersion", "UCRTVersion", "UniversalCRTSdkDir")
BUILD_ENV_KEYS = ("SystemRoot", "ComSpec", "PATHEXT", "WINDIR", *NATIVE_ENV_KEYS, "TEMP", "TMP", "CARGO_HOME", "RUSTC", "CARGO_BUILD_RUSTC", "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "CARGO_BUILD_RUSTC_WRAPPER", "CARGO_INCREMENTAL", "CARGO_NET_OFFLINE", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CL", "_CL_", "LINK")
NATIVE_TOOL_NAMES = {"cl": "cl.exe", "lib": "lib.exe", "rc": "rc.exe"}
REJECTED_VCVARS_CHARS = set('%!"&|<>^\r\n')


def canonicalize_environment(environment: dict[str, str]) -> dict[str, str]:
    """Normalize Windows' case-insensitive environment names and reject aliases."""
    known = {key.casefold(): key for key in BUILD_ENV_KEYS}
    result: dict[str, str] = {}
    seen: set[str] = set()
    for raw_key, value in environment.items():
        if not isinstance(raw_key, str) or not isinstance(value, str):
            raise ValueError("environment entries must be strings")
        folded = raw_key.casefold()
        if folded in seen:
            raise ValueError(f"duplicate case-insensitive environment key: {raw_key}")
        seen.add(folded)
        result[known.get(folded, raw_key)] = value
    return result


def canonical_env_lookup(environment: dict[str, str], key: str) -> str | None:
    return canonicalize_environment(environment).get(key)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400)
    except (OSError, ValueError):
        return True


def canonical_root_path() -> Path:
    temp_root = Path(tempfile.gettempdir()).resolve()
    root = temp_root / CANONICAL_ROOT_BASENAME
    if root.parent != temp_root or root.name != CANONICAL_ROOT_BASENAME:
        raise RuntimeError("canonical materialization root layout is invalid")
    return root


def canonical_lock_path() -> Path:
    temp_root = Path(tempfile.gettempdir()).resolve()
    lock = temp_root / CANONICAL_LOCK_BASENAME
    if lock.parent != temp_root or lock.name != CANONICAL_LOCK_BASENAME:
        raise RuntimeError("canonical lock layout is invalid")
    return lock


def paths_overlap(first: Path, second: Path) -> bool:
    first = first.resolve(strict=False)
    second = second.resolve(strict=False)
    return first == second or first in second.parents or second in first.parents


def cleanup_canonical_root(root: Path, owner: bytes | None = None) -> None:
    temp_root = Path(tempfile.gettempdir()).resolve()
    if root.is_symlink():
        raise RuntimeError("canonical materialization root cannot be a symlink")
    resolved = root.resolve(strict=False)
    if resolved.parent != temp_root or resolved.name != CANONICAL_ROOT_BASENAME:
        raise RuntimeError("canonical materialization root escaped TEMP")
    lock = canonical_lock_path()
    if owner is None:
        if root.exists() or lock.exists():
            raise RuntimeError("canonical materialization root is not available")
        return
    if not lock.is_file() or lock.read_bytes() != owner:
        raise RuntimeError("canonical materialization lock ownership changed")
    sentinel = root / ".fresh-sentinel"
    if not sentinel.is_file() or sentinel.read_bytes() != owner:
        raise RuntimeError("canonical materialization sentinel ownership changed")
    shutil.rmtree(root)
    lock.unlink()


@contextmanager
def canonical_materialization_root() -> Any:
    root = canonical_root_path()
    lock = canonical_lock_path()
    cleanup_canonical_root(root)
    owner = f"pid={os.getpid()};nonce={secrets.token_hex(32)}".encode("ascii")
    try:
        with lock.open("xb") as stream:
            stream.write(owner)
        root.mkdir()
        sentinel = root / ".fresh-sentinel"
        sentinel.write_bytes(owner)
        yield root
    finally:
        if lock.is_file() and lock.read_bytes() == owner:
            sentinel = root / ".fresh-sentinel"
            if sentinel.is_file() and sentinel.read_bytes() == owner:
                cleanup_canonical_root(root, owner)
            elif root.is_dir() and not any(root.iterdir()):
                root.rmdir()
                lock.unlink()
            elif not root.exists():
                lock.unlink()


def bounded_file_bytes(path: Path) -> bytes:
    stat_result = path.stat()
    if stat_result.st_size < 0 or stat_result.st_size > MAX_IDENTITY_FILE_BYTES:
        raise ValueError("identity file exceeds bounded size")
    with path.open("rb") as stream:
        payload = stream.read(MAX_IDENTITY_FILE_BYTES + 1)
    if len(payload) != stat_result.st_size or len(payload) > MAX_IDENTITY_FILE_BYTES:
        raise ValueError("identity file changed while reading")
    return payload


def bounded_file_digest(path: Path) -> tuple[int, str]:
    stat_result = path.stat()
    if stat_result.st_size < 0 or stat_result.st_size > MAX_IDENTITY_FILE_BYTES:
        raise ValueError("identity file exceeds bounded size")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    after = path.stat()
    if size != stat_result.st_size or after.st_size != stat_result.st_size:
        raise ValueError("identity file changed while hashing")
    return size, digest.hexdigest()


def redact(text: str) -> str:
    normalized = text.replace("\\", "/")
    redacted = re.sub(r"(?i)(?<![A-Za-z0-9_])(?:[A-Za-z]:/|\\\\|//|file://|/(?:users|home|opt|tmp|var|etc)/)[^\s,;)]*", "<abs-path>", normalized)
    return "<abs-path>" if "<abs-path>" in redacted else redacted


def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or ":" in path.parts[0] or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("unsafe archive path")
    return path


def archive(repo: Path, destination: Path) -> dict[str, Any]:
    command = ["git", "-c", "core.autocrlf=false", "-C", str(repo), "archive", "--format=tar", CANDIDATE_COMMIT]
    with destination.open("xb") as stream:
        completed = subprocess.run(command, stdout=stream, stderr=subprocess.PIPE, timeout=IDENTITY_TIMEOUT_S, check=False)
    payload = destination.read_bytes()
    if completed.returncode or len(payload) != CANDIDATE_ARCHIVE_BYTES or sha256(payload) != CANDIDATE_ARCHIVE_SHA256:
        raise RuntimeError("candidate archive identity mismatch")
    return {"command": "git -c core.autocrlf=false archive --format=tar <candidate>", "exit": completed.returncode, "bytes": len(payload), "sha256": sha256(payload)}


def safe_extract(archive_path: Path, destination: Path) -> None:
    seen: set[str] = set()
    root = destination.resolve()
    with tarfile.open(archive_path, "r") as stream:
        for member in stream.getmembers():
            relative = safe_relative(member.name)
            name = relative.as_posix()
            if name in seen:
                raise ValueError("duplicate archive member")
            seen.add(name)
            if member.issym() or member.islnk() or not (member.isdir() or member.isreg()):
                raise ValueError("archive links and special members are rejected")
            target = (root / Path(*relative.parts)).resolve()
            if root not in target.parents and target != root:
                raise ValueError("archive path escapes root")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                source = stream.extractfile(member)
                if source is None:
                    raise ValueError("archive member has no data")
                output.write(source.read())


def pinned_blob(upstream: Path, fixture: dict[str, Any], destination: Path) -> dict[str, Any]:
    path = fixture["path"]
    blob = subprocess.check_output(["git", "-C", str(upstream), "show", f"{UPSTREAM_COMMIT}:{path}"], timeout=IDENTITY_TIMEOUT_S)
    blob_id = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", f"{UPSTREAM_COMMIT}:{path}"], text=True, timeout=IDENTITY_TIMEOUT_S).strip()
    if blob_id != fixture["git_blob_sha1"] or len(blob) != fixture["bytes"] or sha256(blob) != fixture["sha256"]:
        raise RuntimeError(f"pinned fixture identity mismatch: {path}")
    with destination.open("xb") as output:
        output.write(blob)
    return {"path": path, "basename": Path(path).name, "git_blob_sha1": blob_id, "bytes": len(blob), "sha256": sha256(blob), "source_commit": UPSTREAM_COMMIT}


def source_inventory(upstream: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path in SOURCE_PATHS:
        blob = subprocess.check_output(["git", "-C", str(upstream), "show", f"{UPSTREAM_COMMIT}:{path}"], timeout=IDENTITY_TIMEOUT_S)
        blob_id = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", f"{UPSTREAM_COMMIT}:{path}"], text=True, timeout=IDENTITY_TIMEOUT_S).strip()
        result[path] = {"git_blob_sha1": blob_id, "bytes": len(blob), "sha256": sha256(blob), "license": "MIT"}
    return result


def candidate_inventory(root: Path) -> dict[str, Any]:
    base = root / "crates" / "sipi-agent-com-direct"
    result: dict[str, Any] = {}
    for path in sorted(base.rglob("*")):
        if not path.is_file() or "target" in path.parts:
            continue
        payload = path.read_bytes()
        result[path.relative_to(root).as_posix()] = {"bytes": len(payload), "sha256": sha256(payload)}
    return result


def cargo_registry_inventory(cargo_home: Path, source_root: Path) -> dict[str, Any]:
    """Bind locked registry source/cache/index bytes and reject local config overrides."""
    for forbidden_name in ("config", "config.toml", "credentials", "credentials.toml"):
        if (cargo_home / forbidden_name).exists():
            raise RuntimeError("cargo home config or credentials override is not admitted")
    lock_path = source_root / "Cargo.lock"
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = sorted({f"{item['name']}-{item['version']}" for item in lock.get("package", []) if isinstance(item, dict) and str(item.get("source", "")).startswith("registry+")})
    src_root = cargo_home / "registry" / "src"
    if not src_root.is_dir() or is_reparse_point(src_root):
        raise RuntimeError("fixed cargo home registry src input is missing")
    roots = sorted(src_root.glob("*"))
    result: dict[str, Any] = {}
    if any(is_reparse_point(root) for root in roots):
        raise RuntimeError("fixed cargo home registry src contains a symlink")
    for package in packages:
        matches = [root / package for root in roots if (root / package).is_dir() and not (root / package).is_symlink()]
        if len(matches) != 1:
            raise RuntimeError(f"fixed cargo home registry package inventory mismatch: {package}")
        package_root = matches[0]
        pending = [package_root]
        while pending:
            current = pending.pop()
            with os.scandir(current) as entries:
                for entry in sorted(entries, key=lambda item: item.name, reverse=True):
                    if is_reparse_point(Path(entry.path)):
                        raise RuntimeError("fixed cargo home registry src contains a symlink")
                    path = Path(entry.path)
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        size, digest = bounded_file_digest(path)
                        result[f"registry/src/{package}/{path.relative_to(package_root).as_posix()}"] = {"bytes": size, "sha256": digest}
    for channel in ("cache", "index"):
        root = cargo_home / "registry" / channel
        if not root.is_dir() or is_reparse_point(root):
            raise RuntimeError(f"fixed cargo home registry {channel} input is missing")
        pending = [root]
        while pending:
            current = pending.pop()
            with os.scandir(current) as entries:
                for entry in sorted(entries, key=lambda item: item.name, reverse=True):
                    if is_reparse_point(Path(entry.path)):
                        raise RuntimeError(f"fixed cargo home registry {channel} contains a symlink")
                    path = Path(entry.path)
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        size, digest = bounded_file_digest(path)
                        result[f"registry/{channel}/{path.relative_to(root).as_posix()}"] = {"bytes": size, "sha256": digest}
    entries = {key: result[key] for key in sorted(result)}
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return {"entries": entries, "count": len(entries), "total_bytes": sum(item["bytes"] for item in entries.values()), "sha256": sha256(encoded)}


def verify_fixed_candidate_binding(inventory: dict[str, Any], binary: dict[str, Any]) -> None:
    if inventory["count"] != CARGO_INVENTORY_COUNT or inventory["total_bytes"] != CARGO_INVENTORY_TOTAL_BYTES or inventory["sha256"] != CARGO_INVENTORY_SHA256:
        raise RuntimeError("fixed cargo inventory hard anchor drift")
    if not binary["exists"]:
        raise RuntimeError("fixed candidate build did not produce a PE")
    for key, expected in PE_EXPECTED.items():
        if binary.get(key) != expected:
            raise RuntimeError(f"fixed PE hard anchor drift: {key}")
    if binary["normalization_map"] != PE_NORMALIZATION:
        raise RuntimeError("fixed PE normalization map drift")
    shape = [(item["name"], item["virtual_address"], item["virtual_bytes"], item["raw_pointer"], item["bytes"]) for item in binary["sections"]]
    expected_shape = [(item[0], item[1], item[2], item[3], item[4]) for item in PE_SECTION_SHAPE]
    if shape != expected_shape:
        raise RuntimeError("fixed PE section layout drift")


def resolve_regular(path: Path, role: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError(f"{role} must be an absolute regular file")
    resolved = path.resolve()
    if resolved.is_symlink() or not resolved.is_file():
        raise ValueError(f"{role} resolved to a non-regular file")
    return resolved


def tool_identity(path: Path, role: str) -> dict[str, Any]:
    path = resolve_regular(path, role)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"invalid {role} executable")
    if role == "linker" and path.name.lower() != "rust-lld.exe":
        raise ValueError("linker must be rust-lld.exe")
    version_args = ["-flavor", "link", "--version"] if role == "linker" and path.name.lower() == "rust-lld.exe" else ["/d", "/c", "ver"] if role == "cmd" else ["--version"]
    completed = subprocess.run([str(path), *version_args], capture_output=True, text=True, timeout=IDENTITY_TIMEOUT_S, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{role} version probe failed")
    return {"role": role, "basename": path.name, "file_sha256": sha256(bounded_file_bytes(path)), "version_args": version_args, "version_output_sha256": sha256((completed.stdout + completed.stderr).encode()), "version_exit": completed.returncode, "timeout_s": IDENTITY_TIMEOUT_S, "path_redacted": True}


def vcvars_identity(path: Path) -> dict[str, Any]:
    if not path.is_absolute() or path.name.lower() != "vcvars64.bat" or path.is_symlink() or any(char in str(path) for char in REJECTED_VCVARS_CHARS):
        raise ValueError("vcvars64 must be an absolute regular vcvars64.bat")
    resolved = path.resolve()
    if resolved.name.lower() != "vcvars64.bat" or not resolved.is_file():
        raise ValueError("vcvars64 must be an existing regular vcvars64.bat")
    payload = bounded_file_bytes(resolved)
    return {"role": "vcvars64", "basename": resolved.name, "bytes": len(payload), "file_sha256": sha256(payload), "path_redacted": True}


def _parse_vcvars_output(stdout: str, marker: str) -> dict[str, str]:
    if stdout.count(marker) != 1:
        raise ValueError("vcvars marker missing or duplicated")
    stdout = stdout.split(marker, 1)[1]
    result: dict[str, str] = {}
    for raw in stdout.splitlines():
        if not raw.strip():
            continue
        if "=" not in raw:
            raise ValueError("vcvars output contains a malformed line")
        key, value = raw.split("=", 1)
        canonical = next((item for item in NATIVE_ENV_KEYS if item.lower() == key.lower()), None)
        if canonical is not None:
            if canonical in result:
                raise ValueError("vcvars output contains a duplicate native variable")
            result[canonical] = value
    missing = set(NATIVE_ENV_KEYS) - set(result)
    if missing:
        raise ValueError("vcvars output is missing native variables")
    return result


def capture_vcvars_env(vcvars64: Path, cmd_exe: Path) -> tuple[dict[str, str], dict[str, Any]]:
    vcvars64 = resolve_regular(vcvars64, "vcvars64")
    cmd_exe = resolve_regular(cmd_exe, "cmd")
    before = bounded_file_bytes(vcvars64)
    identity = vcvars_identity(vcvars64)
    marker = f"__SIPI_COM_VCVARS_{secrets.token_hex(16)}__"
    probe_env = canonicalize_environment(dict(os.environ))
    command = ["cmd.exe", "/d", "/u", "/s", "/c", f"call vcvars64.bat amd64 && echo {marker} && set"]
    try:
        completed = subprocess.run([str(cmd_exe), *command[1:]], cwd=vcvars64.parent, env=probe_env, capture_output=True, timeout=IDENTITY_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("vcvars64 environment probe timed out") from error
    if completed.returncode != 0:
        raise RuntimeError("vcvars64 environment probe failed")
    raw_stdout = completed.stdout.encode() if isinstance(completed.stdout, str) else completed.stdout
    if len(raw_stdout) > MAX_CAPTURE_BYTES:
        raise RuntimeError("vcvars environment output exceeds bounded size")
    stdout = raw_stdout.decode("utf-16-le", "strict")
    after = bounded_file_bytes(vcvars64)
    if before != after:
        raise RuntimeError("vcvars64 changed during environment probe")
    return _parse_vcvars_output(stdout, marker), identity


def _find_native_tool(native_env: dict[str, str], name: str) -> Path | None:
    for directory in native_env["PATH"].split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / name
        if candidate.is_file() and not candidate.is_symlink():
            return candidate.resolve()
    return None


def native_tool_identity(path: Path, role: str) -> dict[str, Any]:
    resolved = resolve_regular(path, f"native {role}")
    if resolved.name.lower() != NATIVE_TOOL_NAMES[role]:
        raise ValueError(f"invalid native {role} executable")
    args = ["/nologo", "/?"] if role == "cl" else ["/Bv"] if role == "lib" else ["/?"]
    try:
        completed = subprocess.run([str(resolved), *args], capture_output=True, timeout=IDENTITY_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"native {role} version probe timed out") from error
    if completed.returncode != 0:
        raise RuntimeError(f"native {role} version probe failed")
    stdout = completed.stdout if isinstance(completed.stdout, bytes) else (completed.stdout or "").encode()
    stderr = completed.stderr if isinstance(completed.stderr, bytes) else (completed.stderr or "").encode()
    return {"role": role, "basename": resolved.name, "file_sha256": sha256(bounded_file_bytes(resolved)), "version_args": args, "version_output_sha256": sha256(stdout + stderr), "version_exit": completed.returncode, "timeout_s": IDENTITY_TIMEOUT_S, "path_redacted": True}


def native_toolset(native_env: dict[str, str]) -> dict[str, dict[str, Any]]:
    result = {}
    for role in ("cl", "lib", "rc"):
        path = _find_native_tool(native_env, NATIVE_TOOL_NAMES[role])
        if path is None:
            raise RuntimeError(f"vcvars64 did not expose {role}.exe")
        result[role] = native_tool_identity(path, role)
    return result


def _pe_rva_offset(sections: list[tuple[int, int, int, int]], rva: int, size: int, payload_size: int) -> int:
    matches = []
    for virtual_address, virtual_size, raw_size, raw_pointer in sections:
        span = max(virtual_size, raw_size)
        if virtual_address <= rva < virtual_address + span and rva - virtual_address + size <= raw_size and raw_pointer + rva - virtual_address + size <= payload_size:
            matches.append(raw_pointer + rva - virtual_address)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError("PE RVA is outside section raw data")
    raise ValueError("PE RVA maps to overlapping sections")


def _pe_debug_identity(payload: bytes, pe_offset: int, optional: int, magic: int, optional_size: int, sections: list[tuple[int, int, int, int]]) -> tuple[str, bool, list[dict[str, Any]], int, int, int, int, int, int]:
    directory_offset = optional + (112 if magic == 0x20B else 96)
    if directory_offset + 16 * 8 > optional + optional_size:
        raise ValueError("PE optional header has no debug directory")
    debug_rva, debug_size = struct.unpack_from("<II", payload, directory_offset + 6 * 8)
    if debug_size == 0 or debug_size % 28 != 0:
        raise ValueError("PE debug directory shape invalid")
    debug_offset = _pe_rva_offset(sections, debug_rva, debug_size, len(payload))
    codeview: list[tuple[str, int, int, int]] = []
    repro_count = 0
    normalization: list[dict[str, Any]] = []
    for index in range(debug_size // 28):
        entry = debug_offset + index * 28
        _, timestamp, _, _, debug_type, size, address_of_raw_data, pointer = struct.unpack_from("<IIHHIIII", payload, entry)
        normalization.append({"role": "debug_timestamp", "offset": entry + 4, "bytes": 4})
        if size > 0 and (pointer == 0 or pointer + size > len(payload)):
            raise ValueError("PE debug payload escapes file")
        if debug_type == 2 and (address_of_raw_data == 0 or _pe_rva_offset(sections, address_of_raw_data, size, len(payload)) != pointer):
            raise ValueError("PE debug RVA/raw pointer mismatch")
        data = payload[pointer:pointer + size]
        if debug_type == 2:
            if len(data) < 28 or data[:4] != b"RSDS":
                raise ValueError("PE CodeView is not RSDS")
            normalization.append({"role": "rsds_guid", "offset": pointer + 4, "bytes": 16})
            path_bytes = data[24:].split(b"\0", 1)[0]
            try:
                pdb_path = path_bytes.decode("ascii")
            except UnicodeDecodeError as error:
                raise ValueError("PE CodeView PDB path is not ASCII") from error
            pdb_basename = Path(pdb_path.replace("\\", "/")).name
            if not pdb_basename or pdb_basename != pdb_path.replace("\\", "/") or not pdb_basename.lower().endswith(".pdb"):
                raise ValueError("PE CodeView PDB path is not basename-only")
            codeview.append((pdb_basename, address_of_raw_data, pointer, size))
        elif debug_type == 16:
            repro_count += 1
    if len(codeview) != 1 or repro_count != 1:
        raise ValueError("PE must contain exactly one RSDS CodeView and one REPRO entry")
    return codeview[0][0], True, normalization, debug_size // 28, debug_offset, codeview[0][1], codeview[0][2], codeview[0][3], repro_count


def binary_identity(path: Path, forbidden_roots: tuple[Path, ...] = ()) -> dict[str, Any]:
    if not path.is_file():
        return {"basename": path.name, "exists": False, "bytes": 0, "sha256": None, "canonical_sha256": None, "pe_offset": None, "optional_header_offset": None, "debug_directory_raw_pointer": None, "machine": None, "optional_magic": None, "characteristics": None, "debug_entries": 0, "codeview_rva": None, "codeview_raw_pointer": None, "codeview_bytes": None, "repro_entries": 0, "pdb_basename": None, "repro": False, "sections": [], "normalization_map": [], "certificate_bytes": 0, "overlay_bytes": 0}
    payload = read_result_bytes(path)
    canonical = bytearray(payload)
    valid_pe = False
    pdb_basename = None
    machine_value = None
    optional_magic_value = None
    characteristics_value = None
    debug_entries = 0
    codeview_rva = None
    codeview_raw_pointer = None
    codeview_bytes = None
    repro_entries = 0
    pe_offset_value = None
    optional_header_offset_value = None
    debug_directory_raw_pointer = None
    repro = False
    section_inventory: list[dict[str, Any]] = []
    normalization_map: list[dict[str, Any]] = []
    certificate_bytes = 0
    overlay_bytes = 0
    if len(canonical) >= 0x40 and canonical[:2] == b"MZ":
        pe_offset = int.from_bytes(canonical[0x3C:0x40], "little")
        pe_offset_value = pe_offset
        if 0 <= pe_offset <= len(canonical) - 24 and canonical[pe_offset:pe_offset + 4] == b"PE\0\0":
            coff = pe_offset + 4
            machine = int.from_bytes(canonical[coff:coff + 2], "little")
            machine_value = machine
            characteristics_value = int.from_bytes(canonical[coff + 18:coff + 20], "little")
            sections = int.from_bytes(canonical[coff + 2:coff + 4], "little")
            optional_size = int.from_bytes(canonical[coff + 16:coff + 18], "little")
            optional = coff + 20
            optional_header_offset_value = optional
            magic = int.from_bytes(canonical[optional:optional + 2], "little") if optional + 2 <= len(canonical) else 0
            optional_magic_value = magic
            entrypoint = int.from_bytes(canonical[optional + 16:optional + 20], "little") if optional + 20 <= len(canonical) else 0
            size_headers = int.from_bytes(canonical[optional + 60:optional + 64], "little") if optional + 64 <= len(canonical) else 0
            table = optional + optional_size
            valid_pe = machine == 0x8664 and (characteristics_value & 0x0002) != 0 and 0 < sections <= 96 and magic == 0x20B and optional_size >= 112 and 0 < entrypoint and 0 < size_headers <= len(canonical) and table + sections * 40 <= len(canonical)
            entry_in_exec = False
            section_ranges: list[tuple[int, int, int, int]] = []
            for index in range(sections):
                header = table + index * 40
                virtual_size = int.from_bytes(canonical[header + 8:header + 12], "little")
                virtual_address = int.from_bytes(canonical[header + 12:header + 16], "little")
                raw_size = int.from_bytes(canonical[header + 16:header + 20], "little")
                raw_ptr = int.from_bytes(canonical[header + 20:header + 24], "little")
                section_ranges.append((virtual_address, virtual_size, raw_size, raw_ptr))
                section_name = canonical[header:header + 8].split(b"\0", 1)[0].decode("ascii", "strict")
                section_inventory.append({"name": section_name, "virtual_address": virtual_address, "virtual_bytes": virtual_size, "raw_pointer": raw_ptr, "bytes": raw_size, "sha256": sha256(bytes(canonical[raw_ptr:raw_ptr + raw_size])) if raw_size else sha256(b"")})
                valid_pe = valid_pe and ((raw_size == 0 and raw_ptr == 0) or (raw_size > 0 and raw_ptr < len(canonical) and raw_size <= len(canonical) - raw_ptr))
                if (int.from_bytes(canonical[header + 36:header + 40], "little") & 0x20000000) and virtual_address <= entrypoint < virtual_address + max(virtual_size, raw_size):
                    entry_in_exec = True
            valid_pe = valid_pe and entry_in_exec
            if valid_pe:
                virtual_ranges = sorted((item[0], item[0] + max(item[1], 1)) for item in section_ranges)
                raw_ranges = sorted((item[3], item[3] + item[2]) for item in section_ranges if item[2])
                if any(left[1] > right[0] for left, right in zip(virtual_ranges, virtual_ranges[1:])) or any(left[1] > right[0] for left, right in zip(raw_ranges, raw_ranges[1:])):
                    raise ValueError("PE sections overlap")
                pdb_basename, repro, debug_normalization, debug_entries, debug_directory_raw_pointer, codeview_rva, codeview_raw_pointer, codeview_bytes, repro_entries = _pe_debug_identity(bytes(canonical), pe_offset, optional, magic, optional_size, section_ranges)
                pdb_path = path.parent / pdb_basename
                if not pdb_path.is_file() or pdb_path.is_symlink():
                    raise ValueError("PE CodeView PDB sibling is missing")
                read_result_bytes(pdb_path)
                normalization_map.extend(debug_normalization)
                normalization_map.insert(0, {"role": "coff_timestamp", "offset": pe_offset + 8, "bytes": 4})
                normalization_map.append({"role": "pe_checksum", "offset": optional + 64, "bytes": 4})
                directory_offset = optional + (112 if magic == 0x20B else 96)
                if directory_offset + 5 * 8 <= optional + optional_size:
                    certificate_pointer, certificate_bytes = struct.unpack_from("<II", canonical, directory_offset + 4 * 8)
                    if certificate_bytes:
                        if certificate_pointer == 0 or certificate_pointer + certificate_bytes > len(canonical):
                            raise ValueError("PE certificate directory escapes file")
                end_of_payload = max([size_headers] + [raw_pointer + raw_size for _, _, raw_size, raw_pointer in section_ranges])
                if certificate_bytes:
                    end_of_payload = max(end_of_payload, certificate_pointer + certificate_bytes)
                if end_of_payload > len(canonical):
                    raise ValueError("PE payload bounds invalid")
                overlay_bytes = len(canonical) - end_of_payload
                for forbidden in forbidden_roots:
                    resolved_forbidden = str(forbidden.resolve())
                    path_spellings = {resolved_forbidden, resolved_forbidden.replace("/", "\\"), resolved_forbidden.replace("\\", "/")}
                    for spelling in path_spellings:
                        if spelling.replace("\\", "/").casefold() in {"c:/sipi-cargo", "c:/sipi-cargo-home-v1"}:
                            continue
                        for encoded in (spelling.encode("utf-8"), spelling.encode("utf-16-le")):
                            if encoded in payload:
                                raise ValueError("PE contains an unreplaced canonical path")
                for item in normalization_map:
                    start = int(item["offset"]); size = int(item["bytes"])
                    canonical[start:start + size] = b"\0" * size
    if path.suffix.lower() == ".exe" and not valid_pe:
        raise ValueError("binary is not a parseable PE")
    return {"basename": path.name, "exists": True, "bytes": len(payload), "sha256": sha256(payload), "canonical_sha256": sha256(bytes(canonical)), "pe_offset": pe_offset_value, "optional_header_offset": optional_header_offset_value, "debug_directory_raw_pointer": debug_directory_raw_pointer, "machine": machine_value, "optional_magic": optional_magic_value, "characteristics": characteristics_value, "debug_entries": debug_entries, "codeview_rva": codeview_rva, "codeview_raw_pointer": codeview_raw_pointer, "codeview_bytes": codeview_bytes, "repro_entries": repro_entries, "pdb_basename": pdb_basename, "repro": repro, "sections": section_inventory, "normalization_map": normalization_map, "certificate_bytes": certificate_bytes, "overlay_bytes": overlay_bytes}


def env_receipt(env: dict[str, str]) -> dict[str, Any]:
    env = canonicalize_environment(env)
    result = {}
    roles = {"SystemRoot": "system_root", "ComSpec": "cmd", "PATHEXT": "system_path_ext", "WINDIR": "system_root", "TEMP": "fresh_run_temp", "TMP": "fresh_run_temp", "CARGO_HOME": "cargo_home", "RUSTC": "resolved_tool", "CARGO_BUILD_RUSTC": "resolved_tool", "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER": "resolved_tool", "RUSTC_WRAPPER": "cleared_wrapper", "RUSTC_WORKSPACE_WRAPPER": "cleared_wrapper", "CARGO_BUILD_RUSTC_WRAPPER": "cleared_wrapper", "CARGO_INCREMENTAL": "incremental_zero", "CARGO_NET_OFFLINE": "offline", "RUSTFLAGS": "deterministic_flags", "CARGO_ENCODED_RUSTFLAGS": "deterministic_encoded_flags", "CL": "native_deterministic_flags", "_CL_": "cleared_native_flags", "LINK": "cleared_linker_override"}
    for key in BUILD_ENV_KEYS:
        raw = env.get(key, "")
        if key in {"TEMP", "TMP"}:
            entries = ["<fresh-run-temp>"]
            value_hash = sha256(b"<fresh-run-temp>")
        elif key == "RUSTFLAGS":
            entries = []
            value_hash = sha256(raw.encode())
        elif key == "CARGO_ENCODED_RUSTFLAGS":
            entries = ["<canonical-cargo-home-remap>", "<canonical-target-remap>", "<canonical-source-remap>", "<canonical-temp-remap>", "-C", "link-arg=/Brepro"] if raw else []
            value_hash = sha256(raw.encode())
        elif key == "CL":
            entries = ["/Brepro"] if raw else []
            value_hash = sha256(raw.encode())
        else:
            entries = [Path(item).name for item in raw.split(os.pathsep) if item]
            value_hash = sha256(raw.encode())
        relation = None
        if key in {"SystemRoot", "WINDIR"}:
            relation = "system_root"
        elif key == "ComSpec":
            root = Path(env["SystemRoot"]).resolve() if env.get("SystemRoot") else None
            command = Path(raw).resolve() if raw else None
            relation = "system32_under_system_root" if root is not None and command is not None and command.parent.name.lower() == "system32" and command.parent.parent == root else "invalid"
        result[key] = {"role": roles.get(key, "native_environment"), "exists": key in env, "entry_basenames": entries, "value_sha256": value_hash, "path_redacted": True, "relation": relation}
    return result


def deterministic_flag_receipt(cargo_home: Path, source_root: Path, target_root: Path, temp_root: Path) -> list[dict[str, str]]:
    return [
        {"role": "cargo_home_remap", "value": "<canonical-cargo-home>=C:/sipi-cargo", "sha256": sha256(f"--remap-path-prefix={cargo_home.resolve()}=C:/sipi-cargo".encode())},
        {"role": "target_remap", "value": "<canonical-target>=C:/sipi-target", "sha256": sha256(f"--remap-path-prefix={target_root.resolve()}=C:/sipi-target".encode())},
        {"role": "source_remap", "value": "<canonical-source>=C:/sipi-source", "sha256": sha256(f"--remap-path-prefix={source_root.resolve()}=C:/sipi-source".encode())},
        {"role": "temp_remap", "value": "<canonical-temp>=C:/sipi-temp", "sha256": sha256(f"--remap-path-prefix={temp_root.resolve()}=C:/sipi-temp".encode())},
        {"role": "linker_repro", "value": "-C link-arg=/Brepro", "sha256": sha256(b"-C link-arg=/Brepro")},
    ]


def deterministic_rustflag_args(cargo_home: Path, source_root: Path, target_root: Path, temp_root: Path) -> list[str]:
    return [
        f"--remap-path-prefix={cargo_home.resolve()}=C:/sipi-cargo",
        f"--remap-path-prefix={target_root.resolve()}=C:/sipi-target",
        f"--remap-path-prefix={source_root.resolve()}=C:/sipi-source",
        f"--remap-path-prefix={temp_root.resolve()}=C:/sipi-temp",
        "-C",
        "link-arg=/Brepro",
    ]


def deterministic_cl_flags() -> str:
    return "/Brepro"


def build_env(rustc: Path, linker: Path, vcvars64: Path, cmd_exe: Path, cargo_home: Path, temp_dir: Path, source_root: Path | None = None, target_root: Path | None = None) -> tuple[dict[str, str], dict[str, Any]]:
    inherited = canonicalize_environment(dict(os.environ))
    forbidden = tuple(key for key in inherited if key.startswith("CARGO_") or key in {"RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "_CL_"})
    if any(inherited.get(key) for key in forbidden):
        raise RuntimeError("inherited rust/build flags or wrapper are not admitted")
    system_root = inherited.get("SystemRoot")
    windir = inherited.get("WINDIR")
    if system_root is None:
        raise RuntimeError("SystemRoot is required")
    if windir is not None and windir != system_root:
        raise RuntimeError("SystemRoot and WINDIR disagree")
    native, vcvars = capture_vcvars_env(vcvars64, cmd_exe)
    cmd_exe = resolve_regular(cmd_exe, "cmd")
    allowed = {"SystemRoot", "PATHEXT", "WINDIR"}
    env = {key: value for key, value in inherited.items() if key in allowed}
    env["SystemRoot"] = system_root
    env["WINDIR"] = windir or system_root
    env.update(native)
    cargo_home = cargo_home.resolve(strict=False)
    if not cargo_home.is_absolute() or cargo_home.is_symlink() or not cargo_home.is_dir():
        raise ValueError("cargo home must be an existing absolute regular directory")
    temp_dir = temp_dir.resolve(strict=False)
    if not temp_dir.is_absolute() or temp_dir.is_symlink():
        raise ValueError("temporary directory must be an explicit absolute regular path")
    temp_dir.mkdir(parents=True, exist_ok=True)
    encoded_flags = deterministic_rustflag_args(cargo_home, source_root or temp_dir, target_root or temp_dir, temp_dir)
    env.update({"ComSpec": str(cmd_exe), "TEMP": str(temp_dir), "TMP": str(temp_dir), "CARGO_HOME": str(cargo_home), "RUSTC": str(rustc), "CARGO_BUILD_RUSTC": str(rustc), "RUSTC_WRAPPER": "", "RUSTC_WORKSPACE_WRAPPER": "", "CARGO_BUILD_RUSTC_WRAPPER": "", "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER": str(linker), "CL": deterministic_cl_flags(), "_CL_": "", "LINK": "", "CARGO_INCREMENTAL": "0", "CARGO_NET_OFFLINE": "true", "RUSTFLAGS": "", "CARGO_ENCODED_RUSTFLAGS": "\x1f".join(encoded_flags)})
    return env, {"vcvars64": vcvars, "variables": env_receipt(env), "native_tools": native_toolset(native)}


def bounded_run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
    captured: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}

    def drain(name: str, stream: Any) -> None:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                return
            if len(captured[name]) < MAX_CAPTURE_BYTES:
                captured[name].extend(chunk[: MAX_CAPTURE_BYTES - len(captured[name])])

    threads = [threading.Thread(target=drain, args=(name, getattr(process, name)), daemon=True) for name in ("stdout", "stderr")]
    for thread in threads:
        thread.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=IDENTITY_TIMEOUT_S, check=False)
        process.kill()
        process.wait()
        for thread in threads:
            thread.join()
        return subprocess.CompletedProcess(command, 124, bytes(captured["stdout"]).decode("utf-8", "replace"), "timeout: " + bytes(captured["stderr"]).decode("utf-8", "replace"))
    for thread in threads:
        thread.join()
    return subprocess.CompletedProcess(command, process.returncode, bytes(captured["stdout"]).decode("utf-8", "replace"), bytes(captured["stderr"]).decode("utf-8", "replace"))


def parse_result_artifact(payload: bytes, control_vector: list[float]) -> tuple[dict[str, Any], dict[str, dict[str, float]]]:
    if len(payload) == 0 or len(payload) > MAX_RESULT_BYTES:
        raise ValueError("result artifact exceeds bounded size")
    value = json.loads(payload)
    if not isinstance(value, dict) or set(value) != RESULT_KEYS or value["schema_version"] != 1 or value.get("source_revision") != "r480" or not isinstance(value["profile"], dict) or not isinstance(value["provenance"], dict) or not isinstance(value["warnings"], list) or not isinstance(value["timings_s"], dict) or not isinstance(value["input_manifest"], dict) or not isinstance(value["report_manifest"], dict):
        raise ValueError("result artifact schema mismatch")
    cases = value["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("result artifact cases missing")
    result: dict[str, dict[str, float]] = {}
    for case in cases:
        required_case = {"case_index", "channels", "metrics", "diagnostics"}
        if not isinstance(case, dict) or not required_case.issubset(case) or not isinstance(case.get("case_index"), int) or isinstance(case.get("case_index"), bool) or case["case_index"] < 0 or case["case_index"] >= len(control_vector) or not isinstance(case.get("metrics"), dict) or not isinstance(case.get("channels"), dict) or not isinstance(case.get("diagnostics"), dict):
            raise ValueError("result artifact case identity invalid")
        key = str(case["case_index"])
        if key in result:
            raise ValueError("duplicate result artifact case")
        metrics = case["metrics"]
        if not {"FOM", "COM_dB", "sigma_N_V"}.issubset(metrics):
            raise ValueError("result artifact metric schema mismatch")
        selected = {}
        for metric in ("FOM", "COM_dB", "sigma_N_V"):
            number = metrics.get(metric)
            if not isinstance(number, (int, float)) or isinstance(number, bool) or not math.isfinite(number):
                raise ValueError("result artifact metric is not finite")
            selected["FOM_dB" if metric == "FOM" else metric] = float(number)
        result[key] = selected
    if set(result) != {str(index) for index in range(len(control_vector))}:
        raise ValueError("result artifact cases do not match controls")
    return value, result


def canonical_receipt(case_metrics: dict[str, dict[str, float]], control_vector: list[float], raw_value: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for key in sorted(case_metrics, key=int):
        source = next(case for case in raw_value["cases"] if str(case["case_index"]) == key)
        item = {"case_index": int(key), "ac_cm_rms": float(control_vector[int(key)]), "metrics": case_metrics[key]}
        for field in ("case_id", "package_case_index", "channel_identity"):
            if field in source and isinstance(source[field], (str, int, float, bool, type(None))):
                item[field] = source[field]
        cases.append(item)
    return {"schema": "sipi.com.workbook-accm-canonical-metrics.v1", "control_vector": control_vector, "cases": cases, "metric_fields": ["FOM_dB", "COM_dB", "sigma_N_V"], "channel_policy": "single_fd_to_td_impulse"}


def read_result_bytes(path: Path) -> bytes:
    before = path.lstat()
    if not path.is_file() or path.is_symlink() or before.st_size <= 0 or before.st_size > MAX_RESULT_BYTES:
        raise ValueError("result artifact is not a bounded regular file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        opened = os.fstat(descriptor)
        if opened.st_size != before.st_size or not stat_is_regular(opened.st_mode):
            raise ValueError("result artifact changed before read")
        payload = bytearray()
        while len(payload) <= MAX_RESULT_BYTES:
            chunk = os.read(descriptor, min(1024 * 1024, MAX_RESULT_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if len(payload) > MAX_RESULT_BYTES or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ValueError("result artifact changed while reading")
    return bytes(payload)


def stat_is_regular(mode: int) -> bool:
    return (mode & 0o170000) == 0o100000


def custody_file_identity(path: Path) -> dict[str, Any]:
    payload = read_result_bytes(path)
    return {"basename": path.name, "bytes": len(payload), "sha256": sha256(payload)}


def prepare_custody(path: Path, root: Path, run_id: str) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("binary custody directory must be an absolute non-symlink directory")
    resolved = path.resolve(strict=False)
    if paths_overlap(resolved, root) or paths_overlap(resolved, canonical_lock_path()):
        raise ValueError("binary custody directory must be outside canonical root")
    resolved.mkdir(parents=True, exist_ok=True)
    if not resolved.is_dir() or resolved.is_symlink():
        raise ValueError("binary custody directory is not a regular directory")
    run_root = resolved / run_id
    if run_root.exists() or run_root.is_symlink():
        raise FileExistsError("binary custody run directory already exists")
    run_root.mkdir()
    destination = run_root / "sipi-com-direct-run.exe"
    if destination.exists():
        raise FileExistsError("binary custody destination already exists")
    return destination


def copy_binary_custody(binary: Path, destination: Path, identity: dict[str, Any]) -> dict[str, Any]:
    if not binary.is_file() or binary.is_symlink():
        raise ValueError("built binary is not a regular file")
    if identity.get("pdb_basename") is None or identity.get("repro") is not True:
        raise ValueError("built binary has no unique CodeView PDB identity")
    pdb = binary.parent / identity["pdb_basename"]
    if pdb.parent != binary.parent or pdb.name != identity["pdb_basename"]:
        raise ValueError("PDB is not the direct CodeView basename sibling")
    pdb_destination = destination.parent / identity["pdb_basename"]
    if not pdb.is_file() or pdb.is_symlink():
        raise ValueError("built binary PDB custody is missing")
    if pdb_destination.exists():
        raise FileExistsError("PDB custody destination already exists")
    source_exe = custody_file_identity(binary)
    source_pdb = custody_file_identity(pdb)
    exe_payload = read_result_bytes(binary)
    pdb_payload = read_result_bytes(pdb)
    with destination.open("xb") as output:
        output.write(exe_payload)
    with pdb_destination.open("xb") as output:
        output.write(pdb_payload)
    if custody_file_identity(binary) != source_exe or custody_file_identity(pdb) != source_pdb:
        raise RuntimeError("binary custody source changed during copy")
    pdb_identity = {**custody_file_identity(pdb_destination), "source_bytes": source_pdb["bytes"], "source_sha256": source_pdb["sha256"]}
    exe_identity = {**custody_file_identity(destination), "source_bytes": source_exe["bytes"], "source_sha256": source_exe["sha256"]}
    return {"exe": exe_identity, "pdb": pdb_identity}


def run_one(repo: Path, upstream: Path, cargo: Path, rustc: Path, linker: Path, vcvars64: Path, cmd_exe: Path, cargo_home: Path, run_id: str, output: Path, custody_dir: Path | None = None) -> dict[str, Any]:
    if len(run_id) != 64 or run_id.lower() != run_id or any(c not in "0123456789abcdef" for c in run_id):
        raise ValueError("run_id must be 64 lowercase hex characters")
    if output.exists():
        raise FileExistsError("report path already exists")
    cargo = resolve_regular(cargo, "cargo")
    rustc = resolve_regular(rustc, "rustc")
    linker = resolve_regular(linker, "linker")
    if linker.name.lower() != "rust-lld.exe":
        raise ValueError("linker must be rust-lld.exe")
    vcvars64 = resolve_regular(vcvars64, "vcvars64")
    cmd_exe = resolve_regular(cmd_exe, "cmd")
    cargo_home = cargo_home.resolve(strict=False)
    if cargo_home != FIXED_CARGO_HOME.resolve(strict=False) or cargo_home.is_symlink() or not cargo_home.is_dir():
        raise ValueError("cargo home must be the fixed external C:/sipi-cargo-home-v1 directory")
    canonical = canonical_root_path()
    lock = canonical_lock_path()
    for external in (cargo_home, output.resolve(strict=False), custody_dir.resolve(strict=False) if custody_dir is not None else None):
        if external is not None and (paths_overlap(external, canonical) or paths_overlap(external, lock)):
            raise ValueError("run output or cargo custody overlaps canonical materialization root")
    with canonical_materialization_root() as root:
        if custody_dir is None:
            raise ValueError("binary custody directory is required")
        custody_exe = prepare_custody(custody_dir, root, run_id)
        archive_path = root / "candidate.tar"
        archive_id = archive(repo, archive_path)
        materialized = root / "candidate"
        materialized.mkdir()
        safe_extract(archive_path, materialized)
        before = candidate_inventory(materialized)
        cargo_inventory_before = cargo_registry_inventory(cargo_home, materialized)
        if cargo_home.resolve(strict=False) == Path("C:/sipi-cargo-home-v1").resolve(strict=False) and (cargo_inventory_before["count"] != CARGO_INVENTORY_COUNT or cargo_inventory_before["total_bytes"] != CARGO_INVENTORY_TOTAL_BYTES or cargo_inventory_before["sha256"] != CARGO_INVENTORY_SHA256):
            raise RuntimeError("fixed cargo inventory hard anchor drift")
        work = root / "inputs"
        work.mkdir()
        fixture_ids = {key: pinned_blob(upstream, value, work / ("pinned-workbook.xlsx" if key == "workbook" else "pinned-channel.s4p")) for key, value in FIXTURES.items()}
        for fixture in fixture_ids.values():
            fixture["pre_sha256"] = fixture["sha256"]
        identities_pre = {"cargo": tool_identity(cargo, "cargo"), "rustc": tool_identity(rustc, "rustc"), "linker": tool_identity(linker, "linker"), "cmd": tool_identity(cmd_exe, "cmd")}
        target_root = materialized / "crates" / "sipi-agent-com-direct" / "target"
        native_temp = root / "native-tmp"
        if root == cargo_home or root in cargo_home.parents:
            raise ValueError("cargo home overlaps canonical materialization root")
        env, native = build_env(rustc, linker, vcvars64, cmd_exe, cargo_home, native_temp, materialized, target_root)
        command = [str(cargo), "build", "--manifest-path", "crates/sipi-agent-com-direct/Cargo.toml", "--bin", "sipi-com-direct-run", "--release", "--locked", "--offline"]
        build = bounded_run(command, cwd=materialized, env=env, timeout=BUILD_TIMEOUT_S)
        binary = materialized / "crates" / "sipi-agent-com-direct" / "target" / "release" / "sipi-com-direct-run.exe"
        binary_before = binary_identity(binary, (materialized, target_root, native_temp, cargo_home))
        if binary_before["exists"] and cargo_home.resolve(strict=False) == Path("C:/sipi-cargo-home-v1").resolve(strict=False):
            verify_fixed_candidate_binding(cargo_inventory_before, binary_before)
        custody_before = copy_binary_custody(binary, custody_exe, binary_before) if binary_before["exists"] else None
        controls = [[0.0, 0.0], [0.0, 0.001]]
        runs: list[dict[str, Any]] = []
        zero_metrics: dict[str, dict[str, float]] | None = None
        for vector in controls:
            out = root / ("out-zero" if vector[1] == 0.0 else "out-nonzero")
            if build.returncode or not binary.is_file():
                runtime = None
            else:
                runtime_command = [str(binary), "run", "--config", str(work / "pinned-workbook.xlsx"), "--thru", str(work / "pinned-channel.s4p"), "--output-dir", str(out), "--override", f"AC_CM_RMS={json.dumps(vector, separators=(',', ':'))}", "--overwrite"]
                runtime = bounded_run(runtime_command, cwd=materialized, env=env, timeout=RUN_TIMEOUT_S)
            stderr = runtime.stderr if runtime else build.stderr
            stdout = runtime.stdout if runtime else ""
            artifact = None
            final_metrics = None
            parse_error = None
            if runtime and runtime.returncode == 0:
                try:
                    result_path = out / "result.json"
                    if not result_path.is_file():
                        raise ValueError("successful COM run did not publish result.json")
                    result_bytes = read_result_bytes(result_path)
                    raw_value, case_metrics = parse_result_artifact(result_bytes, vector)
                    if vector[1] == 0.0:
                        zero_metrics = case_metrics
                    elif zero_metrics is None or "1" not in case_metrics or "1" not in zero_metrics or case_metrics["1"] == zero_metrics["1"]:
                        raise ValueError("nonzero target case did not change consumer metrics")
                    final_metrics = case_metrics
                    output.parent.mkdir(parents=True, exist_ok=True)
                    artifact_path = output.parent / f"{output.stem}-metrics-{len(runs)}.json"
                    receipt = canonical_receipt(case_metrics, vector, raw_value)
                    receipt_bytes = json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
                    with artifact_path.open("xb") as artifact_file:
                        artifact_file.write(receipt_bytes)
                    artifact = {"path": artifact_path.name, "bytes": len(receipt_bytes), "sha256": sha256(receipt_bytes), "raw_bytes": len(result_bytes), "raw_sha256": sha256(result_bytes), "case_metrics": case_metrics}
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    parse_error = str(error)
            success = runtime is not None and runtime.returncode == 0 and artifact is not None and final_metrics is not None
            exit_code = runtime.returncode if runtime else build.returncode
            invalid_artifact = runtime is not None and runtime.returncode == 0 and not success
            status = "matched" if success else "artifact_invalid" if invalid_artifact else "blocked"
            blocker = redact((stderr.strip() if stderr.strip() else parse_error) or "result artifact consumer proof blocked") if not success else None
            runs.append({"control_vector": vector, "status": status, "exit": exit_code, "stdout_sha256": sha256(stdout.encode()), "stderr_sha256": sha256(stderr.encode()), "final_metrics": final_metrics if success else None, "consumer_proof": success, "artifact": artifact, "blocker": blocker})
        after = candidate_inventory(materialized)
        cargo_inventory_after = cargo_registry_inventory(cargo_home, materialized)
        for fixture in fixture_ids.values():
            fixture["post_sha256"] = sha256((work / ("pinned-workbook.xlsx" if fixture["path"].endswith(".xlsx") else "pinned-channel.s4p")).read_bytes())
            if fixture["pre_sha256"] != fixture["post_sha256"]:
                raise RuntimeError("fixture custody drift")
        native_post_env, vcvars_post = capture_vcvars_env(vcvars64, cmd_exe)
        if native_post_env != {key: env[key] for key in NATIVE_ENV_KEYS}:
            raise RuntimeError("native vcvars environment drift")
        native_post = native_toolset(native_post_env)
        if vcvars_post != native["vcvars64"]:
            raise RuntimeError("vcvars64 identity drift")
        identities_post = {"cargo": tool_identity(cargo, "cargo"), "rustc": tool_identity(rustc, "rustc"), "linker": tool_identity(linker, "linker"), "cmd": tool_identity(cmd_exe, "cmd")}
        binary_pre = binary_before
        binary_post = binary_identity(binary, (materialized, target_root, native_temp, cargo_home))
        if binary_post["exists"] and cargo_home.resolve(strict=False) == Path("C:/sipi-cargo-home-v1").resolve(strict=False):
            verify_fixed_candidate_binding(cargo_inventory_after, binary_post)
        source_exe_after = custody_file_identity(binary) if custody_before is not None else None
        source_pdb_path = binary.parent / binary_post["pdb_basename"] if binary_post["pdb_basename"] else binary.with_suffix(".pdb")
        custody_pdb_path = custody_exe.parent / binary_post["pdb_basename"] if binary_post["pdb_basename"] else custody_exe.with_suffix(".pdb")
        source_pdb_after = custody_file_identity(source_pdb_path) if custody_before is not None else None
        custody_after = {"exe": {**custody_file_identity(custody_exe), "source_bytes": source_exe_after["bytes"], "source_sha256": source_exe_after["sha256"]}, "pdb": {**custody_file_identity(custody_pdb_path), "source_bytes": source_pdb_after["bytes"], "source_sha256": source_pdb_after["sha256"]} if custody_pdb_path.is_file() else None} if custody_before is not None else None
        if custody_before != custody_after:
            raise RuntimeError("binary custody changed during runtime")
        blocked = any(item["status"] in {"blocked", "artifact_invalid"} for item in runs)
        result = {"schema": SCHEMA, "run_id": run_id, "nonce": secrets.token_hex(32), "candidate": {"commit": CANDIDATE_COMMIT, "tree": CANDIDATE_TREE, "archive": archive_id, "binary_pre": binary_pre, "binary": binary_post, "binary_custody": {"id": run_id, "pre": custody_before, "post": custody_after}}, "upstream": {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE, "runtime": "not_executed_external_only", "source_inventory": source_inventory(upstream)}, "fixtures": fixture_ids, "toolchain": {"pre": identities_pre, "post": identities_post, "vcvars64_pre": native["vcvars64"], "vcvars64_post": vcvars_post, "native_pre": native["native_tools"], "native_post": native_post}, "build": {"command": "cargo build --manifest-path crates/sipi-agent-com-direct/Cargo.toml --bin sipi-com-direct-run --release --locked --offline", "exit": build.returncode, "stdout_sha256": sha256(build.stdout.encode()), "stderr_sha256": sha256(build.stderr.encode()), "timeout_s": BUILD_TIMEOUT_S, "env_policy": "canonical_root_rustflags_brepro_vcvars64_allowlist_wrappers_cleared_offline_incremental_zero", "env_receipt": native["variables"], "deterministic_flags": deterministic_flag_receipt(cargo_home, materialized, target_root, native_temp), "cargo_registry_inventory_before": cargo_inventory_before, "cargo_registry_inventory_after": cargo_inventory_after, "cargo_registry_inventory_equal": cargo_inventory_before == cargo_inventory_after}, "execution": {"runtime_timeout_s": RUN_TIMEOUT_S, "source_inventory_before": before, "source_inventory_after": after, "source_inventory_equal": before == after, "canonical_root": CANONICAL_ROOT_BASENAME, "canonical_root_fresh": True, "canonical_root_cleanup": True}, "controls": {"ac_cm_rms_vectors": controls, "source": "pinned workbook vector override", "no_sparam_fit": True, "channel_policy": "single_fd_to_td_impulse"}, "runs": runs, "parity": {"status": "blocked" if blocked else "numeric_observation", "matched": False, "acceptance": False}, "non_claims": ["no S-parameter fit", "single FD-to-TD impulse", "no upstream numeric parity", "no global/product/release claim", "PDB is opaque environment-local debug custody and nonpublish"] + (["no final consumer proof while blocked"] if blocked else [])}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--linker", type=Path, required=True)
    parser.add_argument("--vcvars64", type=Path, required=True)
    parser.add_argument("--cmd", type=Path, required=True)
    parser.add_argument("--cargo-home", type=Path, required=True)
    parser.add_argument("--run-id", default=secrets.token_hex(32))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--custody-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run_one(args.repo, args.upstream_repo, args.cargo, args.rustc, args.linker, args.vcvars64, args.cmd, args.cargo_home, args.run_id, args.report, args.custody_dir)
    print(json.dumps({"schema": report["schema"], "status": report["parity"]["status"], "run_id": report["run_id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
