"""Caller-custody preflight for the pinned Agent-Spice XSPICE RFM build."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from typing import Any, BinaryIO

UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
UPSTREAM_ARCHIVE_SHA256 = "a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144"
NGSPICE_SOURCE_SHA256 = "a0d1699af1940b06649276dcd6ff5a566c8c0cad01b2f7b5e99dedbb4d64c19b"
SOURCE_BASENAME = "ngspice-46.tar.gz"
SOURCE_PATHS = (
    "poc/xspice-rfm/build-windows.ps1",
    "poc/xspice-rfm/Dockerfile",
    "poc/xspice-rfm/cfunc.mod",
    "poc/xspice-rfm/ifspec.ifs",
    "poc/xspice-rfm/modpath.lst",
    "poc/xspice-rfm/udnpath.lst",
    "LICENSE",
)
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_SOURCE_BYTES = 512 * 1024 * 1024
MAX_ASSET_FILES = 1
MAX_ASSET_TOTAL_BYTES = 512 * 1024 * 1024
MAX_ASSET_ENTRIES = 1
MAX_TAR_MEMBERS = 100_000
MAX_OUTPUT_BYTES = 64 * 1024
COMMAND_TIMEOUT_SECONDS = 20
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass
class PipeResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    overflowed: bool


class SharedBudget:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.total = 0
        self.overflowed = False
        self._lock = threading.Lock()

    def add(self, count: int) -> bool:
        with self._lock:
            self.total += count
            if self.total > self.maximum:
                self.overflowed = True
                return False
            return True


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path, maximum: int | None = None) -> tuple[int, str, bool]:
    digest = hashlib.sha256()
    size = 0
    overflowed = False
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if maximum is not None and size > maximum:
                overflowed = True
                break
            digest.update(chunk)
    return size, digest.hexdigest(), overflowed


def run_process(path: Path, args: tuple[str, ...], maximum: int, timeout: float) -> PipeResult:
    env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_CONFIG", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_COUNT"):
        env.pop(key, None)
    process = subprocess.Popen(
        [str(path), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env=env,
    )
    budget = SharedBudget(maximum)
    outputs: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    def drain(name: str, pipe: BinaryIO | None) -> None:
        if pipe is None:
            return
        while True:
            chunk = pipe.read(64 * 1024)
            if not chunk:
                break
            if not budget.add(len(chunk)):
                break
            outputs[name].extend(chunk)

    threads = [threading.Thread(target=drain, args=(name, getattr(process, name))) for name in outputs]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout
    timed_out = False
    while process.poll() is None:
        if budget.overflowed:
            process.kill()
            break
        if time.monotonic() >= deadline:
            timed_out = True
            process.kill()
            break
        time.sleep(0.01)
    try:
        returncode = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        returncode = process.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()
    return PipeResult(returncode, bytes(outputs["stdout"]), bytes(outputs["stderr"]), timed_out, budget.overflowed)


def tool_identity(path: Path) -> dict[str, Any]:
    size, file_sha, overflowed = digest_file(path, MAX_SOURCE_BYTES)
    if overflowed:
        raise ValueError("tool exceeds file budget")
    result = run_process(path, ("--version",), MAX_OUTPUT_BYTES, COMMAND_TIMEOUT_SECONDS)
    output = result.stdout + result.stderr
    return {
        "basename": path.name,
        "file_bytes": size,
        "file_sha256": file_sha,
        "version_exit_code": result.returncode,
        "version_output_bytes": len(output),
        "version_output_sha256": digest_bytes(output),
        "version_timeout": result.timed_out,
        "version_overflow": result.overflowed,
        "path_redacted": True,
    }


def identity_valid(value: dict[str, Any]) -> bool:
    return (
        value.get("version_exit_code") == 0
        and value.get("version_timeout") is False
        and value.get("version_overflow") is False
        and type(value.get("version_output_bytes")) is int
        and value["version_output_bytes"] > 0
        and isinstance(value.get("file_sha256"), str)
        and bool(HEX64.fullmatch(value["file_sha256"]))
        and isinstance(value.get("version_output_sha256"), str)
        and bool(HEX64.fullmatch(value["version_output_sha256"]))
    )


def python_identity() -> dict[str, Any]:
    executable = Path(sys.executable)
    if executable.is_symlink():
        raise ValueError("python executable is a symlink")
    executable = regular_absolute(executable, "python-executable")
    result = tool_identity(executable)
    result["runtime_version_sha256"] = digest_bytes(sys.version.encode("utf-8"))
    return result


def tarfile_identity() -> dict[str, Any]:
    module = Path(tarfile.__file__ or "")
    if not module.is_file() or module.is_symlink():
        raise ValueError("tarfile module is not a regular file")
    size, sha, overflowed = digest_file(module, MAX_SOURCE_BYTES)
    return {"basename": module.name, "file_bytes": size, "file_sha256": sha if not overflowed else None, "module_version": "python-stdlib", "path_redacted": True}


def blocked_identity() -> dict[str, Any]:
    return {"status": "unknown", "path_redacted": True}


def regular_absolute(value: Path, label: str) -> Path:
    if not value.is_absolute() or ".." in value.parts:
        raise ValueError(f"{label} must be absolute without traversal")
    if value.is_symlink() or not value.is_file():
        raise ValueError(f"{label} must be a regular file")
    return value


def regular_directory(value: Path, label: str) -> Path:
    if not value.is_absolute() or ".." in value.parts:
        raise ValueError(f"{label} must be absolute without traversal")
    if value.is_symlink() or not value.is_dir():
        raise ValueError(f"{label} must be a regular directory")
    return value


def safe_member(name: str, seen: set[str]) -> tuple[bool, tuple[str, ...]]:
    if not name or "\x00" in name or "\\" in name:
        return False, ()
    path = PurePosixPath(name)
    parts = path.parts
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    if path.is_absolute() or not parts or ".." in parts or any(
        not part or part in {"."} or ":" in part or part.endswith((".", " ")) or part.split(".", 1)[0].casefold() in reserved
        for part in parts
    ):
        return False, ()
    folded = "/".join(parts).casefold()
    if folded in seen:
        return False, ()
    seen.add(folded)
    return True, parts


def extract_clean_archive(archive: Path, destination: Path) -> tuple[bool, str]:
    total = 0
    try:
        destination.mkdir(parents=True, exist_ok=True)
        root = destination.resolve()
        seen: set[str] = set()
        with tarfile.open(archive, "r:") as tar:
            member_count = 0
            while member := tar.next():
                member_count += 1
                if member_count > MAX_TAR_MEMBERS:
                    return False, "member_budget"
                safe, parts = safe_member(member.name, seen)
                if not safe or member.issym() or member.islnk() or member.isdev() or not (member.isdir() or member.isfile()):
                    return False, "unsafe_member"
                target = (destination.joinpath(*parts)).resolve()
                if target != root and root not in target.parents:
                    return False, "containment"
                if member.isfile():
                    total += member.size
                    if total > MAX_ARCHIVE_BYTES:
                        return False, "extract_budget"
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    if target.is_symlink():
                        return False, "unsafe_member"
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    return False, "missing_member_data"
                try:
                    with target.open("xb") as output:
                        while chunk := source.read(1024 * 1024):
                            output.write(chunk)
                except (OSError, ValueError):
                    target.unlink(missing_ok=True)
                    return False, "member_write_failed"
    except (OSError, tarfile.TarError):
        return False, "invalid_archive"
    return True, "ok"


def clean_archive(git: Path, upstream: Path, destination: Path, commit: str) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "upstream.tar"
    env_args = ("-c", "core.autocrlf=true", "-C", str(upstream), "archive", "--format=tar", commit)
    result = run_process(git, env_args, MAX_ARCHIVE_BYTES, COMMAND_TIMEOUT_SECONDS)
    archive.write_bytes(result.stdout)
    observation = {"bytes": len(result.stdout), "sha256": None if result.timed_out or result.overflowed else digest_bytes(result.stdout), "returncode": result.returncode, "timeout": result.timed_out, "overflow": result.overflowed}
    if result.returncode == 0 and not result.timed_out and not result.overflowed:
        extracted, reason = extract_clean_archive(archive, destination / "source")
    else:
        extracted, reason = False, "git_archive_failed"
    observation.update({"extracted": extracted, "extract_status": reason})
    return observation


def runtime_member_observation(extracted_root: Path) -> dict[str, Any]:
    relative = Path("tools") / "preflight_as06_xspice_rfm.py"
    member = extracted_root / relative
    runtime = Path(__file__).resolve()
    runtime_size, runtime_sha, runtime_overflow = digest_file(runtime, MAX_SOURCE_BYTES)
    if not member.is_file() or member.is_symlink():
        return {"present": False, "runtime_bytes": runtime_size, "runtime_sha256": runtime_sha, "runtime_overflow": runtime_overflow, "match": False, "path_redacted": True}
    member_size, member_sha, member_overflow = digest_file(member, MAX_SOURCE_BYTES)
    return {"present": True, "member_bytes": member_size, "member_sha256": member_sha, "member_overflow": member_overflow, "runtime_bytes": runtime_size, "runtime_sha256": runtime_sha, "runtime_overflow": runtime_overflow, "match": not member_overflow and not runtime_overflow and member_size == runtime_size and member_sha == runtime_sha, "path_redacted": True}


def runner_snapshot() -> dict[str, Any]:
    runtime = Path(__file__)
    if runtime.is_symlink():
        raise OSError("runner is a symlink")
    size, sha, overflowed = digest_file(runtime.resolve(), MAX_SOURCE_BYTES)
    return {"bytes": size, "sha256": sha if not overflowed else None, "overflow": overflowed}


def runner_identity_gate(initial: dict[str, Any], member: dict[str, Any], post: dict[str, Any]) -> bool:
    if not member.get("match", False) or any(value.get("overflow", True) for value in (initial, post)):
        return False
    identity = (initial.get("bytes"), initial.get("sha256"))
    runtime_identity = (member.get("runtime_bytes"), member.get("runtime_sha256"))
    archive_identity = (member.get("member_bytes"), member.get("member_sha256"))
    return identity == runtime_identity == archive_identity == (post.get("bytes"), post.get("sha256"))


def asset_identity_stable(pre: dict[str, Any], mid: dict[str, Any], post: dict[str, Any]) -> bool:
    return pre == mid == post


def git_revision(git: Path, root: Path, revision: str) -> str | None:
    result = run_process(git, ("-C", str(root), "rev-parse", revision), MAX_OUTPUT_BYTES, COMMAND_TIMEOUT_SECONDS)
    if result.returncode != 0 or result.timed_out or result.overflowed:
        return None
    try:
        return result.stdout.decode("ascii").strip()
    except UnicodeDecodeError:
        return None


def source_asset(asset_root: Path) -> dict[str, Any]:
    expected = asset_root / SOURCE_BASENAME
    file_count = 0
    total_bytes = 0
    other_entry_count = 0
    expected_present = False
    expected_size: int | None = None
    expected_symlink = False
    try:
        for item in asset_root.iterdir():
            if item.is_symlink():
                if item == expected:
                    expected_symlink = True
                else:
                    other_entry_count += 1
            elif item.is_file():
                file_count += 1
                if item == expected:
                    expected_present = True
                    expected_size = item.stat().st_size
                else:
                    if file_count > MAX_ASSET_FILES:
                        return {"basename": SOURCE_BASENAME, "present": False, "kind": "wrong_file", "mismatch": False, "path_redacted": True, "file_count": file_count, "total_bytes": total_bytes, "single_bytes": None, "sha256": None, "wrong_file_count": file_count - 1, "other_entry_count": other_entry_count, "wrong_files": []}
                total_bytes += item.stat().st_size
            else:
                other_entry_count += 1
            if total_bytes > MAX_ASSET_TOTAL_BYTES or other_entry_count > MAX_ASSET_ENTRIES:
                return {"basename": SOURCE_BASENAME, "present": expected_present, "kind": "overflow" if total_bytes > MAX_ASSET_TOTAL_BYTES else "wrong_file", "mismatch": False, "path_redacted": True, "file_count": file_count, "total_bytes": total_bytes, "single_bytes": expected_size, "sha256": None, "wrong_file_count": max(0, file_count - 1), "other_entry_count": other_entry_count, "wrong_files": []}
    except OSError:
        return {"basename": SOURCE_BASENAME, "present": False, "kind": "asset_root_error", "mismatch": False, "path_redacted": True, "file_count": file_count, "total_bytes": total_bytes, "single_bytes": None, "sha256": None, "wrong_file_count": max(0, file_count - 1), "other_entry_count": other_entry_count, "wrong_files": []}
    common = {"basename": SOURCE_BASENAME, "path_redacted": True, "file_count": file_count, "total_bytes": total_bytes, "wrong_file_count": file_count if not expected_present else max(0, file_count - 1), "other_entry_count": other_entry_count, "wrong_files": []}
    if expected_symlink:
        return {**common, "present": False, "kind": "wrong_file", "mismatch": False, "single_bytes": None, "sha256": None, "symlink": True}
    if not expected_present:
        return {**common, "present": False, "kind": "wrong_file" if file_count or other_entry_count else "missing", "mismatch": False, "single_bytes": None, "sha256": None}
    if file_count != MAX_ASSET_FILES or other_entry_count or expected_size is None or expected_size > MAX_SOURCE_BYTES:
        return {**common, "present": True, "kind": "overflow" if expected_size is not None and expected_size > MAX_SOURCE_BYTES else "wrong_file", "mismatch": False, "single_bytes": expected_size, "sha256": None}
    size, sha, overflowed = digest_file(expected, MAX_SOURCE_BYTES)
    if overflowed:
        return {**common, "present": True, "kind": "overflow", "mismatch": False, "single_bytes": size, "sha256": None}
    mismatch = overflowed or sha != NGSPICE_SOURCE_SHA256
    return {**common, "present": True, "kind": "mismatch" if mismatch else "exact", "mismatch": mismatch, "single_bytes": size, "sha256": sha}


def archive_sources(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for relative in SOURCE_PATHS:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            result[relative] = {"present": False, "status": "unknown", "reason": "not_observed"}
        else:
            size, sha, overflowed = digest_file(path, MAX_ARCHIVE_BYTES)
            result[relative] = {"present": True, "bytes": size, "sha256": sha, "status": "observed", "overflow": overflowed}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", required=True, type=Path)
    parser.add_argument("--upstream-root", required=True, type=Path)
    parser.add_argument("--asset-root", required=True, type=Path)
    parser.add_argument("--git-executable", required=True, type=Path)
    parser.add_argument("--docker-executable", required=True, type=Path)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-report", required=True, type=Path)
    args = parser.parse_args()
    if not args.output_report.is_absolute():
        raise SystemExit("output report must be absolute")
    if not re.fullmatch(r"[0-9a-f]{40}", args.candidate_commit) or not SAFE_RUN_ID.fullmatch(args.run_id):
        raise SystemExit("invalid candidate or run identity")
    candidate = regular_directory(args.candidate_root, "candidate-root")
    upstream = regular_directory(args.upstream_root, "upstream-root")
    asset_root = regular_directory(args.asset_root, "asset-root")
    git = regular_absolute(args.git_executable, "git-executable")
    docker = regular_absolute(args.docker_executable, "docker-executable")
    report: dict[str, Any] = {
        "schema": "sipi.as-06-xspice-rfm-build-preflight.v2",
        "status": "blocked_external_build_preflight",
        "run_id": args.run_id,
        "os_nonce": secrets.token_hex(32),
        "candidate": {"commit": args.candidate_commit, "materialization": "candidate_clean_git_archive", "overlay_current_worktree": False},
        "upstream": {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE, "archive_sha256": UPSTREAM_ARCHIVE_SHA256, "materialization": "upstream_clean_git_archive"},
        "runner": {"path_redacted": True},
        "source_asset": {"expected_basename": SOURCE_BASENAME, "expected_sha256": NGSPICE_SOURCE_SHA256, "root_path_redacted": True},
        "build": {"attempted": False, "artifact_present": False},
        "non_claims": ["no_code_model_built", "no_ngspice_replay", "no_numeric_parity", "no_as06_row_closure", "no_release_promotion"],
    }
    blockers: list[str] = []
    with tempfile.TemporaryDirectory(prefix="sipi-as06-preflight-") as temp:
        temp_root = Path(temp)
        try:
            runner_initial = runner_snapshot()
        except OSError:
            runner_initial = {"bytes": 0, "sha256": None, "overflow": True}
            blockers.append("runner_initial_blocked")
        report["runner"]["initial"] = runner_initial
        try:
            pre_git = tool_identity(git)
            pre_docker = tool_identity(docker)
            pre_python = python_identity()
            tar_identity = tarfile_identity()
        except (OSError, ValueError, subprocess.SubprocessError):
            pre_git = blocked_identity()
            pre_docker = blocked_identity()
            pre_python = blocked_identity()
            tar_identity = blocked_identity()
            blockers.append("tool_identity_preflight_failed")
        observed_commit = git_revision(git, candidate, "HEAD")
        observed_tree = git_revision(git, candidate, "HEAD^{tree}")
        report["candidate"]["observed_commit"] = observed_commit
        report["candidate"]["observed_tree"] = observed_tree
        report["candidate"]["commit"] = observed_commit
        report["candidate"]["tree"] = observed_tree
        if observed_commit != args.candidate_commit:
            blockers.append("candidate_identity_mismatch")
        try:
            asset_pre = source_asset(asset_root)
            asset_mid = source_asset(asset_root)
            asset_post = source_asset(asset_root)
            asset = asset_post
        except OSError:
            asset_pre = asset_mid = asset = asset_post = {"basename": SOURCE_BASENAME, "present": False, "kind": "asset_root_error", "mismatch": False, "path_redacted": True, "file_count": 0, "total_bytes": 0, "single_bytes": None, "sha256": None, "wrong_file_count": 0, "other_entry_count": 0, "wrong_files": []}
            blockers.append("source_asset_blocked")
        report["source_asset"].update(asset)
        report["source_asset"]["pre_identity"] = asset_pre
        report["source_asset"]["mid_identity"] = asset_mid
        report["source_asset"]["post_identity"] = asset_post
        if asset["kind"] != "exact":
            blockers.append(f"source_asset_{asset['kind']}")
        asset_stable = asset_identity_stable(asset_pre, asset_mid, asset_post)
        report["source_asset"]["identity_stable"] = asset_stable
        if not asset_stable:
            blockers.append("source_asset_identity_drift")
        try:
            candidate_result = clean_archive(git, candidate, temp_root / "candidate", args.candidate_commit)
        except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError):
            candidate_result = {"bytes": 0, "sha256": None, "returncode": -1, "timeout": False, "overflow": False, "extracted": False, "extract_status": "typed_blocked"}
            blockers.append("candidate_archive_blocked")
        report["candidate"]["archive_observation"] = candidate_result
        report["candidate"]["archive_sha256"] = candidate_result["sha256"]
        candidate_source = temp_root / "candidate" / "source"
        try:
            report["candidate"]["runner_member"] = runtime_member_observation(candidate_source) if candidate_result["extracted"] else {"present": False, "match": False, "path_redacted": True}
        except OSError:
            report["candidate"]["runner_member"] = {"present": False, "match": False, "path_redacted": True}
            blockers.append("candidate_runner_member_blocked")
        if candidate_result["returncode"] != 0 or candidate_result["sha256"] is None:
            blockers.append("candidate_archive_failed")
        if not report["candidate"]["runner_member"].get("match", False):
            blockers.append("candidate_runner_member_mismatch")
        try:
            upstream_result = clean_archive(git, upstream, temp_root / "upstream", UPSTREAM_COMMIT)
        except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError):
            upstream_result = {"bytes": 0, "sha256": None, "returncode": -1, "timeout": False, "overflow": False, "extracted": False, "extract_status": "typed_blocked"}
            blockers.append("upstream_archive_blocked")
        observed_upstream_commit = git_revision(git, upstream, UPSTREAM_COMMIT)
        observed_upstream_tree = git_revision(git, upstream, f"{UPSTREAM_COMMIT}^{{tree}}")
        report["upstream"]["observed_commit"] = observed_upstream_commit
        report["upstream"]["observed_tree"] = observed_upstream_tree
        if observed_upstream_commit != UPSTREAM_COMMIT or observed_upstream_tree != UPSTREAM_TREE:
            blockers.append("upstream_revision_mismatch")
        report["upstream"]["archive_observation"] = upstream_result
        try:
            report["sources"] = archive_sources(temp_root / "upstream" / "source") if upstream_result["extracted"] else {}
        except OSError:
            report["sources"] = {}
            blockers.append("archive_source_read_blocked")
        if upstream_result["sha256"] != UPSTREAM_ARCHIVE_SHA256:
            blockers.append("upstream_archive_mismatch")
        if not upstream_result["extracted"]:
            blockers.append("upstream_archive_not_extracted")
        report["closure"] = {
            "dockerfile": report["sources"].get("poc/xspice-rfm/Dockerfile", {"status": "unknown", "reason": "not_observed"}),
            "agent_spice_license": report["sources"].get("LICENSE", {"status": "unknown", "reason": "not_observed"}),
            "ngspice_source": {"status": "source_exact_by_hash" if asset_stable and asset["kind"] == "exact" else "unknown", "reason": "not_observed" if not (asset_stable and asset["kind"] == "exact") else "caller_asset_hash_only", "path_redacted": True},
            "ngspice_license": {"status": "unknown", "reason": "not_inspected", "path_redacted": True},
        }
        if asset_stable and asset["kind"] == "exact":
            blockers.append("ngspice_license_not_inspected")
        try:
            docker_result = run_process(docker, ("info", "--format", "{{.ServerVersion}}"), MAX_OUTPUT_BYTES, COMMAND_TIMEOUT_SECONDS)
        except (OSError, ValueError, subprocess.SubprocessError):
            docker_result = PipeResult(-1, b"", b"", False, False)
            blockers.append("docker_info_blocked")
        docker_output = docker_result.stdout + docker_result.stderr
        report["docker"] = {"status": "docker_info_ok" if docker_result.returncode == 0 else "docker_info_failed", "exit_code": docker_result.returncode, "timeout": docker_result.timed_out, "output_bytes": len(docker_output), "output_sha256": digest_bytes(docker_output), "path_redacted": True}
        if docker_result.returncode != 0 or docker_result.timed_out or docker_result.overflowed:
            blockers.append("docker_info_failed")
        try:
            post_git = tool_identity(git)
            post_docker = tool_identity(docker)
            post_python = python_identity()
        except (OSError, ValueError, subprocess.SubprocessError):
            post_git = blocked_identity()
            post_docker = blocked_identity()
            post_python = blocked_identity()
            blockers.append("tool_identity_postflight_failed")
        try:
            runner_post = runner_snapshot()
        except OSError:
            runner_post = {"bytes": 0, "sha256": None, "overflow": True}
            blockers.append("runner_post_blocked")
        report["runner"]["post"] = runner_post
        member = report["candidate"].get("runner_member", {})
        report["runner"]["runtime"] = {"bytes": member.get("runtime_bytes"), "sha256": member.get("runtime_sha256"), "overflow": member.get("runtime_overflow", True)}
        report["runner"]["archive_member"] = {"bytes": member.get("member_bytes"), "sha256": member.get("member_sha256"), "overflow": member.get("member_overflow", True)}
        if not runner_identity_gate(runner_initial, member, runner_post):
            blockers.append("runner_identity_mismatch")
        report["toolchain"] = {"git_pre": pre_git, "git_post": post_git, "docker_pre": pre_docker, "docker_post": post_docker, "python_pre": pre_python, "python_post": post_python, "tarfile": tar_identity}
        if pre_git != post_git or pre_docker != post_docker or pre_python != post_python:
            blockers.append("tool_identity_drift")
        if any(not identity_valid(value) for value in (pre_git, post_git, pre_docker, post_docker, pre_python, post_python)):
            blockers.append("tool_identity_invalid")
        if tar_identity.get("file_sha256") is None:
            blockers.append("tarfile_identity_invalid")
    report["blockers"] = blockers
    report["ready_to_build"] = not blockers
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output_report.open("xb") as output:
            output.write((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    except FileExistsError as error:
        raise SystemExit("output report already exists") from error
    print("ready" if not blockers else "blocked")
    for blocker in blockers:
        print(f"- {blocker}")
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
