"""SQLite single-writer supervisor registry (M3-04a).

The registry is the coordination authority for a local Platform MVP
supervisor.  Four tables (``executions``, ``nodes``, ``attempts``,
``backend_executions``) hold the four-layer identity, status, monotonic
version, cancellation flags, lease/heartbeat state and child identity.
Every mutation runs in a single-writer ``BEGIN IMMEDIATE`` transaction and
uses compare-and-swap on the row version; terminal rows are never reopened.
Submission idempotency replays the original ``run_id`` for the same key +
project hash and rejects reuse with a different hash.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


class SupervisorRegistryError(ValueError):
    pass


class SubmissionKeyConflict(SupervisorRegistryError):
    pass


class DuplicateNode(SupervisorRegistryError):
    pass


class DuplicateAttempt(SupervisorRegistryError):
    pass


class CasConflict(SupervisorRegistryError):
    pass


class TerminalTransition(SupervisorRegistryError):
    pass


EXECUTION_TERMINAL = {"succeeded", "failed", "cancelled"}
NODE_TERMINAL = {"succeeded", "failed", "cancelled", "blocked"}
ATTEMPT_TERMINAL = {"succeeded", "failed", "cancelled"}
BACKEND_TERMINAL = {"succeeded", "failed", "cancelled"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupervisorRegistry:
    """One local SQLite registry; callers must serialize writers externally."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SupervisorRegistry":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _create_schema(self) -> None:
        with self._txn() as cursor:
            cursor.executescript(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    run_id TEXT PRIMARY KEY,
                    project_hash TEXT NOT NULL,
                    submission_key TEXT NOT NULL UNIQUE,
                    retry_of TEXT,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    failure_policy TEXT NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    heartbeat_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS nodes (
                    run_id TEXT NOT NULL,
                    analysis_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    effective_required INTEGER NOT NULL,
                    blocked_by TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (run_id, analysis_id),
                    FOREIGN KEY (run_id) REFERENCES executions(run_id)
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    attempt_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    analysis_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    retry_index INTEGER NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    success_manifest_sha256 TEXT,
                    FOREIGN KEY (run_id, analysis_id) REFERENCES nodes(run_id, analysis_id)
                );
                CREATE TABLE IF NOT EXISTS backend_executions (
                    backend_execution_id TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    engine_instance_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    pid INTEGER,
                    process_start_time TEXT,
                    run_token TEXT,
                    executable_hash TEXT,
                    FOREIGN KEY (attempt_id) REFERENCES attempts(attempt_id)
                );
                CREATE INDEX IF NOT EXISTS idx_nodes_run ON nodes(run_id);
                CREATE INDEX IF NOT EXISTS idx_attempts_run ON attempts(run_id);
                CREATE INDEX IF NOT EXISTS idx_backends_attempt ON backend_executions(attempt_id);
                """
            )

    @contextmanager
    def _txn(self) -> Iterator[sqlite3.Cursor]:
        cursor = self._connection.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            yield cursor
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()

    def _read(self, sql: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        return self._connection.execute(sql, parameters).fetchone()

    @staticmethod
    def _guard_terminal(current_status: str, terminal: set[str], updates: Mapping[str, Any]) -> None:
        if current_status in terminal and any(value is not None for value in updates.values()):
            raise TerminalTransition(f"terminal row cannot be mutated from {current_status}")

    def submit_execution_record(
        self,
        *,
        run_id: str,
        project_hash: str,
        submission_key: str,
        failure_policy: str,
        retry_of: str | None = None,
    ) -> tuple[Mapping[str, Any], bool]:
        with self._txn() as cursor:
            existing = cursor.execute("SELECT * FROM executions WHERE submission_key = ?", (submission_key,)).fetchone()
            if existing is not None:
                if existing["project_hash"] != project_hash:
                    raise SubmissionKeyConflict("submission key reused with a different project hash")
                return dict(existing), False
            now = _utcnow()
            cursor.execute(
                """
                INSERT INTO executions (
                    run_id, project_hash, submission_key, retry_of, status, version,
                    failure_policy, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'queued', 1, ?, ?, ?)
                """,
                (run_id, project_hash, submission_key, retry_of, failure_policy, now, now),
            )
            return dict(cursor.execute("SELECT * FROM executions WHERE run_id = ?", (run_id,)).fetchone()), True

    def submit_execution(
        self,
        *,
        run_id: str,
        project_hash: str,
        submission_key: str,
        failure_policy: str,
        retry_of: str | None = None,
    ) -> Mapping[str, Any]:
        row, _ = self.submit_execution_record(
            run_id=run_id,
            project_hash=project_hash,
            submission_key=submission_key,
            failure_policy=failure_policy,
            retry_of=retry_of,
        )
        return row

    def get_execution(self, run_id: str) -> Mapping[str, Any] | None:
        row = self._read("SELECT * FROM executions WHERE run_id = ?", (run_id,))
        return dict(row) if row is not None else None

    def cas_execution(self, run_id: str, expected_version: int, *, status: str | None = None, cancel_requested: bool | None = None, lease_owner: str | None = None, lease_expires_at: str | None = None, heartbeat_at: str | None = None) -> bool:
        updates = {
            "status": status,
            "cancel_requested": cancel_requested,
            "lease_owner": lease_owner,
            "lease_expires_at": lease_expires_at,
            "heartbeat_at": heartbeat_at,
        }
        return self._cas_row("executions", "run_id", run_id, expected_version, updates, EXECUTION_TERMINAL)

    def create_node(self, *, run_id: str, analysis_id: str, effective_required: bool, blocked_by: list[Mapping[str, Any]] | None = None) -> Mapping[str, Any]:
        with self._txn() as cursor:
            existing = cursor.execute("SELECT * FROM nodes WHERE run_id = ? AND analysis_id = ?", (run_id, analysis_id)).fetchone()
            if existing is not None:
                raise DuplicateNode(f"node already exists: {run_id}/{analysis_id}")
            cursor.execute(
                """
                INSERT INTO nodes (run_id, analysis_id, status, version, effective_required, blocked_by)
                VALUES (?, ?, 'pending', 1, ?, ?)
                """,
                (run_id, analysis_id, int(effective_required), json.dumps(blocked_by or [])),
            )
            return dict(cursor.execute("SELECT * FROM nodes WHERE run_id = ? AND analysis_id = ?", (run_id, analysis_id)).fetchone())

    def get_node(self, run_id: str, analysis_id: str) -> Mapping[str, Any] | None:
        row = self._read("SELECT * FROM nodes WHERE run_id = ? AND analysis_id = ?", (run_id, analysis_id))
        return dict(row) if row is not None else None

    def cas_node(self, run_id: str, analysis_id: str, expected_version: int, *, status: str | None = None, blocked_by: list[Mapping[str, Any]] | None = None, cancel_requested: bool | None = None) -> bool:
        updates = {"status": status, "blocked_by": None if blocked_by is None else json.dumps(blocked_by), "cancel_requested": cancel_requested}
        return self._cas_row("nodes", "node_key", f"{run_id}/{analysis_id}", expected_version, updates, NODE_TERMINAL, extra_where="run_id = ? AND analysis_id = ?", extra_params=(run_id, analysis_id))

    def append_attempt(self, *, attempt_id: str, run_id: str, analysis_id: str, retry_index: int) -> Mapping[str, Any]:
        with self._txn() as cursor:
            existing = cursor.execute("SELECT 1 FROM attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
            if existing is not None:
                raise DuplicateAttempt(f"attempt already exists: {attempt_id}")
            cursor.execute(
                """
                INSERT INTO attempts (attempt_id, run_id, analysis_id, status, version, retry_index)
                VALUES (?, ?, ?, 'queued', 1, ?)
                """,
                (attempt_id, run_id, analysis_id, retry_index),
            )
            return dict(cursor.execute("SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,)).fetchone())

    def get_attempt(self, attempt_id: str) -> Mapping[str, Any] | None:
        row = self._read("SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,))
        return dict(row) if row is not None else None

    def list_attempts(self, run_id: str, analysis_id: str | None = None) -> tuple[Mapping[str, Any], ...]:
        if analysis_id is None:
            rows = self._connection.execute("SELECT * FROM attempts WHERE run_id = ? ORDER BY retry_index", (run_id,)).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM attempts WHERE run_id = ? AND analysis_id = ? ORDER BY retry_index",
                (run_id, analysis_id),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def cas_attempt(self, attempt_id: str, expected_version: int, *, status: str | None = None, cancel_requested: bool | None = None) -> bool:
        updates = {"status": status, "cancel_requested": cancel_requested}
        return self._cas_row("attempts", "attempt_id", attempt_id, expected_version, updates, ATTEMPT_TERMINAL)

    def attempt_publish_cas(self, *, attempt_id: str, expected_version: int, success_manifest_sha256: str, require_publishing: bool = True) -> str:
        """Prepare/commit success publication (SPEC 9.4): single-writer CAS with cancel fencing."""
        with self._txn() as cursor:
            attempt = cursor.execute("SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
            if attempt is None:
                raise SupervisorRegistryError(f"unknown attempt: {attempt_id}")
            if attempt["status"] in ATTEMPT_TERMINAL:
                return "already_terminal"
            if attempt["version"] != expected_version:
                return "version_conflict"
            if require_publishing and attempt["status"] != "publishing":
                return "not_publishing"
            execution = cursor.execute("SELECT cancel_requested FROM executions WHERE run_id = ?", (attempt["run_id"],)).fetchone()
            node = cursor.execute(
                "SELECT cancel_requested FROM nodes WHERE run_id = ? AND analysis_id = ?",
                (attempt["run_id"], attempt["analysis_id"]),
            ).fetchone()
            if execution is None or node is None:
                raise SupervisorRegistryError("attempt is not attached to execution/node rows")
            if execution["cancel_requested"] or node["cancel_requested"] or attempt["cancel_requested"]:
                return "cancel_accepted"
            cursor.execute(
                "UPDATE attempts SET status = 'succeeded', success_manifest_sha256 = ?, version = version + 1 WHERE attempt_id = ? AND version = ?",
                (success_manifest_sha256, attempt_id, expected_version),
            )
            return "committed"

    def cancel_scope(self, *, run_id: str, analysis_id: str | None = None) -> tuple[str, tuple[str, ...]]:
        """CAS-write cancel_requested on execution/node/active attempts; return scope status and affected attempts."""
        with self._txn() as cursor:
            execution = cursor.execute("SELECT * FROM executions WHERE run_id = ?", (run_id,)).fetchone()
            if execution is None:
                return "unknown_run", ()
            if execution["status"] in EXECUTION_TERMINAL:
                return "already_terminal", ()
            changed = False
            if execution["cancel_requested"] == 0:
                cursor.execute(
                    "UPDATE executions SET cancel_requested = 1, version = version + 1, updated_at = ? WHERE run_id = ? AND version = ?",
                    (_utcnow(), run_id, execution["version"]),
                )
                changed = True
            if analysis_id is not None:
                node = cursor.execute("SELECT * FROM nodes WHERE run_id = ? AND analysis_id = ?", (run_id, analysis_id)).fetchone()
                if node is None:
                    return "unknown_analysis", ()
                if node["status"] not in NODE_TERMINAL and node["cancel_requested"] == 0:
                    cursor.execute(
                        "UPDATE nodes SET cancel_requested = 1, version = version + 1 WHERE run_id = ? AND analysis_id = ? AND version = ?",
                        (run_id, analysis_id, node["version"]),
                    )
                    changed = True
                attempts = cursor.execute(
                    "SELECT attempt_id, status, version, cancel_requested FROM attempts WHERE run_id = ? AND analysis_id = ?",
                    (run_id, analysis_id),
                ).fetchall()
            else:
                attempts = cursor.execute(
                    "SELECT attempt_id, status, version, cancel_requested FROM attempts WHERE run_id = ?",
                    (run_id,),
                ).fetchall()
            affected: list[str] = []
            for attempt in attempts:
                if attempt["status"] not in ATTEMPT_TERMINAL and attempt["cancel_requested"] == 0:
                    cursor.execute(
                        "UPDATE attempts SET cancel_requested = 1, version = version + 1 WHERE attempt_id = ? AND version = ?",
                        (attempt["attempt_id"], attempt["version"]),
                    )
                    affected.append(attempt["attempt_id"])
                    changed = True
            return ("accepted" if changed else "already_requested"), tuple(affected)

    def expire_stale_executions(self, now_iso: str) -> tuple[str, ...]:
        """Restart reconciliation: fail/cancel non-terminal executions whose lease expired.

        M3-04b3 marks stale executions ``failed`` without child-evidence
        classification; SPEC 9.4's EngineProtocolFailure / orphan-identity
        matching requires consuming ``backend_executions`` child identity and
        real process probing, which belongs to M3-09 failure injection.
        """
        with self._txn() as cursor:
            rows = cursor.execute(
                """
                SELECT run_id, status, version, cancel_requested FROM executions
                WHERE status NOT IN ('succeeded', 'failed', 'cancelled')
                  AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
                """,
                (now_iso,),
            ).fetchall()
            expired: list[str] = []
            for row in rows:
                new_status = "cancelled" if row["cancel_requested"] else "failed"
                cursor.execute(
                    "UPDATE executions SET status = ?, version = version + 1, updated_at = ? WHERE run_id = ? AND version = ?",
                    (new_status, _utcnow(), row["run_id"], row["version"]),
                )
                expired.append(row["run_id"])
            return tuple(expired)

    def expire_cancelled_publishing(self) -> tuple[str, ...]:
        """Publish-journal reconciliation: publishing attempts with accepted cancel become cancelled."""
        with self._txn() as cursor:
            rows = cursor.execute(
                "SELECT attempt_id, version FROM attempts WHERE status = 'publishing' AND cancel_requested = 1"
            ).fetchall()
            for row in rows:
                cursor.execute(
                    "UPDATE attempts SET status = 'cancelled', version = version + 1 WHERE attempt_id = ? AND version = ?",
                    (row["attempt_id"], row["version"]),
                )
            return tuple(row["attempt_id"] for row in rows)

    def record_backend_execution(self, *, backend_execution_id: str, attempt_id: str, role: str, engine_instance_id: str) -> Mapping[str, Any]:
        with self._txn() as cursor:
            cursor.execute(
                """
                INSERT INTO backend_executions (backend_execution_id, attempt_id, role, engine_instance_id, status, version)
                VALUES (?, ?, ?, ?, 'pending', 1)
                """,
                (backend_execution_id, attempt_id, role, engine_instance_id),
            )
            return dict(cursor.execute("SELECT * FROM backend_executions WHERE backend_execution_id = ?", (backend_execution_id,)).fetchone())

    def get_backend_execution(self, backend_execution_id: str) -> Mapping[str, Any] | None:
        row = self._read("SELECT * FROM backend_executions WHERE backend_execution_id = ?", (backend_execution_id,))
        return dict(row) if row is not None else None

    def list_backend_executions(self, attempt_id: str | None = None) -> tuple[Mapping[str, Any], ...]:
        if attempt_id is None:
            rows = self._connection.execute("SELECT * FROM backend_executions ORDER BY backend_execution_id").fetchall()
        else:
            rows = self._connection.execute("SELECT * FROM backend_executions WHERE attempt_id = ? ORDER BY backend_execution_id", (attempt_id,)).fetchall()
        return tuple(dict(row) for row in rows)

    def update_backend_identity(self, backend_execution_id: str, expected_version: int, *, pid: int | None, process_start_time: str | None, run_token: str | None, executable_hash: str | None) -> bool:
        updates = {"pid": pid, "process_start_time": process_start_time, "run_token": run_token, "executable_hash": executable_hash}
        return self._cas_row("backend_executions", "backend_execution_id", backend_execution_id, expected_version, updates, BACKEND_TERMINAL)

    def cas_backend_execution(self, backend_execution_id: str, expected_version: int, *, status: str | None = None) -> bool:
        updates = {"status": status}
        return self._cas_row("backend_executions", "backend_execution_id", backend_execution_id, expected_version, updates, BACKEND_TERMINAL)

    def _cas_row(
        self,
        table: str,
        key_column: str,
        key_value: str,
        expected_version: int,
        updates: Mapping[str, Any],
        terminal: set[str],
        *,
        extra_where: str | None = None,
        extra_params: tuple[Any, ...] = (),
    ) -> bool:
        select_where = f"{key_column} = ?" if extra_where is None else extra_where
        select_params: tuple[Any, ...] = (key_value,) if extra_where is None else extra_params
        with self._txn() as cursor:
            row = cursor.execute(f"SELECT status, version FROM {table} WHERE {select_where}", select_params).fetchone()
            if row is None or row["version"] != expected_version:
                raise CasConflict(f"{table} version mismatch or missing row")
            self._guard_terminal(row["status"], terminal, updates)
            assignments: list[str] = []
            parameters: list[Any] = []
            for field, value in updates.items():
                if value is None:
                    continue
                assignments.append(f"{field} = ?")
                parameters.append(value)
            if not assignments:
                return False
            assignments.append("version = version + 1")
            if table == "executions":
                assignments.append("updated_at = ?")
                parameters.append(_utcnow())
            if extra_where is None:
                where = f"{key_column} = ? AND version = ?"
                parameters.extend([key_value, expected_version])
            else:
                where = f"{extra_where} AND version = ?"
                parameters.extend([*extra_params, expected_version])
            cursor.execute(f"UPDATE {table} SET {', '.join(assignments)} WHERE {where}", parameters)
            if cursor.rowcount != 1:
                raise CasConflict(f"{table} CAS lost the race")
            return True
