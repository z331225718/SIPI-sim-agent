"""Measure the existing Agent-Spice RFM response kernel against MATLAB.

The comparison is deliberately narrow: both implementations parse the same
existing ``VERSION 200600`` RFM input once, then evaluate the same pole/residue
formula on the same frequency grid. It does not compare two SPICE solvers and
does not enable any S-parameter fitting path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = ROOT / "tools" / "as_performance_rfm_kernel_bench"
RUST_MANIFEST = BENCHMARK_DIR / "Cargo.toml"
RUST_RFM_SOURCE = ROOT / "crates" / "sipi-agent-spice-direct" / "src" / "as06_run_rfm.rs"
MATLAB_HARNESS = BENCHMARK_DIR / "as_performance_rfm_kernel_bench.m"
DEFAULT_RFM = ROOT / "examples" / "circuit" / "rfm-deck" / "models" / "channel.rfm"
DEFAULT_MATLAB = Path(r"C:\Program Files\MATLAB\R2024b\bin\matlab.exe")
DEFAULT_CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
DEFAULT_RUSTC = Path.home() / ".cargo" / "bin" / "rustc.exe"
DEFAULT_PYTHON = Path(r"C:\Users\z3312\code\agent-spice\.venv\Scripts\python.exe")
DEFAULT_UPSTREAM = Path(r"C:\Users\z3312\code\agent-spice")
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_FREQUENCY_COUNT = 2_000_000


class BenchmarkError(RuntimeError):
    """Raised when a benchmark run cannot be made reproducible."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_regular(path: Path, label: str) -> Path:
    path = path.expanduser().resolve(strict=True)
    info = path.stat()
    if not path.is_file() or path.is_symlink():
        raise BenchmarkError(f"{label} must be a regular file")
    if info.st_size <= 0:
        raise BenchmarkError(f"{label} must not be empty")
    return path


def resolve_executable(raw: Path, label: str) -> Path:
    candidate = raw.expanduser()
    if not candidate.is_file():
        found = shutil.which(str(raw))
        if found is None:
            raise BenchmarkError(f"{label} executable not found")
        candidate = Path(found)
    return require_regular(candidate, label)


def bounded_run(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: int,
) -> tuple[subprocess.CompletedProcess[bytes], int]:
    started = time.perf_counter_ns()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        process.kill()
        stdout, stderr = process.communicate()
        raise BenchmarkError(f"benchmark process timed out: {command[0]}") from error
    elapsed = time.perf_counter_ns() - started
    if len(stdout) > MAX_OUTPUT_BYTES or len(stderr) > MAX_OUTPUT_BYTES:
        raise BenchmarkError(f"benchmark process output exceeded the bounded budget: {command[0]}")
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr), elapsed


def version_identity(path: Path, args: tuple[str, ...], label: str) -> dict[str, Any]:
    environment = dict(os.environ)
    result, _ = bounded_run([str(path), *args], cwd=ROOT, environment=environment, timeout=60)
    if result.returncode != 0:
        raise BenchmarkError(f"{label} version command failed")
    version_bytes = result.stdout + b"\0" + result.stderr
    return {
        "role": label,
        "executable": path.name,
        "path_redacted": True,
        "file_sha256": sha256_file(path),
        "version_sha256": hashlib.sha256(version_bytes).hexdigest(),
        "version_exit": result.returncode,
    }


def matlab_identity(path: Path) -> dict[str, Any]:
    pref = Path(os.environ.get("TEMP", ".")) / f"as-rfm-matlab-pref-{os.getpid()}-{time.time_ns()}"
    pref.mkdir(parents=True, exist_ok=False)
    environment = dict(os.environ)
    environment["MATLAB_PREFDIR"] = str(pref)
    environment["MW_DISABLE_CONNECTOR"] = "1"
    result, _ = bounded_run(
        [str(path), "-batch", "disp(version)"],
        cwd=ROOT,
        environment=environment,
        timeout=120,
    )
    version_text = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    if result.returncode != 0 or "R2024b" not in version_text:
        raise BenchmarkError("MATLAB R2024b identity check failed")
    return {
        "role": "matlab",
        "executable": path.name,
        "path_redacted": True,
        "file_sha256": sha256_file(path),
        "version_sha256": hashlib.sha256(result.stdout + b"\0" + result.stderr).hexdigest(),
        "version_exit": result.returncode,
        "release": "R2024b",
        "launch_mode": "-batch with isolated MATLAB_PREFDIR and MW_DISABLE_CONNECTOR=1",
    }


