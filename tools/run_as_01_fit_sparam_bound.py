"""Run one AS-01 differential replay from two immutable Git archives.

The candidate executable and the pinned Agent-Spice source are materialized
from explicit commits.  The archived preparation runner supplies the frozen
fixture and scenario set.  This tool records bounded observations only; it
never turns a mismatch into a parity or release claim.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
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
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.agent-spice-as-01-bound-replay.v1"
EXPECTED_CANDIDATE_COMMIT = "8bcfd1d1bc511461615f19338e453f0148e5dcb1"
EXPECTED_CANDIDATE_TREE = "ed221a36f2d3325b0aac3f3336a9c8a14d13e99a"
EXPECTED_UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
EXPECTED_UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
DEFAULT_UPSTREAM = Path(r"C:\Users\z3312\code\agent-spice")
ARCHIVED_PREPARATION_RUNNER = Path("tools/run_as_01_fit_sparam_oracle.py")
CRATE_MANIFEST = Path("crates/sipi-agent-spice-direct/Cargo.toml")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
PACKAGE_NAMES = ("numpy", "PyYAML", "scipy", "scikit-rf", "cvxpy")
DEFAULT_ORACLE_LOCK = ROOT / "docs" / "baselines" / "as-01-agent-spice-oracle-windows-py312.lock"
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 50_000
MAX_ARCHIVE_FILE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_TOTAL_FILE_BYTES = 512 * 1024 * 1024
CANDIDATE_INVENTORY_PATHS = (
    "Cargo.toml",
    "Cargo.lock",
    "crates/sipi-agent-spice-direct",
    "crates/sipi-channel",
    "crates/sipi-types",
    ARCHIVED_PREPARATION_RUNNER.as_posix(),
    "rust-toolchain.toml",
)
UPSTREAM_INVENTORY_PATHS = (
    "LICENSE",
    "pyproject.toml",
    "src/agent_spice/cli.py",
    "src/agent_spice/sparam/fitting.py",
    "src/agent_spice/sparam/target_fit.py",
    "src/agent_spice/sparam/io.py",
    "src/agent_spice/sparam/artifacts.py",
    "src/agent_spice/sparam/rational_lft.py",
    "src/agent_spice/sparam/y_pr.py",
)
UPSTREAM_ARCHIVE_PATHS = ("LICENSE", "pyproject.toml", "src/agent_spice")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )


def _git(root: Path, *args: str, raw: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout if raw else result.stdout.decode("ascii").strip()


def _content_binding(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    blob = subprocess.run(
        ["git", "hash-object", "--stdin"],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.decode("ascii").strip()
    try:
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        relative = path.name
    return {"path": relative, "bytes": len(payload), "sha256": _sha256(payload), "git_blob_sha1": blob}


def _commit_tree(repo: Path, revision: str) -> tuple[str, str]:
    commit = str(_git(repo, "rev-parse", f"{revision}^{{commit}}"))
    tree = str(_git(repo, "rev-parse", f"{commit}^{{tree}}"))
    return commit, tree


def _extract_archive(payload: bytes, destination: Path) -> None:
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise RuntimeError("archive byte budget exceeded")
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        members = archive.getmembers()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise RuntimeError("archive member budget exceeded")
        seen: set[str] = set()
        total_file_bytes = 0
        for member in members:
            target = (destination / member.name).resolve()
            identity = member.name.replace("\\", "/").casefold()
            if identity in seen:
                raise RuntimeError(f"archive duplicate/case-collision: {member.name}")
            seen.add(identity)
            if not (member.isfile() or member.isdir()):
                raise RuntimeError(f"archive member type is unsupported: {member.name}")
            if member.isfile():
                if member.size < 0 or member.size > MAX_ARCHIVE_FILE_BYTES:
                    raise RuntimeError(f"archive file budget exceeded: {member.name}")
                total_file_bytes += member.size
                if total_file_bytes > MAX_ARCHIVE_TOTAL_FILE_BYTES:
                    raise RuntimeError("archive extracted byte budget exceeded")
            if target != root and root not in target.parents:
                raise RuntimeError(f"archive path escapes destination: {member.name}")
        archive.extractall(destination)


def _materialize(repo: Path, revision: str, destination: Path, prefixes: Iterable[str]) -> dict[str, Any]:
    commit, tree = _commit_tree(repo, revision)
    archive_paths = tuple(prefixes)
    payload = bytes(_git(repo, "archive", "--format=tar", commit, "--", *archive_paths, raw=True))
    _extract_archive(payload, destination)
    return {
        "commit": commit,
        "tree": tree,
        "archive_sha256": _sha256(payload),
        "archive_paths": list(archive_paths),
    }


def _iter_files(root: Path, prefixes: Iterable[str]) -> Iterable[tuple[str, Path]]:
    for prefix in prefixes:
        path = root / prefix
        if path.is_file():
            yield Path(prefix).as_posix(), path
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and not child.is_symlink():
                    yield child.relative_to(root).as_posix(), child


def _inventory(root: Path, prefixes: Iterable[str]) -> dict[str, Any]:
    entries = [
        {"path": relative, "bytes": path.stat().st_size, "sha256": _sha256(path.read_bytes())}
        for relative, path in _iter_files(root, prefixes)
    ]
    entries.sort(key=lambda item: item["path"])
    return {"entries": entries, "sha256": _sha256(_canonical(entries))}


def _resolve_executable(value: str, role: str) -> Path:
    literal = Path(value)
    if literal.is_file():
        return literal.resolve()
    resolved = shutil.which(value)
    if resolved is None or not Path(resolved).is_file():
        raise RuntimeError(f"{role} executable cannot be resolved")
    return Path(resolved).resolve()


def _basename(path: Path, role: str) -> str:
    raw = os.fspath(path)
    return PureWindowsPath(raw).name or PurePosixPath(raw).name or role


def _tool_identity(path: Path, role: str, version_args: tuple[str, ...]) -> dict[str, Any]:
    version = subprocess.run(
        [str(path), *version_args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if version.returncode != 0:
        raise RuntimeError(f"{role} version command returned nonzero")
    return {
        "role": role,
        "executable": _basename(path, role),
        "path_redacted": True,
        "file_sha256": _sha256(path.read_bytes()),
        "version_exit_code": version.returncode,
        "version_output_sha256": _sha256(version.stdout + b"\0" + version.stderr),
    }


def _rustc_for(cargo: Path) -> Path:
    name = f"rustc{cargo.suffix}" if cargo.suffix else "rustc"
    sibling = cargo.with_name(name)
    return sibling.resolve() if sibling.is_file() else _resolve_executable("rustc", "rustc")


def _python_packages(python: Path) -> dict[str, Any]:
    script = """
