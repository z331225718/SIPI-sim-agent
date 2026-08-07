from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))

from sipi_runtime import Supervisor, SupervisorBusy, SupervisorClient, SupervisorServer, SupervisorUnavailable, ipc_address, ipc_family


class SupervisorIpcTests(unittest.TestCase):
    def test_address_is_local_and_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            first = ipc_address(directory)
            second = ipc_address(directory)
            self.assertEqual(first, second)
            self.assertEqual(ipc_family(), "AF_PIPE" if sys.platform == "win32" else "AF_UNIX")

    def test_ping_submit_status_cancel_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            supervisor = Supervisor(directory)
            with SupervisorServer(supervisor, directory) as server:
                client = SupervisorClient(directory)
                self.assertTrue(client.ping()["ok"])
                submitted = client.request(
                    {
                        "command": "submit",
                        "run_id": "run-1",
                        "project_hash": "h1",
                        "submission_key": "key-1",
                        "failure_policy": "block-dependents, continue-independent",
                    }
                )
                self.assertTrue(submitted["ok"])
                status = client.request({"command": "status", "run_id": "run-1"})
                self.assertEqual(status["execution"]["status"], "queued")
                cancelled = client.request({"command": "cancel", "run_id": "run-1"})
                self.assertEqual(cancelled["status"], "accepted")
                server.close()

    def test_second_server_is_busy(self):
        with tempfile.TemporaryDirectory() as directory:
            first = SupervisorServer(Supervisor(directory), directory)
            first.start()
            try:
                second = SupervisorServer(Supervisor(directory), directory)
                with self.assertRaises(SupervisorBusy):
                    second.start()
                second.close()
            finally:
                first.close()

    def test_client_fails_when_no_supervisor(self):
        with tempfile.TemporaryDirectory() as directory:
            client = SupervisorClient(directory)
            with self.assertRaises(SupervisorUnavailable):
                client.ping()

    def test_unknown_command_returns_error_response(self):
        with tempfile.TemporaryDirectory() as directory:
            with SupervisorServer(Supervisor(directory), directory) as server:
                response = SupervisorClient(directory).request({"command": "nope"})
                self.assertFalse(response["ok"])
                server.close()


