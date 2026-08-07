from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))

from sipi_runtime import (
    CasConflict,
    DuplicateAttempt,
    DuplicateNode,
    SubmissionKeyConflict,
    SupervisorRegistry,
    TerminalTransition,
)


class SupervisorRegistryTests(unittest.TestCase):
    def test_submission_is_idempotent_and_key_conflict_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with SupervisorRegistry(Path(directory) / "registry.sqlite3") as registry:
                first = registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="block-dependents, continue-independent")
                self.assertEqual(first["status"], "queued")
                self.assertEqual(first["version"], 1)
                replay = registry.submit_execution(run_id="run-2", project_hash="h1", submission_key="key-1", failure_policy="block-dependents, continue-independent")
                self.assertEqual(replay["run_id"], "run-1")
                self.assertEqual(registry.get_execution("run-2"), None)
                with self.assertRaises(SubmissionKeyConflict):
                    registry.submit_execution(run_id="run-3", project_hash="h2", submission_key="key-1", failure_policy="block-dependents, continue-independent")

    def test_retry_of_lineage_and_unknown_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            with SupervisorRegistry(Path(directory) / "registry.sqlite3") as registry:
                row = registry.submit_execution(run_id="run-2", project_hash="h2", submission_key="key-2", failure_policy="p", retry_of="run-1")
                self.assertEqual(row["retry_of"], "run-1")
                self.assertIsNone(registry.get_execution("missing"))

    def test_execution_cas_bumps_version_and_terminal_is_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with SupervisorRegistry(Path(directory) / "registry.sqlite3") as registry:
                registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
                self.assertTrue(registry.cas_execution("run-1", 1, status="resolving"))
                row = registry.get_execution("run-1")
                self.assertEqual(row["version"], 2)
                with self.assertRaises(CasConflict):
                    registry.cas_execution("run-1", 1, status="active")
                self.assertTrue(registry.cas_execution("run-1", 2, status="succeeded"))
                with self.assertRaises(TerminalTransition):
                    registry.cas_execution("run-1", 3, status="failed")
                with self.assertRaises(TerminalTransition):
                    registry.cas_execution("run-1", 3, cancel_requested=True)
                with self.assertRaises(TerminalTransition):
                    registry.cas_execution("run-1", 3, lease_owner="supervisor-2")

    def test_cancel_flag_and_lease_heartbeat(self):
        with tempfile.TemporaryDirectory() as directory:
            with SupervisorRegistry(Path(directory) / "registry.sqlite3") as registry:
                registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
                self.assertTrue(registry.cas_execution("run-1", 1, cancel_requested=True))
                row = registry.get_execution("run-1")
                self.assertEqual(row["cancel_requested"], 1)
                self.assertTrue(registry.cas_execution("run-1", 2, lease_owner="supervisor-1", lease_expires_at="2099-01-01T00:00:00+00:00", heartbeat_at="2099-01-01T00:00:00+00:00"))
                row = registry.get_execution("run-1")
                self.assertEqual(row["lease_owner"], "supervisor-1")
                self.assertEqual(row["version"], 3)

    def test_node_cas_with_composite_key_and_blocked_by(self):
        with tempfile.TemporaryDirectory() as directory:
            with SupervisorRegistry(Path(directory) / "registry.sqlite3") as registry:
                registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
                node = registry.create_node(run_id="run-1", analysis_id="a", effective_required=True)
                self.assertEqual(node["status"], "pending")
                with self.assertRaises(DuplicateNode):
                    registry.create_node(run_id="run-1", analysis_id="a", effective_required=False)
                self.assertTrue(registry.cas_node("run-1", "a", 1, status="blocked", blocked_by=[{"analysis_id": "up", "terminal_status": "failed"}]))
                node = registry.get_node("run-1", "a")
                self.assertEqual(node["status"], "blocked")
                self.assertEqual(node["version"], 2)
                self.assertEqual(node["blocked_by"], '[{"analysis_id": "up", "terminal_status": "failed"}]')
                with self.assertRaises(CasConflict):
                    registry.cas_node("run-1", "a", 1, status="ready")

    def test_attempts_are_appended_and_unique(self):
        with tempfile.TemporaryDirectory() as directory:
            with SupervisorRegistry(Path(directory) / "registry.sqlite3") as registry:
                registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
                registry.create_node(run_id="run-1", analysis_id="a", effective_required=True)
                attempt = registry.append_attempt(attempt_id="attempt-1", run_id="run-1", analysis_id="a", retry_index=0)
                self.assertEqual(attempt["status"], "queued")
                with self.assertRaises(DuplicateAttempt):
                    registry.append_attempt(attempt_id="attempt-1", run_id="run-1", analysis_id="a", retry_index=1)
                registry.append_attempt(attempt_id="attempt-2", run_id="run-1", analysis_id="a", retry_index=1)
                self.assertTrue(registry.cas_attempt("attempt-1", 1, status="running"))
                self.assertEqual(registry.get_attempt("attempt-1")["version"], 2)

    def test_backend_execution_identity_and_cas(self):
        with tempfile.TemporaryDirectory() as directory:
            with SupervisorRegistry(Path(directory) / "registry.sqlite3") as registry:
                registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
                registry.create_node(run_id="run-1", analysis_id="a", effective_required=True)
                registry.append_attempt(attempt_id="attempt-1", run_id="run-1", analysis_id="a", retry_index=0)
                backend = registry.record_backend_execution(backend_execution_id="be-1", attempt_id="attempt-1", role="reference", engine_instance_id="pybert-python")
                self.assertEqual(backend["status"], "pending")
                self.assertTrue(registry.update_backend_identity("be-1", 1, pid=1234, process_start_time="2026-08-07T00:00:00+00:00", run_token="token-1", executable_hash="a" * 64))
                row = registry.get_backend_execution("be-1")
                self.assertEqual(row["pid"], 1234)
                self.assertEqual(row["run_token"], "token-1")
                self.assertTrue(registry.cas_backend_execution("be-1", 2, status="running"))
                self.assertEqual(registry.get_backend_execution("be-1")["version"], 3)

    def test_registry_persists_across_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.sqlite3"
            with SupervisorRegistry(path) as registry:
                registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
                registry.create_node(run_id="run-1", analysis_id="a", effective_required=True)
                registry.append_attempt(attempt_id="attempt-1", run_id="run-1", analysis_id="a", retry_index=0)
            with SupervisorRegistry(path) as reopened:
                self.assertEqual(reopened.get_execution("run-1")["status"], "queued")
                self.assertEqual(reopened.get_node("run-1", "a")["status"], "pending")
                self.assertEqual(reopened.get_attempt("attempt-1")["status"], "queued")


if __name__ == "__main__":
    unittest.main()
