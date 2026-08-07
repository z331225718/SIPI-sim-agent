from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))

from sipi_runtime import Supervisor, SupervisorBusy, SupervisorLock, SupervisorRegistry


def seeded_registry(directory: Path, *, analysis_count: int = 1) -> SupervisorRegistry:
    registry = SupervisorRegistry(directory / "supervisor.sqlite3")
    registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="block-dependents, continue-independent")
    for index in range(analysis_count):
        analysis_id = f"a{index}"
        registry.create_node(run_id="run-1", analysis_id=analysis_id, effective_required=True)
        registry.append_attempt(attempt_id=f"attempt-{analysis_id}", run_id="run-1", analysis_id=analysis_id, retry_index=0)
    return registry


class SupervisorLockTests(unittest.TestCase):
    def test_lock_is_exclusive_and_releasable(self):
        with tempfile.TemporaryDirectory() as directory:
            first = SupervisorLock(directory)
            first.acquire()
            with self.assertRaises(SupervisorBusy):
                SupervisorLock(directory).acquire()
            first.release()
            with SupervisorLock(directory) as second:
                self.assertTrue(second.path.is_file())

    def test_lock_release_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = SupervisorLock(directory)
            lock.acquire()
            lock.release()
            lock.release()


class PublishProtocolTests(unittest.TestCase):
    def test_publish_commits_when_fenced(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = seeded_registry(Path(directory))
            registry.cas_attempt("attempt-a0", 1, status="publishing")
            supervisor = Supervisor(directory, registry=registry)
            self.assertEqual(supervisor.publish_success(attempt_id="attempt-a0", expected_version=2, success_manifest_sha256="m" * 64), "committed")
            attempt = registry.get_attempt("attempt-a0")
            self.assertEqual(attempt["status"], "succeeded")
            self.assertEqual(attempt["success_manifest_sha256"], "m" * 64)
            self.assertEqual(attempt["version"], 3)
            supervisor.close()

    def test_publish_requires_publishing_state_and_version(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = seeded_registry(Path(directory))
            registry.cas_attempt("attempt-a0", 1, status="running")
            self.assertEqual(registry.attempt_publish_cas(attempt_id="attempt-a0", expected_version=2, success_manifest_sha256="m" * 64), "not_publishing")
            self.assertEqual(registry.attempt_publish_cas(attempt_id="attempt-a0", expected_version=1, success_manifest_sha256="m" * 64), "version_conflict")
            registry.close()

    def test_publish_rejects_terminal_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = seeded_registry(Path(directory))
            registry.cas_attempt("attempt-a0", 1, status="succeeded")
            self.assertEqual(registry.attempt_publish_cas(attempt_id="attempt-a0", expected_version=2, success_manifest_sha256="m" * 64), "already_terminal")
            registry.close()

    def test_publish_is_fenced_by_accepted_cancel(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = seeded_registry(Path(directory))
            registry.cas_execution("run-1", 1, cancel_requested=True)
            registry.cas_attempt("attempt-a0", 1, status="publishing")
            self.assertEqual(registry.attempt_publish_cas(attempt_id="attempt-a0", expected_version=2, success_manifest_sha256="m" * 64), "cancel_accepted")
            attempt = registry.get_attempt("attempt-a0")
            self.assertEqual(attempt["status"], "publishing")
            self.assertIsNone(attempt["success_manifest_sha256"])
            registry.close()


class CancelProtocolTests(unittest.TestCase):
    def test_cancel_scope_accepted_then_already_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = seeded_registry(Path(directory))
            status, affected = registry.cancel_scope(run_id="run-1")
            self.assertEqual(status, "accepted")
            self.assertEqual(affected, ("attempt-a0",))
            self.assertEqual(registry.get_execution("run-1")["cancel_requested"], 1)
            self.assertEqual(registry.get_attempt("attempt-a0")["cancel_requested"], 1)
            status, _ = registry.cancel_scope(run_id="run-1")
            self.assertEqual(status, "already_requested")
            registry.close()

    def test_cancel_scope_analysis_and_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = seeded_registry(Path(directory), analysis_count=2)
            status, affected = registry.cancel_scope(run_id="run-1", analysis_id="a1")
            self.assertEqual(status, "accepted")
            self.assertEqual(affected, ("attempt-a1",))
            self.assertEqual(registry.get_node("run-1", "a1")["cancel_requested"], 1)
            self.assertEqual(registry.get_attempt("attempt-a0")["cancel_requested"], 0)
            status, _ = registry.cancel_scope(run_id="run-1", analysis_id="missing")
            self.assertEqual(status, "unknown_analysis")
            registry.cas_execution("run-1", registry.get_execution("run-1")["version"], status="succeeded")
            status, _ = registry.cancel_scope(run_id="run-1")
            self.assertEqual(status, "already_terminal")
            self.assertEqual(registry.cancel_scope(run_id="missing")[0], "unknown_run")
            registry.close()


if __name__ == "__main__":
    unittest.main()