import contextlib, hashlib, importlib.metadata as m, io, json
items = sorted(
    ({"name": (d.metadata.get("Name") or "").lower(), "version": d.version} for d in m.distributions()),
    key=lambda item: (item["name"], item["version"]),
)
config = io.StringIO()
with contextlib.redirect_stdout(config), contextlib.redirect_stderr(config):
    import numpy as np
    import scipy
    np.show_config()
    scipy.show_config()
payload = {
    "distributions": items,
    "distribution_sha256": hashlib.sha256(json.dumps(items,sort_keys=True,separators=(",", ":")).encode()).hexdigest(),
    "numeric_config_sha256": hashlib.sha256(config.getvalue().encode()).hexdigest(),
}
print(json.dumps(payload,sort_keys=True,separators=(",", ":")))
"""
    result = subprocess.run(
        [str(python), "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("Python dependency identity is unavailable")
    value = json.loads(result.stdout.decode("utf-8"))
    if not isinstance(value, dict) or set(value) != {"distributions", "distribution_sha256", "numeric_config_sha256"}:
        raise RuntimeError("Python dependency identity is incomplete")
    return value


def _toolchain(cargo_value: str, python_value: str, uv_value: str, timeout: int) -> tuple[dict[str, Any], dict[str, Path]]:
    cargo = _resolve_executable(cargo_value, "cargo")
    rustc = _rustc_for(cargo)
    python = _resolve_executable(python_value, "python")
    uv = _resolve_executable(uv_value, "uv")
    identity = {
        "cargo": _tool_identity(cargo, "cargo", ("-Vv",)),
        "rustc": _tool_identity(rustc, "rustc", ("-Vv",)),
        "python": _tool_identity(python, "python", ("-VV",)),
        "uv": _tool_identity(uv, "uv", ("--version",)),
        "timeout_seconds": timeout,
    }
    return identity, {"cargo": cargo, "rustc": rustc, "python": python, "uv": uv}


def _execution_env(rustc: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name in tuple(env):
        if name.startswith(("CARGO_", "RUST", "PYTHON")) or name in {
            "VIRTUAL_ENV",
            "UV_PROJECT_ENVIRONMENT",
            "CC",
            "CXX",
            "AR",
        }:
            env.pop(name, None)
    env["RUSTC"] = str(rustc)
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONNOUSERSITE"] = "1"
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[name] = "1"
    return env


def _binary_path(target: Path) -> Path:
    name = "sipi-agent-spice-fit-sparam.exe" if os.name == "nt" else "sipi-agent-spice-fit-sparam"
    return target / "release" / name


def _frozen_corpus(path: Path) -> tuple[str, list[dict[str, Any]], str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fixture = None
    scenarios = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "FIXTURE_TEXT" for target in node.targets):
            fixture = ast.literal_eval(node.value)
        if isinstance(node, ast.FunctionDef) and node.name == "scenario_documents":
            returned = next((item for item in node.body if isinstance(item, ast.Return)), None)
            if returned is not None:
                scenarios = ast.literal_eval(returned.value)
    if not isinstance(fixture, str) or not isinstance(scenarios, list):
        raise RuntimeError("archived preparation corpus cannot be extracted")
    scenario_sha = _sha256(_canonical(scenarios))
    return fixture, scenarios, scenario_sha


def _artifact_inventory(root: Path) -> list[dict[str, Any]]:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "input.s2p":
            entries.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path.read_bytes()),
                }
            )
    return entries


def _report_path(identifier: str) -> Path:
    return Path("out/fit_report.json") if identifier == "explicit_output_artifact_family" else Path("input_fitted_report.json")


def _fitted_path(identifier: str) -> Path:
    return Path("out/model.s2p") if identifier == "explicit_output_artifact_family" else Path("input_fitted.s2p")


def _exact_report(root: Path, identifier: str, role: str) -> dict[str, Any] | None:
    path = root / _report_path(identifier)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{role} report is not an object")
    if role == "upstream":
        return {
            "schema_version": payload.get("schema_version"),
            "target_met": payload.get("target_met"),
            "best_effort_final_mean_rms": payload.get("best_effort_final_mean_rms"),
            "best_effort_requested_order": payload.get("best_effort_requested_order"),
            "passivity_policy": payload.get("passivity_policy"),
        }
    if payload.get("schema") != "as-01-fit-sparam-result-v1":
        raise RuntimeError("candidate report schema drift")
    return {
        "schema": payload.get("schema"),
        "target_met": payload.get("target_met"),
        "rms_error": payload.get("rms_error"),
        "selected_order": payload.get("selected_order"),
        "passivity": payload.get("passivity"),
    }


def _parse_touchstone(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="ascii").splitlines()
    header = next((line.strip() for line in lines if line.strip() and not line.lstrip().startswith("!")), None)
    if header is None or not header.startswith("#"):
        raise RuntimeError(f"Touchstone header missing: {path.name}")
    tokens = header.split()
    if len(tokens) < 4 or tokens[2].upper() != "S" or tokens[3].upper() != "RI":
        raise RuntimeError(f"bounded comparison requires S RI Touchstone: {path.name}")
    scale = {"HZ": 1.0, "KHZ": 1e3, "MHZ": 1e6, "GHZ": 1e9}.get(tokens[1].upper())
    if scale is None:
        raise RuntimeError(f"Touchstone frequency unit unsupported: {path.name}")
    rows: list[tuple[float, list[complex]]] = []
    for raw in lines:
        line = raw.split("!", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        values = [float(value) for value in line.split()]
        if len(values) != 9 or not all(math.isfinite(value) for value in values):
            raise RuntimeError(f"Touchstone row is not bounded two-port RI: {path.name}")
        rows.append((values[0] * scale, [complex(values[index], values[index + 1]) for index in range(1, 9, 2)]))
    if len(rows) < 2 or any(rows[index][0] < rows[index - 1][0] for index in range(1, len(rows))):
        raise RuntimeError(f"Touchstone frequency grid invalid: {path.name}")
    frequency_bytes = b"".join(struct.pack("<d", frequency) for frequency, _ in rows)
    complex_bytes = b"".join(
        struct.pack("<dd", value.real, value.imag)
        for _, values in rows
        for value in values
    )
    return {
        "sample_count": len(rows),
        "frequency_f64_sha256": _sha256(frequency_bytes),
        "complex_ri_f64_sha256": _sha256(complex_bytes),
        "logical_sha256": _sha256(frequency_bytes + complex_bytes),
        "rows": rows,
    }


def _sigma_max(values: list[complex]) -> float:
    a, c, b, d = values
    trace = sum(abs(value) ** 2 for value in values)
    determinant = abs(a * d - b * c) ** 2
    eigenvalue = 0.5 * (trace + math.sqrt(max(0.0, trace * trace - 4.0 * determinant)))
    return math.sqrt(max(0.0, eigenvalue))


def _independent_metrics(reference: dict[str, Any], fitted: dict[str, Any]) -> dict[str, Any]:
    if [row[0] for row in reference["rows"]] != [row[0] for row in fitted["rows"]]:
        raise RuntimeError("fitted Touchstone frequency grid drift")
    squared = [
        abs(actual - expected) ** 2
        for (_, expected_row), (_, actual_row) in zip(reference["rows"], fitted["rows"], strict=True)
        for expected, actual in zip(expected_row, actual_row, strict=True)
    ]
    full_rms = math.sqrt(sum(squared) / len(squared))
    band_squared = [
        abs(actual - expected) ** 2
        for (frequency, expected_row), (_, actual_row) in zip(reference["rows"], fitted["rows"], strict=True)
        if 0.0 <= frequency <= 5.0e6
        for expected, actual in zip(expected_row, actual_row, strict=True)
    ]
    return {
        "formula": "sqrt(mean(abs(S_fit-S_input)^2_over_samples_and_four_complex_responses))",
        "full_band_rms": full_rms,
        "priority_0_to_5mhz_rms": math.sqrt(sum(band_squared) / len(band_squared)),
        "sample_grid_sigma_max": max(_sigma_max(values) for _, values in fitted["rows"]),
    }


def _touchstone_semantics(root: Path, identifier: str, reference: dict[str, Any]) -> dict[str, Any] | None:
    path = root / _fitted_path(identifier)
    if not path.is_file():
        return None
    parsed = _parse_touchstone(path)
    result = {key: value for key, value in parsed.items() if key != "rows"}
    result["path"] = _fitted_path(identifier).as_posix()
    result["independent_metrics"] = _independent_metrics(reference, parsed)
    return result


def _run_stage(
    *,
    role: str,
    scenarios: list[dict[str, Any]],
    fixture: bytes,
    root: Path,
    upstream_root: Path,
    binary: Path,
    python: Path,
    rustc: Path,
    timeout: int,
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=False)
    reference_path = root / "reference.s2p"
    reference_path.write_bytes(fixture)
    reference = _parse_touchstone(reference_path)
    reference_path.unlink()
    results = []
    isolated_script = (
        "import runpy,sys;"
        "source=sys.argv[1];args=sys.argv[2:];"
        "sys.path.insert(0,source);sys.argv=['agent-spice',*args];"
        "runpy.run_module('agent_spice.cli',run_name='__main__')"
    )
    for scenario in scenarios:
        identifier = scenario["id"]
        scenario_root = root / identifier
        scenario_root.mkdir()
        (scenario_root / "input.s2p").write_bytes(fixture)
        args = list(scenario["args"])
        if role == "upstream":
            command = [str(python), "-I", "-c", isolated_script, str(upstream_root / "src"), *args]
        else:
            command = [str(binary), *args]
        process = _run(command, cwd=scenario_root, env=_execution_env(rustc), timeout=timeout)
        result = {
            "id": identifier,
            "args": args,
            "exit_code": process.returncode,
            "stdout_sha256": _sha256(process.stdout),
            "stderr_sha256": _sha256(process.stderr),
            "artifacts": _artifact_inventory(scenario_root),
            "exact_report": _exact_report(scenario_root, identifier, role),
            "fitted_touchstone": _touchstone_semantics(scenario_root, identifier, reference),
            "coverage_note": "duplicate_of_full_band_defaults" if identifier == "target_failure_and_success" else None,
        }
        results.append(result)
    return {"role": role, "fixture_sha256": _sha256(fixture), "scenarios": results}


def _compare(upstream: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    upstream_by_id = {item["id"]: item for item in upstream["scenarios"]}
    candidate_by_id = {item["id"]: item for item in candidate["scenarios"]}
    if set(upstream_by_id) != set(candidate_by_id):
        raise RuntimeError("upstream/candidate scenario IDs differ")
    scenarios = []
    numeric_cases = []
    for identifier in sorted(upstream_by_id):
        left = upstream_by_id[identifier]
        right = candidate_by_id[identifier]
        left_summary = left.get("exact_report") or {}
        right_summary = right.get("exact_report") or {}
        upstream_rms = left_summary.get("best_effort_final_mean_rms")
        candidate_rms = right_summary.get("rms_error")
        numeric_delta = None
        if type(upstream_rms) in (int, float) and type(candidate_rms) in (int, float):
            numeric_delta = abs(float(upstream_rms) - float(candidate_rms))
            numeric_cases.append(identifier)
        scenarios.append(
            {
                "id": identifier,
                "args_equal": left.get("args") == right.get("args"),
                "exit_code_equal": left.get("returncode") == right.get("returncode"),
                "candidate_leaf_available": right.get("fitted_touchstone") is not None,
                "upstream_only_artifacts_excluded": sorted(
                    item["path"]
                    for item in left.get("artifacts", [])
                    if item["path"].endswith((".sp", ".rfm", ".html"))
                ),
                "upstream_summary": left_summary,
                "candidate_summary": right_summary,
                "upstream_fitted_touchstone": left.get("fitted_touchstone"),
                "candidate_fitted_touchstone": right.get("fitted_touchstone"),
                "rms_abs_delta": numeric_delta,
                "coverage_note": left.get("coverage_note"),
            }
        )
    numeric_parity = bool(numeric_cases) and all(item["rms_abs_delta"] == 0.0 for item in scenarios if item["id"] in numeric_cases)
    common_leaf = [item for item in scenarios if item["candidate_leaf_available"]]
    common_leaf_exit_equal = bool(common_leaf) and all(item["args_equal"] and item["exit_code_equal"] for item in common_leaf)
    observation = {
        "scenario_count": len(scenarios),
        "numeric_cases": numeric_cases,
        "numeric_parity": numeric_parity,
        "complete_contract_parity_claim": False,
        "common_leaf_exit_equal": common_leaf_exit_equal,
        "numeric_mismatch_open": not numeric_parity,
        "acceptance_tolerance": None,
        "scenarios": scenarios,
    }
    observation["sha256"] = _sha256(_canonical(observation))
    return observation


def run(args: argparse.Namespace) -> dict[str, Any]:
    candidate_repo = args.candidate_repo.resolve()
    upstream_repo = args.upstream_repo.resolve()
    candidate_commit, candidate_tree = _commit_tree(candidate_repo, args.candidate_commit)
    upstream_commit, upstream_tree = _commit_tree(upstream_repo, args.upstream_commit)
    if (candidate_commit, candidate_tree) != (EXPECTED_CANDIDATE_COMMIT, EXPECTED_CANDIDATE_TREE):
        raise RuntimeError("candidate commit/tree is not the frozen AS-01 preparation source")
    if (upstream_commit, upstream_tree) != (EXPECTED_UPSTREAM_COMMIT, EXPECTED_UPSTREAM_TREE):
        raise RuntimeError("upstream commit/tree is not the pinned Agent-Spice source")
    if args.timeout_seconds <= 0:
        raise RuntimeError("timeout must be positive")
    if args.timeout_seconds > 3_600:
        raise RuntimeError("timeout exceeds the 3600 second replay budget")
    if RUN_ID.fullmatch(args.run_id) is None or ".." in args.run_id:
        raise RuntimeError("run ID must be a bounded path-free identifier")
    fresh_nonce = secrets.token_hex(32)
    oracle_lock = args.oracle_lock.resolve()
    if not oracle_lock.is_file():
        raise RuntimeError("oracle dependency lock is missing")
    lock_bytes = oracle_lock.read_bytes()
    if b"--hash=sha256:" not in lock_bytes:
        raise RuntimeError("oracle dependency lock has no wheel hashes")
    toolchain, tools = _toolchain(args.cargo, args.python, args.uv, args.timeout_seconds)
    parent = args.work_root.resolve() if args.work_root else Path(tempfile.mkdtemp(prefix="sipi-as01-bound-"))
    parent.mkdir(parents=True, exist_ok=True)
    run_root = parent / args.run_id
    if run_root.exists():
        raise RuntimeError(f"run root already exists: {run_root}")
    run_root.mkdir()
    candidate_root = run_root / "candidate"
    upstream_root = run_root / "upstream"
    candidate_info = _materialize(candidate_repo, candidate_commit, candidate_root, CANDIDATE_INVENTORY_PATHS)
    upstream_info = _materialize(upstream_repo, upstream_commit, upstream_root, UPSTREAM_ARCHIVE_PATHS)
    candidate_info["inventory"] = _inventory(candidate_root, CANDIDATE_INVENTORY_PATHS)
    candidate_info["cargo_lock_sha256"] = _sha256((candidate_root / "crates/sipi-agent-spice-direct/Cargo.lock").read_bytes())
    upstream_info["inventory"] = _inventory(upstream_root, UPSTREAM_INVENTORY_PATHS)
    upstream_info["license_sha256"] = _sha256((upstream_root / "LICENSE").read_bytes())

    target = run_root / "target"
    env = _execution_env(tools["rustc"])
    env["CARGO_TARGET_DIR"] = str(target)
    env["CARGO_ENCODED_RUSTFLAGS"] = "\x1f".join(
        (
            f"--remap-path-prefix={candidate_root}=/sipi-candidate",
            f"--remap-path-prefix={target}=/sipi-target",
            "-Cmetadata=as01-bound",
            "-Clink-arg=/Brepro",
        )
    )
    env["CARGO_INCREMENTAL"] = "0"
    env["SOURCE_DATE_EPOCH"] = "0"
    build = _run(
        [
            str(tools["cargo"]),
            "build",
            "--manifest-path",
            str(candidate_root / CRATE_MANIFEST),
            "--release",
            "--locked",
        ],
        cwd=candidate_root,
        env=env,
        timeout=args.timeout_seconds,
    )
    binary = _binary_path(target)
    build_summary = {
        "exit_code": build.returncode,
        "stdout_sha256": _sha256(build.stdout),
        "stderr_sha256": _sha256(build.stderr),
        "binary_present": binary.is_file(),
        "binary_bytes": binary.stat().st_size if binary.is_file() else None,
        "binary_sha256": _sha256(binary.read_bytes()) if binary.is_file() else None,
        "reproducibility": {
            "candidate_prefix": "/sipi-candidate",
            "target_prefix": "/sipi-target",
            "cargo_incremental": False,
            "source_date_epoch": 0,
            "rustc_metadata": "as01-bound",
            "link_reproducible": True,
        },
    }
    if build.returncode != 0 or not binary.is_file():
        raise RuntimeError("candidate archive build failed")

    oracle_venv = run_root / "oracle-venv"
    venv = _run(
        [
            str(tools["uv"]),
            "--no-config",
            "venv",
            "--python",
            str(tools["python"]),
            str(oracle_venv),
        ],
        cwd=run_root,
        env=_execution_env(tools["rustc"]),
        timeout=args.timeout_seconds,
    )
    runtime_python = oracle_venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv.returncode != 0 or not runtime_python.is_file():
        raise RuntimeError("isolated oracle venv creation failed")
    sync = _run(
        [
            str(tools["uv"]),
            "--no-config",
            "pip",
            "sync",
            "--python",
            str(runtime_python),
            "--require-hashes",
            "--strict",
            str(oracle_lock),
        ],
        cwd=run_root,
        env=_execution_env(tools["rustc"]),
        timeout=args.timeout_seconds,
    )
    if sync.returncode != 0:
        raise RuntimeError("hashed oracle dependency sync failed")
    oracle_environment = {
        "lock": {
            "path": oracle_lock.name,
            "bytes": len(lock_bytes),
            "sha256": _sha256(lock_bytes),
            "require_hashes": True,
        },
        "venv": {
            "exit_code": venv.returncode,
        },
        "sync": {
            "exit_code": sync.returncode,
        },
        "runtime_python": _tool_identity(runtime_python, "oracle_python", ("-VV",)),
        "installed": _python_packages(runtime_python),
        "isolation": {
            "isolated_flag": "-I",
            "python_no_user_site": True,
            "python_path_cleared": True,
            "python_home_cleared": True,
            "virtual_env_cleared": True,
            "numeric_threads": 1,
        },
    }

    fixture_text, scenarios, scenario_sha = _frozen_corpus(candidate_root / ARCHIVED_PREPARATION_RUNNER)
    fixture = fixture_text.encode("ascii")
    upstream = _run_stage(
        role="upstream",
        scenarios=scenarios,
        fixture=fixture,
        root=run_root / "upstream-output",
        upstream_root=upstream_root,
        binary=binary,
        python=runtime_python,
        rustc=tools["rustc"],
        timeout=args.timeout_seconds,
    )
    candidate = _run_stage(
        role="candidate",
        scenarios=scenarios,
        fixture=fixture,
        root=run_root / "candidate-output",
        upstream_root=upstream_root,
        binary=binary,
        python=runtime_python,
        rustc=tools["rustc"],
        timeout=args.timeout_seconds,
    )
    comparison = _compare(upstream, candidate)
    if len(upstream["scenarios"]) != 10 or len(candidate["scenarios"]) != 10:
        raise RuntimeError("archived preparation corpus is incomplete")
    status = "completed_numeric_mismatch" if comparison["numeric_mismatch_open"] else "completed_no_numeric_mismatch_unreviewed"
    report = {
        "schema": SCHEMA,
        "status": status,
        "custody_valid": True,
        "parity_claim": False,
        "numeric_mismatch_open": comparison["numeric_mismatch_open"],
        "run_id": args.run_id,
        "fresh_run_nonce": fresh_nonce,
        "source_mode": "candidate_and_upstream_git_archive_at_immutable_commit",
        "harness_source_mode": "content_addressed_worktree_file_pending_owner_commit",
        "bound_runner": _content_binding(Path(__file__)),
        "bound_oracle_lock": _content_binding(oracle_lock),
        "candidate": candidate_info,
        "upstream": upstream_info,
        "archived_preparation_runner": {
            "path": ARCHIVED_PREPARATION_RUNNER.as_posix(),
            "sha256": _sha256((candidate_root / ARCHIVED_PREPARATION_RUNNER).read_bytes()),
        },
        "scenario_set_sha256": scenario_sha,
        "fixture_sha256": upstream.get("fixture_sha256"),
        "toolchain": toolchain,
        "oracle_environment": oracle_environment,
        "build": build_summary,
        "replay": {"upstream": upstream, "candidate": candidate},
        "comparison": comparison,
        "non_claims": [
            "The observed numerical and command/artifact mismatches remain open.",
            "Artifact content parity is not claimed by this bounded observation.",
            "The two-port fixed-pole leaf is not complete fit-sparam parity.",
            "Sampled passivity is not continuous passivity enforcement or certification.",
            "This report is not acceptance, release approval, license admission, or product capability promotion.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    if args.work_root is None and not args.keep_work:
        shutil.rmtree(parent, ignore_errors=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--candidate-commit", default=EXPECTED_CANDIDATE_COMMIT)
    parser.add_argument("--upstream-repo", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--upstream-commit", default=EXPECTED_UPSTREAM_COMMIT)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--cargo", default=os.environ.get("CARGO", "cargo"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--uv", default=os.environ.get("UV", "uv"))
    parser.add_argument("--oracle-lock", type=Path, default=DEFAULT_ORACLE_LOCK)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--keep-work", action="store_true")
    args = parser.parse_args()
    try:
        report = run(args)
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "report": args.report.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
