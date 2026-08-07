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
        if current_status in terminal and updates.get("status") not in {None, current_status}:
            raise TerminalTransition(f"terminal row cannot transition from {current_status}")

    def submit_execution(
        self,
        *,
        run_id: str,
        project_hash: str,
        submission_key: str,
        failure_policy: str,
        retry_of: str | None = None,
    ) -> Mapping[str, Any]:
        with self._txn() as cursor:
            existing = cursor.execute("SELECT * FROM executions WHERE submission_key = ?", (submission_key,)).fetchone()
            if existing is not None:
                if existing["project_hash"] != project_hash:
                    raise SubmissionKeyConflict("submission key reused with a different project hash")
                return dict(existing)
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
            return dict(cursor.execute("SELECT * FROM executions WHERE run_id = ?", (run_id,)).fetchone())

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

    def cas_attempt(self, attempt_id: str, expected_version: int, *, status: str | None = None, cancel_requested: bool | None = None) -> bool:
        updates = {"status": status, "cancel_requested": cancel_requested}
        return self._cas_row("attempts", "attempt_id", attempt_id, expected_version, updates, ATTEMPT_TERMINAL)

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