def escape_matlab_literal(value: Path) -> str:
    return str(value).replace("'", "''")


def load_report(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BenchmarkError(f"{label} report is not valid JSON") from error
    if not isinstance(value, dict) or value.get("schema") != "sipi.as-performance-rfm-kernel.v1" or value.get("status") != "observed":
        raise BenchmarkError(f"{label} report schema/status is invalid")
    return value


def numeric(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise BenchmarkError(f"{label} is not finite")
    return float(value)


def validate_report(report: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    workload = report.get("workload")
    if not isinstance(workload, dict):
        raise BenchmarkError(f"{label} workload is missing")
    if workload.get("frequency_count") != expected["frequency_count"] or workload.get("response_count") != expected["response_count"]:
        raise BenchmarkError(f"{label} workload shape drift")
    if abs(numeric(workload.get("fmax_hz"), f"{label} fmax") - expected["fmax_hz"]) > 0.0:
        raise BenchmarkError(f"{label} fmax drift")
    timings = report.get("durations_ns")
    if timings is not None:
        valid_timings = isinstance(timings, list) and len(timings) == expected["repetitions"] and all(
            type(item) is int and item > 0 for item in timings
        )
    else:
        seconds = report.get("durations_seconds")
        valid_timings = isinstance(seconds, list) and len(seconds) == expected["repetitions"] and all(
            isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(float(item)) and float(item) > 0.0
            for item in seconds
        )
    if not valid_timings:
        raise BenchmarkError(f"{label} timing samples are invalid")
    if report.get("warmup_completed") is not True:
        raise BenchmarkError(f"{label} warmup did not complete")
    checksum = report.get("checksum")
    if not isinstance(checksum, dict):
        raise BenchmarkError(f"{label} checksum is missing")
    for field in ("sum_real", "sum_imag", "sum_abs_squared", "first_re", "first_im"):
        numeric(checksum.get(field), f"{label} checksum.{field}")


def checksum_delta(left: dict[str, Any], right: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for field in ("sum_real", "sum_imag", "sum_abs_squared", "first_re", "first_im"):
        result[field] = abs(numeric(left[field], field) - numeric(right[field], field))
    return result


def within_tolerance(delta: dict[str, float], left: dict[str, Any], right: dict[str, Any]) -> bool:
    for field, difference in delta.items():
        scale = max(1.0, abs(numeric(left[field], field)), abs(numeric(right[field], field)))
        if difference > 2.0e-12 * scale:
            return False
    return True


def run_rust(
    executable: Path,
    rfm: Path,
    report: Path,
    *,
    frequency_count: int,
    fmax_hz: float,
    warmups: int,
    repetitions: int,
    environment: dict[str, str],
) -> tuple[dict[str, Any], int]:
    command = [
        str(executable),
        "--rfm",
        str(rfm),
        "--output",
        str(report),
        "--frequency-count",
        str(frequency_count),
        "--fmax-hz",
        format(fmax_hz, ".17g"),
        "--warmups",
        str(warmups),
        "--repetitions",
        str(repetitions),
    ]
    result, elapsed = bounded_run(command, cwd=ROOT, environment=environment, timeout=600)
    if result.returncode != 0:
        raise BenchmarkError("Rust benchmark failed: " + result.stderr.decode("utf-8", errors="replace")[-1000:])
    return load_report(report, "Rust"), elapsed


def run_matlab(
    executable: Path,
    rfm: Path,
    report: Path,
    *,
    frequency_count: int,
    fmax_hz: float,
    warmups: int,
    repetitions: int,
    environment: dict[str, str],
) -> tuple[dict[str, Any], int]:
    pref = Path(environment.get("TEMP", ".")) / f"as-rfm-matlab-pref-run-{os.getpid()}-{time.time_ns()}"
    pref.mkdir(parents=True, exist_ok=False)
    run_environment = dict(environment)
    run_environment["MATLAB_PREFDIR"] = str(pref)
    run_environment["MW_DISABLE_CONNECTOR"] = "1"
    expression = (
        "addpath('"
        + escape_matlab_literal(MATLAB_HARNESS.parent)
        + "'); as_performance_rfm_kernel_bench('"
        + escape_matlab_literal(rfm)
        + "','"
        + escape_matlab_literal(report)
        + "',"
        + str(frequency_count)
        + ","
        + format(fmax_hz, ".17g")
        + ","
        + str(warmups)
        + ","
        + str(repetitions)
        + ")"
    )
    result, elapsed = bounded_run([str(executable), "-batch", expression], cwd=ROOT, environment=run_environment, timeout=600)
    if result.returncode != 0:
        raise BenchmarkError("MATLAB benchmark failed: " + result.stderr.decode("utf-8", errors="replace")[-1000:])
    return load_report(report, "MATLAB"), elapsed


def run_upstream(
    python: Path,
    upstream: Path,
    rfm: Path,
    report: Path,
    *,
    frequency_count: int,
    fmax_hz: float,
    warmups: int,
    repetitions: int,
    environment: dict[str, str],
) -> tuple[dict[str, Any], int]:
    run_environment = dict(environment)
    old_pythonpath = run_environment.get("PYTHONPATH")
    run_environment["PYTHONPATH"] = str(upstream / "src") + (os.pathsep + old_pythonpath if old_pythonpath else "")
    command = [
        str(python),
        str(ROOT / "tools" / "as_performance_upstream_rfm_kernel.py"),
        "--rfm",
        str(rfm),
        "--output",
        str(report),
        "--frequency-count",
        str(frequency_count),
        "--fmax-hz",
        format(fmax_hz, ".17g"),
        "--warmups",
        str(warmups),
        "--repetitions",
        str(repetitions),
    ]
    result, elapsed = bounded_run(command, cwd=upstream, environment=run_environment, timeout=600)
    if result.returncode != 0:
        raise BenchmarkError("upstream Python benchmark failed: " + result.stderr.decode("utf-8", errors="replace")[-1000:])
    return load_report(report, "upstream Python"), elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rfm", type=Path, default=DEFAULT_RFM)
    parser.add_argument("--upstream-repo", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--matlab", type=Path, default=DEFAULT_MATLAB)
    parser.add_argument("--cargo", type=Path, default=DEFAULT_CARGO)
    parser.add_argument("--rustc", type=Path, default=DEFAULT_RUSTC)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--frequency-count", type=int, default=262_144)
    parser.add_argument("--fmax-hz", type=float, default=200.0e9)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repetitions", type=int, default=7)
    args = parser.parse_args()
    if not (1 <= args.frequency_count <= MAX_FREQUENCY_COUNT) or not (0 <= args.warmups <= 100) or not (1 <= args.repetitions <= 100):
        parser.error("frequency-count/warmups/repetitions are outside the bounded range")
    if not isinstance(args.fmax_hz, float) or not math.isfinite(args.fmax_hz) or args.fmax_hz <= 0.0:
        parser.error("fmax-hz must be finite and positive")
    output_root = args.output_root.expanduser().resolve()
    if output_root.exists():
        parser.error("output-root must not already exist")
    if output_root == ROOT or ROOT in output_root.parents:
        parser.error("output-root must be outside the repository")
    output_root.mkdir(parents=True)

    rfm = require_regular(args.rfm, "RFM input")
    upstream = args.upstream_repo.expanduser().resolve()
    if not upstream.is_dir() or not (upstream / ".git").exists():
        parser.error("upstream-repo must be a Git checkout")
    rustc = resolve_executable(args.rustc, "rustc")
    cargo = resolve_executable(args.cargo, "cargo")
    python = resolve_executable(args.python, "Python")
    matlab = resolve_executable(args.matlab, "MATLAB")
    environment = dict(os.environ)
    environment.pop("RUSTC_WRAPPER", None)
    environment.pop("RUSTC_WORKSPACE_WRAPPER", None)
    rust_target = output_root / "cargo-target"
    build_environment = dict(environment)
    build_environment["CARGO_TARGET_DIR"] = str(rust_target)
    build, _ = bounded_run(
        [str(cargo), "build", "--release", "--locked", "--manifest-path", str(RUST_MANIFEST)],
        cwd=ROOT,
        environment=build_environment,
        timeout=1800,
    )
    if build.returncode != 0:
        raise BenchmarkError("Rust benchmark harness build failed: " + build.stderr.decode("utf-8", errors="replace")[-2000:])
    rust_executable = rust_target / "release" / ("as-performance-rfm-kernel-bench.exe" if os.name == "nt" else "as-performance-rfm-kernel-bench")
    rust_executable = require_regular(rust_executable, "Rust benchmark")

    expected = {
        "frequency_count": args.frequency_count,
        "fmax_hz": args.fmax_hz,
        "response_count": 0,
        "repetitions": args.repetitions,
    }
    # The response count is read from the Rust report after the shared model
    # has been parsed; subsequent engines must match it exactly.
    rust_report, rust_launch_ns = run_rust(
        rust_executable,
        rfm,
        output_root / "rust.json",
        frequency_count=args.frequency_count,
        fmax_hz=args.fmax_hz,
        warmups=args.warmups,
        repetitions=args.repetitions,
        environment=environment,
    )
    rust_input = rust_report.get("input")
    rust_workload = rust_report.get("workload")
    if not isinstance(rust_input, dict) or not isinstance(rust_workload, dict):
        raise BenchmarkError("Rust report input/workload is invalid")
    expected["response_count"] = rust_workload.get("response_count")
    if not isinstance(expected["response_count"], int) or expected["response_count"] <= 0:
        raise BenchmarkError("Rust response count is invalid")
    validate_report(rust_report, expected, "Rust")

    matlab_report, matlab_launch_ns = run_matlab(
        matlab,
        rfm,
        output_root / "matlab.json",
        frequency_count=args.frequency_count,
        fmax_hz=args.fmax_hz,
        warmups=args.warmups,
        repetitions=args.repetitions,
        environment=environment,
    )
    validate_report(matlab_report, expected, "MATLAB")
    upstream_report, upstream_launch_ns = run_upstream(
        python,
        upstream,
        rfm,
        output_root / "upstream-python.json",
        frequency_count=args.frequency_count,
        fmax_hz=args.fmax_hz,
        warmups=args.warmups,
        repetitions=args.repetitions,
        environment=environment,
    )
    validate_report(upstream_report, expected, "upstream Python")

    rust_checksum = rust_report["checksum"]
    matlab_checksum = matlab_report["checksum"]
    upstream_checksum = upstream_report["checksum"]
    assert isinstance(rust_checksum, dict) and isinstance(matlab_checksum, dict) and isinstance(upstream_checksum, dict)
    matlab_delta = checksum_delta(rust_checksum, matlab_checksum)
    upstream_delta = checksum_delta(rust_checksum, upstream_checksum)
    if not within_tolerance(matlab_delta, rust_checksum, matlab_checksum):
        raise BenchmarkError(f"Rust/MATLAB kernel output drift exceeds comparison tolerance: {matlab_delta}")
    if not within_tolerance(upstream_delta, rust_checksum, upstream_checksum):
        raise BenchmarkError(f"Rust/upstream Python kernel output drift exceeds comparison tolerance: {upstream_delta}")

    rust_median_ns = int(rust_report["median_ns"])
    matlab_median_ns = int(round(float(matlab_report["median_seconds"]) * 1.0e9))
    upstream_median_ns = int(upstream_report["median_ns"])
    if rust_median_ns <= 0 or matlab_median_ns <= 0 or upstream_median_ns <= 0:
        raise BenchmarkError("kernel median is invalid")
    report = {
        "schema": "sipi.as-performance-rfm-comparison.v1",
        "status": "observed",
        "comparison_scope": "same_rfm_pole_residue_frequency_kernel",
        "timing_scope": "kernel_medians_exclude_parse_process_launch_filesystem_and_json_serialization",
        "timing_clock": {"rust": "std::time::Instant", "matlab": "tic/toc", "upstream_python": "time.perf_counter_ns"},
        "input": {
            "file_name": rfm.name,
            "sha256": sha256_file(rfm),
            "bytes": rfm.stat().st_size,
            "nports": rust_input.get("nports"),
            "stored_poles": rust_input.get("stored_poles"),
            "effective_order": rust_input.get("effective_order"),
        },
        "workload": {
            "frequency_count": args.frequency_count,
            "fmax_hz": args.fmax_hz,
            "response_count": expected["response_count"],
            "warmup_count": args.warmups,
            "repetition_count": args.repetitions,
        },
        "engines": {
            "rust": {
                "kernel_median_ns": rust_median_ns,
                "kernel_durations_ns": rust_report["durations_ns"],
                "launch_elapsed_ns": rust_launch_ns,
                "executable": rust_executable.name,
                "executable_sha256": sha256_file(rust_executable),
                "rayon_threads": rust_report.get("execution", {}).get("rayon_threads")
                if isinstance(rust_report.get("execution"), dict)
                else None,
                "report_file": "rust.json",
            },
            "matlab": {
                "kernel_median_ns": matlab_median_ns,
                "kernel_durations_ns": [int(round(float(value) * 1.0e9)) for value in matlab_report["durations_seconds"]],
                "launch_elapsed_ns": matlab_launch_ns,
                "executable": matlab.name,
                "executable_sha256": sha256_file(matlab),
                "report_file": "matlab.json",
            },
            "upstream_python": {
                "kernel_median_ns": upstream_median_ns,
                "kernel_durations_ns": upstream_report["durations_ns"],
                "launch_elapsed_ns": upstream_launch_ns,
                "executable": python.name,
                "executable_sha256": sha256_file(python),
                "report_file": "upstream-python.json",
            },
        },
        "ratios": {
            "rust_over_matlab_kernel": rust_median_ns / matlab_median_ns,
            "matlab_over_rust_kernel": matlab_median_ns / rust_median_ns,
            "rust_over_upstream_python_kernel": rust_median_ns / upstream_median_ns,
            "rust_over_matlab_end_to_end": rust_launch_ns / matlab_launch_ns,
        },
        "output_comparison": {
            "rust_matlab_checksum_abs_delta": matlab_delta,
            "rust_upstream_python_checksum_abs_delta": upstream_delta,
            "within_numeric_tolerance": True,
        },
        "toolchain": {
            "cargo": version_identity(cargo, ("--version",), "cargo"),
            "rustc": version_identity(rustc, ("-Vv",), "rustc"),
            "python": version_identity(python, ("--version",), "python"),
            "matlab": matlab_identity(matlab),
        },
        "host": {
            "logical_cpu_count": os.cpu_count(),
        },
        "source": {
            "runner": {"file": "tools/benchmark_as_rfm_matlab.py", "sha256": sha256_file(Path(__file__))},
            "matlab_harness": {"file": "tools/as_performance_rfm_kernel_bench/as_performance_rfm_kernel_bench.m", "sha256": sha256_file(MATLAB_HARNESS)},
            "rust_manifest": {"file": "tools/as_performance_rfm_kernel_bench/Cargo.toml", "sha256": sha256_file(RUST_MANIFEST)},
            "rust_source": {"file": "tools/as_performance_rfm_kernel_bench/src/main.rs", "sha256": sha256_file(BENCHMARK_DIR / "src" / "main.rs")},
            "rust_rfm_source": {"file": "crates/sipi-agent-spice-direct/src/as06_run_rfm.rs", "sha256": sha256_file(RUST_RFM_SOURCE)},
            "upstream_script": {"file": "tools/as_performance_upstream_rfm_kernel.py", "sha256": sha256_file(ROOT / "tools" / "as_performance_upstream_rfm_kernel.py")},
        },
        "limitations": [
            "This is a kernel comparison, not a full MATLAB SPICE solver comparison.",
            "MATLAB uses the repository benchmark harness to evaluate the same RFM formula; no MATLAB product route consumes RFM directly.",
            "No S-parameter fitting, Xyce/XDM, or new simulation capability is exercised.",
            "One Windows host, one existing RFM fixture, and one fixed frequency grid; no performance acceptance threshold is asserted.",
            "Launch elapsed time is reported separately and includes process startup; it is not used as the kernel parity gate.",
        ],
        "claims": {
            "rust_matlab_kernel_numeric_agreement": True,
            "rust_faster_than_matlab": rust_median_ns < matlab_median_ns,
            "performance_acceptance": False,
            "release": False,
            "s_parameter_fit": False,
            "as05_xyce_xdm": False,
        },
    }
    (output_root / "comparison.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output_root), "ratios": report["ratios"], "claims": report["claims"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BenchmarkError as error:
        print(f"benchmark blocked: {error}", file=sys.stderr)
        raise SystemExit(2)
