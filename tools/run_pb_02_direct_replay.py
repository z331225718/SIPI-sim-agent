"""Run two-source PB-02 replays from immutable Git archives.

This tool is deliberately a preparation/verification runner, not a product
runtime.  It never reads the candidate working tree.  The candidate and the
pinned PyBERT oracle are materialized from explicit Git commits into separate
temporary roots, then built and run in separate target/output directories.
Reports contain hashes and normalized logical artifact facts, not waveform
payloads.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import math
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
DEFAULT_UPSTREAM = Path(r"C:\Users\z3312\code\Py-bert-agent")
EXPECTED_UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
EXPECTED_UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
FIXTURE_RELATIVE = Path("crates/sipi-pybert-direct/fixtures/pb-02-nrz.json")
CRATE_RELATIVE = Path("crates/sipi-pybert-direct")
UPSTREAM_FACT_PATHS = (
    "LICENSE",
    "uv.lock",
    "native/pybert-core",
    "native/pybert-python",
    "src/pybert/cli.py",
    "src/pybert/engine/rust_backend.py",
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _git(root: Path, *args: str, raw: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout if raw else result.stdout.decode("ascii").strip()


def _commit_tree(repo: Path, commit: str) -> tuple[str, str]:
    resolved = str(_git(repo, "rev-parse", f"{commit}^{{commit}}"))
    tree = str(_git(repo, "rev-parse", f"{resolved}^{{tree}}"))
    return resolved, tree


def _extract_archive(payload: bytes, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        root = destination.resolve()
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"archive path escapes destination: {member.name}")
            archive.extract(member, destination)


def _materialize_git_archive(repo: Path, commit: str, destination: Path) -> dict[str, str]:
    payload = bytes(_git(repo, "archive", "--format=tar", commit, raw=True))
    _extract_archive(payload, destination)
    resolved, tree = _commit_tree(repo, commit)
    return {"commit": resolved, "tree": tree, "archive_sha256": _sha256(payload)}


def _file_digest(path: Path) -> str | None:
    try:
        return _sha256(path.read_bytes())
    except OSError:
        return None


def _tool_identity(value: str, role: str) -> dict[str, Any]:
    """Return stable tool metadata without retaining an invocation path."""

    raw = os.fspath(value)
    basename = PureWindowsPath(raw).name or PurePosixPath(raw).name or role
    return {"role": role, "executable": basename, "path_redacted": True}


def _resolve_executable(value: str, role: str) -> Path:
    """Resolve a literal executable file or a PATH command before execution."""

    literal = Path(value)
    if literal.is_file():
        return literal.resolve()
    resolved = shutil.which(value)
    if resolved is None or not Path(resolved).is_file():
        raise RuntimeError(f"{role} executable cannot be resolved")
    return Path(resolved).resolve()


def _runtime_tool_identity(value: str, role: str, version_args: tuple[str, ...]) -> dict[str, Any]:
    """Capture executable identity and version hashes without retaining paths."""

    executable = _resolve_executable(value, role)
    identity = _tool_identity(str(executable), role)
    file_sha256 = _file_digest(executable)
    if not isinstance(file_sha256, str) or HEX64.fullmatch(file_sha256) is None:
        raise RuntimeError(f"{role} executable digest unavailable")
    identity["file_sha256"] = file_sha256
    try:
        version = subprocess.run(
            [str(executable), *version_args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        raise RuntimeError(f"{role} version command failed") from error
    if version.returncode != 0:
        raise RuntimeError(f"{role} version command returned nonzero")
    if not isinstance(version.stdout, bytes) or not isinstance(version.stderr, bytes):
        raise RuntimeError(f"{role} version output unavailable")
    version_output_sha256 = _sha256(version.stdout + b"\x00" + version.stderr)
    if not isinstance(version_output_sha256, str) or HEX64.fullmatch(version_output_sha256) is None:
        raise RuntimeError(f"{role} version digest unavailable")
    identity["version_exit_code"] = version.returncode
    identity["version_output_sha256"] = version_output_sha256
    return identity


def _rustc_from_cargo(cargo: Path) -> str:
    suffix = cargo.suffix
    rustc_name = f"rustc{suffix}" if suffix else "rustc"
    sibling = cargo.with_name(rustc_name)
    if sibling.is_file():
        return str(sibling)
    resolved = shutil.which("rustc")
    if resolved is None:
        raise RuntimeError("rustc executable cannot be resolved")
    return resolved


def _runtime_toolchain_identity(cargo: str, uv: str, timeout_seconds: int) -> tuple[dict[str, Any], dict[str, Path]]:
    cargo_path = _resolve_executable(cargo, "cargo")
    uv_path = _resolve_executable(uv, "uv")
    rustc_path = Path(_rustc_from_cargo(cargo_path))
    identities = {
        "cargo": _runtime_tool_identity(str(cargo_path), "cargo", ("-Vv",)),
        "rustc": _runtime_tool_identity(str(rustc_path), "rustc", ("-Vv",)),
        "uv": _runtime_tool_identity(str(uv_path), "uv", ("--version",)),
        "timeout_seconds": timeout_seconds,
    }
    return identities, {"cargo": cargo_path, "rustc": rustc_path, "uv": uv_path}


def _execution_env(rustc: Path) -> dict[str, str]:
    env = dict(os.environ)
    for variable in ("RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"):
        env.pop(variable, None)
    env["RUSTC"] = str(rustc)
    return env


def _safe_fixture_relative(value: Path | str) -> Path:
    """Return a strictly repository-relative fixture path.

    ``Path`` follows the host platform, so a Windows drive/UNC path could look
    relative when this runner is inspected from a POSIX host (and vice versa).
    Check both path grammars before accepting the value and reject traversal
    components before joining it to either the working tree or an archive.
    """

    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise RuntimeError("fixture must be a non-empty repository-relative path")
    host_path = Path(raw)
    posix_path = PurePosixPath(raw)
    windows_path = PureWindowsPath(raw)
    if (
        host_path.is_absolute()
        or bool(host_path.anchor)
        or posix_path.is_absolute()
        or bool(posix_path.anchor)
        or windows_path.is_absolute()
        or bool(windows_path.anchor)
        or bool(windows_path.drive)
        or raw.startswith(("/", "\\"))
    ):
        raise RuntimeError(f"fixture must be repository-relative: {raw}")
    components = [component for component in re.split(r"[\\/]+", raw) if component not in ("", ".")]
    if not components or any(component == ".." for component in components):
        raise RuntimeError(f"fixture must not contain parent traversal: {raw}")
    return Path(*components)


def _read_archived_fixture(root: Path, relative: Path) -> tuple[Path, bytes]:
    """Read only a fixture that is contained by the materialized archive."""

    relative = _safe_fixture_relative(relative)
    archive_root = root.resolve()
    fixture = root / relative
    resolved_fixture = fixture.resolve()
    if resolved_fixture != archive_root and archive_root not in resolved_fixture.parents:
        raise RuntimeError(f"archived fixture escapes candidate archive: {relative}")
    if not resolved_fixture.is_file():
        raise RuntimeError(f"archived fixture is missing: {relative}")
    return resolved_fixture, resolved_fixture.read_bytes()


def _iter_files(root: Path, prefixes: Iterable[str]) -> Iterable[tuple[str, Path]]:
    for prefix in prefixes:
        path = root / prefix
        if path.is_file():
            yield prefix.replace("\\", "/"), path
            continue
        if not path.is_dir():
            continue
        for child in sorted(path.rglob("*")):
            if child.is_file() and not child.is_symlink():
                yield child.relative_to(root).as_posix(), child


def _inventory(root: Path, prefixes: Iterable[str]) -> dict[str, Any]:
    entries = [{"path": path, "sha256": _sha256(file.read_bytes()), "bytes": file.stat().st_size} for path, file in _iter_files(root, prefixes)]
    entries.sort(key=lambda item: item["path"])
    return {"entries": entries, "sha256": _sha256(_canonical(entries))}


def _source_facts(root: Path, commit_info: dict[str, str], prefixes: Iterable[str]) -> dict[str, Any]:
    return {
        **commit_info,
        "inventory": _inventory(root, prefixes),
        "cargo_lock_sha256": _file_digest(root / "crates/sipi-pybert-direct/Cargo.lock"),
        "rust_toolchain_sha256": _file_digest(root / "rust-toolchain.toml"),
    }


def _upstream_facts(root: Path, commit_info: dict[str, str]) -> dict[str, Any]:
    return {
        **commit_info,
        "inventory": _inventory(root, UPSTREAM_FACT_PATHS),
        "native_core_cargo_lock_sha256": _file_digest(root / "native/pybert-core/Cargo.lock"),
        "uv_lock_sha256": _file_digest(root / "uv.lock"),
        "license_sha256": _file_digest(root / "LICENSE"),
    }


def _normalize_meta(value: Any, *, key: str | None = None) -> Any:
    if key == "input_file":
        return "<input-file>"
    if isinstance(value, dict):
        return {name: _normalize_meta(item, key=name) for name, item in sorted(value.items())}
    if isinstance(value, list):
        return [_normalize_meta(item) for item in value]
    if isinstance(value, str):
        # Both runners may expose an absolute path in an error/diagnostic
        # string.  Preserve its message while removing only machine-local roots.
        normalized = value.replace("\\", "/")
        for marker in ("/candidate/", "/upstream/", "/output/"):
            if marker in normalized:
                normalized = normalized[normalized.index(marker) :]
        return normalized
    return value


def _npy_logical_summary(payload: bytes) -> dict[str, Any]:
    if len(payload) < 10 or payload[:6] != b"\x93NUMPY":
        raise ValueError("NPZ member is not an NPY payload")
    major = payload[6]
    if major == 1:
        header_length = int.from_bytes(payload[8:10], "little")
        data_offset = 10 + header_length
    elif major in (2, 3):
        if len(payload) < 12:
            raise ValueError("truncated NPY v2/v3 header")
        header_length = int.from_bytes(payload[8:12], "little")
        data_offset = 12 + header_length
    else:
        raise ValueError(f"unsupported NPY version: {major}")
    if data_offset > len(payload):
        raise ValueError("truncated NPY header")
    try:
        header = ast.literal_eval(payload[10:data_offset].decode("latin-1").strip()) if major == 1 else ast.literal_eval(payload[12:data_offset].decode("utf-8").strip())
    except (SyntaxError, UnicodeDecodeError, ValueError) as error:
        raise ValueError("invalid NPY header") from error
    if not isinstance(header, dict) or not isinstance(header.get("descr"), str) or not isinstance(header.get("shape"), tuple):
        raise ValueError("NPY header shape/dtype is invalid")
    dtype = header["descr"]
    shape = tuple(int(item) for item in header["shape"])
    if any(item < 0 for item in shape):
        raise ValueError("NPY shape contains a negative dimension")
    count = math.prod(shape)
    raw = payload[data_offset:]
    if dtype in {"<f8", "|f8"}:
        f64 = raw
    elif dtype == ">f8":
        f64 = b"".join(raw[index : index + 8][::-1] for index in range(0, len(raw), 8))
    else:
        raise ValueError(f"NPY member is not float64: {dtype}")
    if len(raw) != count * 8:
        raise ValueError("NPY payload length does not match float64 shape")
    return {
        "dtype": dtype,
        "shape": list(shape),
        "count": count,
        "fortran_order": bool(header.get("fortran_order")),
        "f64_sha256": _sha256(f64),
    }


def _npz_summary(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    members: dict[str, str] = {}
    member_bytes: dict[str, int] = {}
    logical_members: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.endswith(".npy"):
                continue
            data = archive.read(info)
            members[info.filename] = _sha256(data)
            member_bytes[info.filename] = len(data)
            logical_members[info.filename] = _npy_logical_summary(data)
    return {
        "sha256": _sha256(payload),
        "bytes": len(payload),
        "member_sha256": dict(sorted(members.items())),
        "member_bytes": dict(sorted(member_bytes.items())),
        "logical_members": dict(sorted(logical_members.items())),
        "logical_sha256": _sha256(_canonical(dict(sorted(logical_members.items())))),
    }


def _artifact_summary(output: Path) -> dict[str, Any]:
    meta_path = output / "meta.json"
    arrays_path = output / "arrays.npz"
    result: dict[str, Any] = {
        "meta_present": meta_path.is_file(),
        "arrays_present": arrays_path.is_file(),
    }
    if meta_path.is_file():
        raw = meta_path.read_bytes()
        result["meta_sha256"] = _sha256(raw)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            result["meta_json_valid"] = False
        else:
            normalized = _normalize_meta(parsed)
            result["meta_json_valid"] = True
            result["meta_normalized_sha256"] = _sha256(_canonical(normalized))
            result["meta_schema"] = parsed.get("schema") if isinstance(parsed, dict) else None
    if arrays_path.is_file():
        try:
            result["arrays"] = _npz_summary(arrays_path)
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            result["arrays_error"] = type(error).__name__
    return result


def _process_summary(process: subprocess.CompletedProcess[bytes], output: Path) -> dict[str, Any]:
    return {
        "exit_code": process.returncode,
        "stdout_sha256": _sha256(process.stdout),
        "stderr_sha256": _sha256(process.stderr),
        "artifacts": _artifact_summary(output),
    }


def _binary_path(target: Path) -> Path:
    name = "sipi-pybert-direct.exe" if os.name == "nt" else "sipi-pybert-direct"
    return target / "release" / name


def _logical_array_hashes(summary: dict[str, Any]) -> dict[str, Any] | None:
    arrays = summary.get("artifacts", {}).get("arrays")
    if not isinstance(arrays, dict):
        return None
    members = arrays.get("logical_members")
    return members if isinstance(members, dict) else None


def _run_one(
    *,
    run_root: Path,
    candidate_root: Path,
    upstream_root: Path,
    fixture: Path,
    cargo: Path,
    rustc: Path,
    uv: Path,
    timeout: int,
) -> dict[str, Any]:
    candidate_target = run_root / "candidate-target"
    upstream_target = run_root / "upstream-target"
    candidate_output = run_root / "candidate-output"
    upstream_output = run_root / "upstream-output"
    candidate_target.mkdir(parents=True)
    upstream_target.mkdir(parents=True)
    env = _execution_env(rustc)
    env["CARGO_TARGET_DIR"] = str(candidate_target)
    build = _run(
        [str(cargo), "build", "--manifest-path", str(candidate_root / "crates/sipi-pybert-direct/Cargo.toml"), "--release", "--locked"],
        cwd=candidate_root,
        env=env,
        timeout=timeout,
    )
    binary = _binary_path(candidate_target)
    build_summary = {
        "exit_code": build.returncode,
        "stdout_sha256": _sha256(build.stdout),
        "stderr_sha256": _sha256(build.stderr),
        "binary_sha256": _file_digest(binary),
        "binary_bytes": binary.stat().st_size if binary.is_file() else None,
    }
    candidate_process: dict[str, Any]
    if build.returncode == 0 and binary.is_file():
        candidate_env = _execution_env(rustc)
        candidate_env["CARGO_TARGET_DIR"] = str(candidate_target)
        process = _run(
            [str(binary), str(fixture), "--output-dir", str(candidate_output)],
            cwd=candidate_root,
            env=candidate_env,
            timeout=timeout,
        )
        candidate_process = _process_summary(process, candidate_output)
    else:
        candidate_process = {"exit_code": None, "skipped": True, "artifacts": {}}

    upstream_env = _execution_env(rustc)
    upstream_env["CARGO_TARGET_DIR"] = str(upstream_target)
    upstream_env["UV_PROJECT_ENVIRONMENT"] = str(run_root / "upstream-venv")
    cargo_executable = cargo
    if cargo_executable.is_file():
        upstream_env["PATH"] = str(cargo_executable.resolve().parent) + os.pathsep + upstream_env.get("PATH", "")
    oracle = _run(
        [
            str(uv),
            "run",
            "--project",
            str(upstream_root),
            "--frozen",
            "--extra",
            "native",
            "pybert",
            "sim-native",
            str(upstream_root / "oracle-input.json"),
            "--output-dir",
            str(upstream_output),
        ],
        cwd=upstream_root,
        env=upstream_env,
        timeout=timeout,
    )
    oracle_process = _process_summary(oracle, upstream_output)
    candidate_arrays = _logical_array_hashes(candidate_process)
    oracle_arrays = _logical_array_hashes(oracle_process)
    parity = {
        "candidate_exit_zero": candidate_process.get("exit_code") == 0,
        "oracle_exit_zero": oracle.returncode == 0,
        "candidate_array_members_equal_oracle": candidate_arrays is not None and candidate_arrays == oracle_arrays,
        "array_member_names": sorted(candidate_arrays or oracle_arrays or {}),
    }
    return {
        "build": build_summary,
        "candidate": candidate_process,
        "oracle": oracle_process,
        "parity": parity,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    candidate_repo = args.candidate_repo.resolve()
    upstream_repo = args.upstream_repo.resolve()
    fixture_relative = _safe_fixture_relative(args.fixture)
    fresh_run_nonce = secrets.token_hex(32)
    toolchain_identity, runtime_tools = _runtime_toolchain_identity(args.cargo, args.uv, args.timeout_seconds)
    candidate_commit, candidate_tree = _commit_tree(candidate_repo, args.candidate_commit)
    upstream_commit, upstream_tree = _commit_tree(upstream_repo, args.upstream_commit)
    if upstream_commit != EXPECTED_UPSTREAM_COMMIT or upstream_tree != EXPECTED_UPSTREAM_TREE:
        raise RuntimeError("upstream commit/tree is not the pinned PB-02 source")
    work_parent = args.work_root.resolve() if args.work_root else Path(tempfile.mkdtemp(prefix="sipi-pb-02-replay-"))
    work_parent.mkdir(parents=True, exist_ok=True)
    run_root = work_parent / args.run_id
    if run_root.exists():
        raise RuntimeError(f"run root already exists: {run_root}")
    run_root.mkdir()
    candidate_materialized = run_root / "candidate"
    upstream_materialized = run_root / "upstream"
    candidate_info = _materialize_git_archive(candidate_repo, candidate_commit, candidate_materialized)
    upstream_info = _materialize_git_archive(upstream_repo, upstream_commit, upstream_materialized)
    # Capture source inventories before uv/cargo can create build outputs in
    # the materialized oracle tree.  Reports bind the immutable archive, not
    # generated .pyd/.pyc files from a particular replay environment.
    candidate_facts = _source_facts(candidate_materialized, candidate_info, [str(CRATE_RELATIVE)])
    upstream_facts = _upstream_facts(upstream_materialized, upstream_info)
    fixture, fixture_payload = _read_archived_fixture(candidate_materialized, fixture_relative)
    fixture_hash = _sha256(fixture_payload)
    (upstream_materialized / "oracle-input.json").write_bytes(fixture_payload)
    replay = _run_one(
        run_root=run_root,
        candidate_root=candidate_materialized,
        upstream_root=upstream_materialized,
        fixture=fixture,
        cargo=runtime_tools["cargo"],
        rustc=runtime_tools["rustc"],
        uv=runtime_tools["uv"],
        timeout=args.timeout_seconds,
    )
    report = {
        "schema": "sipi.pb-02-direct-replay.v1",
        "status": "passed" if all(replay["parity"].values()) else "blocked",
        "run_id": args.run_id,
        "fresh_run_nonce": fresh_run_nonce,
        "source_mode": "git_archive_at_immutable_commit",
        "candidate": candidate_facts,
        "upstream": upstream_facts,
        "fixture": {"path": fixture_relative.as_posix(), "sha256": fixture_hash, "bytes": len(fixture_payload)},
        "toolchain": toolchain_identity,
        "replay": replay,
        "non_claims": [
            "This report does not prove parity for uncovered SimulationInputV1 branches.",
            "SIPI strict JSON, artifact, NPZ compression, and symlink policies are wrapper behavior, not upstream sim-native semantics.",
            "The report is not a license decision, release approval, or product capability admission.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        output.write("\n")
    if not args.keep_work and args.work_root is None:
        shutil.rmtree(work_parent, ignore_errors=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--candidate-commit", required=True, help="immutable candidate Git commit; working-tree bytes are never used")
    parser.add_argument("--upstream-repo", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--upstream-commit", default=EXPECTED_UPSTREAM_COMMIT)
    parser.add_argument("--fixture", type=Path, default=FIXTURE_RELATIVE)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--cargo", default=os.environ.get("CARGO", "cargo"))
    parser.add_argument("--uv", default=os.environ.get("UV", "uv"))
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--keep-work", action="store_true")
    args = parser.parse_args()
    try:
        report = run(args)
    except (OSError, RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"valid": False, "error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "report": str(args.report)}, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
