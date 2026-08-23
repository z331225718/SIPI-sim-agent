"""Run the bounded PB-01 Rust legacy leaf against the pinned Python oracle.

Stage one materializes immutable Git archives. Stage two runs both ``pybert
sim`` and the Rust ``sim`` command with the exact same legacy YAML bytes, then
decodes only the selected numeric arrays needed for the scoped leaf compare.
The Rust result is a Python-readable pickle dictionary, not a claim of
class-compatible ``PyBertData`` serialization.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import secrets
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import run_pb_02_direct_replay as custody

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UPSTREAM = Path(r"C:\Users\z3312\code\Py-bert-agent")
EXPECTED_UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
EXPECTED_UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
UPSTREAM_FACT_PATHS = (
    "LICENSE",
    "uv.lock",
    "src/pybert/cli.py",
    "src/pybert/configuration.py",
    "src/pybert/pybert.py",
    "src/pybert/results.py",
    "src/pybert/engine/python_backend.py",
)
CRATE_RELATIVE = Path("crates/sipi-pybert-direct")
FIXTURE_RELATIVE = CRATE_RELATIVE / "fixtures/pb-01-legacy-nrz.yaml"
CANONICAL_ITEM_NAMES = (
    "chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h", "chnl_s", "tx_s",
    "ctle_s", "dfe_s", "tx_out_s", "ctle_out_s", "dfe_out_s", "chnl_p",
    "tx_out_p", "ctle_out_p", "dfe_out_p", "chnl_H", "tx_H", "ctle_H",
    "dfe_H", "tx_out_H", "ctle_out_H", "dfe_out_H", "tx_out",
)
ARRAY_NAMES = (
    "chnl_h",
    "tx_out_h",
    "ctle_out_h",
    "dfe_out_h",
    "chnl_s",
    "tx_out_s",
    "ctle_out_s",
    "dfe_out_s",
    "chnl_p",
    "tx_out_p",
    "ctle_out_p",
    "dfe_out_p",
)
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


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
    return resolved, str(_git(repo, "rev-parse", f"{resolved}^{{tree}}"))


def _extract_archive(payload: bytes, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"archive path escapes destination: {member.name}")
            if member.issym() or member.islnk():
                raise RuntimeError(f"archive links are not accepted: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise RuntimeError(f"archive member kind is not accepted: {member.name}")
            archive.extract(member, destination)


def _materialize(repo: Path, commit: str, destination: Path) -> dict[str, str]:
    payload = bytes(_git(repo, "archive", "--format=tar", commit, raw=True))
    _extract_archive(payload, destination)
    resolved, tree = _commit_tree(repo, commit)
    return {"commit": resolved, "tree": tree, "archive_sha256": _sha256(payload)}


def _safe_relative(value: str | Path) -> Path:
    raw = str(value)
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
        or raw.startswith(("/", "\\"))
    ):
        raise RuntimeError("path must be repository-relative")
    parts = [part for part in re.split(r"[\\/]+", raw) if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise RuntimeError("path traversal is not accepted")
    return Path(*parts)


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _inventory(root: Path, prefixes: tuple[str, ...]) -> dict[str, Any]:
    entries = []
    for prefix in prefixes:
        path = root / prefix
        paths = [path] if path.is_file() else sorted(path.rglob("*")) if path.is_dir() else []
        for child in paths:
            if child.is_file() and not child.is_symlink():
                relative = child.relative_to(root).as_posix()
                entries.append({"path": relative, "bytes": child.stat().st_size, "sha256": _file_sha256(child)})
    entries.sort(key=lambda item: item["path"])
    return {"entries": entries, "sha256": _sha256(_canonical(entries))}


def _runtime_identity(path: str, role: str, version_args: tuple[str, ...]) -> tuple[dict[str, Any], Path]:
    literal = Path(path)
    resolved = literal.resolve() if literal.is_file() else shutil.which(path)
    if resolved is None:
        raise RuntimeError(f"{role} executable cannot be resolved")
    executable = Path(resolved).resolve()
    file_sha256 = _file_sha256(executable)
    result = subprocess.run([str(executable), *version_args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0 or not HEX64.fullmatch(file_sha256):
        raise RuntimeError(f"{role} identity is unavailable")
    return (
        {
            "role": role,
            "executable": executable.name,
            "path_redacted": True,
            "file_sha256": file_sha256,
            "version_exit_code": result.returncode,
            "version_output_sha256": _sha256(result.stdout + b"\x00" + result.stderr),
        },
        executable,
    )


def _copy_fixture(source: Path, root: Path) -> dict[str, Any]:
    if source.suffix not in {".yaml", ".yml"}:
        raise RuntimeError("PB-01 scoped leaf fixture must be YAML")
    target = root / ("oracle-input" + source.suffix)
    payload = source.read_bytes()
    target.write_bytes(payload)
    return {"path": "oracle-input" + source.suffix, "bytes": len(payload), "sha256": _sha256(payload)}


def _artifact(root: Path, relative: str) -> dict[str, Any]:
    path = root / _safe_relative(relative)
    if not path.is_file():
        return {"present": False, "path": relative}
    return {"present": True, "path": relative, "bytes": path.stat().st_size, "sha256": _file_sha256(path)}


def _process(process: subprocess.CompletedProcess[bytes], root: Path, result: str) -> dict[str, Any]:
    return {
        "exit_code": process.returncode,
        "stdout_sha256": _sha256(process.stdout),
        "stderr_sha256": _sha256(process.stderr),
        "artifact": _artifact(root, result),
    }


EXTRACTOR = r'''
import hashlib, io, json, pickle, struct, sys

class RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        raise pickle.UnpicklingError("globals are forbidden for candidate dictionary")

names = json.loads(sys.argv[2])
with open(sys.argv[1], "rb") as stream:
    payload = stream.read()
obj = RestrictedUnpickler(io.BytesIO(payload)).load() if sys.argv[3] == "candidate" else pickle.loads(payload)
if hasattr(obj, "the_data"):
    arrays = {name: obj.the_data.arrays.get(name) for name in names}
    schema = {"kind": "PyBertData_class_pickle", "item_names": None, "array_keys": None}
elif isinstance(obj, dict):
    arrays = obj.get("arrays", {})
    schema = {
        "kind": "python_pickle_dict",
        "schema": obj.get("schema"),
        "item_names": obj.get("item_names"),
        "array_keys": sorted(arrays) if isinstance(arrays, dict) else None,
    }
else:
    arrays = {}
    schema = {"kind": "unknown", "item_names": None, "array_keys": None}
out = {}
for name in names:
    value = arrays.get(name)
    if value is None:
        out[name] = {"present": False}
        continue
    if hasattr(value, "reshape"):
        value = value.reshape(-1).tolist()
    elif not isinstance(value, (list, tuple)):
        value = [float(value)]
    values = [float(item) for item in value]
    payload = struct.pack("<" + "d" * len(values), *values)
    out[name] = {
        "present": True,
        "length": len(values),
        "f64le_sha256": hashlib.sha256(payload).hexdigest(),
        "max_abs": max((abs(item) for item in values), default=0.0),
        "values": values,
    }
print(json.dumps({"arrays": out, "artifact_schema": schema}, sort_keys=True, separators=(",", ":")))
'''


def _decode(uv: Path, upstream_root: Path, artifact_root: Path, relative: str, mode: str, env: dict[str, str]) -> dict[str, Any]:
    artifact_path = (artifact_root / _safe_relative(relative)).resolve()
    process = subprocess.run(
        [str(uv), "run", "--project", str(upstream_root), "--frozen", "python", "-c", EXTRACTOR, str(artifact_path), json.dumps(ARRAY_NAMES), mode],
        cwd=upstream_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=1200,
    )
    if process.returncode != 0:
        raise RuntimeError("pickle extraction failed")
    try:
        summary = json.loads(process.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("pickle extraction returned invalid JSON") from error
    if not isinstance(summary, dict) or not isinstance(summary.get("arrays"), dict):
        raise RuntimeError("pickle extraction returned a non-object")
    return summary


def _compare(oracle: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    rows = []
    blockers = []
    for name in ARRAY_NAMES:
        left = oracle.get(name, {})
        right = candidate.get(name, {})
        if not left.get("present") or not right.get("present"):
            blockers.append(f"{name}: missing selected array")
            continue
        if left.get("length") != right.get("length"):
            blockers.append(f"{name}: length drift")
            continue
        left_values = left.get("values", [])
        right_values = right.get("values", [])
        if not all(math.isfinite(value) for value in [*left_values, *right_values]):
            blockers.append(f"{name}: non-finite numeric payload")
            continue
        values = [abs(a - b) for a, b in zip(left_values, right_values)]
        max_abs = max(values, default=0.0)
        scale = max(float(left.get("max_abs", 0.0)), float(right.get("max_abs", 0.0)), 1.0)
        tolerance = 1.0e-7 + 1.0e-6 * scale
        passed = max_abs <= tolerance
        if not passed:
            blockers.append(f"{name}: max_abs={max_abs} > tolerance={tolerance}")
        rows.append({"name": name, "length": left["length"], "max_abs": max_abs, "scale": scale, "tolerance": tolerance, "passed": passed})
    return {
        "status": "passed" if not blockers else "blocked",
        "policy": {"absolute_tolerance": 1.0e-7, "relative_scale": 1.0e-6, "formula": "absolute_tolerance + relative_scale * scale"},
        "arrays": rows,
        "blockers": blockers,
    }


def _binary_path(target: Path) -> Path:
    return target / "release" / ("sipi-pybert-direct.exe" if os.name == "nt" else "sipi-pybert-direct")


def _source_facts(root: Path, info: dict[str, str]) -> dict[str, Any]:
    return {
        **info,
        "inventory": _inventory(root, (CRATE_RELATIVE.as_posix(),)),
        "cargo_lock_sha256": custody._file_digest(root / CRATE_RELATIVE / "Cargo.lock"),
        "rust_toolchain_sha256": custody._file_digest(root / "rust-toolchain.toml"),
    }


def _upstream_facts(root: Path, info: dict[str, str]) -> dict[str, Any]:
    return {
        **info,
        "inventory": _inventory(root, UPSTREAM_FACT_PATHS),
        "uv_lock_sha256": custody._file_digest(root / "uv.lock"),
        "license_sha256": custody._file_digest(root / "LICENSE"),
    }


def _run_one(
    *, run_root: Path, candidate_root: Path, upstream_root: Path, fixture: Path,
    cargo: Path, rustc: Path, uv: Path, timeout: int,
) -> dict[str, Any]:
    target = run_root / "candidate-target"
    target.mkdir()
    build_env = custody._execution_env(rustc)
    build_env["CARGO_TARGET_DIR"] = str(target)
    build = custody._run(
        [str(cargo), "build", "--manifest-path", str(candidate_root / CRATE_RELATIVE / "Cargo.toml"), "--release", "--locked"],
        cwd=candidate_root, env=build_env, timeout=timeout,
    )
    binary = _binary_path(target)
    build_summary = {
        "exit_code": build.returncode,
        "stdout_sha256": _sha256(build.stdout),
        "stderr_sha256": _sha256(build.stderr),
        "binary_sha256": custody._file_digest(binary),
        "binary_bytes": binary.stat().st_size if binary.is_file() else None,
    }
    candidate_result = run_root / "candidate-result.pybert_data"
    oracle_result = run_root / "oracle-result.pybert_data"
    if build.returncode == 0 and binary.is_file():
        candidate_process = custody._run(
            [str(binary), "sim", str(fixture), "--results", str(candidate_result)],
            cwd=candidate_root, env=custody._execution_env(rustc), timeout=timeout,
        )
        candidate_summary = _process(candidate_process, run_root, candidate_result.name)
    else:
        candidate_process = None
        candidate_summary = {"exit_code": None, "skipped": True, "artifact": {"present": False, "path": candidate_result.name}}

    oracle_fixture = upstream_root / "oracle-input.yaml"
    oracle_env = custody._execution_env(rustc)
    oracle_env["CARGO_TARGET_DIR"] = str(run_root / "upstream-target")
    oracle_env["UV_PROJECT_ENVIRONMENT"] = str(run_root / "upstream-venv")
    oracle_env["PATH"] = str(cargo.parent) + os.pathsep + oracle_env.get("PATH", "")
    oracle_process = custody._run(
        [str(uv), "run", "--project", str(upstream_root), "--frozen", "pybert", "sim", str(oracle_fixture), "--results", str(oracle_result)],
        cwd=upstream_root, env=oracle_env, timeout=timeout,
    )
    oracle_summary = _process(oracle_process, run_root, oracle_result.name)
    schema: dict[str, Any] | None = None
    if candidate_process is None or candidate_process.returncode != 0 or oracle_process.returncode != 0:
        comparison = {
            "status": "blocked",
            "policy": {"absolute_tolerance": 1.0e-7, "relative_scale": 1.0e-6, "formula": "absolute_tolerance + relative_scale * scale"},
            "arrays": [],
            "blockers": ["one replay exited non-zero"],
        }
    else:
        candidate_decoded = _decode(uv, upstream_root, run_root, candidate_result.name, "candidate", oracle_env)
        oracle_decoded = _decode(uv, upstream_root, run_root, oracle_result.name, "oracle", oracle_env)
        schema = candidate_decoded["artifact_schema"]
        comparison = _compare(oracle_decoded["arrays"], candidate_decoded["arrays"])
        expected = list(CANONICAL_ITEM_NAMES)
        if schema != {
            "kind": "python_pickle_dict",
            "schema": "sipi.pybert_data.v1",
            "item_names": expected,
            "array_keys": sorted(expected),
        }:
            comparison["status"] = "blocked"
            comparison["blockers"].append("candidate artifact is not the exact canonical 23-key dictionary")
    return {
        "build": build_summary,
        "candidate": candidate_summary,
        "oracle": oracle_summary,
        "candidate_artifact_schema": schema,
        "comparison": comparison,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    candidate_repo = args.candidate_repo.resolve()
    upstream_repo = args.upstream_repo.resolve()
    fixture_relative = custody._safe_fixture_relative(args.fixture)
    toolchain, tools = custody._runtime_toolchain_identity(args.cargo, args.uv, args.timeout_seconds)
    candidate_commit, _ = _commit_tree(candidate_repo, args.candidate_commit)
    upstream_commit, upstream_tree = _commit_tree(upstream_repo, args.upstream_commit)
    if (upstream_commit, upstream_tree) != (EXPECTED_UPSTREAM_COMMIT, EXPECTED_UPSTREAM_TREE):
        raise RuntimeError("upstream commit/tree is not pinned")
    work_parent = args.work_root.resolve() if args.work_root else Path(tempfile.mkdtemp(prefix="sipi-pb-01-leaf-"))
    work_parent.mkdir(parents=True, exist_ok=True)
    run_root = work_parent / args.run_id
    if run_root.exists():
        raise RuntimeError(f"run root already exists: {run_root}")
    run_root.mkdir()
    candidate_root, upstream_root = run_root / "candidate", run_root / "upstream"
    candidate_info = _materialize(candidate_repo, candidate_commit, candidate_root)
    upstream_info = _materialize(upstream_repo, upstream_commit, upstream_root)
    candidate_facts = _source_facts(candidate_root, candidate_info)
    upstream_facts = _upstream_facts(upstream_root, upstream_info)
    fixture, payload = custody._read_archived_fixture(candidate_root, fixture_relative)
    if fixture.suffix not in {".yaml", ".yml"}:
        raise RuntimeError("PB-01 scoped leaf fixture must be YAML")
    (upstream_root / "oracle-input.yaml").write_bytes(payload)
    replay = _run_one(
        run_root=run_root, candidate_root=candidate_root, upstream_root=upstream_root,
        fixture=fixture, cargo=tools["cargo"], rustc=tools["rustc"], uv=tools["uv"], timeout=args.timeout_seconds,
    )
    runner_path = Path(__file__).resolve()
    custody_runner_path = Path(custody.__file__).resolve()
    report = {
        "schema": "sipi.pb-01-legacy-leaf-replay.v1",
        "status": "passed" if replay["comparison"]["status"] == "passed" else "blocked",
        "run_id": args.run_id,
        "fresh_run_nonce": secrets.token_hex(32),
        "source_mode": "git_archive_at_immutable_commit",
        "candidate": candidate_facts,
        "upstream": upstream_facts,
        "fixture": {"path": fixture_relative.as_posix(), "bytes": len(payload), "sha256": _sha256(payload), "archive_present": True},
        "toolchain": toolchain,
        "harness": {
            "source_mode": "git_archive_at_immutable_commit",
            "runner": {"path": "tools/run_pb_01_legacy_leaf_replay.py", "sha256": _file_sha256(runner_path)},
            "custody_runner_helper": {"path": "tools/run_pb_02_direct_replay.py", "sha256": _file_sha256(custody_runner_path)},
        },
        "replay": replay,
        "reproducibility": {"binary_bit_reproducible": False},
        "artifact_contract": {
            "result_suffix": ".pybert_data",
            "selected_arrays": list(ARRAY_NAMES),
            "canonical_item_names": list(CANONICAL_ITEM_NAMES),
            "array_key_policy": "exact_set_equal_to_canonical_item_names",
            "rust_codec": "python_pickle_dict_sipi.pybert_data.v1",
            "upstream_codec": "PyBertData_pickle",
        },
        "non_claims": [
            "This is one scoped NRZ analytic-metallic-line 23-key dictionary leaf, not complete PyBERT branch parity.",
            "The Rust artifact is a Python-readable canonical-item dictionary, not a PyBertData class-compatible pickle.",
            "Imported S2P, .pybert_cfg pickle input, AMI/IBIS, periodic/random noise, adaptive DFE/Viterbi, and jitter/eye/bathtub branches remain open.",
            "The external Python invocation is oracle evidence only; the Rust candidate does not call Python at runtime.",
            "This report is not a license decision, product admission, release approval, or redistribution authorization.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    if args.work_root is None and not args.keep_work:
        shutil.rmtree(work_parent, ignore_errors=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--upstream-repo", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--upstream-commit", default=EXPECTED_UPSTREAM_COMMIT)
    parser.add_argument("--fixture", type=Path, default=FIXTURE_RELATIVE)
    parser.add_argument("--cargo", default=os.environ.get("CARGO", "cargo"))
    parser.add_argument("--uv", default=os.environ.get("UV", "uv"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--keep-work", action="store_true")
    args = parser.parse_args()
    try:
        report = run(args)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "report": str(args.report)}, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
