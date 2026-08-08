"""Hermetic process execution for strict backend adapters.

The runner verifies the engine bundle, materializes bound inputs into an
isolated per-run directory, executes the engine entrypoint with an allowlisted
environment and wall-time limit, and assembles exactly one
``BackendExecutionResultV1``.  Hard resource enforcement (M3-11) is applied by
this managed-worker layer: Windows Job Object limits (memory/process count/CPU
time) plus artifact-byte publication checks on every platform, and POSIX
``setrlimit`` (memory/CPU; process count stays unsupported on POSIX because
``RLIMIT_NPROC`` is a weak per-user limit).  Unsupported required limits fail
preflight instead of being silently ignored.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sipi_contracts import BackendExecutionRequestV1, BackendExecutionResultV1, parse_backend_execution_result

from .attestation import AttestationError, verify_wheel_bundle
from .capabilities import AdapterCapability, preflight
from .spi import AdapterContractError, UnsupportedCapabilityError, require_backend_request, validate_pinned_instance
from .venv import (
    BundleExecutionError,
    install_pip_dependencies,
    install_wheels_with_dependencies,
    required_console_script,
    required_pip_dependencies,
    resolve_console_script,
    resolve_interpreter,
)

ALLOWED_ENV = frozenset(
    {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "COMSPEC",
        "PATHEXT",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "OS",
    }
)
_RESOURCE_FIELDS = ("wall_time_s", "cpu_time_s", "memory_bytes", "process_count", "artifact_bytes")

MANAGED_HARD_ENFORCEMENT = {
    "nt": {name: "hard" for name in _RESOURCE_FIELDS},
    "posix": {
        "wall_time_s": "hard",
        "cpu_time_s": "hard",
        "memory_bytes": "hard",
        "process_count": "unsupported",
        "artifact_bytes": "hard",
    },
}


class BundleVerificationError(ValueError):
    """Raised when an engine bundle cannot be verified before execution."""


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed_s: float
    timed_out: bool
    resource_violation: str | None = None


@dataclass(frozen=True)
class BackendOutcome:
    """One backend result plus files that must be handed to the runtime store."""

    result: BackendExecutionResultV1
    artifact_paths: tuple[Path, ...] = ()


def platform_error(
    category: str,
    message: str,
    resource: str | None = None,
    details: Mapping[str, Any] | None = None,
    cause: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {"category": category, "message": message, "resource": resource, "cause": cause, "details": dict(details or {})}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def filtered_env() -> dict[str, str]:
    env = {name: value for name, value in os.environ.items() if name in ALLOWED_ENV}
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _create_job_with_limits(limits: Mapping[str, Any]) -> Any | None:
    """Create a Windows Job Object with hard resource limits (M3-11)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except (ImportError, OSError):
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    JOB_OBJECT_LIMIT_JOB_TIME = 0x0004
    JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x0008
    JOB_OBJECT_LIMIT_JOB_MEMORY = 0x0200
    JobObjectExtendedLimitInformation = 9
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    limit_flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    memory_bytes = limits.get("memory_bytes")
    process_count = limits.get("process_count")
    cpu_time_s = limits.get("cpu_time_s")
    if memory_bytes is not None:
        info.JobMemoryLimit = int(memory_bytes)
        limit_flags |= JOB_OBJECT_LIMIT_JOB_MEMORY
    if process_count is not None:
        info.BasicLimitInformation.ActiveProcessLimit = int(process_count)
        limit_flags |= JOB_OBJECT_LIMIT_ACTIVE_PROCESS
    if cpu_time_s is not None:
        info.BasicLimitInformation.PerJobUserTimeLimit = int(cpu_time_s * 1e7)
        limit_flags |= JOB_OBJECT_LIMIT_JOB_TIME
    info.BasicLimitInformation.LimitFlags = limit_flags
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    if not kernel32.SetInformationJobObject(job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)):
        kernel32.CloseHandle(job)
        return None
    return job


def _assign_job(job: Any, pid: int) -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes
    except (ImportError, OSError):
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PROCESS_SET_QUOTA = 0x0100
    PROCESS_TERMINATE = 0x0001
    handle = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
    if not handle:
        return False
    try:
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        return bool(kernel32.AssignProcessToJobObject(job, handle))
    finally:
        kernel32.CloseHandle(handle)


