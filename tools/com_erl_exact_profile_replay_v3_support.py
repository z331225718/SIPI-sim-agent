"""Shared provenance helpers for the COM exact-profile replay evidence."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

ARCHIVE_TIMEOUT_S = 900


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
