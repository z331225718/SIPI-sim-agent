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
from datetime import datetime, timezone
from pathlib import Path

from .supervisor_registry import SupervisorRegistry
from .process_tree import is_process_alive, matches_identity, terminate_tree


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
        self._last_unmatched_backends: tuple[str, ...] = ()

    def close(self) -> None:
        self.registry.close()

    def publish_success(self, *, attempt_id: str, expected_version: int, success_manifest_sha256: str) -> str:
        """Commit a staged success manifest; SQLite commit is the linearization point."""
        return self.registry.attempt_publish_cas(attempt_id=attempt_id, expected_version=expected_version, success_manifest_sha256=success_manifest_sha256)

    def request_cancel(self, *, run_id: str, analysis_id: str | None = None) -> tuple[str, tuple[str, ...]]:
        """Write cancel flags, then terminate managed trees of affected backends."""
        status, affected = self.registry.cancel_scope(run_id=run_id, analysis_id=analysis_id)
        if status == "accepted":
            for attempt_id in affected:
                for backend in self.registry.list_backend_executions(attempt_id):
                    if backend["status"] in {"pending", "running"} and backend["pid"] is not None:
                        if matches_identity(backend["pid"], backend["process_start_time"]):
                            terminate_tree(pid=backend["pid"])
                            self.registry.cas_backend_execution(backend["backend_execution_id"], backend["version"], status="cancelled")
        return status, affected

    def reconcile(self) -> dict[str, object]:
        """Restart reconciliation: expire stale leases and settle cancelled publishing attempts.

        Stale executions are settled as ``failed``/``cancelled`` here without
        child-evidence classification; EngineProtocolFailure and orphan
        identity matching against ``backend_executions`` child identity are
        M3-09 failure-injection scope.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        expired = self.registry.expire_stale_executions(now_iso)
        cancelled_publishing = self.registry.expire_cancelled_publishing()
        settled_backends = self._reconcile_backends()
        return {
            "expired_executions": expired,
            "cancelled_publishing_attempts": cancelled_publishing,
            "settled_backends": settled_backends,
            "unmatched_alive_backends": self._last_unmatched_backends,
        }

    def _reconcile_backends(self) -> tuple[str, ...]:
        """Settle orphaned/stopped backend children; identity-matched orphans are reaped."""
        settled: list[str] = []
        unmatched: list[str] = []
        for backend in self.registry.list_backend_executions():
            if backend["status"] not in {"pending", "running"} or backend["pid"] is None:
                continue
            alive = is_process_alive(backend["pid"])
            if alive and not matches_identity(backend["pid"], backend["process_start_time"]):
                unmatched.append(backend["backend_execution_id"])
                continue  # PID reuse with a different child: warn-only, do not reap
            if alive:
                terminate_tree(pid=backend["pid"])
            try:
                self.registry.cas_backend_execution(backend["backend_execution_id"], backend["version"], status="failed")
                settled.append(backend["backend_execution_id"])
            except Exception:  # noqa: BLE001 - reconciliation must stay idempotent
                pass
        self._last_unmatched_backends = tuple(unmatched)
        return tuple(settled)
