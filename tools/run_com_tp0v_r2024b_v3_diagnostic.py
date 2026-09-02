"""Run a temporary, archive-only TP0V Rust/MATLAB diagnostic.

The command is deliberately a diagnostic rather than an acceptance runner. It
materializes only the two caller-supplied archives, builds the candidate root
CLI, and invokes the public ``sipi com run`` route. MATLAB is started through
the explicit R2024b Engine installation with an isolated preference directory.
No report is written below the repository and no samples are aligned,
interpolated, resampled, truncated, or delay-corrected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import subprocess
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/com-tp0v-current-asset-scoped-acceptance.v3.yaml"
SCHEMA = "sipi.com.tp0v-r2024b-v3-temp-diagnostic.v1"
MATLAB_RELEASE = "R2024b"
MAX_ARCHIVE_MEMBERS = 20_000
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
CASE_INDICES = (0, 1)
CANONICAL_SCALAR_METRICS = (
    "COM_dB",
    "CTLE_DC_gain_dB",
    "ERL",
    "FOM",
    "ICN_mV",
    "IL_dB_channel_only_at_Fnq",
    "Peak_ISI_XTK_and_Noise_interference_at_BER_mV",
    "VEC_dB",
    "VEO_mV",
    "fitted_IL_dB_at_Fnq",
    "g_DC_HP",
    "itick",
)
CROSS_SCALAR_TOLERANCE = 1.0e-9

# Keep the wrapper runnable with the explicit offline Python used to build the
# MATLAB Engine.  The manifest is a human/audit document and is validated by
# its own gate; the diagnostic repeats only the immutable input receipts here
# instead of making PyYAML a runtime dependency.
UPSTREAM_RECEIPT = {
    "commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
    "tree": "7094ab6e84989b218730c52432c70da10261f8ea",
    "archive_sha256": "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf",
    "archive_bytes": 43_694_080,
    "workbook": {
        "path": "matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA _TP0V_08_17_2022.xlsx",
        "bytes": 67_151,
        "sha256": "54562fa2bbe856f1fb6e96b7c1c873d2b399555b1fb38e50cd6f4ad3ddc69f0a",
    },
    "assets": (
        {"role": "THRU", "path": "fixtures/synthetic/thru_10db_at_26p56ghz.s4p", "bytes": 6_393_177, "sha256": "fcbcce086dbae6bbb9a1f8ca5df775073ebb6303f80a9f062caf1f2ab5607361"},
        {"role": "FEXT", "path": "fixtures/synthetic/fext_m40db_at_26p56ghz.s4p", "bytes": 6_393_140, "sha256": "cc5968bacd5bd40d6ccd7db4927dbb1dd3f20d82f4d3ad5a3193ad86e0e9ca04"},
        {"role": "NEXT", "path": "fixtures/synthetic/next_m40db_at_26p56ghz.s4p", "bytes": 6_392_860, "sha256": "882819542f43b8fb5f174c7e984b418ceb0f56e068654c9be362a84547b93e65"},
    ),
}
CANDIDATE_RECEIPT = {
    "commit": "9e8ca698beccf0561683f89649b5ec0d2441b379",
    "tree": "f01db873646763f02baf51561ab8287e10eb0869",
    "archive_sha256": "6524c1c894657e9efd0e242fe812ffe4c8e34d671e01ba12e2ea8ccaa3f07f54",
    "archive_bytes": 61_880_320,
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_manifest() -> dict[str, Any]:
    # The prep manifest is checked independently.  This runtime path keeps its
    # exact input receipts local so the offline Engine Python has no YAML
    # dependency and cannot accidentally consult a mutable working-tree file.
    return {"candidate": CANDIDATE_RECEIPT, "upstream": UPSTREAM_RECEIPT, "formal_record_absent": True}


def archive_receipt(path: Path, expected: dict[str, Any], label: str) -> dict[str, Any]:
    require(path.is_file(), f"{label} archive is missing")
    byte_count = path.stat().st_size
    digest = sha256_file(path)
    require(byte_count == expected["archive_bytes"], f"{label} archive byte drift")
    require(digest == expected["archive_sha256"], f"{label} archive hash drift")
    return {
        "commit": expected.get("commit"),
        "tree": expected.get("tree"),
        "archive_sha256": digest,
        "archive_bytes": byte_count,
        "path_redacted": True,
    }


def _safe_member_path(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    windows = PureWindowsPath(normalized)
    posix = PurePosixPath(normalized)
    require(normalized not in ("", "."), "empty archive member")
    require(not windows.is_absolute() and not posix.is_absolute(), "absolute archive member")
    require(windows.drive == "", "drive-qualified archive member")
    parts = posix.parts
    require(".." not in parts, "parent archive member")
    require(all(part not in ("", ".") for part in parts), "non-canonical archive member")
    return posix


def safe_materialize(archive: Path, destination: Path) -> dict[str, Any]:
    """Extract regular files/directories without following archive links."""
    require(not destination.exists(), "materialization destination already exists")
    destination.mkdir(parents=True)
    total = 0
    seen: set[str] = set()
    with tarfile.open(archive, "r:*") as stream:
        members = stream.getmembers()
        require(len(members) <= MAX_ARCHIVE_MEMBERS, "archive member budget exceeded")
        for member in members:
            relative = _safe_member_path(member.name)
            key = relative.as_posix()
            require(key not in seen, "duplicate archive member")
            seen.add(key)
            require(member.isdir() or member.isfile(), "non-regular archive member")
            target = (destination / Path(*relative.parts)).resolve()
            base = destination.resolve()
            require(target == base or base in target.parents, "archive member escapes destination")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            require(member.size >= 0, "negative archive member size")
            total += member.size
            require(total <= MAX_ARCHIVE_BYTES, "archive expanded byte budget exceeded")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = stream.extractfile(member)
            require(source is not None, "archive member has no payload")
            with target.open("xb") as output:
                remaining = member.size
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    require(bool(chunk), "short archive member")
                    output.write(chunk)
                    remaining -= len(chunk)
                require(source.read(1) == b"", "long archive member")
    return {"sha256": sha256_file(archive), "bytes": archive.stat().st_size, "path_redacted": True}


def inventory(root: Path) -> dict[str, tuple[int, str]]:
    result: dict[str, tuple[int, str]] = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "source archive contains a link after extraction")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            result[relative] = (path.stat().st_size, sha256_file(path))
    return result


def explicit_file(path: Path, label: str) -> Path:
    """Accept a caller-supplied file only; never fall back to PATH lookup."""
    require(path.is_file(), f"explicit {label} is missing")
    require(not path.is_dir(), f"explicit {label} is a directory")
    return path


def run_command(
    command: list[str],
    cwd: Path,
    timeout: int,
    environment: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[bytes], float]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        completed = subprocess.CompletedProcess(
            command,
            124,
            error.stdout or b"",
            error.stderr or b"",
        )
    return completed, time.perf_counter() - started


def tool_receipt(path: Path, role: str) -> dict[str, Any]:
    explicit_file(path, role)
    version_command = [str(path), "--version"] if role in {"cargo", "uv", "python"} else [str(path), "-Vv"]
    completed, _ = run_command(version_command, path.parent, 60)
    require(completed.returncode == 0, f"{role} version command failed")
    version = completed.stdout + completed.stderr
    require(version, f"{role} version output is empty")
    return {
        "role": role,
        "executable": path.name,
        "file_sha256": sha256_file(path),
        "version_sha256": sha256_bytes(version),
        "version_exit_code": completed.returncode,
        "path_redacted": True,
    }


def matlab_receipt(path: Path, root: Path) -> dict[str, Any]:
    explicit_file(path, "MATLAB R2024b executable")
    preference = root / "matlab-identity-prefdir"
    preference.mkdir()
    environment = os.environ.copy()
    environment["MATLAB_PREFDIR"] = str(preference)
    environment["MW_DISABLE_CONNECTOR"] = "1"
    environment["MATLABPATH"] = ""
    completed, _ = run_command(
        [str(path), "-batch", "disp(version('-release')); disp(version); disp(computer('arch'));"],
        path.parent,
        180,
        environment,
    )
    text = (completed.stdout + completed.stderr).decode("utf-8", "replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    require(completed.returncode == 0, "MATLAB R2024b identity command failed")
    require(lines and lines[0] == "2024b", "MATLAB release is not exactly R2024b")
    require(len(lines) >= 3 and lines[-1] == "win64", "MATLAB architecture drift")
    return {
        "role": "matlab",
        "executable": path.name,
        "release": MATLAB_RELEASE,
        "release_raw": lines[0],
        "arch": lines[-1],
        "file_sha256": sha256_file(path),
        "version_sha256": sha256_bytes(completed.stdout + completed.stderr),
        "version_exit_code": completed.returncode,
        "launch": ["-batch", "python_engine", "-noFigureWindows", "-singleCompThread"],
        "mw_disable_connector": "1",
        "isolated_preference_dir": True,
        "path_redacted": True,
    }


def _engine_source(matlab: Path) -> Path:
    source = matlab.parent.parent / "extern" / "engines" / "python"
    require((source / "setup.py").is_file(), "MATLAB Engine Python source is missing")
    return source


def prepare_engine(worker_python: Path, uv: Path, matlab: Path, root: Path) -> Path:
    source = _engine_source(matlab)
    build = root / "matlab-engine-build"
    site = build / "lib"
    if (site / "matlab" / "engine" / "_arch.txt").is_file():
        return site
    bootstrap_environment = os.environ.copy()
    bootstrap_environment["PYTHONDONTWRITEBYTECODE"] = "1"
    bootstrap, _ = run_command(
        [str(uv), "pip", "install", "--offline", "--python", str(worker_python), "setuptools", "wheel"],
        root,
        300,
        bootstrap_environment,
    )
    require(bootstrap.returncode == 0, "offline MATLAB Engine build bootstrap failed")
    build_environment = os.environ.copy()
    build_environment.pop("PYTHONPATH", None)
    build_environment["PYTHONDONTWRITEBYTECODE"] = "1"
    built, _ = run_command(
        [str(worker_python), "setup.py", "build", "--build-base", str(build)],
        source,
        300,
        build_environment,
    )
    require(built.returncode == 0, "MATLAB Engine Python build failed")
    require((site / "matlab" / "engine" / "_arch.txt").is_file(), "MATLAB Engine build output missing")
    return site


def worker_environment(source: Path, engine_site: Path, preference: Path) -> dict[str, str]:
    preference.mkdir()
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join((str(engine_site), str(source / "src")))
    environment["MATLAB_PREFDIR"] = str(preference)
    environment["MW_DISABLE_CONNECTOR"] = "1"
    environment["MATLABPATH"] = ""
    return environment


def _matlab_worker(spec_path: Path) -> None:
    import numpy as np
    import matlab.engine
    from scipy.io import savemat
    from agent_com.config import ComSettings

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    settings = ComSettings.from_xlsx(Path(spec["config"]))
    rows = settings.rows
    columns = max((len(row) for row in rows), default=0)
    require(columns > 0, "workbook has no cells")
    parameter = np.empty((len(rows), columns), dtype=object)
    slots: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        for column_index in range(columns):
            raw = row[column_index].value if column_index < len(row) else None
            if raw is None:
                value = ""
                kind = "blank"
            elif isinstance(raw, (bool, int, float, np.integer, np.floating)):
                value = float(raw)
                kind = "number"
            elif isinstance(raw, str):
                value = raw
                kind = "string"
            else:
                raise TypeError(f"unsupported workbook cell type: {type(raw).__name__}")
            parameter[row_index, column_index] = value
            slots.append({"row": row_index, "column": column_index, "kind": kind, "value": value})
    parameter_mat = Path(spec["parameter_mat"])
    savemat(parameter_mat, {"parameter": parameter}, do_compression=False, oned_as="row")
    engine = matlab.engine.start_matlab("-noFigureWindows -singleCompThread")
    try:
        engine.cd(str(Path(spec["output"]).parent), nargout=0)
        engine.addpath(str(Path(spec["harness"]).parent), nargout=0)
        engine.sipi_com_final_surface_oracle_v3(
            spec["source_root"],
            str(parameter_mat),
            spec["output"],
            float(1),
            float(1),
            spec["nonce"],
            *spec["channels"],
            nargout=0,
        )
    finally:
        engine.quit()
    logical_parameter = {"shape": [len(rows), columns], "slots": slots}
    bridge_expected = Path(spec["bridge_expected"])
    bridge_expected.write_text(
        json.dumps(logical_parameter, sort_keys=True, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
        newline="\n",
    )


def root_command(binary: Path, config: Path, thru: Path, fext: Path, next_channel: Path, output: Path) -> list[str]:
    """Construct only the public root route; direct-crate binaries are absent."""
    return [
        str(binary),
        "com",
        "run",
        "--config",
        str(config),
        "--thru",
        str(thru),
        "--fext",
        str(fext),
        "--next",
        str(next_channel),
        "--output-dir",
        str(output),
    ]


def _decode_metric(value: Any) -> Any:
    if isinstance(value, dict) and value.get("kind") == "finite" and set(value) == {"kind", "value"}:
        return value["value"]
    if isinstance(value, dict) and value.get("kind") in {"inf", "-inf", "nan"}:
        return {"inf": "+Inf", "-inf": "-Inf", "nan": "NaN"}[value["kind"]]
    return value


def matlab_cases(summary: dict[str, Any]) -> list[dict[str, Any]]:
    values = summary.get("case_metrics")
    if not isinstance(values, list):
        raise RuntimeError("MATLAB scalar summary case_metrics is not an array")
    result: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            raise RuntimeError("MATLAB scalar case is not an object")
        output = item.get("output_metrics")
        if not isinstance(output, dict):
            raise RuntimeError("MATLAB scalar output_metrics is not an object")
        result.append({str(key): _decode_metric(value) for key, value in output.items()})
    return result


def rust_cases(result: dict[str, Any]) -> list[dict[str, Any]]:
    values = result.get("cases")
    if not isinstance(values, list):
        raise RuntimeError("Rust result cases is not an array")
    output: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict) or not isinstance(item.get("metrics"), dict):
            raise RuntimeError("Rust scalar case metrics is not an object")
        output.append({str(key): _decode_metric(value) for key, value in item["metrics"].items()})
    return output


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def scalar_comparison(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare the frozen original-13 final-scalar projection only.

    Candidate-only diagnostic fields are intentionally excluded.  The 1e-9
    finite tolerance is the existing original-13 Stage-1 parity policy, not a
    newly chosen tolerance or any form of sample alignment.
    """
    comparison: list[dict[str, Any]] = []
    passed = len(left) == len(right)
    if len(left) != len(right):
        comparison.append({"case": None, "equal": False, "reason": "case_count_drift", "matlab": len(left), "rust": len(right)})
    for index, (matlab, rust) in enumerate(zip(left, right)):
        keys = CANONICAL_SCALAR_METRICS
        values: list[dict[str, Any]] = []
        for key in keys:
            if key not in matlab or key not in rust:
                equal = False
                values.append({"name": key, "equal": False, "reason": "missing_key"})
            else:
                a, b = matlab[key], rust[key]
                if _finite_number(a) and _finite_number(b):
                    difference = abs(float(a) - float(b))
                    equal = difference <= CROSS_SCALAR_TOLERANCE
                else:
                    difference = None
                    equal = type(a) is type(b) and a == b and a != "NaN"
                record: dict[str, Any] = {"name": key, "equal": equal, "matlab": a, "rust": b}
                if difference is not None:
                    record["absolute_difference"] = difference
                values.append(record)
            passed = passed and equal
        comparison.append({"case": index, "equal": all(item["equal"] for item in values), "values": values})
    return {
        "passed": passed,
        "cases": comparison,
        "metrics": list(CANONICAL_SCALAR_METRICS),
        "finite_absolute_tolerance": CROSS_SCALAR_TOLERANCE,
        "policy": "original13_final_scalar_projection_no_alignment",
    }


