from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))

from sipi_runtime import (
    Supervisor,
    SupervisorRegistry,
    child_identity,
    is_process_alive,
    matches_identity,
    spawn_managed,
    terminate_tree,
)

SLEEP_SCRIPT = "import time; time.sleep(30)"


class ProcessTreeTests(unittest.TestCase):
    def _env(self) -> dict:
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PYTHONNOUSERSITE"] = "1"
        return env

    def test_spawn_managed_identity_and_terminate(self):
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            process, identity = spawn_managed(
                [sys.executable, "-c", SLEEP_SCRIPT],
                workdir=workdir,
                env=self._env(),
                run_token="token-1",
                executable_hash="a" * 64,
            )
            try:
                self.assertTrue(is_process_alive(process.pid))
                self.assertEqual(identity.pid, process.pid)
                self.assertEqual(identity.run_token, "token-1")
                self.assertIsNotNone(identity.process_start_time)
                self.assertTrue(matches_identity(process.pid, identity.process_start_time))
            finally:
                terminate_tree(process)
                process.wait(timeout=15)
            self.assertFalse(is_process_alive(process.pid))

    def test_terminate_tree_by_pid_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.Popen([sys.executable, "-c", SLEEP_SCRIPT], cwd=directory)
            try:
                self.assertTrue(is_process_alive(process.pid))
                terminate_tree(pid=process.pid)
                process.wait(timeout=15)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=15)
            self.assertFalse(is_process_alive(process.pid))

    def test_matches_identity_rejects_pid_reuse_with_different_start(self):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.Popen([sys.executable, "-c", SLEEP_SCRIPT], cwd=directory)
            try:
                identity = child_identity(process.pid, run_token="t")
                self.assertTrue(matches_identity(process.pid, identity.process_start_time))
                self.assertFalse(matches_identity(process.pid, "0"))
            finally:
                process.kill()
                process.wait(timeout=15)


class SupervisorProcessTests(unittest.TestCase):
    def test_cancel_terminates_managed_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            supervisor = Supervisor(data_dir)
            supervisor.registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
            supervisor.registry.create_node(run_id="run-1", analysis_id="a", effective_required=True)
            supervisor.registry.append_attempt(attempt_id="attempt-1", run_id="run-1", analysis_id="a", retry_index=0)
            process, identity = spawn_managed(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                workdir=data_dir,
                env=dict(os.environ),
                run_token="token-1",
            )
            try:
                supervisor.registry.record_backend_execution(backend_execution_id="be-1", attempt_id="attempt-1", role="primary", engine_instance_id="pybert-python")
                supervisor.registry.update_backend_identity(
                    "be-1",
                    1,
                    pid=identity.pid,
                    process_start_time=identity.process_start_time,
                    run_token=identity.run_token,
                    executable_hash=identity.executable_hash,
                )
                supervisor.registry.cas_backend_execution("be-1", 2, status="running")
                status, _ = supervisor.request_cancel(run_id="run-1", analysis_id="a")
                self.assertEqual(status, "accepted")
                process.wait(timeout=15)
                self.assertFalse(is_process_alive(identity.pid))
                self.assertEqual(supervisor.registry.get_backend_execution("be-1")["status"], "cancelled")
            finally:
                if process.poll() is None:
                    terminate_tree(pid=identity.pid)
                    process.wait(timeout=15)
                supervisor.close()

    def test_reconcile_settles_dead_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            supervisor = Supervisor(data_dir)
            supervisor.registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
            supervisor.registry.create_node(run_id="run-1", analysis_id="a", effective_required=True)
            supervisor.registry.append_attempt(attempt_id="attempt-1", run_id="run-1", analysis_id="a", retry_index=0)
            process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], cwd=data_dir)
            identity = child_identity(process.pid, run_token="t")
            process.kill()
            process.wait(timeout=15)
            supervisor.registry.record_backend_execution(backend_execution_id="be-1", attempt_id="attempt-1", role="primary", engine_instance_id="pybert-python")
            supervisor.registry.update_backend_identity("be-1", 1, pid=identity.pid, process_start_time=identity.process_start_time, run_token="t", executable_hash=None)
            supervisor.registry.cas_backend_execution("be-1", 2, status="running")
            report = supervisor.reconcile()
            self.assertIn("be-1", report["settled_backends"])
            self.assertEqual(supervisor.registry.get_backend_execution("be-1")["status"], "failed")
            supervisor.close()


if __name__ == "__main__":
    unittest.main()