def _job_violation(job: Any, limits: Mapping[str, Any]) -> str | None:
    """Return the first resource limit the job demonstrably exceeded, if any."""
    if job is None or os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except (ImportError, OSError):
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong),
            ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong),
            ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    accounting = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
    JobObjectBasicAccountingInformation = 1
    kernel32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD, wintypes.LPDWORD]
    if not kernel32.QueryInformationJobObject(job, JobObjectBasicAccountingInformation, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
        return None
    cpu_time_s = limits.get("cpu_time_s")
    if cpu_time_s is not None and (accounting.TotalUserTime + accounting.TotalKernelTime) >= int(cpu_time_s * 1e7):
        return "cpu_time_s"
    process_count = limits.get("process_count")
    if process_count is not None and accounting.ActiveProcesses > int(process_count):
        return "process_count"
    memory_bytes = limits.get("memory_bytes")
    if memory_bytes is not None:
        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        extended = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        JobObjectExtendedLimitInformation = 9
        if kernel32.QueryInformationJobObject(job, JobObjectExtendedLimitInformation, ctypes.byref(extended), ctypes.sizeof(extended), None):
            # Under a job memory commit limit allocation fails at the ceiling,
            # so the measured peak lands at (or just below) the limit.
            if extended.PeakJobMemoryUsed >= int(memory_bytes * 0.9):
                return "memory_bytes"
    return None


def _posix_rlimit_preexec(limits: Mapping[str, Any]) -> Any | None:
    """Build a preexec hook applying hard rlimits on POSIX (M3-11)."""
    if os.name == "nt":
        return None
    memory_bytes = limits.get("memory_bytes")
    cpu_time_s = limits.get("cpu_time_s")
    if memory_bytes is None and cpu_time_s is None:
        return None

    def preexec() -> None:
        import resource

        if memory_bytes is not None:
            resource.setrlimit(resource.RLIMIT_AS, (int(memory_bytes), int(memory_bytes)))
        if cpu_time_s is not None:
            resource.setrlimit(resource.RLIMIT_CPU, (int(cpu_time_s), int(cpu_time_s)))

    return preexec


def invocation(bundle_path: Path) -> list[str]:
    if bundle_path.suffix.lower() == ".py":
        return [sys.executable, "-I", str(bundle_path)]
    return [str(bundle_path)]


def verify_engine_bundle(engine_entry: Mapping[str, Any], repo_root: Path) -> Path:
    """Verify a pinned local bundle: wheel archives get full content attestation."""
    bundle = engine_entry["bundle"]
    if bundle["kind"] != "local_path":
        raise BundleVerificationError("https_url bundles cannot be executed without an approved downloader")
    candidate = (repo_root / bundle["path"]).resolve()
    if not candidate.is_relative_to(repo_root):
        raise BundleVerificationError("bundle path escapes the repository root")
    if not candidate.is_file():
        raise BundleVerificationError(f"engine bundle is missing: {candidate}")
    if _sha256(candidate) != bundle["sha256"]:
        raise BundleVerificationError(f"engine bundle sha256 mismatch: {candidate}")
    if candidate.suffix.lower() == ".whl":
        try:
            verify_wheel_bundle(engine_entry, repo_root)
        except AttestationError as error:
            raise BundleVerificationError(str(error)) from error
        return candidate
    manifest = engine_entry["bundle_manifest"]
    if manifest["entrypoint"] != candidate.name:
        raise BundleVerificationError("multi-file bundles are not supported yet; entrypoint must be the bundle file itself")
    entrypoints = [item for item in manifest["files"] if item["role"] == "entrypoint"]
    if (
        len(manifest["files"]) != 1
        or len(entrypoints) != 1
        or entrypoints[0]["relative_path"] != candidate.name
        or entrypoints[0]["sha256"] != bundle["sha256"]
        or entrypoints[0]["byte_length"] != candidate.stat().st_size
    ):
        raise BundleVerificationError("single-file bundle manifest must match the bundle exactly")
    return candidate


def _managed_dependency_wheels(engine_entry: Mapping[str, Any], repo_root: Path) -> tuple[Path, ...]:
    """Resolve and verify managed dependency wheels declared in bundle_manifest.

    Every ``role == "dependency"`` manifest entry is resolved relative to the
    repository root, must point at a real ``.whl`` file, and must match its
    pinned sha256/byte_length.  A missing or mismatched dependency fails closed
    before any engine process is started.
    """
    manifest = engine_entry.get("bundle_manifest")
    if manifest is None:
        return ()
    wheels: list[Path] = []
    for item in manifest.get("files", ()):
        if item.get("role") != "dependency":
            continue
        relative = item.get("relative_path")
        if not isinstance(relative, str) or not relative.endswith(".whl"):
            raise BundleVerificationError("managed dependency wheel requires a relative .whl path")
        candidate = (repo_root / relative).resolve()
        if not candidate.is_relative_to(repo_root):
            raise BundleVerificationError(f"dependency wheel escapes the repository root: {relative}")
        if not candidate.is_file():
            raise BundleVerificationError(f"managed dependency wheel is missing: {candidate}")
        if _sha256(candidate) != item.get("sha256") or candidate.stat().st_size != item.get("byte_length"):
            raise BundleVerificationError(f"managed dependency wheel hash mismatch: {candidate}")
        wheels.append(candidate)
    return tuple(wheels)


def materialize_bound_inputs(request: BackendExecutionRequestV1, repo_root: Path, workdir: Path) -> None:
    for name, artifact in request["bound_inputs"].items():
        relative = Path(artifact["relative_path"])
        source = (repo_root / relative).resolve()
        target = (workdir / relative).resolve()
        if not source.is_relative_to(repo_root):
            raise AdapterContractError(f"bound input escapes the repository root: {relative}")
        if not target.is_relative_to(workdir):
            raise AdapterContractError(f"bound input escapes the work directory: {relative}")
        if not source.is_file():
            raise AdapterContractError(f"bound input is missing: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if _sha256(target) != artifact["sha256"] or target.stat().st_size != artifact["byte_length"]:
            raise AdapterContractError(f"bound input hash mismatch: {relative}")


def run_process(
    argv: list[str],
    *,
    workdir: Path,
    env: Mapping[str, str],
    wall_time_s: float | None,
    resource_limits: Mapping[str, Any] | None = None,
    on_start: Callable[[int], None] | None = None,
) -> ProcessResult:
    started = time.monotonic()
    limits = resource_limits or {}
    job = None
    flags = 0
    preexec = None
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        job = _create_job_with_limits(limits)
    else:
        preexec = _posix_rlimit_preexec(limits)
    process = subprocess.Popen(
        argv,
        cwd=workdir,
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
        preexec_fn=preexec,
    )
    if job is not None:
        _assign_job(job, process.pid)
        process._sipi_job_handle = job  # type: ignore[attr-defined]
    if on_start is not None:
        on_start(process.pid)
    try:
        stdout, stderr = process.communicate(timeout=wall_time_s)
        violation = _job_violation(job, limits) if job is not None else None
        return ProcessResult(
            returncode=process.returncode,
            stdout=stdout or "",
            stderr=stderr or "",
            elapsed_s=time.monotonic() - started,
            timed_out=False,
            resource_violation=violation,
        )
    except subprocess.TimeoutExpired as error:
        process.kill()
        stdout, stderr = process.communicate()
        return ProcessResult(returncode=-1, stdout=stdout, stderr=stderr, elapsed_s=time.monotonic() - started, timed_out=True, resource_violation=None)


def assemble_backend_result(
    request: BackendExecutionRequestV1,
    *,
    status: str,
    error: Mapping[str, Any] | None = None,
    domain_result: Any = None,
    domain_result_schema: str | None = None,
    artifacts: tuple[Mapping[str, Any], ...] = (),
    warnings: tuple[str, ...] = (),
    timings: Mapping[str, Any] | None = None,
    actual_enforcement: Mapping[str, str] | None = None,
) -> BackendExecutionResultV1:
    wire: dict[str, Any] = {
        "schema": "sipi.backend-execution-result.v1",
        "run_id": request["run_id"],
        "analysis_id": request["analysis_id"],
        "attempt_id": request["attempt_id"],
        "backend_execution_id": request["backend_execution_id"],
        "role": request["role"],
        "engine_instance_id": request["engine_instance_id"],
        "bundle_hash": request["bundle_hash"],
        "operation": request["operation"],
        "payload_schema": request["payload_schema"],
        "status": status,
        "domain_result_schema": domain_result_schema,
        **({"domain_result": domain_result} if domain_result is not None else {}),
        "artifacts": list(artifacts),
        "events": [],
        "warnings": list(warnings),
        "timings": dict(timings or {}),
        "resource_usage": {"actual_enforcement": dict(actual_enforcement or {name: "unsupported" for name in _RESOURCE_FIELDS})},
        "error": dict(error) if error is not None else None,
    }
    return parse_backend_execution_result(wire)


class CommandBuilder(Protocol):
    """Builds one engine invocation and one domain result from a run."""

    def build(self, request: BackendExecutionRequestV1, bundle_path: Path, workdir: Path) -> list[str]:
        ...

    def build_outcome(self, request: BackendExecutionRequestV1, engine_entry: Mapping[str, Any], workdir: Path, process: ProcessResult) -> BackendOutcome:
        ...


def _failed_from_error(request: BackendExecutionRequestV1, error: BaseException) -> BackendExecutionResultV1:
    message = str(error)
    cause = {"kind": type(error).__name__, "message": message}
    if isinstance(error, UnsupportedCapabilityError):
        category = "UnsupportedCapability"
    elif "escapes" in message:
        category = "InvalidRequest"
    elif "missing" in message or "hash mismatch" in message:
        category = "InputNotFound"
    elif isinstance(error, AdapterContractError):
        category = "InvalidRequest"
    else:
        category = "EngineUnavailable"
    return assemble_backend_result(request, status="failed", error=platform_error(category, message, cause=cause))


def execute_backend(
    request: BackendExecutionRequestV1,
    engine_entry: Mapping[str, Any],
    repo_root: Path,
    *,
    builder: CommandBuilder,
    workdir: Path | None = None,
    artifact_root: Path | None = None,
    capabilities: tuple[AdapterCapability, ...] | None = None,
    on_child_start: Callable[[int], None] | None = None,
) -> BackendExecutionResultV1:
    """Execute one strict backend execution and return its single result."""
    require_backend_request(request)
    validate_pinned_instance(request, engine_entry["instance_id"])
    os_key = "nt" if os.name == "nt" else "posix"
    managed_hard = MANAGED_HARD_ENFORCEMENT[os_key]
    if capabilities is not None:
        try:
            preflight(request, capabilities, platform_enforcement=managed_hard)
        except UnsupportedCapabilityError as error:
            return _failed_from_error(request, error)
    try:
        bundle_path = verify_engine_bundle(engine_entry, repo_root)
    except BundleVerificationError as error:
        return assemble_backend_result(request, status="failed", error=platform_error("EngineUnavailable", str(error)))

    owns_workdir = workdir is None
    if owns_workdir:
        workdir = Path(tempfile.mkdtemp(prefix="sipi-backend-"))
    else:
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
    try:
        try:
            materialize_bound_inputs(request, repo_root, workdir)
        except AdapterContractError as error:
            return _failed_from_error(request, error)
        try:
            entry_target = bundle_path
            if bundle_path.suffix.lower() == ".whl":
                try:
                    required_console_script(engine_entry)
                    dependency_wheels = _managed_dependency_wheels(engine_entry, repo_root)
                    interpreter = resolve_interpreter(engine_entry.get("runtime", {}).get("python_abi"))
                    install_wheels_with_dependencies(bundle_path, dependency_wheels, workdir / "engine-venv", python=interpreter)
                    pip_dependencies = required_pip_dependencies(engine_entry)
                    if pip_dependencies:
                        install_pip_dependencies(workdir / "engine-venv", pip_dependencies, python=interpreter)
                    entry_target = resolve_console_script(engine_entry, workdir / "engine-venv")
                except (BundleExecutionError, BundleVerificationError) as error:
                    return assemble_backend_result(
                        request,
                        status="failed",
                        error=platform_error("UnsupportedCapability", str(error)),
                    )
            argv = builder.build(request, entry_target, workdir)
        except AdapterContractError as error:
            return _failed_from_error(request, error)
        limits = request["resource_limits"]
        wall_time_s = limits.get("wall_time_s")
        enforcement_limits: dict[str, Any] = {"wall_time_s": wall_time_s}
        if limits.get("enforcement") == "required":
            enforcement_limits.update({name: limits[name] for name in _RESOURCE_FIELDS if limits.get(name) is not None})
        process = run_process(
            argv,
            workdir=workdir,
            env=filtered_env(),
            wall_time_s=wall_time_s,
            resource_limits=enforcement_limits,
            on_start=on_child_start,
        )
        actual_enforcement = {
            name: ("hard" if limits.get("enforcement") == "required" and limits.get(name) is not None and managed_hard.get(name) == "hard" else "unsupported")
            for name in _RESOURCE_FIELDS
        }
        if process.timed_out:
            return assemble_backend_result(
                request,
                status="failed",
                error=platform_error("Timeout", f"engine exceeded wall_time_s={wall_time_s}", "wall_time_s", {"sipi.adapter.elapsed-seconds": process.elapsed_s}),
                actual_enforcement=actual_enforcement,
            )
        if process.returncode != 0:
            if process.resource_violation is not None:
                return assemble_backend_result(
                    request,
                    status="failed",
                    error=platform_error(
                        "ResourceLimit",
                        f"engine exceeded hard {process.resource_violation} limit",
                        process.resource_violation,
                        {"sipi.adapter.returncode": process.returncode},
                    ),
                    actual_enforcement=actual_enforcement,
                )
            message = f"engine exited with code {process.returncode}"
            if process.stderr.strip():
                message += f": {process.stderr.strip().splitlines()[-1]}"
            return assemble_backend_result(request, status="failed", error=platform_error("ExternalModelFailure", message), actual_enforcement=actual_enforcement)
        outcome = builder.build_outcome(request, engine_entry, workdir, process)
        if outcome.result["artifacts"] and artifact_root is None:
            return assemble_backend_result(
                request,
                status="failed",
                error=platform_error("InternalInvariant", "backend result has artifacts but no artifact_root was provided"),
                actual_enforcement=actual_enforcement,
            )
        artifact_bytes_limit = limits.get("artifact_bytes")
        if limits.get("enforcement") == "required" and artifact_bytes_limit is not None:
            total_bytes = sum(int(artifact.get("byte_length", 0)) for artifact in outcome.result["artifacts"])
            if total_bytes > artifact_bytes_limit:
                return assemble_backend_result(
                    request,
                    status="failed",
                    error=platform_error(
                        "ResourceLimit",
                        f"artifacts exceed hard artifact_bytes limit: {total_bytes} > {artifact_bytes_limit}",
                        "artifact_bytes",
                        {"sipi.adapter.artifact-bytes": total_bytes},
                    ),
                    actual_enforcement=actual_enforcement,
                )
        if artifact_root is not None:
            artifact_root = Path(artifact_root)
            artifact_root.mkdir(parents=True, exist_ok=True)
            for source in outcome.artifact_paths:
                try:
                    relative = source.resolve().relative_to(workdir.resolve())
                except ValueError:
                    return assemble_backend_result(
                        request,
                        status="failed",
                        error=platform_error("InternalInvariant", f"artifact path escapes the work directory: {source}"),
                        actual_enforcement=actual_enforcement,
                    )
                target = artifact_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            for artifact in outcome.result["artifacts"]:
                stored = artifact_root / artifact["relative_path"]
                if not stored.is_file() or _sha256(stored) != artifact["sha256"] or stored.stat().st_size != artifact["byte_length"]:
                    return assemble_backend_result(
                        request,
                        status="failed",
                        error=platform_error("InternalInvariant", f"artifact handoff verification failed: {artifact['relative_path']}"),
                        actual_enforcement=actual_enforcement,
                    )
        if actual_enforcement != {name: "unsupported" for name in _RESOURCE_FIELDS}:
            wire = outcome.result.to_wire()
            wire["resource_usage"]["actual_enforcement"] = actual_enforcement
            return parse_backend_execution_result(wire)
        return outcome.result
    finally:
        if owns_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