def bridge_comparison(expected_path: Path, observed_path: Path) -> dict[str, Any]:
    """Require MATLAB to reload the exact MAT cache produced from the XLSX."""
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    observed = json.loads(observed_path.read_text(encoding="utf-8"))
    equal = expected == observed
    return {
        "passed": equal,
        "expected_sha256": sha256_bytes(json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()),
        "observed_sha256": sha256_bytes(json.dumps(observed, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()),
        "policy": "exact_shape_row_column_kind_value_no_normalization",
    }


def d3_checkpoint_policy(matlab: list[dict[str, Any]], rust: list[dict[str, Any]]) -> dict[str, Any]:
    """Expose the owner D3 gate without substituting unrelated metrics."""
    entries = []
    for name, matlab_name, rust_name in (("COM_dB", "COM_dB", "COM_dB"), ("ERL_dB", "ERL", "ERL"), ("TD_ILN_dB", "TD_ILN_dB", "TD_ILN_dB")):
        present = all(matlab_name in item for item in matlab) and all(rust_name in item for item in rust)
        entries.append({"metric": name, "present": present, "absolute_tolerance_db": 0.1, "passed": False if not present else None})
    return {
        "checkpoint": "TP0V/current-assets/package-case",
        "alignment": "forbidden",
        "entries": entries,
        "passed": False,
        "reason": "TD_ILN_dB checkpoint unavailable" if not entries[-1]["present"] else "not_evaluated_by_diagnostic",
    }


def _channel_inputs(source: Path, manifest: dict[str, Any]) -> tuple[Path, Path, Path, dict[str, Any]]:
    assets = manifest["upstream"]["assets"]
    require([item["role"] for item in assets] == ["THRU", "FEXT", "NEXT"], "asset role/order drift")
    resolved = [source / item["path"] for item in assets]
    for item, path in zip(assets, resolved):
        require(path.is_file(), f"channel asset missing: {item['role']}")
        require(path.stat().st_size == item["bytes"] and sha256_file(path) == item["sha256"], f"channel asset drift: {item['role']}")
    return resolved[0], resolved[1], resolved[2], {
        item["role"]: {"path": item["path"], "bytes": item["bytes"], "sha256": item["sha256"]}
        for item in assets
    }


def _case_result_error(completed: subprocess.CompletedProcess[bytes], timed_seconds: float, label: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "label": label,
        "exit_code": completed.returncode,
        "wall_clock_s": timed_seconds,
        "stdout_sha256": sha256_bytes(completed.stdout or b""),
        "stderr_sha256": sha256_bytes(completed.stderr or b""),
    }


def _run_rust_case(binary: Path, source: Path, manifest: dict[str, Any], root: Path, index: int, timeout: int) -> dict[str, Any]:
    config = source / manifest["upstream"]["workbook"]["path"]
    thru, fext, next_channel, _ = _channel_inputs(source, manifest)
    output = root / "rust-output"
    command = root_command(binary, config, thru, fext, next_channel, output)
    completed, elapsed = run_command(command, source, timeout)
    record = {"case": index, "engine": "rust", "wall_clock_s": elapsed}
    if completed.returncode != 0 or not (output / "result.json").is_file():
        record.update(_case_result_error(completed, elapsed, "rust_root_route_failed"))
        return record
    result_path = output / "result.json"
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        cases = rust_cases(payload)
    except (OSError, json.JSONDecodeError, RuntimeError) as error:
        record.update({"status": "failed", "label": "rust_result_schema_failed", "error": type(error).__name__})
        return record
    record.update({
        "status": "passed",
        "result_bytes": result_path.stat().st_size,
        "result_sha256": sha256_file(result_path),
        "case_count": len(cases),
        "metrics": cases,
        "stdout_sha256": sha256_bytes(completed.stdout or b""),
        "stderr_sha256": sha256_bytes(completed.stderr or b""),
        "route": "public_root_sipi_com_run",
    })
    return record


def _run_matlab_case(worker_python: Path, engine_site: Path, harness: Path, source: Path, manifest: dict[str, Any], root: Path, index: int, timeout: int) -> dict[str, Any]:
    config = source / manifest["upstream"]["workbook"]["path"]
    thru, fext, next_channel, _ = _channel_inputs(source, manifest)
    output = root / "matlab-output"
    preference = root / "matlab-prefdir"
    spec = {
        "source_root": str(source),
        "config": str(config),
        "parameter_mat": str(root / "parameter.mat"),
        "bridge_expected": str(root / "parameter-bridge-expected.json"),
        "output": str(output),
        "harness": str(harness),
        "nonce": secrets.token_hex(32),
        "channels": [str(thru), str(fext), str(next_channel)],
    }
    spec_path = root / "engine-spec.json"
    spec_path.write_text(json.dumps(spec, sort_keys=True), encoding="utf-8", newline="\n")
    environment = worker_environment(source, engine_site, preference)
    completed, elapsed = run_command([str(worker_python), str(Path(__file__).resolve()), "--engine-worker", str(spec_path)], root, timeout, environment)
    record = {"case": index, "engine": "matlab", "wall_clock_s": elapsed}
    summary_path = output / "summary.json"
    bridge_path = output / "parameter-bridge.json"
    if completed.returncode != 0 or not summary_path.is_file() or not bridge_path.is_file():
        record.update(_case_result_error(completed, elapsed, "matlab_engine_failed"))
        return record
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        cases = matlab_cases(summary)
    except (OSError, json.JSONDecodeError, RuntimeError) as error:
        record.update({"status": "failed", "label": "matlab_result_schema_failed", "error": type(error).__name__})
        return record
    require(summary.get("matlab_release") == "R2024b", "MATLAB Engine case did not report R2024b")
    bridge = bridge_comparison(Path(spec["bridge_expected"]), bridge_path)
    record.update({
        "status": "passed",
        "summary_bytes": summary_path.stat().st_size,
        "summary_sha256": sha256_file(summary_path),
        "case_count": len(cases),
        "metrics": cases,
        "stdout_sha256": sha256_bytes(completed.stdout or b""),
        "stderr_sha256": sha256_bytes(completed.stderr or b""),
        "route": "pinned_agent_com_matlab_core_uninstrumented",
        "parameter_bridge": bridge,
    })
    return record


def _run_engine_worker(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "--engine-worker":
        return 2
    _matlab_worker(Path(argv[1]))
    return 0


def run_diagnostic(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest()
    candidate_expected = manifest["candidate"]
    upstream_expected = manifest["upstream"]
    candidate_archive = explicit_file(args.candidate_archive, "candidate archive")
    upstream_archive = explicit_file(args.upstream_archive, "upstream archive")
    candidate_receipt = archive_receipt(candidate_archive, candidate_expected, "candidate")
    upstream_receipt = archive_receipt(upstream_archive, upstream_expected, "upstream")
    require(not args.output_root.exists(), "temporary output root already exists")
    args.output_root.mkdir(parents=True)

    cargo = explicit_file(args.cargo, "cargo")
    rustc = explicit_file(args.rustc, "rustc")
    uv = explicit_file(args.uv, "uv")
    python = explicit_file(args.python, "Python")
    matlab = explicit_file(args.matlab, "MATLAB R2024b")
    toolchain = {
        "cargo": tool_receipt(cargo, "cargo"),
        "rustc": tool_receipt(rustc, "rustc"),
        "uv": tool_receipt(uv, "uv"),
        "python": tool_receipt(python, "python"),
        "matlab": matlab_receipt(matlab, args.output_root),
    }

    candidate = args.output_root / "candidate-source"
    candidate_materialized = safe_materialize(candidate_archive, candidate)
    candidate_before = inventory(candidate)
    target = args.output_root / "candidate-target"
    build_environment = os.environ.copy()
    build_environment["CARGO_TARGET_DIR"] = str(target)
    build_environment["RUSTC"] = str(rustc)
    build_environment.pop("RUSTC_WRAPPER", None)
    build_environment.pop("RUSTC_WORKSPACE_WRAPPER", None)
    build, build_elapsed = run_command(
        [str(cargo), "build", "--release", "--locked", "-p", "sipi-cli", "--features", "com-direct-integration", "--bin", "sipi"],
        candidate,
        args.timeout,
        build_environment,
    )
    require(build.returncode == 0, "candidate root CLI build failed")
    require(inventory(candidate) == candidate_before, "candidate archive changed during build")
    binary = target / "release" / ("sipi.exe" if os.name == "nt" else "sipi")
    require(binary.is_file(), "candidate root CLI binary is missing")

    upstream_base = args.output_root / "upstream-base"
    safe_materialize(upstream_archive, upstream_base)
    python_environment = args.output_root / "python-env"
    sync_environment = os.environ.copy()
    sync_environment["UV_PROJECT_ENVIRONMENT"] = str(python_environment)
    sync, sync_elapsed = run_command(
        [str(uv), "sync", "--frozen", "--offline", "--no-install-project", "--python", str(python)],
        upstream_base,
        600,
        sync_environment,
    )
    worker_python = python_environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    require(sync.returncode == 0 and worker_python.is_file(), "pinned Agent-COM Python environment failed")
    engine_site = prepare_engine(worker_python, uv, matlab, args.output_root)
    harness = candidate / "tools" / "sipi_com_final_surface_oracle_v3.m"
    require(harness.is_file(), "candidate archive MATLAB harness is missing")
    harness_receipt = {"path": "tools/sipi_com_final_surface_oracle_v3.m", "bytes": harness.stat().st_size, "sha256": sha256_file(harness)}

    records: list[dict[str, Any]] = []
    for index in CASE_INDICES:
        rust_source = args.output_root / f"rust-case-{index:02d}" / "upstream-source"
        rust_source.parent.mkdir()
        safe_materialize(upstream_archive, rust_source)
        source_before = inventory(rust_source)
        record = _run_rust_case(binary, rust_source, manifest, rust_source.parent, index, args.timeout)
        record["source_inventory_unchanged"] = inventory(rust_source) == source_before
        require(record["source_inventory_unchanged"], "Rust case changed upstream source archive")
        records.append(record)
    for index in CASE_INDICES:
        matlab_root = args.output_root / f"matlab-case-{index:02d}"
        matlab_root.mkdir()
        matlab_source = matlab_root / "upstream-source"
        safe_materialize(upstream_archive, matlab_source)
        source_before = inventory(matlab_source)
        record = _run_matlab_case(worker_python, engine_site, harness, matlab_source, manifest, matlab_root, index, args.timeout)
        record["source_inventory_unchanged"] = inventory(matlab_source) == source_before
        require(record["source_inventory_unchanged"], "MATLAB case changed upstream source archive")
        records.append(record)

    rust_records = [record for record in records if record["engine"] == "rust"]
    matlab_records = [record for record in records if record["engine"] == "matlab"]
    comparisons: list[dict[str, Any]] = []
    blockers: list[str] = []
    by_rust = {record["case"]: record for record in rust_records}
    by_matlab = {record["case"]: record for record in matlab_records}
    for index in CASE_INDICES:
        rust_record = by_rust[index]
        matlab_record = by_matlab[index]
        if rust_record.get("status") != "passed" or matlab_record.get("status") != "passed":
            blockers.append(f"case_{index}_runtime_failure")
            continue
        comparison = scalar_comparison(matlab_record["metrics"], rust_record["metrics"])
        comparison["case"] = index
        comparisons.append(comparison)
        if not comparison["passed"]:
            blockers.append(f"case_{index}_scalar_surface_drift")
        if not matlab_record["parameter_bridge"]["passed"]:
            blockers.append(f"case_{index}_mat_cache_bridge_drift")
        comparison["d3_checkpoint_policy"] = d3_checkpoint_policy(matlab_record["metrics"], rust_record["metrics"])
        if not comparison["d3_checkpoint_policy"]["passed"]:
            blockers.append(f"case_{index}_d3_checkpoint_unavailable")
        if not rust_record["wall_clock_s"] < matlab_record["wall_clock_s"]:
            blockers.append(f"case_{index}_rust_not_faster")

    status = "passed" if not blockers else "blocked"
    return {
        "schema": SCHEMA,
        "diagnostic_only": True,
        "formal_record": False,
        "status": status,
        "blockers": sorted(set(blockers)),
        "candidate": candidate_receipt,
        "upstream": upstream_receipt,
        "toolchain": toolchain,
        "harness": harness_receipt,
        "build": {"status": "passed", "wall_clock_s": build_elapsed, "stdout_sha256": sha256_bytes(build.stdout or b""), "stderr_sha256": sha256_bytes(build.stderr or b"")},
        "dependency_sync": {"status": "passed", "wall_clock_s": sync_elapsed, "stdout_sha256": sha256_bytes(sync.stdout or b""), "stderr_sha256": sha256_bytes(sync.stderr or b"")},
        "cases": records,
        "comparison": {"cases": comparisons, "policy": "frozen_original13_scalar_projection", "vector_comparison": "not_run"},
        "claims": {
            "acceptance": False,
            "release": False,
            "s_parameter_fit": False,
            "data_transform": False,
            "matlab_instrumentation": False,
            "public_root_route": True,
        },
        "non_claims": ["not_formal_evidence", "not_complete_original13", "not_plot_or_warning_parity", "not_vector_parity"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-archive", type=Path, required=True)
    parser.add_argument("--upstream-archive", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--matlab", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is not None and len(argv) == 2 and argv[0] == "--engine-worker":
        return _run_engine_worker(argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    require(args.timeout > 0, "timeout must be positive")
    require(not args.report.exists(), "report path already exists")
    report_resolved = args.report.resolve()
    root_resolved = ROOT.resolve()
    require(root_resolved not in report_resolved.parents and report_resolved != root_resolved, "report must stay outside repository")
    payload = run_diagnostic(args)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "blockers": payload["blockers"], "report_sha256": sha256_file(args.report)}, sort_keys=True))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--engine-worker":
        raise SystemExit(_run_engine_worker(sys.argv[1:]))
    raise SystemExit(main())
