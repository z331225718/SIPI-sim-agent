"""Shared provenance helpers for the COM exact-profile replay evidence."""

from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

ARCHIVE_TIMEOUT_S = 900
MSVC_VERSION = "14.44.35207"
WINDOWS_SDK_VERSION = "10.0.26100.0"
TARGET_TRIPLE = "x86_64-pc-windows-msvc"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def archive_materialize(git: Path, repo: Path, commit: str, destination: Path, expected: str) -> str:
    import subprocess

    try:
        payload = subprocess.run(
            [str(git), "-c", "core.autocrlf=false", "-C", str(repo), "archive", "--format=tar", commit],
            capture_output=True,
            timeout=ARCHIVE_TIMEOUT_S,
            check=True,
        ).stdout
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("git archive timed out") from error
    actual = sha256_bytes(payload)
    if actual != expected:
        raise RuntimeError("archive digest drift")
    destination.mkdir(parents=True)
    base = destination.resolve()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as handle:
        for member in handle.getmembers():
            if member.issym() or member.islnk():
                raise RuntimeError("archive links are not admitted")
            target = (destination / member.name).resolve()
            if target != base and base not in target.parents:
                raise RuntimeError("archive member escapes materialization root")
        handle.extractall(destination)
    return actual


def basename(path: Path) -> str:
    return path.name


def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _inventory(directory: Path) -> dict[str, Any]:
    entries = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix.lower() == ".lib":
            entries.append({"path": path.relative_to(directory).as_posix(), "sha256": sha256_file(path)})
    return {"count": len(entries), "combined_sha256": sha256_bytes(canonical_json(entries)), "files": entries}


def _key_library_inventory(directory: Path, names: tuple[str, ...]) -> dict[str, Any]:
    files = {path.name.lower(): path for path in directory.glob("*.lib")}
    result = {}
    for name in names:
        path = files.get(name.lower())
        result[name] = {"present": path is not None, "sha256": sha256_file(path) if path is not None else None, "path": path.relative_to(directory).as_posix() if path is not None else None}
    return result


def discover_native_msvc() -> dict[str, Any]:
    """Resolve a fixed x64 MSVC/SDK pair without inheriting LIB or INCLUDE."""
    roots = (Path("C:/Program Files (x86)/Microsoft Visual Studio/2022"), Path("C:/Program Files/Microsoft Visual Studio/2022"))
    msvc_candidates = []
    for family in roots:
        if not family.is_dir():
            continue
        for edition in sorted(family.iterdir()):
            base = edition / "VC" / "Tools" / "MSVC"
            if not base.is_dir():
                continue
            for version in base.iterdir():
                if re.fullmatch(r"\d+(?:\.\d+)+", version.name):
                    cl = version / "bin" / "Hostx64" / "x64" / "cl.exe"
                    include = version / "include"
                    lib = version / "lib" / "x64"
                    if cl.is_file() and include.is_dir() and lib.is_dir():
                        msvc_candidates.append((version.name, cl, include, lib))
    if not msvc_candidates:
        raise RuntimeError("x64 MSVC BuildTools not found")
    msvc_version, compiler, msvc_include, msvc_lib = max(msvc_candidates, key=lambda item: _version_key(item[0]))
    if msvc_version != MSVC_VERSION:
        raise RuntimeError("MSVC version drift")

    kit_root = Path("C:/Program Files (x86)/Windows Kits/10")
    sdk_candidates = []
    include_root = kit_root / "Include"
    lib_root = kit_root / "Lib"
    if include_root.is_dir() and lib_root.is_dir():
        for version in lib_root.iterdir():
            if not re.fullmatch(r"\d+(?:\.\d+)+", version.name):
                continue
            include = include_root / version.name
            ucrt = version / "ucrt" / "x64"
            um = version / "um" / "x64"
            include_names = ("ucrt", "shared", "um", "winrt", "cppwinrt")
            if include.is_dir() and ucrt.is_dir() and um.is_dir() and all((include / name).is_dir() for name in include_names):
                sdk_candidates.append((version.name, include, ucrt, um))
    if not sdk_candidates:
        raise RuntimeError("Windows SDK x64 libraries not found")
    sdk_version, sdk_include, sdk_ucrt_lib, sdk_um_lib = max(sdk_candidates, key=lambda item: _version_key(item[0]))
    if sdk_version != WINDOWS_SDK_VERSION:
        raise RuntimeError("Windows SDK version drift")

    include_dirs = [msvc_include, sdk_include / "ucrt", sdk_include / "shared", sdk_include / "um", sdk_include / "winrt", sdk_include / "cppwinrt"]
    lib_dirs = [msvc_lib, sdk_ucrt_lib, sdk_um_lib]
    key_names = ("vcruntime.lib", "msvcrt.lib", "oldnames.lib", "ucrt.lib", "kernel32.lib", "user32.lib")
    return {
        "target": TARGET_TRIPLE,
        "msvc": {"version": msvc_version, "include_order": ["msvc", "sdk_ucrt", "sdk_shared", "sdk_um", "sdk_winrt", "sdk_cppwinrt"], "lib_order": ["msvc", "sdk_ucrt", "sdk_um"], "lib_inventory": _inventory(msvc_lib), "key_libs": _key_library_inventory(msvc_lib, key_names), "compiler": compiler_identity(compiler, 180)},
        "sdk": {"version": sdk_version, "include_order": ["sdk_ucrt", "sdk_shared", "sdk_um", "sdk_winrt", "sdk_cppwinrt"], "lib_inventory": {"ucrt": _inventory(sdk_ucrt_lib), "um": _inventory(sdk_um_lib)}, "key_libs": {"ucrt": _key_library_inventory(sdk_ucrt_lib, key_names), "um": _key_library_inventory(sdk_um_lib, key_names)}},
        "include_dirs": include_dirs,
        "lib_dirs": lib_dirs,
        "compiler_path": compiler,
        "bin_dir": compiler.parent,
    }


