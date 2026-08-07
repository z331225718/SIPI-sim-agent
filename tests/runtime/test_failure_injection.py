from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))

from sipi_runtime import SupervisorRegistry


class FailureInjectionTests(unittest.TestCase):
    def test_concurrent_same_key_submission_creates_once(self):
        with tempfile.TemporaryDirectory() as directory:
            with SupervisorRegistry(Path(directory) / "registry.sqlite3") as registry:
                results: list[tuple[str, bool]] = []
                barrier = threading.Barrier(2)

                def submit(name: str) -> None:
                    barrier.wait()
                    row, created = registry.submit_execution_record(run_id=f"run-{name}", project_hash="h1", submission_key="same-key", failure_policy="p")
                    results.append((row["run_id"], created))

                first = threading.Thread(target=submit, args=("a",))
                second = threading.Thread(target=submit, args=("b",))
                first.start()
                second.start()
                first.join(timeout=15)
                second.join(timeout=15)
                self.assertFalse(first.is_alive())
                self.assertFalse(second.is_alive())
                self.assertEqual(len(results), 2)
                self.assertEqual(sum(created for _, created in results), 1)
                self.assertEqual(results[0][0], results[1][0])
                self.assertEqual(len(registry.list_backend_executions()), 0)  # no stray rows

    def test_cancel_publish_race_is_single_writer_consistent(self):
        with tempfile.TemporaryDirectory() as directory:
            with SupervisorRegistry(Path(directory) / "registry.sqlite3") as registry:
                registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
                registry.create_node(run_id="run-1", analysis_id="a", effective_required=True)
                registry.append_attempt(attempt_id="attempt-1", run_id="run-1", analysis_id="a", retry_index=0)
                registry.cas_attempt("attempt-1", 1, status="publishing")
                outcomes: list[str] = []
                barrier = threading.Barrier(2)

                def publisher() -> None:
                    barrier.wait()
                    outcomes.append(registry.attempt_publish_cas(attempt_id="attempt-1", expected_version=2, success_manifest_sha256="m" * 64))

                def canceller() -> None:
                    barrier.wait()
                    status, _ = registry.cancel_scope(run_id="run-1", analysis_id="a")
                    outcomes.append(status)

                first = threading.Thread(target=publisher)
                second = threading.Thread(target=canceller)
                first.start()
                second.start()
                first.join(timeout=15)
                second.join(timeout=15)
                self.assertFalse(first.is_alive())
                self.assertFalse(second.is_alive())
                publish_outcome = next(item for item in outcomes if item in {"committed", "cancel_accepted", "not_publishing", "already_terminal", "version_conflict"})
                attempt = registry.get_attempt("attempt-1")
                execution = registry.get_execution("run-1")
                if publish_outcome == "committed":
                    self.assertEqual(attempt["status"], "succeeded")
                    self.assertEqual(attempt["success_manifest_sha256"], "m" * 64)
                else:
                    self.assertEqual(attempt["status"], "publishing")
                    self.assertEqual(execution["cancel_requested"], 1)


if __name__ == "__main__":
    unittest.main()
