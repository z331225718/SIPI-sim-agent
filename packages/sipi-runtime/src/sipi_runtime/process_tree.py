"""Managed process-tree helpers (M3-09c).

Windows children are spawned with ``CREATE_NEW_PROCESS_GROUP`` and, when
available, assigned to a Job Object with ``KILL_ON_JOB_CLOSE`` so a tree can be
terminated as a unit; a ``taskkill /T`` fallback covers unassigned processes.
POSIX uses process groups.  ``ChildIdentity`` (pid, process start time, run
token, executable hash) is the evidence used by the supervisor to avoid
reaping an unrelated process on PID reuse.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class ProcessTreeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChildIdentity:
    pid: int
    process_start_time: str | None
    run_token: str | None
    executable_hash: str | None

    def to_wire(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "process_start_time": self.process_start_time,
            "run_token": self.run_token,
            "executable_hash": self.executable_hash,
        }


def _create_job() -> Any | None:
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
    JobObjectExtendedLimitInformation = 9
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
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


def spawn_managed(
    argv: list[str],
    *,
    workdir: str | Path,
    env: Mapping[str, str],
    run_token: str,
    executable_hash: str | None = None,
) -> tuple[subprocess.Popen, ChildIdentity]:
    """Spawn a child whose whole tree can be terminated as a unit."""
    creationflags = 0
    job = None
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        job = _create_job()
    process = subprocess.Popen(argv, cwd=str(workdir), env=dict(env), creationflags=creationflags)
    if job is not None:
        _assign_job(job, process.pid)
    process._sipi_job_handle = job  # type: ignore[attr-defined]
    identity = child_identity(process.pid, run_token=run_token, executable_hash=executable_hash)
    return process, identity


def _process_start_time(pid: int) -> str | None:
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
        except (ImportError, OSError):
            return None
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel_time), ctypes.byref(user_time)):
                return None
            raw = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            return str(raw)
        finally:
            kernel32.CloseHandle(handle)
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as stream:
            fields = stream.read().split()
            return fields[21] if len(fields) > 21 else None
    except OSError:
        return None


def child_identity(pid: int, *, run_token: str, executable_hash: str | None = None) -> ChildIdentity:
    return ChildIdentity(pid=pid, process_start_time=_process_start_time(pid), run_token=run_token, executable_hash=executable_hash)


def is_process_alive(pid: int) -> bool:
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
        except (ImportError, OSError):
            return False
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def matches_identity(pid: int, stored_start_time: str | None) -> bool:
    if stored_start_time is None:
        return True
    current = _process_start_time(pid)
    return current is not None and current == stored_start_time


def terminate_tree(process: subprocess.Popen | None = None, *, pid: int | None = None) -> None:
    """Terminate the whole tree; prefers the Job Object when available."""
    job = getattr(process, "_sipi_job_handle", None) if process is not None else None
    target_pid = process.pid if process is not None else pid
    if target_pid is None:
        return
    if job is not None and os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            kernel32.TerminateJobObject(job, 1)
            kernel32.CloseHandle(job)
            return
        except (ImportError, OSError):
            pass
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(target_pid)], capture_output=True, text=True)
        return
    try:
        os.killpg(os.getpgid(target_pid), 9)
    except (OSError, ProcessLookupError):
        try:
            os.kill(target_pid, 9)
        except OSError:
            pass
