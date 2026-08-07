"""Local supervisor coordination core (M3-04b).

The supervisor owns the per-data-directory SQLite registry and the OS-level
singleton lock.  This slice provides the coordination core: the singleton
lock, success-publish CAS (with cancel fencing) and scoped cancel protocol.
IPC, the supervisor loop, process-tree management and restart reconciliation
are the next slice (M3-04b3); this module deliberately does not spawn or
signal child processes yet.
"""

from __future__ import annotations

import os
from pathlib import Path

from .supervisor_registry import SupervisorRegistry


class SupervisorBusy(RuntimeError):
    """Raised when another supervisor writer already owns the data directory."""


class SupervisorLock:
    """OS-level exclusive lock naming the single supervisor writer."""

    def __init__(self, data_dir: str | Path) -> None:
        self.path = Path(data_dir) / "supervisor.lock"
        self._handle: object | None = None

    def acquire(self) -> "SupervisorLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")
        try:
            handle.seek(0)
            handle.write(b"\0")
            handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            raise SupervisorBusy(f"supervisor is already running in {self.path.parent}") from error
        self._handle = handle
        return self

    def release(self) -> None:
        if self._handle is None:
            return
        handle = self._handle
        self._handle = None
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self) -> "SupervisorLock":
        return self.acquire()

    def __exit__(self, *_: object) -> None:
        self.release()


class Supervisor:
    """Coordination authority for one local platform data directory."""

    def __init__(self, data_dir: str | Path, *, registry: SupervisorRegistry | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.registry = registry if registry is not None else SupervisorRegistry(self.data_dir / "supervisor.sqlite3")

    def close(self) -> None:
        self.registry.close()

    def publish_success(self, *, attempt_id: str, expected_version: int, success_manifest_sha256: str) -> str:
        """Commit a staged success manifest; SQLite commit is the linearization point."""
        return self.registry.attempt_publish_cas(attempt_id=attempt_id, expected_version=expected_version, success_manifest_sha256=success_manifest_sha256)

    def request_cancel(self, *, run_id: str, analysis_id: str | None = None) -> tuple[str, tuple[str, ...]]:
        """Write cancel_requested CAS flags; returns (status, affected attempt ids)."""
        return self.registry.cancel_scope(run_id=run_id, analysis_id=analysis_id)
