"""Run one immutable AS-03 power-wave solve replay.

The candidate is executed only through its committed focused test from a clean
Git archive.  The numeric comparator is a pinned scikit-rf leaf replay, not an
Agent-Spice yparam-path execution.  No source overlay, private probe, tolerance,
or S-parameter fit is admitted by this harness.
"""

from __future__ import annotations

import argparse
import hashlib
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
import threading
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CARGO = str(Path.home() / ".cargo/bin/cargo.exe") if os.name == "nt" else "cargo"
DEFAULT_RUSTC = str(Path.home() / ".cargo/bin/rustc.exe") if os.name == "nt" else "rustc"
LINKER_VERSION_ARGS = ("-flavor", "link", "--version") if os.name == "nt" else ("--version",)
PRODUCTION_COMMIT = "dadc9720d932f2e71886700d9112a12cd2a027d5"
PRODUCTION_TREE = "72c6888d9f5433abfb1523e774431231dcc86f5d"
EXPECTED_PREP_PARENT_COMMIT = "4042f0d9fdd0846e20ea95e8da7752812a4eea45"
UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
SKRF_COMMIT = "bd651e923cac6020de49a096e1d7e9b5f949f884"
SKRF_TREE = "e01dc798d1ba119357cc41e96802ac9aca83b9bc"
RUNNER_PATH = "tools/run_as_03_power_wave_solve_replay.py"
PREP_PATHS = (
    RUNNER_PATH,
    "tools/aggregate_as_03_power_wave_solve_replay.py",
    "tools/verify_as_03_power_wave_solve_replay.py",
    "tools/test_verify_as_03_power_wave_solve_replay.py",
)
FORMAL_PATHS = (
    "docs/baselines/as-03-power-wave-solve-replay-run-01.v1.json",
    "docs/baselines/as-03-power-wave-solve-replay-run-02.v1.json",
    "docs/baselines/as-03-power-wave-solve-replay-aggregate.v1.json",
    "docs/baselines/as-03-power-wave-solve-replay.v1.yaml",
    "docs/baselines/audits/2026-08-27-as-03-power-wave-solve-replay.md",
)
PRODUCTION_PATHS = (
    "crates/sipi-agent-spice-direct/src/as03_fit_yparam.rs",
    "crates/sipi-agent-spice-direct/NOTICE-SCIKIT-RF-AS-03-POWER-WAVE.txt",
    "docs/baselines/as-03-power-wave-solve-source-map.v1.yaml",
    "docs/baselines/as-03-numeric-checkpoint-run-01.json",
    "Cargo.lock",
    "rust-toolchain.toml",
)
UPSTREAM_PATHS = (
    "src/agent_spice/sparam/yparam.py",
    "pyproject.toml",
    "LICENSE",
)
SKRF_PATHS = (
    "skrf/network.py",
    "skrf/mathFunctions.py",
    "skrf/constants.py",
    "LICENSE.txt",
)
FIXTURE = b"# Hz S RI R 50\n1e6 0.01 0 0.8 0 0.8 0 0.01 0\n1e7 0.01 0 0.79 0 0.79 0 0.01 0\n1e8 0.01 0 0.7 0 0.7 0 0.01 0\n1e9 0.01 0 0.4 0 0.4 0 0.01 0\n"
FIXTURE_SHA256 = "4da06c257a0f0108e4391d65f894b6bb0d62a24a8f00f82f0f0734e061f5de70"
INDEPENDENT_PROBE = r'''use faer::{Mat,prelude::Solve};
use num_complex::Complex64 as C;
fn mul(a:&[C],b:&[C],n:usize)->Vec<C>{(0..n).flat_map(|i|(0..n).map(move|j|(0..n).map(|k|a[i*n+k]*b[k*n+j]).sum())).collect()}
fn main(){
 let n=2usize;let z0=50.0f64;
 let s=vec![C::new(0.01,0.0),C::new(0.8,0.0),C::new(0.8,0.0),C::new(0.01,0.0)];
 let g=vec![C::new(z0,0.0),C::new(0.0,0.0),C::new(0.0,0.0),C::new(z0,0.0)];
 let fv=1.0/(2.0*z0.sqrt());let f=vec![C::new(fv,0.0),C::new(0.0,0.0),C::new(0.0,0.0),C::new(fv,0.0)];
 let sg=mul(&s,&g,n);let sum=sg.iter().zip(g.iter()).map(|(l,r)|*l+r.conj()).collect::<Vec<_>>();let a=mul(&sum,&f,n);
 let id=vec![C::new(1.0,0.0),C::new(0.0,0.0),C::new(0.0,0.0),C::new(1.0,0.0)];
 let sub=id.iter().zip(s.iter()).map(|(l,r)|*l-*r).collect::<Vec<_>>();let b=mul(&sub,&f,n);
 let lhs=Mat::from_fn(n,n,|r,c|a[r*n+c]);let rhs=Mat::from_fn(n,n,|r,c|b[r*n+c]);let y=lhs.partial_piv_lu().solve(rhs.as_ref());
 print!("AS03_INDEPENDENT_COMPLEX_V1=[");for i in 0..4{if i>0{print!(",");}let v=y[(i/2,i%2)];print!("{{\"re_bits\":\"{:016x}\",\"im_bits\":\"{:016x}\"}}",v.re.to_bits(),v.im.to_bits());}println!("]");
}'''.encode("ascii")
BASELINE_PATH = "docs/baselines/as-03-numeric-checkpoint-run-01.json"
BASELINE_CANDIDATE_COMMIT = "a804c844d88b6189dba36c4abc41d7d4828d0e5c"
BASELINE_CANDIDATE_TREE = "4bdf6691d3aa40dde2ab0712eaf71fda9b181b3a"
SOURCE_PATH = "crates/sipi-agent-spice-direct/src/as03_fit_yparam.rs"
TEST_NAME = "as03_fit_yparam::tests::power_wave_solve_has_stable_fixed_line_checkpoint"
REPORT_SCHEMA = "sipi.as-03-power-wave-solve-replay.v1"
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOOL_BYTES = 128 * 1024 * 1024
MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_PROCESS_BYTES = 8 * 1024 * 1024
MAX_RUN_ID_BYTES = 128
READ_CHUNK = 64 * 1024
PYTHON_LINE_ENDING = b"\r\n" if os.name == "nt" else b"\n"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX16 = re.compile(r"[0-9a-f]{16}\Z")
_EXECUTION_SUPPORT: dict[Path, dict[str, str]] = {}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex(value: Any, pattern: re.Pattern[str]) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _exact_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{label} exact keys failed")
    return value


def _is_reparse(path: Path) -> bool:
    try:
        info = path.stat(follow_symlinks=False)
    except OSError:
        return True
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_nlink, info.st_mtime_ns, info.st_ctime_ns)


def _structural_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_nlink)


def _directory_identity(info: os.stat_result) -> tuple[int, int, int]:
    return (info.st_dev, info.st_ino, info.st_nlink)