class ReconciliationTests(unittest.TestCase):
    def _registry_with_execution(self, directory: Path, *, lease_expires_at: str | None, cancel_requested: bool = False) -> Supervisor:
        supervisor = Supervisor(directory)
        supervisor.registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
        if lease_expires_at is not None:
            supervisor.registry.cas_execution("run-1", 1, lease_owner="supervisor-1", lease_expires_at=lease_expires_at, heartbeat_at="2000-01-01T00:00:00+00:00")
            if cancel_requested:
                supervisor.registry.cas_execution("run-1", 2, cancel_requested=True)
        return supervisor

    def test_stale_lease_execution_fails_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            supervisor = self._registry_with_execution(Path(directory), lease_expires_at="2000-01-01T00:00:00+00:00")
            report = supervisor.reconcile()
            self.assertEqual(report["expired_executions"], ("run-1",))
            self.assertEqual(supervisor.registry.get_execution("run-1")["status"], "failed")
            second = supervisor.reconcile()
            self.assertEqual(second["expired_executions"], ())
            supervisor.close()

    def test_stale_lease_with_cancel_becomes_cancelled(self):
        with tempfile.TemporaryDirectory() as directory:
            supervisor = self._registry_with_execution(Path(directory), lease_expires_at="2000-01-01T00:00:00+00:00", cancel_requested=True)
            supervisor.reconcile()
            self.assertEqual(supervisor.registry.get_execution("run-1")["status"], "cancelled")
            supervisor.close()

    def test_fresh_lease_is_not_expired(self):
        with tempfile.TemporaryDirectory() as directory:
            supervisor = self._registry_with_execution(Path(directory), lease_expires_at="2099-01-01T00:00:00+00:00")
            report = supervisor.reconcile()
            self.assertEqual(report["expired_executions"], ())
            self.assertEqual(supervisor.registry.get_execution("run-1")["status"], "queued")
            supervisor.close()

    def test_cancelled_publishing_attempt_is_settled(self):
        with tempfile.TemporaryDirectory() as directory:
            supervisor = Supervisor(directory)
            supervisor.registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
            supervisor.registry.create_node(run_id="run-1", analysis_id="a", effective_required=True)
            supervisor.registry.append_attempt(attempt_id="attempt-1", run_id="run-1", analysis_id="a", retry_index=0)
            supervisor.registry.cas_attempt("attempt-1", 1, status="publishing")
            supervisor.registry.cancel_scope(run_id="run-1", analysis_id="a")
            report = supervisor.reconcile()
            self.assertEqual(report["cancelled_publishing_attempts"], ("attempt-1",))
            self.assertEqual(supervisor.registry.get_attempt("attempt-1")["status"], "cancelled")
            supervisor.close()

    def _staged_publish(self, directory: Path, *, analysis_id: str = "a", attempt_id: str = "attempt-1") -> None:
        supervisor = Supervisor(directory)
        supervisor.registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
        supervisor.registry.create_node(run_id="run-1", analysis_id=analysis_id, effective_required=True)
        supervisor.registry.append_attempt(attempt_id=attempt_id, run_id="run-1", analysis_id=analysis_id, retry_index=0)
        supervisor.registry.cas_attempt(attempt_id, 1, status="publishing")
        supervisor.close()

    def _write_staged_manifest(self, directory: Path, *, analysis_id: str = "a", attempt_id: str = "attempt-1", artifact_relative_path: str | None = None, corrupt: bool = False, create_artifact: bool = True) -> bytes | None:
        artifact_relative_path = artifact_relative_path or f"nodes/{analysis_id}/attempts/{attempt_id}/out/data.json"
        artifact_path = Path(directory) / artifact_relative_path
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        if create_artifact:
            artifact_path.write_bytes(b'{"data": 1}')
        manifest = {
            "schema": "sipi.success-manifest.v1",
            "run_id": "run-1",
            "analysis_id": analysis_id,
            "attempt_id": attempt_id,
            "run_record_sha256": "0" * 64,
            "checksums_sha256": "0" * 64,
            "artifacts": [{"schema": "sipi.artifact-ref.v1", "relative_path": artifact_relative_path, "role": "data", "producer": "test"}],
            "extensions": {},
        }
        manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        manifest_path = Path(directory) / "nodes" / analysis_id / "attempts" / attempt_id / "success-manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if corrupt:
            manifest_path.write_bytes(b"{not json")
            return None
        manifest_path.write_bytes(manifest_bytes)
        return manifest_bytes

    def test_staged_manifest_is_rebuilt_after_publish_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            self._staged_publish(Path(directory))
            manifest_bytes = self._write_staged_manifest(Path(directory))
            supervisor = Supervisor(directory)
            report = supervisor.reconcile()
            self.assertEqual(report["rebuilt_publishing_attempts"], ("attempt-1",))
            self.assertEqual(report["failed_publishing_attempts"], ())
            attempt = supervisor.registry.get_attempt("attempt-1")
            self.assertEqual(attempt["status"], "succeeded")
            self.assertEqual(attempt["success_manifest_sha256"], hashlib.sha256(manifest_bytes).hexdigest())
            second = supervisor.reconcile()
            self.assertEqual(second["rebuilt_publishing_attempts"], ())
            self.assertEqual(second["failed_publishing_attempts"], ())
            supervisor.close()

    def test_publishing_without_manifest_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            self._staged_publish(Path(directory))
            supervisor = Supervisor(directory)
            report = supervisor.reconcile()
            self.assertEqual(report["failed_publishing_attempts"], ("attempt-1",))
            self.assertEqual(supervisor.registry.get_attempt("attempt-1")["status"], "failed")
            supervisor.close()

    def test_corrupt_or_missing_artifact_manifest_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            self._staged_publish(Path(directory))
            self._write_staged_manifest(Path(directory), corrupt=True)
            supervisor = Supervisor(directory)
            report = supervisor.reconcile()
            self.assertEqual(report["failed_publishing_attempts"], ("attempt-1",))
            self.assertEqual(supervisor.registry.get_attempt("attempt-1")["status"], "failed")
            supervisor.close()
        with tempfile.TemporaryDirectory() as directory:
            self._staged_publish(Path(directory))
            self._write_staged_manifest(Path(directory), artifact_relative_path="missing/out/data.json", create_artifact=False)
            supervisor = Supervisor(directory)
            report = supervisor.reconcile()
            self.assertEqual(report["failed_publishing_attempts"], ("attempt-1",))
            supervisor.close()
            supervisor.close()

    def test_execution_cancel_settles_staged_publish_as_cancelled(self):
        with tempfile.TemporaryDirectory() as directory:
            supervisor = Supervisor(directory)
            supervisor.registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
            supervisor.registry.create_node(run_id="run-1", analysis_id="a", effective_required=True)
            supervisor.registry.append_attempt(attempt_id="attempt-1", run_id="run-1", analysis_id="a", retry_index=0)
            supervisor.registry.cas_attempt("attempt-1", 1, status="publishing")
            supervisor.registry.cas_execution("run-1", supervisor.registry.get_execution("run-1")["version"], cancel_requested=True)
            self._write_staged_manifest(Path(directory))
            report = supervisor.reconcile()
            self.assertEqual(report["cancelled_publishing_attempts"], ())
            self.assertEqual(report["rebuilt_publishing_attempts"], ())
            self.assertEqual(report["failed_publishing_attempts"], ())
            self.assertEqual(supervisor.registry.get_attempt("attempt-1")["status"], "cancelled")
            supervisor.close()


if __name__ == "__main__":
    unittest.main()
