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
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import PyBertNativeAdapter
from sipi_contracts import parse_project
from sipi_runtime import (
    DriverOptions,
    EngineRegistry,
    ExecutionDriver,
    SupervisorRegistry,
    load_engine_lock,
    plan_dag,
    resolve_project,
)

FAKE_PYBERT = ROOT / "tests" / "adapters" / "fixtures" / "fake_pybert.py"


def write_engine_lock(root: Path) -> EngineRegistry:
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
    lock = {"schema": "sipi.engine-lock.v1", "engines": [entry], "operation_defaults": {}, "extensions": {}}
    (root / "engine.lock").write_text(json.dumps(lock), encoding="utf-8")
    return EngineRegistry(load_engine_lock(root / "engine.lock"))


def write_project(root: Path, *, upstream_payload: dict | None = None, upstream_required: bool = True, with_dependent: bool = True) -> None:
    analyses = [
        {
            "id": "channel-response",
            "operation": "link.simulate.v1",
            "backend_selection": {"mode": "strict", "instance": "pybert-python"},
            "payload_schema": "pybert.simulation.v1",
            "payload": {"simulation_input": upstream_payload} if upstream_payload is not None else {"simulation_input": {"sample": 2}},
            "required": upstream_required,
            "exports": [{"role": "domain_result", "schema": "pybert.native-cli-result.v1"}],
        }
    ]
    if with_dependent:
        analyses.append(
            {
                "id": "link-eye",
                "operation": "link.simulate.v1",
                "backend_selection": {"mode": "strict", "instance": "pybert-python"},
                "payload_schema": "pybert.simulation.v1",
                "payload": {"simulation_input": {"sample": 3}},
                "depends_on": ["channel-response"],
                "inputs": {
                    "channel": {
                        "from_analysis": "channel-response",
                        "artifact_role": "domain_result",
                        "expected_schema": "pybert.native-cli-result.v1",
                    }
                },
            }
        )
    project = {
        "schema": "sipi.project.v1",
        "project": {"name": "driver-test", "extensions": {}},
        "runtime": {"engine_lock": "engine.lock", "extensions": {}},
        "analyses": analyses,
        "extensions": {},
    }
    (root / "project.json").write_text(json.dumps(project), encoding="utf-8")


def driver(root: Path, registry: SupervisorRegistry, *, max_attempts: int = 1) -> tuple[ExecutionDriver, object, object, EngineRegistry]:
    engine_registry = write_engine_lock(root)
    resolved = resolve_project(parse_project((root / "project.json").read_text(encoding="utf-8")), root)
    plan = plan_dag(resolved, engine_registry)
    driver_instance = ExecutionDriver(
        registry,
        {"pybert": PyBertNativeAdapter()},
        options=DriverOptions(max_attempts=max_attempts, artifact_root=root),
    )
    return driver_instance, resolved, plan, engine_registry


class ExecutionDriverTests(unittest.TestCase):
    def test_dag_drives_nodes_and_publishes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root)
            with SupervisorRegistry(root / "registry.sqlite3") as registry:
                registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="block-dependents, continue-independent")
                instance, resolved, plan, engine_registry = driver(root, registry)
                report = instance.run(resolved, plan, engine_registry, run_id="run-1")
                self.assertEqual(report["status"], "succeeded")
                self.assertEqual(report["nodes"], {"channel-response": "succeeded", "link-eye": "succeeded"})
                upstream = registry.get_attempt("channel-response-attempt-0")
                self.assertEqual(upstream["status"], "succeeded")
                self.assertTrue(upstream["success_manifest_sha256"])
                self.assertEqual(registry.get_execution("run-1")["status"], "succeeded")
                manifest = root / "nodes" / "channel-response" / "attempts" / "channel-response-attempt-0" / "success-manifest.json"
                self.assertTrue(manifest.is_file())
                meta = root / "nodes" / "channel-response" / "attempts" / "channel-response-attempt-0" / "backends" / "channel-response-attempt-0-primary" / "out" / "meta.json"
                self.assertTrue(meta.is_file())

    def test_upstream_failure_blocks_dependent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root, upstream_payload={"fail": True})
            with SupervisorRegistry(root / "registry.sqlite3") as registry:
                registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="block-dependents, continue-independent")
                instance, resolved, plan, engine_registry = driver(root, registry)
                report = instance.run(resolved, plan, engine_registry, run_id="run-1")
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["nodes"], {"channel-response": "failed", "link-eye": "blocked"})
                downstream = registry.get_node("run-1", "link-eye")
                self.assertEqual(downstream["status"], "blocked")
                self.assertIn("channel-response", downstream["blocked_by"])

    def test_cancel_before_execution_aggregates_cancelled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root)
            with SupervisorRegistry(root / "registry.sqlite3") as registry:
                registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
                registry.cas_execution("run-1", 1, cancel_requested=True)
                instance, resolved, plan, engine_registry = driver(root, registry)
                report = instance.run(resolved, plan, engine_registry, run_id="run-1")
                self.assertEqual(report["status"], "cancelled")
                self.assertEqual(report["nodes"], {})
                self.assertEqual(registry.get_execution("run-1")["status"], "cancelled")

    def test_auto_retry_appends_attempts_until_exhausted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root, upstream_payload={"fail": True})
            with SupervisorRegistry(root / "registry.sqlite3") as registry:
                registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
                instance, resolved, plan, engine_registry = driver(root, registry, max_attempts=2)
                report = instance.run(resolved, plan, engine_registry, run_id="run-1")
                self.assertEqual(report["status"], "failed")
                attempts = registry.list_attempts("run-1", "channel-response")
                self.assertEqual([attempt["retry_index"] for attempt in attempts], [0, 1])
                self.assertEqual([attempt["status"] for attempt in attempts], ["failed", "failed"])

    def test_optional_failure_does_not_fail_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root, upstream_payload={"fail": True}, upstream_required=False, with_dependent=False)
            with SupervisorRegistry(root / "registry.sqlite3") as registry:
                registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
                instance, resolved, plan, engine_registry = driver(root, registry)
                report = instance.run(resolved, plan, engine_registry, run_id="run-1")
                self.assertEqual(report["status"], "succeeded")
                self.assertEqual(registry.get_node("run-1", "channel-response")["status"], "failed")


if __name__ == "__main__":
    unittest.main()
