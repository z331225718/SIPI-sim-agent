"""Independent stage-1 and future formal-evidence verifier for the PB matrix."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import stat
import subprocess
import tarfile
import tempfile
import threading
import time
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml


PINNED_PARENT = "d44581ac8b10adbc8f803bb0292107ae3303e015"
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_PROCESS_CAPTURE_BYTES = 4 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 120
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
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
CASE_IDS = (
    "pb01_nrz_analytic_line", "pb01_nrz_tx_ffe", "pb01_nrz_rx_dfe",
    "pb01_pam4_analytic_line", "pb01_duo_binary_analytic_line", "pb01_nrz_ctle",
    "pb02_nrz_impulse", "pb02_pam4_impulse", "pb02_duo_binary_impulse",
    "pb02_impulse_tx_rx_equalization", "pb02_impulse_analytic_ctle",
    "pb02_impulse_jitter_bathtub_analysis",
)
CLAIMS = {"global_branch_parity", "whole_payload_parity", "release_acceptance", "numeric_parity"}
PB01_ARRAYS = ("chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h", "chnl_s", "tx_out_s", "ctle_out_s", "dfe_out_s", "chnl_p", "tx_out_p", "ctle_out_p", "dfe_out_p")
PB02_MEMBERS = ("channel_impulse_v_per_v.npy", "channel_output_v.npy", "ctle_output_v.npy", "rx_ffe_impulse_v_per_v.npy", "rx_filter_impulse_v_per_v.npy", "rx_input_v.npy", "rx_output_v.npy", "symbols_v.npy", "time_s.npy", "tx_channel_impulse_v_per_v.npy", "tx_waveform_v.npy")
PB01_ITEMS = ("chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h", "chnl_s", "tx_s", "ctle_s", "dfe_s", "tx_out_s", "ctle_out_s", "dfe_out_s", "chnl_p", "tx_out_p", "ctle_out_p", "dfe_out_p", "chnl_H", "tx_H", "ctle_H", "dfe_H", "tx_out_H", "ctle_out_H", "dfe_out_H", "tx_out")


class VerifyError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise VerifyError("path must be a non-empty string")
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or windows.root or "\\" in value:
        raise VerifyError("absolute/anchored path rejected")
    if any(part in ("", ".", "..") for part in posix.parts):
        raise VerifyError("non-canonical relative path rejected")
    return posix.as_posix()


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
        raise VerifyError(errors[0])
    return child.returncode, bytes(stdout), bytes(stderr)


def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    returncode, stdout, stderr = _bounded_process(["git", "-C", str(repo), *args], timeout=GIT_TIMEOUT_SECONDS, stdout_limit=MAX_FILE_BYTES)
    if returncode:
        raise VerifyError(stderr.decode("utf-8", "replace").strip() or "git command failed")
    return stdout if binary else stdout.decode("utf-8", "strict").strip()


def _json_loads(payload: bytes | str) -> Any:
    def reject_constant(value: str) -> Any:
        raise VerifyError(f"non-finite JSON constant rejected: {value}")

    value = json.loads(payload, parse_constant=reject_constant)
    nodes = 0

    def close(item: Any, depth: int = 0) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > 1_000_000 or depth > 128:
            raise VerifyError("JSON structure budget exceeded")
        if item is None or type(item) in (bool, int, str):
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise VerifyError("non-finite JSON number rejected")
            return
        if type(item) is list:
            for child in item:
                close(child, depth + 1)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                close(child, depth + 1)
            return
        raise VerifyError("unsupported JSON value type")

    close(value)
    return value


def _read(root: Path, relative: str) -> tuple[bytes, dict[str, Any]]:
    original = root.absolute()
    for component in (*reversed(original.parents), original):
        component_info = os.lstat(component)
        if stat.S_ISLNK(component_info.st_mode) or getattr(component_info, "st_file_attributes", 0) & 0x400:
            raise VerifyError("root has a link/reparse ancestor")
    original_info = os.lstat(original)
    if not stat.S_ISDIR(original_info.st_mode) or stat.S_ISLNK(original_info.st_mode) or getattr(original_info, "st_file_attributes", 0) & 0x400:
        raise VerifyError("root must be a plain directory")
    root = original.resolve(strict=True)
    relative = _safe_relative(relative)
    root_info = os.lstat(root)
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode) or getattr(root_info, "st_file_attributes", 0) & 0x400:
        raise VerifyError("root must be a plain directory")
    target = root
    for part in PurePosixPath(relative).parts:
        target /= part
        info = os.lstat(target)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise VerifyError("link/reparse path rejected")
    resolved = target.resolve(strict=True)
    if root not in resolved.parents:
        raise VerifyError("path escaped root")
    pre = os.lstat(target)
    if not stat.S_ISREG(pre.st_mode) or int(pre.st_nlink) != 1 or pre.st_size > MAX_FILE_BYTES:
        raise VerifyError("file must be bounded regular/nonlink/nlink1")
    ident = lambda info: (int(info.st_dev), int(info.st_ino), int(info.st_size), int(info.st_mtime_ns))
    fd = os.open(target, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(fd)
        if ident(opened) != ident(pre) or int(opened.st_nlink) != 1:
            raise VerifyError("file changed before read")
        chunks, total = [], 0
        while True:
            chunk = os.read(fd, min(65536, MAX_FILE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise VerifyError("read budget exceeded")
        after_fd = os.fstat(fd)
    finally:
        os.close(fd)
    post = os.lstat(target)
    if ident(pre) != ident(after_fd) or ident(pre) != ident(post) or int(post.st_nlink) != 1:
        raise VerifyError("file changed during read")
    payload = b"".join(chunks)
    return payload, {"path": relative, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload), "regular": True, "nonlink": True, "nlink": 1, "single_handle_read": True}


def verify_preparation(repo: Path, commit: str, expected_parent: str = PINNED_PARENT, require_live: bool = True) -> dict[str, Any]:
    resolved = str(_git(repo, "rev-parse", f"{commit}^{{commit}}"))
    tree = str(_git(repo, "rev-parse", f"{resolved}^{{tree}}"))
    parents = str(_git(repo, "show", "-s", "--format=%P", resolved)).split()
    if parents != [expected_parent]:
        raise VerifyError("prep commit is not the direct single-parent child")
    changed_raw = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", expected_parent, resolved, binary=True)
    assert isinstance(changed_raw, bytes)
    changed = tuple(sorted(item.decode("utf-8", "strict") for item in changed_raw.split(b"\0") if item))
    if changed != PREP_PATHS:
        raise VerifyError("prep changed paths are not exact")
    files: dict[str, Any] = {}
    for relative in PREP_PATHS:
        old = _git(repo, "ls-tree", "-z", expected_parent, "--", relative, binary=True)
        assert isinstance(old, bytes)
        if old:
            raise VerifyError(f"prep path not first introduced: {relative}")
        if str(_git(repo, "cat-file", "-t", f"{resolved}:{relative}")) != "blob":
            raise VerifyError("prep entry is not a blob")
        blob = str(_git(repo, "rev-parse", f"{resolved}:{relative}"))
        size_text = str(_git(repo, "cat-file", "-s", blob))
        if not size_text.isascii() or not size_text.isdigit() or int(size_text) > MAX_FILE_BYTES:
            raise VerifyError("prep blob exceeds budget")
        raw = _git(repo, "cat-file", "blob", blob, binary=True)
        assert isinstance(raw, bytes)
        if len(raw) != int(size_text):
            raise VerifyError("prep blob size drift")
        fact: dict[str, Any] = {"blob": blob, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        if require_live:
            live, live_fact = _read(repo, relative)
            if live != raw:
                raise VerifyError("live prep file differs from raw Git blob")
            fact["live"] = live_fact
        files[relative] = fact
    for relative in FORMAL_PATHS:
        probe = _git(repo, "ls-tree", "-z", resolved, "--", relative, binary=True)
        assert isinstance(probe, bytes)
        if probe:
            raise VerifyError("formal evidence is present in prep commit")
    return {"commit": resolved, "tree": tree, "parent": expected_parent, "changed_paths": list(PREP_PATHS), "files": files}


def _physical_source(repo: Path, commit: str) -> dict[str, str]:
    resolved = str(_git(repo, "rev-parse", f"{commit}^{{commit}}"))
    tree = str(_git(repo, "rev-parse", f"{resolved}^{{tree}}"))
    with tempfile.TemporaryDirectory(prefix="sipi-pb-verify-archive-") as temporary:
        archive_path = Path(temporary) / "source.tar"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        archive_fd = os.open(archive_path, flags, 0o600)
        opened = os.fstat(archive_fd)
        cleanup_identity = (int(opened.st_dev), int(opened.st_ino))
        try:
            returncode, _, _ = _bounded_process(
                ["git", "-c", "core.autocrlf=false", "-C", str(repo), "archive", "--format=tar", resolved],
                timeout=GIT_TIMEOUT_SECONDS,
                stdout_limit=MAX_ARCHIVE_BYTES,
                stdout_fd=archive_fd,
            )
            os.fsync(archive_fd)
            os.close(archive_fd)
            archive_fd = -1
            if returncode:
                raise VerifyError("physical source archive command failed")
            read_fd = os.open(archive_path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
            try:
                chunks: list[bytes] = []
                total_bytes = 0
                while chunk := os.read(read_fd, 65536):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_ARCHIVE_BYTES:
                        raise VerifyError("physical source archive read exceeded budget")
                    chunks.append(chunk)
                payload = b"".join(chunks)
            finally:
                os.close(read_fd)
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
    entries: list[dict[str, Any]] = []
    total = 0
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for member in archive:
            if member.isdir():
                continue
            if not member.isfile() or member.issym() or member.islnk():
                raise VerifyError("physical source archive contains a link/non-file")
            stream = archive.extractfile(member)
            if stream is None:
                raise VerifyError("physical source member missing")
            payload = stream.read(MAX_FILE_BYTES + 1)
            if len(payload) > MAX_FILE_BYTES:
                raise VerifyError("physical source member exceeds budget")
            total += len(payload)
            if total > MAX_ARCHIVE_BYTES:
                raise VerifyError("physical source total exceeds budget")
            entries.append({"path": _safe_relative(member.name), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    entries.sort(key=lambda item: item["path"])
    return {"commit": resolved, "tree": tree, "archive_sha256": hashlib.sha256(payload).hexdigest(), "inventory_sha256": hashlib.sha256(_canonical(entries)).hexdigest()}


def _exact(value: Any, keys: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise VerifyError(f"{name} schema is not exact")
    return value


def _claims(value: Any) -> dict[str, bool]:
    value = _exact(value, CLAIMS, "claims")
    if any(type(item) is not bool or item for item in value.values()):
        raise VerifyError("scoped claims, including numeric_parity, must all be false")
    return value


def _fact(value: Any, label: str, *, exclusive: bool = False) -> dict[str, Any]:
    base_keys = {"path", "sha256", "bytes", "regular", "nonlink", "nlink", "single_handle_read", "pre_identity", "post_identity"}
    value = _exact(value, base_keys | ({"exclusive_create", "pre_absent", "readback_equal"} if exclusive else set()), label)
    _safe_relative(value["path"])
    if not HEX64.fullmatch(value["sha256"] or "") or type(value["bytes"]) is not int or value["bytes"] < 0:
        raise VerifyError(f"{label} digest invalid")
    if value["regular"] is not True or value["nonlink"] is not True or value["nlink"] != 1 or value["single_handle_read"] is not True:
        raise VerifyError(f"{label} custody flags invalid")
    if type(value["pre_identity"]) is not list or value["pre_identity"] != value["post_identity"] or len(value["pre_identity"]) != 4 or any(type(item) is not int for item in value["pre_identity"]):
        raise VerifyError(f"{label} identity invalid")
    if exclusive and (value["exclusive_create"] is not True or value["pre_absent"] is not True or value["readback_equal"] is not True):
        raise VerifyError(f"{label} exclusive flags invalid")
    return value


def _payload_observation(value: Any) -> dict[str, Any]:
    value = _exact(value, {"meta", "arrays"}, "PB-02 observation")
    meta = _exact(value["meta"], {"canonical_sha256", "fields"}, "metadata summary")
    if not HEX64.fullmatch(meta["canonical_sha256"] or "") or type(meta["fields"]) is not dict:
        raise VerifyError("metadata summary invalid")
    for field in meta["fields"].values():
        if type(field) is not dict or field.get("type") not in {"object", "array", "null", "bool", "number", "string"}:
            raise VerifyError("metadata field summary invalid")
        kind = field["type"]
        expected = {"type", "keys"} if kind == "object" else {"type", "length", "sha256"} if kind == "array" else {"type", "value"}
        if set(field) != expected:
            raise VerifyError("metadata field schema invalid")
    arrays = _exact(value["arrays"], {"bytes", "sha256", "uncompressed_bytes", "logical_members", "logical_sha256"}, "NPZ summary")
    if not HEX64.fullmatch(arrays["sha256"] or "") or not HEX64.fullmatch(arrays["logical_sha256"] or "") or tuple(sorted(arrays["logical_members"])) != PB02_MEMBERS:
        raise VerifyError("NPZ summary invalid")
    for member in arrays["logical_members"].values():
        member = _exact(member, {"dtype", "shape", "fortran_order", "count", "f64_sha256"}, "NPY summary")
        if member["dtype"] not in {"<f8", "|f8", ">f8"} or type(member["shape"]) is not list or type(member["fortran_order"]) is not bool or type(member["count"]) is not int or not HEX64.fullmatch(member["f64_sha256"] or ""):
            raise VerifyError("NPY summary invalid")
    return value


def _pb01_rows(value: Any) -> list[dict[str, Any]]:
    if type(value) is not list:
        raise VerifyError("PB-01 rows must be a list")
    rows: list[dict[str, Any]] = []
    names: list[str] = []
    for item in value:
        row = _exact(item, {"name", "length", "max_abs", "scale", "tolerance", "passed"}, "PB-01 row")
        if type(row["name"]) is not str or row["name"] not in PB01_ARRAYS or row["name"] in names:
            raise VerifyError("PB-01 row name invalid")
        if type(row["length"]) is not int or row["length"] <= 0:
            raise VerifyError("PB-01 row length invalid")
        if any(type(row[key]) not in (int, float) or not math.isfinite(row[key]) for key in ("max_abs", "scale", "tolerance")):
            raise VerifyError("PB-01 row numeric type/finite gate invalid")
        if row["max_abs"] < 0 or row["scale"] < 1:
            raise VerifyError("PB-01 row numeric range invalid")
        expected_tolerance = 1e-7 + 1e-6 * row["scale"]
        if row["tolerance"] != expected_tolerance or type(row["passed"]) is not bool or row["passed"] != (row["max_abs"] <= row["tolerance"]):
            raise VerifyError("PB-01 row tolerance/passed gate invalid")
        names.append(row["name"])
        rows.append(row)
    if names != list(PB01_ARRAYS[: len(names)]):
        raise VerifyError("PB-01 row order/closed set invalid")
    return rows


def _report(value: Any) -> dict[str, Any]:
    value = _exact(value, {"schema", "version", "run_id", "run_nonce", "preparation", "corpus", "source", "toolchain", "build", "oracle_runtime", "custody", "cases", "claims"}, "report")
    if value["schema"] != "sipi.pb-01-02-portable-matrix-report.v2" or type(value["version"]) is not int or value["version"] != 2:
        raise VerifyError("report schema/version invalid")
    if type(value["run_id"]) is not str or not value["run_id"] or not HEX64.fullmatch(value["run_nonce"] or ""):
        raise VerifyError("run identity invalid")
    _claims(value["claims"])
    prep = _exact(value["preparation"], {"commit", "tree", "parent", "changed_paths", "files"}, "report preparation")
    if not all(HEX40.fullmatch(prep[key] or "") for key in ("commit", "tree", "parent")) or tuple(prep["changed_paths"]) != PREP_PATHS or type(prep["files"]) is not dict or set(prep["files"]) != set(PREP_PATHS):
        raise VerifyError("report preparation binding invalid")
    for path, item in prep["files"].items():
        item = _exact(item, {"blob", "sha256", "bytes", "live_pre", "live_post", "live_equal"}, "report prep file")
        if not HEX40.fullmatch(item["blob"] or "") or not HEX64.fullmatch(item["sha256"] or "") or type(item["bytes"]) is not int or item["live_equal"] is not True:
            raise VerifyError("report prep file identity invalid")
        pre, post = _fact(item["live_pre"], "prep live pre"), _fact(item["live_post"], "prep live post")
        if pre != post or pre["path"] != path or pre["sha256"] != item["sha256"] or pre["bytes"] != item["bytes"]:
            raise VerifyError("report prep raw/live cross-binding invalid")
    corpus = _exact(value["corpus"], {"path", "blob", "sha256", "bytes"}, "report corpus")
    if corpus["path"] != PREP_PATHS[0] or not HEX40.fullmatch(corpus["blob"] or "") or not HEX64.fullmatch(corpus["sha256"] or "") or type(corpus["bytes"]) is not int:
        raise VerifyError("report corpus binding invalid")
    if any(corpus[key] != prep["files"][PREP_PATHS[0]][key] for key in ("blob", "sha256", "bytes")):
        raise VerifyError("report corpus is not prep corpus blob")
    source = _exact(value["source"], {"candidate", "upstream"}, "report source")
    for identity in source.values():
        identity = _exact(identity, {"commit", "tree", "archive_sha256", "inventory_pre_sha256", "inventory_post_sha256", "inventory_equal"}, "source identity")
        if not HEX40.fullmatch(identity["commit"] or "") or not HEX40.fullmatch(identity["tree"] or "") or not all(HEX64.fullmatch(identity[key] or "") for key in ("archive_sha256", "inventory_pre_sha256", "inventory_post_sha256")):
            raise VerifyError("source hashes invalid")
        if identity["inventory_equal"] is not True or identity["inventory_pre_sha256"] != identity["inventory_post_sha256"]:
            raise VerifyError("source inventory drift")
    if source["candidate"]["commit"] != prep["commit"] or source["candidate"]["tree"] != prep["tree"]:
        raise VerifyError("candidate source is not the preparation commit/tree")
    if (source["upstream"]["commit"], source["upstream"]["tree"]) != (UPSTREAM_COMMIT, UPSTREAM_TREE):
        raise VerifyError("upstream source is not pinned")
    tools = _exact(value["toolchain"], {"cargo", "rustc", "uv", "link"}, "toolchain")
    for role, tool in tools.items():
        tool = _exact(tool, {"role", "executable", "file_sha256", "version_sha256", "version_exit", "path_redacted", "file_custody_pre", "file_custody_post", "file_custody_equal"}, "tool identity")
        if tool["role"] != role or type(tool["executable"]) is not str or "/" in tool["executable"] or "\\" in tool["executable"] or not HEX64.fullmatch(tool["file_sha256"] or "") or not HEX64.fullmatch(tool["version_sha256"] or "") or type(tool["version_exit"]) is not int or tool["version_exit"] != 0 or tool["path_redacted"] is not True:
            raise VerifyError("tool identity invalid")
        executable_fact = _fact(tool["file_custody_pre"], "tool executable pre")
        executable_post = _fact(tool["file_custody_post"], "tool executable post")
        if tool["file_custody_equal"] is not True or executable_fact != executable_post or executable_fact["sha256"] != tool["file_sha256"] or Path(executable_fact["path"]).name != tool["executable"]:
            raise VerifyError("tool executable custody mismatch")
    build = _exact(value["build"], {"process", "cargo_binary_source", "binary", "env"}, "build")
    cargo_source = _exact(build["cargo_binary_source"], {"path", "sha256", "bytes", "regular", "nonlink", "nlink", "single_handle_read", "pre_identity", "post_identity"}, "cargo binary source")
    if cargo_source["regular"] is not True or cargo_source["nonlink"] is not True or type(cargo_source["nlink"]) is not int or cargo_source["nlink"] < 1 or cargo_source["single_handle_read"] is not True or cargo_source["pre_identity"] != cargo_source["post_identity"] or not HEX64.fullmatch(cargo_source["sha256"] or ""):
        raise VerifyError("cargo binary source invalid")
    process = _exact(build["process"], {"exit_code", "stdout", "stderr"}, "build process")
    if type(process["exit_code"]) is not int or process["exit_code"] != 0:
        raise VerifyError("build process invalid")
    _fact(process["stdout"], "build stdout", exclusive=True); _fact(process["stderr"], "build stderr", exclusive=True)
    binary = _exact(build["binary"], {"pre", "post", "equal"}, "build binary")
    binary_pre = _fact(binary["pre"], "build binary pre", exclusive=True)
    binary_post = _fact(binary["post"], "build binary post")
    if binary["equal"] is not True or {key: data for key, data in binary_pre.items() if key not in {"exclusive_create", "pre_absent", "readback_equal"}} != binary_post:
        raise VerifyError("build binary drift")
    if build["env"] != {"rustc_explicit": True, "rustc_wrappers_cleared": True, "cargo_target_external": True, "cargo_offline": True, "path_closed": True, "cargo_home_explicit": True, "cargo_config_and_flags_cleared": True, "cargo_cache_lock_bound": True}:
        raise VerifyError("build env invalid")
    runtime = _exact(value["oracle_runtime"], {"process", "modules", "clean_archive_or_venv_only", "host_pythonpath_absent", "host_virtual_env_absent", "uv_offline_frozen_no_config", "uv_link_mode_copy", "uv_cache_explicit_lock_bound", "host_uv_flags_cleared", "oracle_work_archive_sha256", "oracle_work_started_clean"}, "oracle runtime")
    if any(runtime[key] is not True for key in ("clean_archive_or_venv_only", "host_pythonpath_absent", "host_virtual_env_absent", "uv_offline_frozen_no_config", "uv_link_mode_copy", "uv_cache_explicit_lock_bound", "host_uv_flags_cleared")):
        raise VerifyError("oracle runtime closure invalid")
    if runtime["oracle_work_started_clean"] is not True or runtime["oracle_work_archive_sha256"] != source["upstream"]["archive_sha256"]:
        raise VerifyError("oracle work archive binding invalid")
    probe = _exact(runtime["process"], {"exit_code", "stdout", "stderr"}, "oracle probe")
    if type(probe["exit_code"]) is not int or probe["exit_code"] != 0:
        raise VerifyError("oracle probe failed")
    _fact(probe["stdout"], "oracle probe stdout", exclusive=True); _fact(probe["stderr"], "oracle probe stderr", exclusive=True)
    modules = _exact(runtime["modules"], {"pybert", "numpy", "scipy"}, "oracle modules")
    for name, module in modules.items():
        module = _exact(module, {"owner", "relative_path", "version", "file"}, "oracle module")
        if module["owner"] not in ({"archive", "venv"} if name == "pybert" else {"venv"}) or type(module["version"]) is not str or not module["version"]:
            raise VerifyError("oracle module containment invalid")
        if _fact(module["file"], "oracle module file")["path"] != _safe_relative(module["relative_path"]):
            raise VerifyError("oracle module fact/path mismatch")
    custody = _exact(value["custody"], {"archive_materialization", "inputs", "artifacts", "output"}, "report custody")
    if type(custody["archive_materialization"]) is not list or len(custody["archive_materialization"]) != 3 or type(custody["inputs"]) is not list or type(custody["artifacts"]) is not list or custody["output"] != {"fresh_root": True, "exclusive_report": True}:
        raise VerifyError("report custody shape invalid")
    archive_roles = {"candidate", "upstream_pristine", "upstream_oracle"}
    seen_archive_roles: set[str] = set()
    for item in custody["archive_materialization"]:
        item = _exact(item, {"role", "archive_sha256", "fact"}, "archive custody")
        if item["role"] not in archive_roles or item["role"] in seen_archive_roles or not HEX64.fullmatch(item["archive_sha256"] or ""):
            raise VerifyError("archive custody role/hash invalid")
        seen_archive_roles.add(item["role"])
        fact = _fact(item["fact"], "archive custody fact")
        if fact["sha256"] != item["archive_sha256"]:
            raise VerifyError("archive custody fact/hash mismatch")
        expected = source["candidate"]["archive_sha256"] if item["role"] == "candidate" else source["upstream"]["archive_sha256"]
        if item["archive_sha256"] != expected:
            raise VerifyError("archive custody source cross-binding invalid")
    if seen_archive_roles != archive_roles:
        raise VerifyError("archive custody roles incomplete")
    for item in custody["inputs"]:
        if type(item) is not dict or set(item) not in ({"lane", "pre", "post", "equal"}, {"case_id", "pre", "post", "equal"}) or item["equal"] is not True:
            raise VerifyError("input custody shape invalid")
        pre = _fact(item["pre"], "input pre", exclusive="case_id" in item)
        post = _fact(item["post"], "input post")
        if {key: data for key, data in pre.items() if key not in {"exclusive_create", "pre_absent", "readback_equal"}} != post:
            raise VerifyError("input custody drift")
    for item in custody["artifacts"]:
        if type(item) is not dict or type(item.get("present")) is not bool:
            raise VerifyError("artifact custody invalid")
        if item["present"] is False:
            if set(item) != {"path", "present", "role", "kind", "case_id"}:
                raise VerifyError("missing artifact schema invalid")
            _safe_relative(item["path"])
        else:
            extras = {key: item[key] for key in ("role", "kind", "case_id") if key in item}
            base = {key: data for key, data in item.items() if key not in extras and key not in {"present", "pre_absent"}}
            _fact(base, "artifact")
            if item.get("pre_absent") is not True or set(extras) != {"role", "kind", "case_id"}:
                raise VerifyError("artifact pre-absence invalid")
    if len(custody["inputs"]) != 14 or [item.get("lane") for item in custody["inputs"][:2]] != ["PB-01", "PB-02"] or tuple(item.get("case_id") for item in custody["inputs"][2:]) != CASE_IDS:
        raise VerifyError("input custody closed set invalid")
    expected_artifacts = {(case_id, role, kind) for case_id in CASE_IDS[:6] for role in ("candidate", "oracle") for kind in ("legacy_result",)}
    expected_artifacts |= {(case_id, role, kind) for case_id in CASE_IDS[6:] for role in ("candidate", "oracle") for kind in ("meta", "arrays")}
    actual_artifacts = [(item.get("case_id"), item.get("role"), item.get("kind")) for item in custody["artifacts"]]
    if len(actual_artifacts) != len(expected_artifacts) or set(actual_artifacts) != expected_artifacts:
        raise VerifyError("artifact custody closed set invalid")
    if type(value["cases"]) is not list:
        raise VerifyError("report cases invalid")
    ids: list[str] = []
    for case in value["cases"]:
        case = _exact(case, {"id", "status", "blockers", "comparison"}, "case")
        if type(case["id"]) is not str or type(case["status"]) is not str or type(case["blockers"]) is not list or type(case["comparison"]) is not dict:
            raise VerifyError("case type invalid")
        if case["status"] not in {"passed", "blocked"} or any(type(item) is not str for item in case["blockers"]):
            raise VerifyError("case status/blockers invalid")
        comparison = case["comparison"]
        if case["id"].startswith("pb01_"):
            comparison = _exact(comparison, {"kind", "class_pickle_covered_by_matrix", "candidate_schema", "oracle_schema", "rows", "blockers", "candidate_process", "oracle_process"}, "PB-01 comparison")
            if comparison["kind"] != "pb01_selected_numeric_arrays" or comparison["class_pickle_covered_by_matrix"] is not False or type(comparison["rows"]) is not list or type(comparison["blockers"]) is not list:
                raise VerifyError("PB-01 comparison invalid")
            rows = _pb01_rows(comparison["rows"])
            if case["status"] == "passed" and (tuple(row["name"] for row in rows) != PB01_ARRAYS or not all(row["passed"] for row in rows) or comparison["blockers"] or case["blockers"]):
                raise VerifyError("PB-01 passed row proof invalid")
            if case["status"] == "passed" and (comparison["candidate_schema"] != {"kind": "python_pickle_dict", "schema": "sipi.pybert_data.v1", "item_names": list(PB01_ITEMS), "array_keys": sorted(PB01_ITEMS)} or comparison["oracle_schema"] != {"kind": "PyBertData_class_pickle"}):
                raise VerifyError("PB-01 artifact schema invalid")
            if sorted(set(comparison["blockers"])) != case["blockers"]:
                raise VerifyError("PB-01 blocker projection drift")
        else:
            comparison = _exact(comparison, {"kind", "candidate", "oracle", "candidate_process", "oracle_process"}, "PB-02 comparison")
            if comparison["kind"] != "pb02_complete_meta_and_logical_npz" or any(item is not None and type(item) is not dict for item in (comparison["candidate"], comparison["oracle"])):
                raise VerifyError("PB-02 comparison invalid")
            for observation in (comparison["candidate"], comparison["oracle"]):
                if observation is not None:
                    _payload_observation(observation)
        for role in ("candidate_process", "oracle_process"):
            process = _exact(comparison[role], {"exit_code", "stdout", "stderr"}, "case process")
            if type(process["exit_code"]) is not int:
                raise VerifyError("case process exit invalid")
            _fact(process["stdout"], "process stdout", exclusive=True)
            _fact(process["stderr"], "process stderr", exclusive=True)
        exits_zero = comparison["candidate_process"]["exit_code"] == comparison["oracle_process"]["exit_code"] == 0
        if (case["status"] == "passed") != (exits_zero and not case["blockers"]):
            raise VerifyError("case status/exits/blockers mismatch")
        if case["id"].startswith("pb02_") and case["status"] == "passed":
            if comparison["candidate"] != comparison["oracle"] or comparison["candidate"] is None:
                raise VerifyError("PB-02 passed observation mismatch")
            for role in ("candidate", "oracle"):
                arrays = comparison[role].get("arrays")
                if type(arrays) is not dict or tuple(sorted(arrays.get("logical_members", {}))) != PB02_MEMBERS:
                    raise VerifyError("PB-02 logical member set invalid")
        ids.append(case["id"])
    if tuple(ids) != CASE_IDS or len(ids) != len(set(ids)):
        raise VerifyError("case IDs are not the unique closed matrix")
    return value


def recompute_aggregate(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    first, second = _report(first), _report(second)
    if first["run_id"] == second["run_id"] or first["run_nonce"] == second["run_nonce"]:
        raise VerifyError("runs are not fresh")
    for key in ("preparation", "corpus", "source", "toolchain"):
        if _canonical(first[key]) != _canonical(second[key]):
            raise VerifyError(f"report {key} drift")
    def module_observation(report: dict[str, Any]) -> dict[str, Any]:
        return {name: {"owner": item["owner"], "relative_path": item["relative_path"], "version": item["version"], "sha256": item["file"]["sha256"], "bytes": item["file"]["bytes"]} for name, item in report["oracle_runtime"]["modules"].items()}
    if _canonical(module_observation(first)) != _canonical(module_observation(second)):
        raise VerifyError("oracle module identity drift")
    cases = []
    for left, right in zip(first["cases"], second["cases"], strict=True):
        def observation(case: dict[str, Any]) -> dict[str, Any]:
            comparison = {key: data for key, data in case["comparison"].items() if key not in {"candidate_process", "oracle_process"}}
            return {"id": case["id"], "status": case["status"], "blockers": case["blockers"], "comparison": comparison}
        equal = _canonical(observation(left)) == _canonical(observation(right))
        passed = left["status"] == "passed" and right["status"] == "passed"
        cases.append({"id": left["id"], "first_status": left["status"], "second_status": right["status"], "observation_equal": equal, "passed_scoped": passed and equal})
    all_passed = all(case["passed_scoped"] for case in cases)
    return {"schema": "sipi.pb-01-02-portable-matrix-aggregate.v2", "version": 2, "status": "passed_scoped" if all_passed else "scoped_matrix_blocked", "runs": [{"run_id": first["run_id"], "nonce": first["run_nonce"]}, {"run_id": second["run_id"], "nonce": second["run_nonce"]}], "preparation": first["preparation"], "corpus": first["corpus"], "source": first["source"], "toolchain": first["toolchain"], "cases": cases, "claims": {key: False for key in sorted(CLAIMS)}}


def validate_manifest_shape(value: Any) -> dict[str, Any]:
    value = _exact(value, {"schema", "version", "status", "preparation", "harness", "evidence", "audit_binding", "claims"}, "manifest")
    if value["schema"] != "sipi.pb-01-02-portable-matrix-evidence.v2" or type(value["version"]) is not int or value["version"] != 2:
        raise VerifyError("manifest schema/version invalid")
    if value["status"] not in {"passed_scoped", "scoped_matrix_blocked"}:
        raise VerifyError("manifest status invalid")
    _claims(value["claims"])
    preparation = _exact(value["preparation"], {"commit", "tree", "parent"}, "manifest preparation")
    if not all(HEX40.fullmatch(preparation[key] or "") for key in preparation):
        raise VerifyError("manifest preparation identity invalid")
    harness = _exact(value["harness"], {"files"}, "manifest harness")
    if type(harness["files"]) is not list or len(harness["files"]) != len(PREP_PATHS):
        raise VerifyError("manifest harness list invalid")
    paths = []
    for item in harness["files"]:
        item = _exact(item, {"path", "blob", "sha256", "bytes"}, "harness file")
        paths.append(_safe_relative(item["path"]))
        if not HEX40.fullmatch(item["blob"] or "") or not HEX64.fullmatch(item["sha256"] or "") or type(item["bytes"]) is not int:
            raise VerifyError("harness binding invalid")
    if tuple(sorted(paths)) != PREP_PATHS:
        raise VerifyError("manifest harness path set invalid")
    evidence = _exact(value["evidence"], {"reports", "aggregate"}, "manifest evidence")
    if type(evidence["reports"]) is not list or len(evidence["reports"]) != 2:
        raise VerifyError("manifest needs exactly two reports")
    for ref in [*evidence["reports"], evidence["aggregate"]]:
        ref = _exact(ref, {"path", "sha256", "bytes"}, "evidence ref")
        _safe_relative(ref["path"])
        if not HEX64.fullmatch(ref["sha256"] or "") or type(ref["bytes"]) is not int:
            raise VerifyError("evidence ref invalid")
    if tuple(ref["path"] for ref in evidence["reports"]) != FORMAL_PATHS[:2] or evidence["aggregate"]["path"] != FORMAL_PATHS[2]:
        raise VerifyError("formal evidence paths are not exact")
    audit = _exact(value["audit_binding"], {"path", "sha256", "bytes", "binding_sha256"}, "audit binding")
    _safe_relative(audit["path"])
    if not HEX64.fullmatch(audit["sha256"] or "") or not HEX64.fullmatch(audit["binding_sha256"] or "") or type(audit["bytes"]) is not int:
        raise VerifyError("audit binding invalid")
    if audit["path"] != FORMAL_PATHS[4]:
        raise VerifyError("audit path is not exact")
    core = {key: value[key] for key in ("schema", "version", "status", "preparation", "harness", "evidence", "claims")}
    core["audit_path"] = audit["path"]
    if hashlib.sha256(_canonical(core)).hexdigest() != audit["binding_sha256"]:
        raise VerifyError("audit binding_sha256 is not the normalized manifest core digest")
    return value


def verify_formal(repo: Path, manifest_relative: str, upstream_repo: Path = Path(r"C:\Users\z3312\code\Py-bert-agent")) -> dict[str, Any]:
    manifest_bytes, manifest_fact = _read(repo, manifest_relative)
    try:
        manifest = yaml.safe_load(manifest_bytes)
    except yaml.YAMLError as error:
        raise VerifyError(f"invalid manifest: {error}") from error
    manifest = validate_manifest_shape(manifest)
    prep = verify_preparation(repo, manifest["preparation"]["commit"], manifest["preparation"]["parent"], require_live=False)
    if {key: prep[key] for key in ("commit", "tree", "parent")} != manifest["preparation"]:
        raise VerifyError("manifest preparation does not match Git")
    for item in manifest["harness"]["files"]:
        fact = prep["files"][item["path"]]
        if any(fact[key] != item[key] for key in ("blob", "sha256", "bytes")):
            raise VerifyError("manifest harness does not match raw Git blob")
    reports, report_facts = [], []
    for ref in manifest["evidence"]["reports"]:
        payload, fact = _read(repo, ref["path"])
        if any(fact[key] != ref[key] for key in ("sha256", "bytes")):
            raise VerifyError("report ref hash/length mismatch")
        reports.append(_report(_json_loads(payload)))
        report_facts.append(fact)
    for report in reports:
        if {key: report["preparation"][key] for key in ("commit", "tree", "parent")} != manifest["preparation"]:
            raise VerifyError("report preparation differs from manifest")
        for harness in manifest["harness"]["files"]:
            bound = report["preparation"]["files"][harness["path"]]
            if any(bound[key] != harness[key] for key in ("blob", "sha256", "bytes")):
                raise VerifyError("report harness differs from manifest/raw Git")
    if report_facts[0]["path"] == report_facts[1]["path"] or report_facts[0]["sha256"] == report_facts[1]["sha256"]:
        raise VerifyError("report path/hash must be distinct")
    for role, source_repo in (("candidate", repo), ("upstream", upstream_repo)):
        physical = _physical_source(source_repo, reports[0]["source"][role]["commit"])
        reported = reports[0]["source"][role]
        if any(physical[key] != reported[key] for key in ("commit", "tree", "archive_sha256")) or physical["inventory_sha256"] != reported["inventory_pre_sha256"] or reported["inventory_pre_sha256"] != reported["inventory_post_sha256"]:
            raise VerifyError(f"{role} physical archive/inventory source binding drift")
    expected = recompute_aggregate(reports[0], reports[1])
    aggregate_ref = manifest["evidence"]["aggregate"]
    aggregate_bytes, aggregate_fact = _read(repo, aggregate_ref["path"])
    if any(aggregate_fact[key] != aggregate_ref[key] for key in ("sha256", "bytes")):
        raise VerifyError("aggregate ref mismatch")
    actual = _json_loads(aggregate_bytes)
    if _canonical(actual) != _canonical({**expected, "report_files": report_facts}):
        raise VerifyError("aggregate is not the mechanical recomputation")
    audit_ref = manifest["audit_binding"]
    audit_bytes, audit_fact = _read(repo, audit_ref["path"])
    if any(audit_fact[key] != audit_ref[key] for key in ("sha256", "bytes")):
        raise VerifyError("audit ref mismatch")
    prefix = b"<!-- sipi-pb-matrix-binding-v2:"
    first_line = audit_bytes.splitlines()[0] if audit_bytes else b""
    if not first_line.startswith(prefix) or not first_line.endswith(b" -->"):
        raise VerifyError("audit lacks machine-readable cross-binding")
    binding = _json_loads(first_line[len(prefix):-4])
    expected_binding = {"manifest_core_sha256": audit_ref["binding_sha256"], "reports": [item["sha256"] for item in manifest["evidence"]["reports"]], "aggregate": aggregate_ref["sha256"], "prep_commit": prep["commit"]}
    if binding != expected_binding:
        raise VerifyError("audit cross-binding mismatch")
    return {"valid": True, "manifest": manifest_fact, "status": actual["status"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--upstream-repo", type=Path, default=Path(r"C:\Users\z3312\code\Py-bert-agent"))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prep-commit")
    group.add_argument("--manifest")
    parser.add_argument("--expected-parent", default=PINNED_PARENT)
    args = parser.parse_args()
    try:
        result = verify_preparation(args.repo, args.prep_commit, args.expected_parent) if args.prep_commit else verify_formal(args.repo, args.manifest, args.upstream_repo)
    except (VerifyError, json.JSONDecodeError, UnicodeDecodeError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"valid": True, "result": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
