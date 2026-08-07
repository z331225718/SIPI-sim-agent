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
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .supervisor_registry import SupervisorRegistry
from .process_tree import is_process_alive, matches_identity, terminate_tree
from .cache import CachePathEscape, CacheStore


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

    def __enter__(self) -> "Supervisor":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

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

    def reconcile(self, *, now: datetime | None = None) -> dict[str, object]:
        """Restart reconciliation: expire stale leases, settle cancelled or crashed publishes.

        Stale executions are settled as ``failed``/``cancelled`` here without
        child-evidence classification; EngineProtocolFailure and orphan
        identity matching against ``backend_executions`` child identity are
        M3-09 failure-injection scope.
        """
        now_iso = (now if now is not None else datetime.now(timezone.utc)).isoformat()
        expired = self.registry.expire_stale_executions(now_iso)
        cancelled_publishing = self.registry.expire_cancelled_publishing()
        rebuilt_publishing, failed_publishing = self._reconcile_publishing()
        settled_backends = self._reconcile_backends()
        return {
            "expired_executions": expired,
            "cancelled_publishing_attempts": cancelled_publishing,
            "rebuilt_publishing_attempts": rebuilt_publishing,
            "failed_publishing_attempts": failed_publishing,
            "settled_backends": settled_backends,
            "unmatched_alive_backends": self._last_unmatched_backends,
        }

    def _reconcile_publishing(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Recover attempts whose publish was interrupted before the SQLite commit.

        The driver stages ``success-manifest.json`` before calling the publish
        CAS (M3 wrap publish-crash slice).  After a crash the attempt stays in
        ``publishing``; this method rebuilds it as ``succeeded`` when the
        staged manifest is intact (valid JSON, safe artifact paths, all files
        present), and otherwise settles it as ``failed`` so it never dangles.
        Cancels already handled by ``expire_cancelled_publishing`` are skipped;
        an execution/node-level cancel surfaces as ``cancel_accepted`` here and
        settles the attempt as ``cancelled``.
        """
        rebuilt: list[str] = []
        failed: list[str] = []
        for attempt in self.registry.list_stale_publishing():
            attempt_id = attempt["attempt_id"]
            manifest_sha = self._validated_manifest_sha(attempt["analysis_id"], attempt_id)
            if manifest_sha is not None:
                outcome = self.registry.attempt_publish_cas(
                    attempt_id=attempt_id,
                    expected_version=attempt["version"],
                    success_manifest_sha256=manifest_sha,
                    require_publishing=False,
                )
                if outcome == "committed":
                    rebuilt.append(attempt_id)
                    continue
                if outcome == "cancel_accepted":
                    try:
                        if self.registry.cas_attempt(attempt_id, attempt["version"], status="cancelled"):
                            continue
                    except Exception:  # noqa: BLE001 - reconciliation stays idempotent
                        pass
                    continue
                # version conflict / already terminal: another path owns the row
                continue
            try:
                if self.registry.cas_attempt(attempt_id, attempt["version"], status="failed"):
                    failed.append(attempt_id)
            except Exception:  # noqa: BLE001 - reconciliation stays idempotent
                pass
        return tuple(rebuilt), tuple(failed)

    def _validated_manifest_sha(self, analysis_id: str, attempt_id: str) -> str | None:
        """Return the staged manifest's byte sha256 only when it is intact and its artifacts exist."""
        manifest_path = (
            self.data_dir / "nodes" / analysis_id / "attempts" / attempt_id / "success-manifest.json"
        )
        try:
            manifest_bytes = manifest_path.read_bytes()
        except OSError:
            return None
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        if manifest.get("schema") != "sipi.success-manifest.v1":
            return None
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list):
            return None
        for artifact in artifacts:
            relative_path = artifact.get("relative_path")
            if not isinstance(relative_path, str):
                return None
            try:
                CacheStore._check_relative(relative_path)
            except CachePathEscape:
                return None
            if not (self.data_dir / relative_path).is_file():
                return None
        return hashlib.sha256(manifest_bytes).hexdigest()

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
