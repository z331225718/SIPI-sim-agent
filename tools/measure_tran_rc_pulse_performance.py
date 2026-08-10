"""Observe the fixed Rust RC/PULSE CLI workload on Windows without setting a budget."""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = "sipi.tran.performance-observation.v1"
PROFILE_ID = "tran-rc-pulse-v1"
REQUEST_SCHEMA = "sipi.tran.rc-pulse-request.v1"
WARMUP_COUNT = 3
MEASURED_COUNT = 10
REQUEST = (
    b'{"schema":"sipi.tran.rc-pulse-request.v1","request_id":"rc-pulse-1",'
    b'"resistance_ohms":1000.0,"capacitance_farads":0.000001,'
    b'"initial_voltage_out_volts":0.0,"output_times_seconds":'
    b'[0.0,0.000001,0.000002,0.000003],"pulse":{"voltage_low_volts":0.0,'
    b'"voltage_high_volts":1.0,"delay_seconds":0.000001,'
    b'"rise_seconds":0.000000001,"fall_seconds":0.000000001,'
    b'"width_seconds":0.00001,"period_seconds":0.00002}}'
)


class MeasurementError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def _external(path: Path) -> bool:
    resolved = path.resolve()
    return resolved != ROOT and ROOT not in resolved.parents


def scrubbed_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for key in list(environment):
        upper = key.upper()
        if upper in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"} or upper.startswith("CONDA_"):
            environment.pop(key, None)
    return environment