def _read_regular(path: Path, maximum: int, *, require_nlink_one: bool = True) -> bytes:
    """Bounded single-handle read with pre/open/post identity checks."""
    if maximum <= 0:
        raise ValueError("read bound must be positive")
    entry_before = path.stat(follow_symlinks=False)
    if _is_reparse(path) or not stat.S_ISREG(entry_before.st_mode) or entry_before.st_nlink < 1:
        raise RuntimeError("file is not a regular nonlink")
    if require_nlink_one and entry_before.st_nlink != 1:
        raise RuntimeError("file must have nlink=1")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink < 1:
            raise RuntimeError("opened object is not regular")
        if require_nlink_one and opened.st_nlink != 1:
            raise RuntimeError("opened object must have nlink=1")
        if _structural_identity(entry_before) != _structural_identity(opened):
            raise RuntimeError("file changed before open")
        identity = _stat_identity(opened)
        if opened.st_size < 0 or opened.st_size > maximum:
            raise RuntimeError("file exceeds bound")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(READ_CHUNK, maximum - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > maximum:
                raise RuntimeError("file grew beyond bound")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        entry_after = path.stat(follow_symlinks=False)
        if (
            _stat_identity(after) != identity
            or _structural_identity(entry_after) != _structural_identity(after)
            or _is_reparse(path)
            or size != opened.st_size
        ):
            raise RuntimeError("file changed during read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _safe_relative(raw: str) -> Path:
    host, posix, windows = Path(raw), PurePosixPath(raw), PureWindowsPath(raw)
    if (
        not raw
        or "\0" in raw
        or host.is_absolute()
        or host.anchor
        or posix.is_absolute()
        or posix.anchor
        or windows.is_absolute()
        or windows.anchor
        or windows.drive
        or raw.startswith(("/", "\\"))
    ):
        raise RuntimeError("path must be relative")
    parts = [part for part in re.split(r"[\\/]", raw) if part not in ("", ".")]
    if not parts or ".." in parts:
        raise RuntimeError("path traversal is forbidden")
    return Path(*parts)


def _safe_directory(path: Path, *, must_exist: bool = True) -> Path:
    absolute = path.absolute()
    if absolute == Path(absolute.anchor) or not absolute.name or ".." in absolute.parts:
        raise RuntimeError("directory root is unsafe")
    if must_exist:
        resolved = absolute.resolve(strict=True)
        cursor = absolute
        while True:
            info = cursor.stat(follow_symlinks=False)
            if _is_reparse(cursor) or not stat.S_ISDIR(info.st_mode) or info.st_nlink < 1:
                raise RuntimeError("directory root has an unsafe ancestor")
            if cursor == Path(cursor.anchor):
                break
            cursor = cursor.parent
        return resolved
    parent = absolute.parent.resolve(strict=True)
    if _is_reparse(absolute.parent) or not parent.is_dir():
        raise RuntimeError("directory parent is unsafe")
    return absolute


def _require_disjoint_roots(named_roots: dict[str, Path]) -> None:
    items = list(named_roots.items())
    for index, (left_name, left) in enumerate(items):
        for right_name, right in items[index + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise RuntimeError(f"roots overlap: {left_name}/{right_name}")


def _fresh_child(root: Path, prefix: str) -> Path:
    root = _safe_directory(root)
    root_before = _directory_identity(root.stat(follow_symlinks=False))
    for _ in range(16):
        target = root / f"{prefix}-{secrets.token_hex(16)}"
        try:
            os.mkdir(target, 0o700)
        except FileExistsError:
            continue
        if _is_reparse(target) or not target.is_dir():
            raise RuntimeError("fresh directory custody failed")
        if _is_reparse(root) or _directory_identity(root.stat(follow_symlinks=False)) != root_before:
            raise RuntimeError("temp root changed during allocation")
        return target
    raise RuntimeError("fresh directory allocation exhausted")


def _create_file(path: Path, payload: bytes, maximum: int) -> dict[str, Any]:
    if len(payload) > maximum or os.path.lexists(path):
        raise RuntimeError("exclusive file payload/path invalid")
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    identity: tuple[int, int, int] | None = None
    complete = False
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or _is_reparse(path):
            raise RuntimeError("created file custody failed")
        identity = (before.st_dev, before.st_ino, before.st_nlink)
        view = memoryview(payload)
        written = 0
        while written < len(payload):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise RuntimeError("exclusive file write made no progress")
            written += count
        os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        readback = bytearray()
        while True:
            chunk = os.read(descriptor, min(READ_CHUNK, maximum - len(readback) + 1))
            if not chunk:
                break
            readback.extend(chunk)
            if len(readback) > maximum:
                raise RuntimeError("created file readback exceeds bound")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_nlink) != identity or after.st_size != len(payload) or bytes(readback) != payload:
            raise RuntimeError("created file readback drift")
        complete = True
    finally:
        os.close(descriptor)
        if not complete:
            try:
                current = path.stat(follow_symlinks=False)
                if identity is not None and (current.st_dev, current.st_ino, current.st_nlink) == identity:
                    path.unlink()
                elif path.exists():
                    raise RuntimeError("failed output cleanup identity gate")
            except FileNotFoundError:
                pass
            except OSError as error:
                raise RuntimeError("failed to clean incomplete exclusive file") from error
    try:
        if _read_regular(path, maximum) != payload:
            raise RuntimeError("published file readback drift")
    except BaseException as error:
        try:
            current = path.stat(follow_symlinks=False)
            if identity is None or (current.st_dev, current.st_ino, current.st_nlink) != identity:
                raise RuntimeError("published output cleanup identity gate failed")
            path.unlink()
        except OSError as cleanup_error:
            raise RuntimeError("failed to clean invalid published output") from cleanup_error
        raise error
    return {"basename": path.name, "bytes": len(payload), "sha256": _sha256(payload), "nlink": 1, "path_redacted": True}


def _write_json(path: Path, root: Path, value: Any) -> bytes:
    root = _safe_directory(root)
    target = path.absolute()
    if ".." in target.parts or target.parent.resolve(strict=True) != root or not target.name:
        raise RuntimeError("output must be a direct child of output root")
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2).encode("ascii") + b"\n"
    _create_file(target, payload, MAX_REPORT_BYTES)
    return payload


def _remove_fresh_tree(path: Path, parent: Path) -> None:
    resolved_parent = _safe_directory(parent)
    resolved = path.resolve(strict=True)
    if resolved.parent != resolved_parent or _is_reparse(path):
        raise RuntimeError("cleanup root custody failed")
    try:
        shutil.rmtree(resolved)
    except OSError as error:
        raise RuntimeError("fresh replay cleanup failed") from error
    if os.path.lexists(resolved):
        raise RuntimeError("fresh replay cleanup incomplete")


def _bounded_process(command: list[str], cwd: Path, env: dict[str, str], timeout: int, limit: int = MAX_PROCESS_BYTES) -> subprocess.CompletedProcess[bytes]:
    env = dict(env)
    support = _EXECUTION_SUPPORT.get(Path(command[0]).resolve(strict=True))
    if support is not None:
        env["PATH"] = support["source_parent"] + os.pathsep + env.get("PATH", "")
        if "git_exec_path" in support:
            env["GIT_EXEC_PATH"] = support["git_exec_path"]
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    buffers = [bytearray(), bytearray()]
    overflow: list[str] = []

    def drain(stream: Any, index: int, label: str) -> None:
        while True:
            chunk = stream.read(READ_CHUNK)
            if not chunk:
                return
            if len(buffers[index]) + len(chunk) > limit:
                overflow.append(label)
                process.kill()
                return
            buffers[index].extend(chunk)

    threads = [
        threading.Thread(target=drain, args=(process.stdout, 0, "stdout"), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, 1, "stderr"), daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.wait()
        raise RuntimeError("subprocess timed out") from error
    finally:
        for thread in threads:
            thread.join()
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
    if overflow:
        raise RuntimeError(f"subprocess {overflow[0]} exceeded bound")
    return subprocess.CompletedProcess(command, process.returncode, bytes(buffers[0]), bytes(buffers[1]))


def _resolve_tool(raw: str, role: str) -> Path:
    literal = Path(raw)
    if literal.is_file():
        found = literal
    else:
        located = shutil.which(raw)
        if located is None:
            raise RuntimeError(f"{role} executable not found")
        found = Path(located)
    resolved = found.resolve(strict=True)
    if os.name == "nt" and role == "git" and resolved.parent.name.casefold() == "cmd":
        direct = resolved.parent.parent / "mingw64/bin/git.exe"
        if direct.is_file():
            resolved = direct.resolve(strict=True)
    _read_regular(resolved, MAX_TOOL_BYTES, require_nlink_one=False)
    return resolved


def _stage_tool(source: Path, role: str, execution_root: Path) -> Path:
    role_root = _fresh_child(execution_root, role)
    copy = role_root / source.name
    payload = _read_regular(source, MAX_TOOL_BYTES, require_nlink_one=False)
    _create_file(copy, payload, MAX_TOOL_BYTES)
    copy.chmod(0o700)
    if _read_regular(copy, MAX_TOOL_BYTES) != payload:
        raise RuntimeError(f"{role} staged executable drift")
    support = {"source_parent": str(source.parent)}
    if os.name == "nt" and role == "git" and source.parent.name.casefold() == "bin" and source.parent.parent.name.casefold() == "mingw64":
        support["git_exec_path"] = str(source.parent.parent / "libexec/git-core")
    _EXECUTION_SUPPORT[copy.resolve(strict=True)] = support
    return copy


def _tool_snapshot(source: Path, copy: Path, role: str, version_args: tuple[str, ...]) -> dict[str, Any]:
    source_payload = _read_regular(source, MAX_TOOL_BYTES, require_nlink_one=False)
    copy_payload = _read_regular(copy, MAX_TOOL_BYTES)
    if source_payload != copy_payload or source.name != copy.name:
        raise RuntimeError(f"{role} source/copy drift")
    source_nlink = source.stat(follow_symlinks=False).st_nlink
    result = _bounded_process([str(copy), *version_args], ROOT, dict(os.environ), 60, 1024 * 1024)
    if result.returncode != 0:
        raise RuntimeError(f"{role} version command failed")
    return {
        "role": role,
        "basename": source.name,
        "source": {"bytes": len(source_payload), "nlink": source_nlink, "file_sha256": _sha256(source_payload), "path_redacted": True},
        "copy": {"bytes": len(copy_payload), "nlink": 1, "file_sha256": _sha256(copy_payload), "path_redacted": True},
        "version_args": list(version_args),
        "version_exit": 0,
        "version_sha256": _sha256(result.stdout + b"\0" + result.stderr),
        "path_redacted": True,
    }


def _linker_for(rustc: Path) -> tuple[Path, str]:
    version = _bounded_process([str(rustc), "-vV"], ROOT, dict(os.environ), 60, 1024 * 1024)
    if version.returncode != 0:
        raise RuntimeError("rustc host discovery failed")
    hosts = [line.split(":", 1)[1].strip() for line in version.stdout.decode("utf-8").splitlines() if line.startswith("host:")]
    if len(hosts) != 1:
        raise RuntimeError("rustc host identity malformed")
    host = hosts[0]
    if os.name == "nt":
        sysroot = _bounded_process([str(rustc), "--print", "sysroot"], ROOT, dict(os.environ), 60, 1024 * 1024)
        if sysroot.returncode != 0:
            raise RuntimeError("rustc sysroot discovery failed")
        path = Path(sysroot.stdout.decode("utf-8").strip()) / f"lib/rustlib/{host}/bin/rust-lld.exe"
        return _resolve_tool(str(path), "linker"), host
    return _resolve_tool("cc", "linker"), host


def _git(git: Path, repo: Path, *args: str, raw: bool = False, timeout: int = 300, raw_limit: int = MAX_ARCHIVE_BYTES) -> bytes | str:
    env = dict(os.environ)
    for key in tuple(env):
        if key in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"} or key.startswith("GIT_CONFIG_"):
            env.pop(key, None)
    result = _bounded_process([str(git), "-c", "core.autocrlf=false", "-C", str(repo), *args], repo, env, timeout, raw_limit if raw else 1024 * 1024)
    if result.returncode != 0:
        raise RuntimeError(f"git command failed: {' '.join(args[:2])}")
    return result.stdout if raw else result.stdout.decode("ascii").strip()


def _repo_identity(git: Path, repo: Path, commit: str, expected_tree: str | None = None) -> dict[str, str]:
    commit_value = str(_git(git, repo, "rev-parse", f"{commit}^{{commit}}"))
    tree = str(_git(git, repo, "rev-parse", f"{commit_value}^{{tree}}"))
    if not _hex(commit_value, HEX40) or not _hex(tree, HEX40) or (expected_tree and tree != expected_tree):
        raise RuntimeError("Git commit/tree identity drift")
    return {"commit": commit_value, "tree": tree}


def _git_exists(git: Path, repo: Path, expression: str) -> bool:
    env = dict(os.environ)
    for key in tuple(env):
        if key in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"} or key.startswith("GIT_CONFIG_"):
            env.pop(key, None)
    result = _bounded_process([str(git), "-c", "core.autocrlf=false", "-C", str(repo), "cat-file", "-e", expression], repo, env, 60, 1024 * 1024)
    return result.returncode == 0


def _prep_gate(git: Path, repo: Path, commit: str) -> dict[str, Any]:
    identity = _repo_identity(git, repo, commit)
    parents = str(_git(git, repo, "rev-list", "--parents", "-n", "1", identity["commit"])).split()
    if len(parents) != 2 or parents[0] != identity["commit"] or parents[1] != EXPECTED_PREP_PARENT_COMMIT:
        raise RuntimeError("prep must be a single-parent child of production")
    changed = tuple(sorted(line for line in str(_git(git, repo, "diff-tree", "--no-commit-id", "--name-only", "-r", parents[1], identity["commit"])).splitlines() if line))
    if changed != tuple(sorted(PREP_PATHS)):
        raise RuntimeError("prep commit must change exactly the four prep tools")
    for path in PREP_PATHS:
        if _git_exists(git, repo, f"{parents[1]}:{path}") or not _git_exists(git, repo, f"{identity['commit']}:{path}"):
            raise RuntimeError("prep tools must be first introduced by prep commit")
    for path in FORMAL_PATHS:
        if _git_exists(git, repo, f"{identity['commit']}:{path}"):
            raise RuntimeError("formal evidence must be absent from prep commit")
    return {**identity, "parent": parents[1], "changed_paths": list(changed), "first_introduction": True, "formal_artifacts_absent": True}


def _git_receipt(git: Path, repo: Path, commit: str, relative: str) -> dict[str, Any]:
    relative = _safe_relative(relative).as_posix()
    blob = str(_git(git, repo, "rev-parse", f"{commit}:{relative}"))
    payload = _git(git, repo, "cat-file", "blob", blob, raw=True, raw_limit=MAX_FILE_BYTES)
    assert isinstance(payload, bytes)
    if not payload or len(payload) > MAX_FILE_BYTES:
        raise RuntimeError("Git blob exceeds source bound")
    return {"path": relative, "git_blob": blob, "bytes": len(payload), "sha256": _sha256(payload)}


def _git_blob(git: Path, repo: Path, commit: str, relative: str) -> bytes:
    receipt = _git_receipt(git, repo, commit, relative)
    payload = _git(git, repo, "cat-file", "blob", receipt["git_blob"], raw=True, raw_limit=MAX_FILE_BYTES)
    assert isinstance(payload, bytes)
    return payload


def _live_receipt(path: Path, relative: str) -> dict[str, Any]:
    payload = _read_regular(path, MAX_FILE_BYTES)
    return {"path": relative, "bytes": len(payload), "sha256": _sha256(payload), "nlink": 1, "path_redacted": True}


def _source_binding(git: Path, repo: Path, commit: str, paths: tuple[str, ...], live_root: Path | None = None) -> dict[str, Any]:
    git_sources = [_git_receipt(git, repo, commit, path) for path in paths]
    if live_root is None:
        return {"git": git_sources}
    live = [_live_receipt(live_root / _safe_relative(path), path) for path in paths]
    for source, observed in zip(git_sources, live, strict=True):
        if (source["path"], source["bytes"], source["sha256"]) != (observed["path"], observed["bytes"], observed["sha256"]):
            raise RuntimeError(f"live source differs from raw Git blob: {source['path']}")
    return {"git": git_sources, "live": live}


def _archive(git: Path, repo: Path, commit: str, destination: Path) -> dict[str, Any]:
    payload = _git(git, repo, "archive", "--format=tar", commit, raw=True)
    assert isinstance(payload, bytes)
    if not payload or len(payload) > MAX_ARCHIVE_BYTES:
        raise RuntimeError("Git archive exceeds bound")
    os.mkdir(destination, 0o700)
    root = destination.resolve(strict=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        members = archive.getmembers()
        seen: set[str] = set()
        for member in members:
            pure = PurePosixPath(member.name)
            folded = member.name.casefold()
            if (
                not member.name
                or "\\" in member.name
                or pure.is_absolute()
                or ".." in pure.parts
                or ":" in pure.parts[0]
                or folded in seen
                or not (member.isdir() or member.isfile())
                or member.issym()
                or member.islnk()
            ):
                raise RuntimeError("unsafe Git archive member")
            seen.add(folded)
            target = destination.joinpath(*pure.parts)
            parent = target.parent.resolve(strict=False)
            if parent != root and root not in parent.parents:
                raise RuntimeError("Git archive member escaped root")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = archive.extractfile(member)
            if stream is None or member.size < 0 or member.size > MAX_MEMBER_BYTES:
                raise RuntimeError("Git archive member exceeds bound")
            content = stream.read(MAX_MEMBER_BYTES + 1)
            if len(content) != member.size or len(content) > MAX_MEMBER_BYTES:
                raise RuntimeError("Git archive member read drift")
            _create_file(target, content, MAX_MEMBER_BYTES)
            if member.mode & 0o111:
                target.chmod(0o700)
    return {"bytes": len(payload), "sha256": _sha256(payload), "links_rejected": True, "overlay": False}


def _summary(result: subprocess.CompletedProcess[bytes]) -> dict[str, Any]:
    return {
        "exit_code": result.returncode,
        "stdout_bytes": len(result.stdout),
        "stdout_sha256": _sha256(result.stdout),
        "stderr_bytes": len(result.stderr),
        "stderr_sha256": _sha256(result.stderr),
        "stream_limit_bytes": MAX_PROCESS_BYTES,
    }


def _candidate_real_assertions(source: bytes) -> list[str]:
    text = source.decode("utf-8", errors="strict")
    match = re.search(r"fn power_wave_solve_has_stable_fixed_line_checkpoint\(\) \{(?P<body>.*?)\n    \}", text, re.DOTALL)
    if match is None:
        raise RuntimeError("committed checkpoint test missing")
    rows = re.findall(r"assert_eq!\(y\[(\d)\]\.re\.to_bits\(\), 0x([0-9a-f_]+)\);", match.group("body"))
    if [int(index) for index, _ in rows] != [0, 1, 2, 3]:
        raise RuntimeError("committed checkpoint assertions drifted")
    return [bits.replace("_", "") for _, bits in rows]


def _independent_matrix(stdout: bytes) -> list[dict[str, str]]:
    prefix = "AS03_INDEPENDENT_COMPLEX_V1="
    lines = [line for line in stdout.decode("utf-8", errors="strict").splitlines() if line.startswith(prefix)]
    if len(lines) != 1:
        raise RuntimeError("independent complex checkpoint missing")
    value = json.loads(lines[0][len(prefix):])
    if type(value) is not list or len(value) != 4:
        raise RuntimeError("independent complex checkpoint shape drift")
    for cell in value:
        if type(cell) is not dict or set(cell) != {"re_bits", "im_bits"} or any(not _hex(cell[name], HEX16) for name in ("re_bits", "im_bits")):
            raise RuntimeError("independent complex checkpoint malformed")
    return value


def _independent_stdout(matrix: list[dict[str, str]]) -> bytes:
    ordered = [{"re_bits": cell["re_bits"], "im_bits": cell["im_bits"]} for cell in matrix]
    return b"AS03_INDEPENDENT_COMPLEX_V1=" + json.dumps(ordered, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n"


def _upstream_stdout(matrix: list[dict[str, str]], sources: dict[str, Any], modules: dict[str, Any]) -> bytes:
    value = {"matrix": matrix, "sources_pre": sources, "sources_post": sources, "modules_pre": modules, "modules_post": modules}
    return b"AS03_POWER_WAVE_V1=" + json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") + PYTHON_LINE_ENDING


def _one_artifact(directory: Path, pattern: str, label: str) -> Path:
    matches = [path for path in directory.glob(pattern) if path.is_file() and not _is_reparse(path)]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {label} artifact")
    return matches[0]


def _ordered(bits: str) -> int:
    raw = int(bits, 16)
    return (~raw & ((1 << 64) - 1)) if raw >> 63 else raw | (1 << 63)


def _difference(candidate: list[dict[str, str]], upstream: list[dict[str, str]]) -> dict[str, Any]:
    if len(candidate) != 4 or len(upstream) != 4:
        raise RuntimeError("matrix shape drift")
    rows: list[dict[str, Any]] = []
    for index, (left, right) in enumerate(zip(candidate, upstream, strict=True)):
        if type(left) is not dict or set(left) != {"re_bits", "im_bits"} or type(right) is not dict or set(right) != {"re_bits", "im_bits"}:
            raise RuntimeError("matrix cell shape drift")
        for component in ("re_bits", "im_bits"):
            if not _hex(left.get(component), HEX16) or not _hex(right.get(component), HEX16):
                raise RuntimeError("matrix component bits malformed")
            ulp = abs(_ordered(left[component]) - _ordered(right[component]))
            if ulp:
                rows.append({"row": index // 2, "column": index % 2, "component": component.removesuffix("_bits"), "candidate_bits": left[component], "upstream_bits": right[component], "ulp": ulp})
    return {"differing_components": len(rows), "max_ulp": max((row["ulp"] for row in rows), default=0), "differences": rows}


def _difference_real(candidate: list[str], upstream: list[str]) -> dict[str, Any]:
    if type(candidate) is not list or type(upstream) is not list or len(candidate) != 4 or len(upstream) != 4:
        raise RuntimeError("real checkpoint shape drift")
    rows: list[dict[str, Any]] = []
    for index, (left, right) in enumerate(zip(candidate, upstream, strict=True)):
        if not _hex(left, HEX16) or not _hex(right, HEX16):
            raise RuntimeError("real checkpoint bits malformed")
        ulp = abs(_ordered(left) - _ordered(right))
        if ulp:
            rows.append({"row": index // 2, "column": index % 2, "component": "re", "candidate_bits": left, "upstream_bits": right, "ulp": ulp})
    return {"differing_components": len(rows), "max_ulp": max((row["ulp"] for row in rows), default=0), "differences": rows}


def _dependency_inventory(metadata_stdout: bytes, candidate_root: Path, cargo_home: Path) -> dict[str, Any]:
    metadata = json.loads(metadata_stdout.decode("utf-8"))
    if type(metadata) is not dict or type(metadata.get("packages")) is not list or type(metadata.get("workspace_members")) is not list:
        raise RuntimeError("cargo metadata shape drift")
    workspace = set(metadata["workspace_members"])
    digest = hashlib.sha256()
    packages = 0
    files = 0
    total = 0
    roots: list[tuple[str, Path]] = []
    for package in metadata["packages"]:
        if type(package) is not dict or type(package.get("id")) is not str or type(package.get("name")) is not str or type(package.get("version")) is not str or type(package.get("manifest_path")) is not str or (package.get("source") is not None and type(package.get("source")) is not str):
            raise RuntimeError("cargo package metadata malformed")
        if package["id"] in workspace:
            continue
        manifest = Path(package["manifest_path"]).resolve(strict=True)
        package_root = manifest.parent
        in_candidate = package_root == candidate_root or candidate_root in package_root.parents
        in_cargo_home = package_root == cargo_home or cargo_home in package_root.parents
        if not in_candidate and not in_cargo_home:
            raise RuntimeError("locked dependency source escaped CARGO_HOME")
        relative_root = package_root.relative_to(candidate_root).as_posix() if in_candidate else package_root.relative_to(cargo_home).as_posix()
        package_key = "\0".join((package["name"], package["version"], package.get("source") or "candidate_archive", relative_root))
        roots.append((package_key, package_root))
    for package_id, package_root in sorted(roots, key=lambda item: item[0]):
        packages += 1
        digest.update(package_id.encode("utf-8") + b"\0")
        for path in sorted(package_root.rglob("*"), key=lambda value: value.as_posix()):
            info = path.stat(follow_symlinks=False)
            if _is_reparse(path):
                raise RuntimeError("dependency source contains reparse entry")
            if stat.S_ISDIR(info.st_mode):
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink < 1:
                raise RuntimeError("dependency source contains non-regular entry")
            payload = _read_regular(path, MAX_FILE_BYTES, require_nlink_one=False)
            relative = path.relative_to(package_root).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(8, "big") + relative + len(payload).to_bytes(8, "big") + hashlib.sha256(payload).digest())
            files += 1
            total += len(payload)
    return {"packages": packages, "files": files, "bytes": total, "sha256": digest.hexdigest(), "path_redacted": True}


def _baseline(payload: bytes) -> dict[str, Any]:
    value = json.loads(payload.decode("utf-8"))
    if value.get("schema") != "sipi.as-03-numeric-physical-checkpoint.v1" or value.get("status") != "blocked_numeric_semantics":
        raise RuntimeError("baseline evidence schema/status drift")
    checkpoint = value.get("checkpoint")
    if type(checkpoint) is not dict:
        raise RuntimeError("baseline checkpoint missing")
    candidate = checkpoint.get("candidate", {}).get("matrix")
    upstream = checkpoint.get("upstream", {}).get("matrix")
    if type(candidate) is not list or type(upstream) is not list:
        raise RuntimeError("baseline matrices missing")
    candidate_bits = [{"re_bits": cell["re_bits"], "im_bits": cell["im_bits"]} for cell in candidate]
    upstream_bits = [{"re_bits": cell["re_bits"], "im_bits": cell["im_bits"]} for cell in upstream]
    prior = _difference(candidate_bits, upstream_bits)
    if prior["differing_components"] != 4 or prior["max_ulp"] != 4:
        raise RuntimeError("baseline 4-cell/4-ULP fact drift")
    if value["candidate"]["commit"] != BASELINE_CANDIDATE_COMMIT or value["candidate"]["tree"] != BASELINE_CANDIDATE_TREE:
        raise RuntimeError("baseline candidate identity drift")
    return {
        "schema": value["schema"],
        "status": value["status"],
        "candidate_commit": value["candidate"]["commit"],
        "candidate_tree": value["candidate"]["tree"],
        "candidate_matrix": candidate_bits,
        "upstream_matrix": upstream_bits,
        "prior_difference": prior,
    }


PYTHON_PROBE = r'''import hashlib,json,pathlib,struct,sys
skrf_root=pathlib.Path(sys.argv[1]).resolve(strict=True)
fixture=pathlib.Path(sys.argv[2]).resolve(strict=True)
python_root=pathlib.Path(sys.argv[3]).resolve(strict=True)
site_packages=pathlib.Path(sys.argv[4]).resolve(strict=True)
site_packages.relative_to(python_root)
sys.path.insert(0,str(site_packages))
sys.path.insert(0,str(skrf_root))
import numpy as np
import numpy.linalg._umath_linalg as umath
import scipy
import skrf
import skrf.constants,skrf.mathFunctions,skrf.network
def bits(value): return struct.pack(">d",float(value)).hex()
def fact(module,root,root_role,source=False):
 p=pathlib.Path(module.__file__).resolve(strict=True)
 try: rel=p.relative_to(root).as_posix()
 except ValueError: raise RuntimeError("runtime module escaped admitted root")
 item={"basename":p.name,"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"version":getattr(module,"__version__",None),"path_redacted":True,"relative_path":rel,"root_role":root_role,"root_contained":True}
 return item
def inventory(): return {"numpy":fact(np,python_root,"python_environment"),"scipy":fact(scipy,python_root,"python_environment"),"numpy_linalg":fact(umath,python_root,"python_environment"),"skrf":fact(skrf,skrf_root,"scikit_rf_archive")}
def sources(): return {name:fact(module,skrf_root,"scikit_rf_archive",True) for name,module in (("network",skrf.network),("mathFunctions",skrf.mathFunctions),("constants",skrf.constants))}
modules_pre=inventory();sources_pre=sources()
n=skrf.Network(str(fixture));y=n.y[0]
matrix=[{"re_bits":bits(v.real),"im_bits":bits(v.imag)} for v in y.reshape(-1)]
modules_post=inventory();sources_post=sources()
if modules_pre != modules_post or sources_pre != sources_post: raise RuntimeError("module/source drift in probe")
sources=sources_pre
print("AS03_POWER_WAVE_V1="+json.dumps({"matrix":matrix,"sources_pre":sources_pre,"sources_post":sources_post,"modules_pre":modules_pre,"modules_post":modules_post},sort_keys=True,separators=(",",":")))'''


def _python_result(stdout: bytes) -> dict[str, Any]:
    prefix = "AS03_POWER_WAVE_V1="
    lines = [line for line in stdout.decode("utf-8", errors="strict").splitlines() if line.startswith(prefix)]
    if len(lines) != 1:
        raise RuntimeError("upstream marker missing or ambiguous")
    value = json.loads(lines[0][len(prefix):])
    _exact_keys(value, {"matrix", "sources_pre", "sources_post", "modules_pre", "modules_post"}, "upstream payload")
    if type(value["matrix"]) is not list or len(value["matrix"]) != 4:
        raise RuntimeError("upstream matrix malformed")
    if value["sources_pre"] != value["sources_post"] or value["modules_pre"] != value["modules_post"]:
        raise RuntimeError("upstream in-process module/source drift")
    return value


def _validate_receipt(value: Any, label: str, *, git_blob: bool = False) -> None:
    keys = {"path", "bytes", "sha256", "git_blob"} if git_blob else {"path", "bytes", "sha256", "nlink", "path_redacted"}
    item = _exact_keys(value, keys, label)
    if type(item["path"]) is not str or type(item["bytes"]) is not int or item["bytes"] <= 0 or not _hex(item["sha256"], HEX64):
        raise ValueError(f"{label} receipt malformed")
    if git_blob and not _hex(item["git_blob"], HEX40):
        raise ValueError(f"{label} blob malformed")
    if not git_blob and (type(item["nlink"]) is not int or item["nlink"] != 1 or item["path_redacted"] is not True):
        raise ValueError(f"{label} live custody malformed")


def _validate_receipts(values: Any, paths: tuple[str, ...], label: str, *, git_blob: bool) -> None:
    if type(values) is not list or len(values) != len(paths):
        raise ValueError(f"{label} receipt count drift")
    for index, (receipt, path) in enumerate(zip(values, paths, strict=True)):
        _validate_receipt(receipt, f"{label}[{index}]", git_blob=git_blob)
        if receipt["path"] != path:
            raise ValueError(f"{label} receipt path drift")


def _validate_archive(value: Any, label: str) -> None:
    item = _exact_keys(value, {"bytes", "sha256", "links_rejected", "overlay"}, label)
    if type(item["bytes"]) is not int or item["bytes"] <= 0 or item["bytes"] > MAX_ARCHIVE_BYTES or not _hex(item["sha256"], HEX64) or item["links_rejected"] is not True or item["overlay"] is not False:
        raise ValueError(f"{label} archive malformed")


def _validate_summary(value: Any, label: str) -> None:
    item = _exact_keys(value, {"exit_code", "stdout_bytes", "stdout_sha256", "stderr_bytes", "stderr_sha256", "stream_limit_bytes"}, label)
    if type(item["exit_code"]) is not int or item["exit_code"] != 0 or type(item["stream_limit_bytes"]) is not int or item["stream_limit_bytes"] != MAX_PROCESS_BYTES:
        raise ValueError(f"{label} execution status drift")
    for name in ("stdout", "stderr"):
        if type(item[f"{name}_bytes"]) is not int or item[f"{name}_bytes"] < 0 or item[f"{name}_bytes"] > MAX_PROCESS_BYTES or not _hex(item[f"{name}_sha256"], HEX64):
            raise ValueError(f"{label} stream receipt malformed")


def _validate_difference_receipt(value: Any, label: str) -> dict[str, Any]:
    item = _exact_keys(value, {"differing_components", "max_ulp", "differences"}, label)
    if type(item["differing_components"]) is not int or item["differing_components"] < 0 or type(item["max_ulp"]) is not int or item["max_ulp"] < 0 or type(item["differences"]) is not list or len(item["differences"]) != item["differing_components"]:
        raise ValueError(f"{label} numeric types drift")
    coordinates: set[tuple[int, int, str]] = set()
    for index, raw in enumerate(item["differences"]):
        row = _exact_keys(raw, {"row", "column", "component", "candidate_bits", "upstream_bits", "ulp"}, f"{label}.differences[{index}]")
        if type(row["row"]) is not int or type(row["column"]) is not int or row["row"] not in (0, 1) or row["column"] not in (0, 1) or row["component"] not in ("re", "im") or not _hex(row["candidate_bits"], HEX16) or not _hex(row["upstream_bits"], HEX16) or type(row["ulp"]) is not int or row["ulp"] <= 0:
            raise ValueError(f"{label} difference row malformed")
        coordinate = (row["row"], row["column"], row["component"])
        if coordinate in coordinates:
            raise ValueError(f"{label} difference coordinates repeat")
        coordinates.add(coordinate)
    if item["max_ulp"] != max((row["ulp"] for row in item["differences"]), default=0):
        raise ValueError(f"{label} max ULP drift")
    return item


def validate_report(value: Any) -> dict[str, Any]:
    root = _exact_keys(value, {"schema", "status", "work_item", "run_id", "nonce", "prep", "candidate", "baseline", "upstream", "scikit_rf", "toolchain", "fixture", "execution", "numeric_change", "blockers", "claims", "non_claims"}, "report")
    if root["schema"] != REPORT_SCHEMA or root["status"] != "blocked_numeric_semantics" or root["work_item"] != "AS-03":
        raise ValueError("report identity gate failed")
    if type(root["run_id"]) is not str or re.fullmatch(r"[A-Za-z0-9._-]{1,128}", root["run_id"]) is None or not _hex(root["nonce"], HEX64):
        raise ValueError("report run identity malformed")
    prep = _exact_keys(root["prep"], {"commit", "tree", "parent", "changed_paths", "first_introduction", "formal_artifacts_absent", "sources", "live_pre", "live_post", "stable"}, "prep")
    if not _hex(prep["commit"], HEX40) or not _hex(prep["tree"], HEX40) or prep["parent"] != EXPECTED_PREP_PARENT_COMMIT or prep["changed_paths"] != sorted(PREP_PATHS) or prep["first_introduction"] is not True or prep["formal_artifacts_absent"] is not True or prep["stable"] is not True or prep["live_pre"] != prep["live_post"]:
        raise ValueError("prep gate failed")
    _validate_receipts(prep["sources"], PREP_PATHS, "prep.sources", git_blob=True)
    _validate_receipts(prep["live_pre"], PREP_PATHS, "prep.live_pre", git_blob=False)
    _validate_receipts(prep["live_post"], PREP_PATHS, "prep.live_post", git_blob=False)
    candidate = _exact_keys(root["candidate"], {"commit", "tree", "archive", "sources", "live_pre", "live_post", "archive_pre", "archive_post", "archive_stable", "binary_pre", "binary_post", "binary_stable", "dependency_inventory_pre", "dependency_inventory_post", "dependency_inventory_stable", "compiled_inputs_pre", "compiled_inputs_post", "compiled_inputs_stable", "stable"}, "candidate")
    if candidate["commit"] != PRODUCTION_COMMIT or candidate["tree"] != PRODUCTION_TREE or candidate["stable"] is not True or candidate["live_pre"] != candidate["live_post"] or candidate["archive_stable"] is not True or candidate["archive_pre"] != candidate["archive_post"] or candidate["binary_stable"] is not True or candidate["binary_pre"] != candidate["binary_post"] or candidate["dependency_inventory_stable"] is not True or candidate["dependency_inventory_pre"] != candidate["dependency_inventory_post"] or candidate["compiled_inputs_stable"] is not True or candidate["compiled_inputs_pre"] != candidate["compiled_inputs_post"]:
        raise ValueError("candidate identity/stability gate failed")
    _validate_archive(candidate["archive"], "candidate.archive")
    _validate_receipts(candidate["sources"], PRODUCTION_PATHS, "candidate.sources", git_blob=True)
    _validate_receipts(candidate["live_pre"], PRODUCTION_PATHS, "candidate.live_pre", git_blob=False)
    _validate_receipts(candidate["live_post"], PRODUCTION_PATHS, "candidate.live_post", git_blob=False)
    archive_paths = (SOURCE_PATH, "Cargo.lock", "rust-toolchain.toml")
    _validate_receipts(candidate["archive_pre"], archive_paths, "candidate.archive_pre", git_blob=False)
    _validate_receipts(candidate["archive_post"], archive_paths, "candidate.archive_post", git_blob=False)
    for label in ("binary_pre", "binary_post"):
        item = _exact_keys(candidate[label], {"path", "bytes", "sha256", "nlink", "path_redacted"}, f"candidate.{label}")
        if type(item["path"]) is not str or "/" in item["path"] or "\\" in item["path"] or type(item["bytes"]) is not int or item["bytes"] <= 0 or not _hex(item["sha256"], HEX64) or type(item["nlink"]) is not int or item["nlink"] != 1 or item["path_redacted"] is not True:
            raise ValueError("candidate binary custody malformed")
    for label in ("dependency_inventory_pre", "dependency_inventory_post"):
        item = _exact_keys(candidate[label], {"packages", "files", "bytes", "sha256", "path_redacted"}, f"candidate.{label}")
        if type(item["packages"]) is not int or item["packages"] <= 0 or type(item["files"]) is not int or item["files"] <= 0 or type(item["bytes"]) is not int or item["bytes"] <= 0 or not _hex(item["sha256"], HEX64) or item["path_redacted"] is not True:
            raise ValueError("dependency inventory malformed")
    for label in ("compiled_inputs_pre", "compiled_inputs_post"):
        _validate_receipts(candidate[label], tuple(item["path"] for item in candidate[label]), f"candidate.{label}", git_blob=False)
        if len(candidate[label]) != 2 or any("/" in item["path"] or "\\" in item["path"] for item in candidate[label]):
            raise ValueError("compiled input inventory malformed")
    baseline = _exact_keys(root["baseline"], {"path", "git_blob", "bytes", "sha256", "schema", "status", "candidate_commit", "candidate_tree", "candidate_matrix", "upstream_matrix", "prior_difference"}, "baseline")
    _validate_receipt({key: baseline[key] for key in ("path", "git_blob", "bytes", "sha256")}, "baseline.receipt", git_blob=True)
    prior = _validate_difference_receipt(baseline["prior_difference"], "baseline.prior_difference")
    if baseline["path"] != BASELINE_PATH or baseline["schema"] != "sipi.as-03-numeric-physical-checkpoint.v1" or baseline["status"] != "blocked_numeric_semantics" or baseline["candidate_commit"] != BASELINE_CANDIDATE_COMMIT or baseline["candidate_tree"] != BASELINE_CANDIDATE_TREE:
        raise ValueError("baseline immutable anchor drift")
    if prior != _difference(baseline["candidate_matrix"], baseline["upstream_matrix"]) or prior["differing_components"] != 4 or prior["max_ulp"] != 4:
        raise ValueError("baseline numeric fact drift")
    for key, commit, tree, paths in (("upstream", UPSTREAM_COMMIT, UPSTREAM_TREE, UPSTREAM_PATHS), ("scikit_rf", SKRF_COMMIT, SKRF_TREE, SKRF_PATHS)):
        keys = {"commit", "tree", "archive", "sources", "executed_sources_pre", "executed_sources_post", "executed_sources_stable"} if key == "scikit_rf" else {"commit", "tree", "archive", "sources"}
        item = _exact_keys(root[key], keys, key)
        if item["commit"] != commit or item["tree"] != tree:
            raise ValueError(f"{key} identity gate failed")
        _validate_archive(item["archive"], f"{key}.archive")
        _validate_receipts(item["sources"], paths, f"{key}.sources", git_blob=True)
        if key == "scikit_rf":
            if item["executed_sources_stable"] is not True or item["executed_sources_pre"] != item["executed_sources_post"] or type(item["executed_sources_pre"]) is not dict or set(item["executed_sources_pre"]) != {"network", "mathFunctions", "constants"}:
                raise ValueError("executed scikit-rf source stability drift")
            for name, raw in item["executed_sources_pre"].items():
                source = _exact_keys(raw, {"basename", "bytes", "sha256", "version", "path_redacted", "relative_path", "root_role", "root_contained"}, f"scikit_rf.executed.{name}")
                expected_path = f"skrf/{name}.py"
                if source["relative_path"] != expected_path or source["root_role"] != "scikit_rf_archive" or source["basename"] != f"{name}.py" or type(source["bytes"]) is not int or source["bytes"] <= 0 or not _hex(source["sha256"], HEX64) or source["path_redacted"] is not True or source["root_contained"] is not True:
                    raise ValueError("executed scikit-rf source receipt malformed")
                raw_source = next((receipt for receipt in item["sources"] if receipt["path"] == expected_path), None)
                if raw_source is None or (source["bytes"], source["sha256"]) != (raw_source["bytes"], raw_source["sha256"]):
                    raise ValueError("executed scikit-rf source differs from raw Git source")
    toolchain = _exact_keys(root["toolchain"], {"pre", "post", "stable", "modules_pre", "modules_post", "modules_stable", "timeout_seconds", "environment"}, "toolchain")
    if toolchain["stable"] is not True or toolchain["pre"] != toolchain["post"] or toolchain["modules_stable"] is not True or toolchain["modules_pre"] != toolchain["modules_post"]:
        raise ValueError("toolchain drift")
    if set(toolchain["pre"]) != {"git", "cargo", "rustc", "python", "linker"} or type(toolchain["timeout_seconds"]) is not int or toolchain["timeout_seconds"] <= 0:
        raise ValueError("toolchain shape drift")
    for role, identity in toolchain["pre"].items():
        item = _exact_keys(identity, {"role", "basename", "source", "copy", "version_args", "version_exit", "version_sha256", "path_redacted"}, f"toolchain.{role}")
        source = _exact_keys(item["source"], {"bytes", "nlink", "file_sha256", "path_redacted"}, f"toolchain.{role}.source")
        copy = _exact_keys(item["copy"], {"bytes", "nlink", "file_sha256", "path_redacted"}, f"toolchain.{role}.copy")
        if item["role"] != role or type(item["basename"]) is not str or not item["basename"] or type(source["bytes"]) is not int or source["bytes"] <= 0 or type(source["nlink"]) is not int or source["nlink"] < 1 or copy != {"bytes": source["bytes"], "nlink": 1, "file_sha256": source["file_sha256"], "path_redacted": True} or not _hex(source["file_sha256"], HEX64) or not _hex(item["version_sha256"], HEX64) or type(item["version_exit"]) is not int or item["version_exit"] != 0 or source["path_redacted"] is not True or item["path_redacted"] is not True:
            raise ValueError("toolchain identity malformed")
    modules = {"numpy", "numpy_linalg", "scipy", "skrf"}
    if type(toolchain["modules_pre"]) is not dict or set(toolchain["modules_pre"]) != modules:
        raise ValueError("toolchain module shape drift")
    for name, raw in toolchain["modules_pre"].items():
        item = _exact_keys(raw, {"basename", "bytes", "sha256", "version", "path_redacted", "relative_path", "root_role", "root_contained"}, f"toolchain.modules.{name}")
        expected_role = "scikit_rf_archive" if name == "skrf" else "python_environment"
        if type(item["basename"]) is not str or not item["basename"] or type(item["relative_path"]) is not str or not item["relative_path"] or item["root_role"] != expected_role or item["root_contained"] is not True or type(item["bytes"]) is not int or item["bytes"] <= 0 or not _hex(item["sha256"], HEX64) or item["path_redacted"] is not True or (item["version"] is not None and type(item["version"]) is not str):
            raise ValueError("toolchain module identity malformed")
    environment = _exact_keys(toolchain["environment"], {"cargo_home_explicit", "cargo_home_path_redacted", "cargo_net_offline", "cargo_locked", "cargo_incremental", "cargo_profile", "target_root_fresh", "rustc_explicit", "linker_explicit", "rust_host", "wrappers_cleared", "paths_redacted"}, "toolchain.environment")
    if environment["cargo_home_explicit"] is not True or environment["cargo_home_path_redacted"] is not True or environment["cargo_net_offline"] is not True or environment["cargo_locked"] is not True or environment["cargo_incremental"] is not False or environment["cargo_profile"] != "test" or environment["target_root_fresh"] is not True or environment["rustc_explicit"] is not True or environment["linker_explicit"] is not True or type(environment["rust_host"]) is not str or not environment["rust_host"] or environment["wrappers_cleared"] is not True or environment["paths_redacted"] is not True:
        raise ValueError("toolchain environment drift")
    fixture = _exact_keys(root["fixture"], {"kind", "bytes", "sha256", "created"}, "fixture")
    if fixture["kind"] != "fixed_touchstone_line_s2p_v1" or fixture["bytes"] != len(FIXTURE) or fixture["sha256"] != FIXTURE_SHA256:
        raise ValueError("fixture gate failed")
    created = _exact_keys(fixture["created"], {"basename", "bytes", "sha256", "nlink", "path_redacted"}, "fixture.created")
    if created != {"basename": "fixture.s2p", "bytes": len(FIXTURE), "sha256": FIXTURE_SHA256, "nlink": 1, "path_redacted": True}:
        raise ValueError("fixture physical custody drift")
    execution = _exact_keys(root["execution"], {"cargo_metadata", "candidate_build", "candidate_test", "scikit_rf_leaf_probe", "independent_probe_build", "independent_probe", "candidate_test_name", "private_probe_injection", "independent_probe_not_production_runtime", "agent_spice_yparam_path_executed"}, "execution")
    for label in ("cargo_metadata", "candidate_build", "candidate_test", "scikit_rf_leaf_probe", "independent_probe_build", "independent_probe"):
        _validate_summary(execution[label], f"execution.{label}")
    if execution["candidate_test_name"] != TEST_NAME or execution["private_probe_injection"] is not False or execution["independent_probe_not_production_runtime"] is not True or execution["agent_spice_yparam_path_executed"] is not False:
        raise ValueError("execution gate failed")
    numeric = _exact_keys(root["numeric_change"], {"prior", "current", "differing_components_change", "max_ulp_change", "first_cell_exact", "numeric_parity", "blocked_numeric_semantics"}, "numeric_change")
    current = _exact_keys(numeric["current"], {"differing_components", "max_ulp", "differences", "committed_asserted_real_bits", "upstream_real_bits", "upstream_complex_matrix", "independent_complex_diagnostic"}, "numeric_change.current")
    _validate_difference_receipt({key: current[key] for key in ("differing_components", "max_ulp", "differences")}, "numeric_change.current")
    recomputed = _difference_real(current["committed_asserted_real_bits"], current["upstream_real_bits"])
    for matrix_name in ("upstream_complex_matrix", "independent_complex_diagnostic"):
        matrix = current[matrix_name]
        if type(matrix) is not list or len(matrix) != 4 or any(type(cell) is not dict or set(cell) != {"re_bits", "im_bits"} or any(not _hex(cell[key], HEX16) for key in ("re_bits", "im_bits")) for cell in matrix):
            raise ValueError("diagnostic complex matrix malformed")
    if current["upstream_real_bits"] != [cell["re_bits"] for cell in current["upstream_complex_matrix"]] or [cell["re_bits"] for cell in current["independent_complex_diagnostic"]] != current["committed_asserted_real_bits"] or {key: current[key] for key in ("differing_components", "max_ulp", "differences")} != recomputed or numeric["prior"] != {"differing_components": 4, "max_ulp": 4} or current["differing_components"] != 3 or current["max_ulp"] != 1 or numeric["differing_components_change"] != "4_to_3" or numeric["max_ulp_change"] != "4_to_1" or numeric["first_cell_exact"] is not True or current["committed_asserted_real_bits"][0] != current["upstream_real_bits"][0] or numeric["numeric_parity"] is not False or numeric["blocked_numeric_semantics"] is not True:
        raise ValueError("numeric result gate failed")
    independent_stdout = _independent_stdout(current["independent_complex_diagnostic"])
    upstream_stdout = _upstream_stdout(current["upstream_complex_matrix"], root["scikit_rf"]["executed_sources_pre"], toolchain["modules_pre"])
    if execution["independent_probe"]["stdout_bytes"] != len(independent_stdout) or execution["independent_probe"]["stdout_sha256"] != _sha256(independent_stdout) or execution["scikit_rf_leaf_probe"]["stdout_bytes"] != len(upstream_stdout) or execution["scikit_rf_leaf_probe"]["stdout_sha256"] != _sha256(upstream_stdout):
        raise ValueError("checkpoint payload/execution cross-binding drift")
    if root["blockers"] != ["blocked_numeric_semantics"]:
        raise ValueError("blocker drift")
    claims = _exact_keys(root["claims"], {"clean_production_archive_execution", "committed_test_execution", "committed_real_checkpoint", "pinned_scikit_rf_leaf_execution", "agent_spice_source_replay", "complete_complex_checkpoint", "private_probe_injection", "numeric_parity", "s_parameter_fit"}, "claims")
    if claims != {"clean_production_archive_execution": True, "committed_test_execution": True, "committed_real_checkpoint": True, "pinned_scikit_rf_leaf_execution": True, "agent_spice_source_replay": False, "complete_complex_checkpoint": False, "private_probe_injection": False, "numeric_parity": False, "s_parameter_fit": False}:
        raise ValueError("claim drift")
    if root["non_claims"] != ["candidate_complete_complex_checkpoint", "independent_probe_is_production_runtime", "agent_spice_yparam_path_execution", "numeric_parity", "acceptance_tolerance", "general_nudge_eig_equivalence", "s_parameter_fit", "AS-05_Xyce_XDM", "release_acceptance"]:
        raise ValueError("non-claims drift")
    return root


def run(args: argparse.Namespace) -> dict[str, Any]:
    repository = _safe_directory(Path(args.repository))
    upstream_repo = _safe_directory(Path(args.upstream_repository))
    skrf_repo = _safe_directory(Path(args.scikit_rf_repository))
    temp_root = _safe_directory(Path(args.temp_root))
    output_root = _safe_directory(Path(args.output_root))
    _require_disjoint_roots({"repository": repository, "agent_spice": upstream_repo, "scikit_rf": skrf_repo, "temp": temp_root, "output": output_root})
    output = Path(args.output).absolute()
    if output.parent.resolve(strict=True) != output_root:
        raise RuntimeError("output must be directly under output root")
    nonce = secrets.token_hex(32)
    if type(args.run_id) is not str or re.fullmatch(r"[A-Za-z0-9._-]{1,128}", args.run_id) is None or len(args.run_id.encode("ascii")) > MAX_RUN_ID_BYTES:
        raise RuntimeError("run-id must be bounded path-free ASCII")
    root = _fresh_child(temp_root, "as03-power-wave")
    execution_root = _fresh_child(root, "exec")
    source_tools = {
        "git": _resolve_tool(args.git, "git"),
        "cargo": _resolve_tool(args.cargo, "cargo"),
        "rustc": _resolve_tool(args.rustc, "rustc"),
        "python": _resolve_tool(args.python, "python"),
    }
    tools = {role: _stage_tool(path, role, execution_root) for role, path in source_tools.items()}
    source_tools["linker"], rust_host = _linker_for(tools["rustc"])
    tools["linker"] = _stage_tool(source_tools["linker"], "linker", execution_root)
    versions = {"git": ("--version",), "cargo": ("-Vv",), "rustc": ("-vV",), "python": ("--version",), "linker": LINKER_VERSION_ARGS}
    tool_pre = {role: _tool_snapshot(source_tools[role], path, role, versions[role]) for role, path in tools.items()}
    prep = _prep_gate(tools["git"], repository, args.prep_commit)
    parent = prep["parent"]
    production = _repo_identity(tools["git"], repository, PRODUCTION_COMMIT, PRODUCTION_TREE)
    upstream = _repo_identity(tools["git"], upstream_repo, UPSTREAM_COMMIT, UPSTREAM_TREE)
    skrf = _repo_identity(tools["git"], skrf_repo, SKRF_COMMIT, SKRF_TREE)
    prep_sources = _source_binding(tools["git"], repository, prep["commit"], PREP_PATHS, repository)
    candidate_sources = _source_binding(tools["git"], repository, production["commit"], PRODUCTION_PATHS, repository)
    prep_live_pre = prep_sources["live"]
    candidate_live_pre = candidate_sources["live"]
    candidate_root, upstream_root, skrf_root = root / "candidate", root / "upstream", root / "scikit-rf"
    candidate_archive = _archive(tools["git"], repository, production["commit"], candidate_root)
    upstream_archive = _archive(tools["git"], upstream_repo, upstream["commit"], upstream_root)
    skrf_archive = _archive(tools["git"], skrf_repo, skrf["commit"], skrf_root)
    fixture = root / "fixture.s2p"
    fixture_created = _create_file(fixture, FIXTURE, len(FIXTURE))
    target = root / "target"
    target.mkdir()
    archive_paths = (SOURCE_PATH, "Cargo.lock", "rust-toolchain.toml")
    archive_pre = [_live_receipt(candidate_root / _safe_relative(path), path) for path in archive_paths]
    cargo_home = _safe_directory(Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")))
    env = dict(os.environ)
    for key in tuple(env):
        upper = key.upper()
        if upper.startswith(("CARGO", "RUST", "RUSTDOC")) or upper in {"CC", "CXX", "AR", "CFLAGS", "CXXFLAGS"} or upper.startswith(("CC_", "CXX_", "AR_", "CFLAGS_", "CXXFLAGS_")) or upper.endswith(("_LINKER", "_RUSTFLAGS")):
            env.pop(key, None)
    linker_env = f"CARGO_TARGET_{rust_host.upper().replace('-', '_')}_LINKER"
    env.update({"RUSTC": str(tools["rustc"]), "CARGO_HOME": str(cargo_home), "CARGO_TARGET_DIR": str(target), "CARGO_NET_OFFLINE": "true", "CARGO_INCREMENTAL": "0", "CARGO_PROFILE_TEST_INCREMENTAL": "false", "CARGO_PROFILE_TEST_DEBUG": "0", linker_env: str(tools["linker"])})
    manifest = candidate_root / "crates/sipi-agent-spice-direct/Cargo.toml"
    metadata_result = _bounded_process([
        str(tools["cargo"]), "metadata", "--locked", "--offline", "--format-version", "1", "--manifest-path", str(manifest),
    ], candidate_root, env, args.timeout_seconds, MAX_PROCESS_BYTES)
    if metadata_result.returncode != 0:
        raise RuntimeError("locked offline cargo metadata failed")
    dependency_inventory_pre = _dependency_inventory(metadata_result.stdout, candidate_root, cargo_home)
    build_result = _bounded_process([
        str(tools["cargo"]), "test", "--locked", "--offline", "--manifest-path", str(manifest), "--lib", "--no-run", TEST_NAME,
    ], candidate_root, env, args.timeout_seconds)
    if build_result.returncode != 0:
        raise RuntimeError("committed candidate test build failed")
    deps = target / "debug/deps"
    suffix = ".exe" if os.name == "nt" else ""
    test_binary = _one_artifact(deps, f"sipi_agent_spice_direct-*{suffix}", "candidate test binary")
    faer_rlib = _one_artifact(deps, "libfaer-*.rlib", "faer rlib")
    complex_rlib = _one_artifact(deps, "libnum_complex-*.rlib", "num-complex rlib")
    compiled_inputs_pre = [_live_receipt(path, path.name) for path in (faer_rlib, complex_rlib)]
    binary_pre = _live_receipt(test_binary, test_binary.name)
    candidate_result = _bounded_process([str(test_binary), TEST_NAME, "--exact", "--nocapture"], candidate_root, env, args.timeout_seconds)
    if candidate_result.returncode != 0:
        raise RuntimeError("committed candidate test failed")
    binary_post = _live_receipt(test_binary, test_binary.name)
    if binary_pre != binary_post:
        raise RuntimeError("candidate test binary changed during execution")
    source_blob = _git_blob(tools["git"], repository, production["commit"], SOURCE_PATH)
    asserted_real_bits = _candidate_real_assertions(source_blob)
    probe_source = root / "independent_probe.rs"
    _create_file(probe_source, INDEPENDENT_PROBE, MAX_FILE_BYTES)
    probe_binary = root / ("independent_probe.exe" if os.name == "nt" else "independent_probe")
    probe_build = _bounded_process([str(tools["rustc"]), "--edition=2024", str(probe_source), "-C", f"linker={tools['linker']}", "-L", f"dependency={deps}", "--extern", f"faer={faer_rlib}", "--extern", f"num_complex={complex_rlib}", "-o", str(probe_binary)], root, env, args.timeout_seconds)
    if probe_build.returncode != 0:
        raise RuntimeError("independent complex checkpoint build failed")
    probe_binary_pre = _live_receipt(probe_binary, probe_binary.name)
    probe_result = _bounded_process([str(probe_binary)], root, env, args.timeout_seconds)
    if probe_result.returncode != 0:
        raise RuntimeError("independent complex checkpoint failed")
    probe_binary_post = _live_receipt(probe_binary, probe_binary.name)
    if probe_binary_pre != probe_binary_post:
        raise RuntimeError("independent checkpoint binary changed")
    candidate_bits = _independent_matrix(probe_result.stdout)
    if [cell["re_bits"] for cell in candidate_bits] != asserted_real_bits:
        raise RuntimeError("independent checkpoint real bits differ from committed runtime assertions")
    python_requested = Path(args.python).absolute()
    python_environment = _safe_directory(python_requested.parent.parent)
    site_packages = python_environment / ("Lib/site-packages" if os.name == "nt" else f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages")
    site_packages = _safe_directory(site_packages)
    python_env = dict(os.environ)
    python_env["PATH"] = os.pathsep.join((str(python_requested.parent), str(python_environment), python_env.get("PATH", "")))
    upstream_result = _bounded_process([
        str(tools["python"]), "-I", "-c", PYTHON_PROBE, str(skrf_root), str(fixture), str(python_environment), str(site_packages),
    ], root, python_env, args.timeout_seconds)
    if upstream_result.returncode != 0:
        raise RuntimeError("upstream source replay failed")
    observed = _python_result(upstream_result.stdout)
    skrf_git_sources = [_git_receipt(tools["git"], skrf_repo, skrf["commit"], path) for path in SKRF_PATHS]
    source_by_name = {Path(item["path"]).name: item for item in skrf_git_sources}
    for key, filename in (("network", "network.py"), ("mathFunctions", "mathFunctions.py"), ("constants", "constants.py")):
        actual, expected = observed["sources_pre"][key], source_by_name[filename]
        if type(actual) is not dict or set(actual) != {"basename", "bytes", "sha256", "version", "path_redacted", "relative_path", "root_role", "root_contained"} or actual["relative_path"] != f"skrf/{filename}" or actual["root_role"] != "scikit_rf_archive" or actual["root_contained"] is not True or actual["path_redacted"] is not True or (actual["bytes"], actual["sha256"]) != (expected["bytes"], expected["sha256"]):
            raise RuntimeError("executed scikit-rf source differs from trusted Git blob")
    baseline_git = _git_receipt(tools["git"], repository, production["commit"], BASELINE_PATH)
    baseline_value = _baseline(_git_blob(tools["git"], repository, production["commit"], BASELINE_PATH))
    if observed["matrix"] != baseline_value["upstream_matrix"]:
        raise RuntimeError("fresh upstream matrix differs from bound baseline")
    upstream_real_bits = [cell["re_bits"] for cell in observed["matrix"]]
    current = _difference_real(asserted_real_bits, upstream_real_bits)
    if current["differing_components"] != 3 or current["max_ulp"] != 1 or asserted_real_bits[0] != upstream_real_bits[0]:
        raise RuntimeError("expected 4->3 / 4->1 ULP diagnostic fact not reproduced")
    modules_pre = observed["modules_pre"]
    modules_post = observed["modules_post"]
    compiled_inputs_post = [_live_receipt(path, path.name) for path in (faer_rlib, complex_rlib)]
    dependency_inventory_post = _dependency_inventory(metadata_result.stdout, candidate_root, cargo_home)
    if compiled_inputs_pre != compiled_inputs_post or dependency_inventory_pre != dependency_inventory_post:
        raise RuntimeError("locked dependency inputs changed during replay")
    tool_post = {role: _tool_snapshot(source_tools[role], path, role, versions[role]) for role, path in tools.items()}
    if tool_pre != tool_post or modules_pre != modules_post:
        raise RuntimeError("toolchain changed during replay")
    prep_live_post = [_live_receipt(repository / _safe_relative(path), path) for path in PREP_PATHS]
    candidate_live_post = [_live_receipt(repository / _safe_relative(path), path) for path in PRODUCTION_PATHS]
    if prep_live_pre != prep_live_post or candidate_live_pre != candidate_live_post:
        raise RuntimeError("live source changed during replay")
    archive_post = [_live_receipt(candidate_root / _safe_relative(path), path) for path in archive_paths]
    if archive_pre != archive_post:
        raise RuntimeError("candidate archive source changed during build/execution")
    report = {
        "schema": REPORT_SCHEMA,
        "status": "blocked_numeric_semantics",
        "work_item": "AS-03",
        "run_id": args.run_id,
        "nonce": nonce,
        "prep": {**prep, "sources": prep_sources["git"], "live_pre": prep_live_pre, "live_post": prep_live_post, "stable": True},
        "candidate": {**production, "archive": candidate_archive, "sources": candidate_sources["git"], "live_pre": candidate_live_pre, "live_post": candidate_live_post, "archive_pre": archive_pre, "archive_post": archive_post, "archive_stable": True, "binary_pre": binary_pre, "binary_post": binary_post, "binary_stable": True, "dependency_inventory_pre": dependency_inventory_pre, "dependency_inventory_post": dependency_inventory_post, "dependency_inventory_stable": True, "compiled_inputs_pre": compiled_inputs_pre, "compiled_inputs_post": compiled_inputs_post, "compiled_inputs_stable": True, "stable": True},
        "baseline": {**baseline_git, "schema": baseline_value["schema"], "status": baseline_value["status"], "candidate_commit": baseline_value["candidate_commit"], "candidate_tree": baseline_value["candidate_tree"], "candidate_matrix": baseline_value["candidate_matrix"], "upstream_matrix": baseline_value["upstream_matrix"], "prior_difference": baseline_value["prior_difference"]},
        "upstream": {**upstream, "archive": upstream_archive, "sources": [_git_receipt(tools["git"], upstream_repo, upstream["commit"], path) for path in UPSTREAM_PATHS]},
        "scikit_rf": {**skrf, "archive": skrf_archive, "sources": skrf_git_sources, "executed_sources_pre": observed["sources_pre"], "executed_sources_post": observed["sources_post"], "executed_sources_stable": True},
        "toolchain": {"pre": tool_pre, "post": tool_post, "stable": True, "modules_pre": modules_pre, "modules_post": modules_post, "modules_stable": True, "timeout_seconds": args.timeout_seconds, "environment": {"cargo_home_explicit": True, "cargo_home_path_redacted": True, "cargo_net_offline": True, "cargo_locked": True, "cargo_incremental": False, "cargo_profile": "test", "target_root_fresh": True, "rustc_explicit": True, "linker_explicit": True, "rust_host": rust_host, "wrappers_cleared": True, "paths_redacted": True}},
        "fixture": {"kind": "fixed_touchstone_line_s2p_v1", "bytes": len(FIXTURE), "sha256": FIXTURE_SHA256, "created": fixture_created},
        "execution": {"cargo_metadata": _summary(metadata_result), "candidate_build": _summary(build_result), "candidate_test": _summary(candidate_result), "scikit_rf_leaf_probe": _summary(upstream_result), "independent_probe_build": _summary(probe_build), "independent_probe": _summary(probe_result), "candidate_test_name": TEST_NAME, "private_probe_injection": False, "independent_probe_not_production_runtime": True, "agent_spice_yparam_path_executed": False},
        "numeric_change": {"prior": {"differing_components": 4, "max_ulp": 4}, "current": {**current, "committed_asserted_real_bits": asserted_real_bits, "upstream_real_bits": upstream_real_bits, "upstream_complex_matrix": observed["matrix"], "independent_complex_diagnostic": candidate_bits}, "differing_components_change": "4_to_3", "max_ulp_change": "4_to_1", "first_cell_exact": True, "numeric_parity": False, "blocked_numeric_semantics": True},
        "blockers": ["blocked_numeric_semantics"],
        "claims": {"clean_production_archive_execution": True, "committed_test_execution": True, "committed_real_checkpoint": True, "pinned_scikit_rf_leaf_execution": True, "agent_spice_source_replay": False, "complete_complex_checkpoint": False, "private_probe_injection": False, "numeric_parity": False, "s_parameter_fit": False},
        "non_claims": ["candidate_complete_complex_checkpoint", "independent_probe_is_production_runtime", "agent_spice_yparam_path_execution", "numeric_parity", "acceptance_tolerance", "general_nudge_eig_equivalence", "s_parameter_fit", "AS-05_Xyce_XDM", "release_acceptance"],
    }
    validate_report(report)
    _remove_fresh_tree(root, temp_root)
    _write_json(output, output_root, report)
    return report


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--repository", default=str(ROOT))
    value.add_argument("--upstream-repository", default=str(ROOT.parent / "agent-spice"))
    value.add_argument("--scikit-rf-repository", required=True)
    value.add_argument("--prep-commit", required=True)
    value.add_argument("--run-id", required=True)
    value.add_argument("--temp-root", required=True)
    value.add_argument("--output-root", required=True)
    value.add_argument("--output", required=True)
    value.add_argument("--git", default="git")
    value.add_argument("--cargo", default=DEFAULT_CARGO)
    value.add_argument("--rustc", default=DEFAULT_RUSTC)
    value.add_argument("--python", default=str(ROOT.parent / "agent-spice/.venv/Scripts/python.exe"))
    value.add_argument("--timeout-seconds", type=int, default=900)
    return value


def main() -> int:
    try:
        run(parser().parse_args())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"AS-03 power-wave replay blocked: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
