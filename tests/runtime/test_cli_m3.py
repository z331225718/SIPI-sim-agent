from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "sipi-cli" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))

from sipi_cli.__main__ import main
from sipi_runtime import Supervisor, SupervisorClient, SupervisorServer
from sipi_runtime.supervisor_main import build_runner, spawn_supervisor

FAKE_PYBERT = ROOT / "tests" / "adapters" / "fixtures" / "fake_pybert.py"


def engine_entry(instance_id: str) -> dict:
    digest = "a" * 64
    return {
        "instance_id": instance_id,
        "engine_family": "pybert",
        "version": "0.1.0",
        "source_commit": "0" * 40,
        "bundle": {"kind": "local_path", "path": "marker.exe", "sha256": digest},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": "2" * 64,
        "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "3" * 64},
        "bundle_manifest": {"entrypoint": "marker.exe", "files": [{"relative_path": "marker.exe", "role": "entrypoint", "sha256": digest, "byte_length": 9}]},
        "extensions": {},
    }


def write_project(root: Path, *, payload_artifact: str | None = None) -> None:
    (root / "engine.lock").write_text(json.dumps({"schema": "sipi.engine-lock.v1", "engines": [engine_entry("pybert-python")], "operation_defaults": {}, "extensions": {}}), encoding="utf-8")
    analysis = {
        "id": "link-eye",
        "operation": "link.simulate.v1",
        "backend_selection": {"mode": "strict", "instance": "pybert-python"},
        "payload_schema": "pybert.simulation.v1",
    }
    if payload_artifact is not None:
        analysis["payload_artifact"] = payload_artifact
        (root / payload_artifact).parent.mkdir(parents=True, exist_ok=True)
        (root / payload_artifact).write_text('{"sample": 2}', encoding="utf-8")
    else:
        analysis["payload"] = {"sample": 2}
    project = {
        "schema": "sipi.project.v1",
        "project": {"name": "cli-test", "extensions": {}},
        "runtime": {"engine_lock": "engine.lock", "extensions": {}},
        "analyses": [analysis],
        "extensions": {},
    }
    (root / "project.json").write_text(json.dumps(project), encoding="utf-8")


def write_fake_project(root: Path) -> None:
    bundle = root / "bundles" / "pybert.py"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_bytes(FAKE_PYBERT.read_bytes())
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    entry = {
        "instance_id": "pybert-python",
        "engine_family": "pybert",
        "version": "0.1.0",
        "source_commit": "0" * 40,
        "bundle": {"kind": "local_path", "path": "bundles/pybert.py", "sha256": digest},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": "2" * 64,
        "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "3" * 64},
        "bundle_manifest": {"entrypoint": "pybert.py", "files": [{"relative_path": "pybert.py", "role": "entrypoint", "sha256": digest, "byte_length": bundle.stat().st_size}]},
        "extensions": {},
    }
    (root / "engine.lock").write_text(json.dumps({"schema": "sipi.engine-lock.v1", "engines": [entry], "operation_defaults": {}, "extensions": {}}), encoding="utf-8")
    project = {
        "schema": "sipi.project.v1",
        "project": {"name": "fake-run", "extensions": {}},
        "runtime": {"engine_lock": "engine.lock", "extensions": {}},
        "analyses": [
            {
                "id": "link-eye",
                "operation": "link.simulate.v1",
                "backend_selection": {"mode": "strict", "instance": "pybert-python"},
                "payload_schema": "pybert.simulation.v1",
                "payload": {"simulation_input": {"sample_count": 2}},
            }
        ],
        "extensions": {},
    }
    (root / "project.json").write_text(json.dumps(project), encoding="utf-8")


class CliM3Tests(unittest.TestCase):
    def run_cli(self, *args: str) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main(list(args))
        return status, stdout.getvalue()

    def test_validate_resolves_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root)
            status, output = self.run_cli("validate", "--root", str(root), "--format", "json")
            self.assertEqual(status, 0)
            payload = json.loads(output)
            self.assertIn("project_hash", payload)
            self.assertEqual(len(payload["analyses"]), 1)

    def test_validate_rejects_missing_payload_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root, payload_artifact="requests/link-input.json")
            (root / "requests" / "link-input.json").unlink()
            status, _ = self.run_cli("validate", "--root", str(root))
            self.assertEqual(status, 1)

    def test_run_status_cancel_retry_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root)
            data_dir = root / ".sipi"
            with SupervisorServer(Supervisor(data_dir), data_dir) as server:
                status, output = self.run_cli("run", "--root", str(root), "--detach")
                self.assertEqual(status, 0)
                run_id = json.loads(output)["run_id"]
                status, output = self.run_cli("status", "--root", str(root), run_id)
                self.assertEqual(status, 0)
                self.assertEqual(json.loads(output)["execution"]["status"], "queued")
                status, output = self.run_cli("cancel", "--root", str(root), run_id)
                self.assertEqual(json.loads(output)["status"], "accepted")
                status, output = self.run_cli("retry", "--root", str(root), run_id)
                self.assertEqual(status, 0)
                retry_payload = json.loads(output)
                self.assertNotEqual(retry_payload["run_id"], run_id)
                self.assertEqual(retry_payload["retry_of"], run_id)
                server.close()

    def test_run_foreground_detach_starts_embedded_server(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root)
            status, output = self.run_cli("run", "--root", str(root), "--detach", "--foreground")
            self.assertEqual(status, 0)
            self.assertIn("run_id", json.loads(output))

    def test_status_without_supervisor_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status, _ = self.run_cli("status", "--root", str(root), "run-missing")
            self.assertEqual(status, 1)

    def test_run_wait_timeout_returns_active_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root)
            data_dir = root / ".sipi"
            with SupervisorServer(Supervisor(data_dir), data_dir) as server:
                status, output = self.run_cli("run", "--root", str(root), "--wait-timeout-s", "1")
                self.assertEqual(status, 0)
                self.assertEqual(json.loads(output)["status"], "queued")
                server.close()

    def test_spawn_daemon_serves_ping(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            process = spawn_supervisor(data_dir)
            try:
                client = SupervisorClient(data_dir)
                response = client.ping()
                self.assertTrue(response["ok"])
                shutdown = client.request({"command": "shutdown"})
                self.assertTrue(shutdown["ok"])
                process.wait(timeout=15)
                self.assertNotEqual(process.returncode, None)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=15)

    def test_run_detach_with_runner_executes_to_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fake_project(root)
            data_dir = root / ".sipi"
            supervisor = Supervisor(data_dir)
            with SupervisorServer(supervisor, data_dir, runner=build_runner(supervisor, data_dir)) as server:
                status, output = self.run_cli("run", "--root", str(root), "--detach")
                self.assertEqual(status, 0)
                run_id = json.loads(output)["run_id"]
                client = SupervisorClient(data_dir)
                deadline = time.monotonic() + 15
                final_status = None
                while time.monotonic() < deadline:
                    execution = client.request({"command": "status", "run_id": run_id}).get("execution")
                    final_status = execution.get("status") if execution else None
                    if final_status in {"succeeded", "failed", "cancelled"}:
                        break
                    time.sleep(0.2)
                self.assertEqual(final_status, "succeeded")
                manifest = root / "nodes" / "link-eye" / "attempts" / "link-eye-attempt-0" / "success-manifest.json"
                self.assertTrue(manifest.is_file())
                server.close()


if __name__ == "__main__":
    unittest.main()