def peak_working_set_bytes(process: subprocess.Popen[bytes]) -> int:
    if platform.system() != "Windows":
        raise MeasurementError("windows_required")

    class ProcessMemoryCountersEx(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("page_fault_count", wintypes.DWORD),
            ("peak_working_set_size", ctypes.c_size_t),
            ("working_set_size", ctypes.c_size_t),
            ("quota_peak_paged_pool_usage", ctypes.c_size_t),
            ("quota_paged_pool_usage", ctypes.c_size_t),
            ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
            ("quota_non_paged_pool_usage", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
            ("private_usage", ctypes.c_size_t),
        ]

    handle = getattr(process, "_handle", None)
    if not isinstance(handle, int) or handle == 0:
        raise MeasurementError("process_handle_unavailable")
    counters = ProcessMemoryCountersEx()
    counters.cb = ctypes.sizeof(counters)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    get_process_memory_info = psapi.GetProcessMemoryInfo
    get_process_memory_info.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    get_process_memory_info.restype = wintypes.BOOL
    if not get_process_memory_info(handle, ctypes.byref(counters), counters.cb):
        raise MeasurementError("peak_working_set_unavailable")
    if counters.peak_working_set_size <= 0:
        raise MeasurementError("peak_working_set_invalid")
    return int(counters.peak_working_set_size)


def _invoke(executable: Path, run_root: Path) -> dict[str, Any]:
    cwd = run_root / "cwd"
    artifact_root = run_root / "artifacts"
    cwd.mkdir(parents=True)
    command = [
        str(executable),
        "tran",
        "run",
        "--stdin",
        "--artifact-root",
        str(artifact_root),
        "--artifact-id",
        "rc-pulse-1",
    ]
    started = time.perf_counter_ns()
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=scrubbed_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate(REQUEST, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MeasurementError("cli_invocation_failed") from error
    elapsed = time.perf_counter_ns() - started
    peak = peak_working_set_bytes(process)
    if process.returncode != 0 or stderr or not stdout.endswith(b"\n") or b"\n" in stdout[:-1]:
        raise MeasurementError("cli_protocol_failed")
    try:
        envelope = json.loads(stdout[:-1])
    except json.JSONDecodeError as error:
        raise MeasurementError("cli_response_invalid") from error
    if envelope.get("schema") != "sipi.cli.response.v1" or envelope.get("status") != "ok":
        raise MeasurementError("cli_response_rejected")
    final = artifact_root / "rc-pulse-1"
    payloads = {name: final / name for name in ("success.json", "result.json", "provenance.json")}
    if not all(path.is_file() for path in payloads.values()):
        raise MeasurementError("artifact_incomplete")
    return {
        "wall_time_ns": elapsed,
        "peak_working_set_bytes": peak,
        "success_sha256": sha256(payloads["success.json"].read_bytes()),
        "result_sha256": sha256(payloads["result.json"].read_bytes()),
        "provenance_sha256": sha256(payloads["provenance.json"].read_bytes()),
    }


def _summary(samples: list[dict[str, Any]], field: str) -> dict[str, int]:
    values = sorted(sample[field] for sample in samples)
    return {"min": values[0], "median": values[len(values) // 2 - 1 : len(values) // 2 + 1][0] if len(values) % 2 else (values[len(values) // 2 - 1] + values[len(values) // 2]) // 2, "max": values[-1]}


def validate_observation(document: object) -> dict[str, Any]:
    if not isinstance(document, dict):
        return {"valid": False, "reason": "report_not_object"}
    expected = {"schema", "status", "workload", "identity", "protocol", "samples", "summary", "limitations"}
    if set(document) != expected or document.get("schema") != REPORT_SCHEMA or document.get("status") != "observed_pending_owner_budget":
        return {"valid": False, "reason": "report_schema_or_status"}
    workload = document.get("workload")
    if workload != {"profile_id": PROFILE_ID, "request_schema": REQUEST_SCHEMA, "request_sha256": sha256(REQUEST)}:
        return {"valid": False, "reason": "workload_identity"}
    identity = document.get("identity")
    if not isinstance(identity, dict) or set(identity) != {"commit", "cargo_lock_sha256", "toolchain", "executable_sha256", "executable_bytes", "platform", "os"} or not _hex(identity.get("commit"), 40) or not _hex(identity.get("cargo_lock_sha256"), 64) or not _hex(identity.get("executable_sha256"), 64) or not isinstance(identity.get("toolchain"), str) or not identity["toolchain"] or not isinstance(identity.get("executable_bytes"), int) or identity["executable_bytes"] <= 0 or identity.get("platform") != "windows-x86_64" or not isinstance(identity.get("os"), str) or not identity["os"]:
        return {"valid": False, "reason": "binary_identity"}
    protocol = document.get("protocol")
    if protocol != {"warmup_count": WARMUP_COUNT, "measured_count": MEASURED_COUNT, "wall_clock": "perf_counter_ns", "peak_working_set": "GetProcessMemoryInfo.PeakWorkingSetSize"}:
        return {"valid": False, "reason": "protocol"}
    samples = document.get("samples")
    if not isinstance(samples, list) or len(samples) != MEASURED_COUNT:
        return {"valid": False, "reason": "sample_count"}
    identities: set[tuple[str, str, str]] = set()
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict) or set(sample) != {"index", "wall_time_ns", "peak_working_set_bytes", "success_sha256", "result_sha256", "provenance_sha256"} or sample.get("index") != index or not isinstance(sample.get("wall_time_ns"), int) or sample["wall_time_ns"] <= 0 or not isinstance(sample.get("peak_working_set_bytes"), int) or sample["peak_working_set_bytes"] <= 0 or not all(_hex(sample.get(key), 64) for key in ("success_sha256", "result_sha256", "provenance_sha256")):
            return {"valid": False, "reason": "sample_invalid"}
        identities.add((sample["success_sha256"], sample["result_sha256"], sample["provenance_sha256"]))
    if len(identities) != 1:
        return {"valid": False, "reason": "output_identity_drift"}
    expected_summary = {"wall_time_ns": _summary(samples, "wall_time_ns"), "peak_working_set_bytes": _summary(samples, "peak_working_set_bytes")}
    if document.get("summary") != expected_summary:
        return {"valid": False, "reason": "summary_invalid"}
    limitations = document.get("limitations")
    if not isinstance(limitations, list) or not limitations or not all(isinstance(item, str) and item for item in limitations):
        return {"valid": False, "reason": "limitations_invalid"}
    return {"valid": True, "status": document["status"], "profile_id": PROFILE_ID}


def run_measurement(executable: Path, output_root: Path, *, commit: str, cargo_lock_sha256: str, toolchain: str) -> dict[str, Any]:
    if platform.system() != "Windows":
        raise MeasurementError("windows_required")
    executable = executable.resolve()
    output_root = output_root.resolve()
    if not executable.is_file() or not _external(executable) or not _external(output_root) or output_root.exists():
        raise MeasurementError("external_input_required")
    if not _hex(commit, 40) or not _hex(cargo_lock_sha256, 64) or not toolchain:
        raise MeasurementError("identity_argument_invalid")
    output_root.mkdir(parents=True)
    try:
        for index in range(WARMUP_COUNT):
            _invoke(executable, output_root / f"warmup-{index}")
        samples = []
        for index in range(MEASURED_COUNT):
            sample = _invoke(executable, output_root / f"sample-{index}")
            samples.append({"index": index, **sample})
        report = {
            "schema": REPORT_SCHEMA,
            "status": "observed_pending_owner_budget",
            "workload": {"profile_id": PROFILE_ID, "request_schema": REQUEST_SCHEMA, "request_sha256": sha256(REQUEST)},
            "identity": {"commit": commit, "cargo_lock_sha256": cargo_lock_sha256, "toolchain": toolchain, "executable_sha256": sha256(executable.read_bytes()), "executable_bytes": executable.stat().st_size, "platform": "windows-x86_64", "os": platform.platform()},
            "protocol": {"warmup_count": WARMUP_COUNT, "measured_count": MEASURED_COUNT, "wall_clock": "perf_counter_ns", "peak_working_set": "GetProcessMemoryInfo.PeakWorkingSetSize"},
            "samples": samples,
            "summary": {"wall_time_ns": _summary(samples, "wall_time_ns"), "peak_working_set_bytes": _summary(samples, "peak_working_set_bytes")},
            "limitations": ["observation only; no owner-approved threshold", "PeakWorkingSetSize is observed child-process high water, not enforced RSS", "single Windows host and fixed RC/PULSE profile only"],
        }
        if not validate_observation(report)["valid"]:
            raise MeasurementError("report_self_validation_failed")
        return report
    except Exception:
        shutil.rmtree(output_root, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--cargo-lock-sha256", required=True)
    parser.add_argument("--toolchain", required=True)
    arguments = parser.parse_args()
    report_path = arguments.report.resolve()
    if not _external(report_path) or report_path == arguments.output_root.resolve() or arguments.output_root.resolve() in report_path.parents:
        parser.error("--report must be outside the workspace and output root")
    try:
        report = run_measurement(arguments.executable, arguments.output_root, commit=arguments.commit, cargo_lock_sha256=arguments.cargo_lock_sha256, toolchain=arguments.toolchain)
    except MeasurementError as error:
        report = {"schema": REPORT_SCHEMA, "status": "rejected", "reason": str(error)}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("status") == "observed_pending_owner_budget" else 2


if __name__ == "__main__":
    raise SystemExit(main())