def tool_identity(path: Path, timeout_s: int) -> dict[str, Any]:
    import subprocess

    command = [str(path), "--version"]
    try:
        completed = subprocess.run(command, capture_output=True, timeout=timeout_s, check=False)
        output = completed.stdout + completed.stderr
        return {
            "basename": basename(path),
            "file_sha256": sha256_file(path),
            "version_output_sha256": sha256_bytes(output),
            "version_exit": completed.returncode,
            "status": "ok" if completed.returncode == 0 else "failed",
            "path_redacted": True,
            "timeout_s": timeout_s,
        }
    except subprocess.TimeoutExpired:
        return {
            "basename": basename(path),
            "file_sha256": sha256_file(path),
            "version_output_sha256": None,
            "version_exit": None,
            "status": "timeout",
            "path_redacted": True,
            "timeout_s": timeout_s,
        }


def linker_identity(path: Path, timeout_s: int) -> dict[str, Any]:
    """Record rust-lld provenance, admitting its documented generic-driver probe."""
    import subprocess

    command = [str(path), "--version"]
    try:
        completed = subprocess.run(command, capture_output=True, timeout=timeout_s, check=False)
        output = completed.stdout + completed.stderr
        generic_driver = completed.returncode == 1 and output.startswith(b"lld is a generic driver.")
        return {
            "role": "rust-lld",
            "basename": basename(path),
            "file_sha256": sha256_file(path),
            "version_output_sha256": sha256_bytes(output),
            "version_exit": completed.returncode,
            "probe_strategy": "rust-lld --version; generic-driver exit 1 admitted",
            "status": "ok_generic_driver" if generic_driver else "ok" if completed.returncode == 0 else "failed",
            "path_redacted": True,
            "timeout_s": timeout_s,
        }
    except subprocess.TimeoutExpired:
        return {
            "role": "rust-lld",
            "basename": basename(path),
            "file_sha256": sha256_file(path),
            "version_output_sha256": None,
            "version_exit": None,
            "probe_strategy": "rust-lld --version; generic-driver exit 1 admitted",
            "status": "timeout",
            "path_redacted": True,
            "timeout_s": timeout_s,
        }


def compiler_identity(path: Path, timeout_s: int) -> dict[str, Any]:
    """Probe cl.exe without inheriting a developer command prompt."""
    import subprocess

    try:
        completed = subprocess.run([str(path)], capture_output=True, timeout=timeout_s, check=False)
        output = completed.stdout + completed.stderr
        admitted = completed.returncode in {0, 2} and b"Microsoft" in output and b"C/C++" in output
        return {
            "role": "msvc-cl",
            "basename": basename(path),
            "file_sha256": sha256_file(path),
            "version_output_sha256": sha256_bytes(output),
            "version_exit": completed.returncode,
            "probe_strategy": "cl.exe; no-source exit 2 admitted",
            "status": "ok_no_source" if admitted else "failed",
            "path_redacted": True,
            "timeout_s": timeout_s,
        }
    except subprocess.TimeoutExpired:
        return {
            "role": "msvc-cl",
            "basename": basename(path),
            "file_sha256": sha256_file(path),
            "version_output_sha256": None,
            "version_exit": None,
            "probe_strategy": "cl.exe; no-source exit 2 admitted",
            "status": "timeout",
            "path_redacted": True,
            "timeout_s": timeout_s,
        }
def hash_float64(values: Any) -> str:
    import numpy as np

    array = np.asarray(values, dtype="<f8")
    return sha256_bytes(array.tobytes(order="C"))


def summarize_stage(values: Any) -> dict[str, Any]:
    import numpy as np

    array = np.asarray(values, dtype=np.float64)
    if not np.all(np.isfinite(array)):
        raise RuntimeError("non-finite stage payload")
    return {"count": int(array.size), "sha256": hash_float64(array)}


def json_metric(value: Any) -> Any:
    import numpy as np

    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return "nan"
        if np.isposinf(value):
            return "inf"
        if np.isneginf(value):
            return "-inf"
    return value


def path_free(value: Any) -> bool:
    if isinstance(value, dict):
        return all(path_free(key) and path_free(item) for key, item in value.items())
    if isinstance(value, list):
        return all(path_free(item) for item in value)
    if isinstance(value, str):
        return not PurePosixPath(value).is_absolute() and not PureWindowsPath(value).is_absolute()
    return True
