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
sys.path.insert(0, str(ROOT / "apps" / "sipi-cli" / "src"))

from sipi_adapters import PyBertNativeAdapter
from sipi_contracts import parse_project
from sipi_runtime import (
    DriverOptions,
    EngineRegistry,
    ExecutionDriver,
    SupervisorRegistry,
    build_run_report,
    load_engine_lock,
    plan_dag,
    resolve_project,
)

FAKE_PYBERT = ROOT / "tests" / "adapters" / "fixtures" / "fake_pybert.py"


def _entry(instance_id: str, bundle_path: str, digest: str, byte_length: int) -> dict:
    return {
        "instance_id": instance_id,
        "engine_family": "pybert",
        "version": "0.1.0",
        "source_commit": "0" * 40,
        "bundle": {"kind": "local_path", "path": bundle_path, "sha256": digest},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": "2" * 64,
        "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "3" * 64},
        "bundle_manifest": {"entrypoint": bundle_path.rsplit("/", 1)[-1], "files": [{"relative_path": bundle_path.rsplit("/", 1)[-1], "role": "entrypoint", "sha256": digest, "byte_length": byte_length}]},
        "extensions": {},
    }


def write_compare_root(root: Path) -> None:
    (root / "bundles").mkdir(parents=True, exist_ok=True)
    entries = []
    for instance, name in (("pybert-python", "pybert.py"), ("pybert-rust", "pybert-rust.py")):
        bundle = root / "bundles" / name
        bundle.write_bytes(FAKE_PYBERT.read_bytes())
        digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
        entries.append(_entry(instance, f"bundles/{name}", digest, bundle.stat().st_size))
    (root / "engine.lock").write_text(json.dumps({"schema": "sipi.engine-lock.v1", "engines": entries, "operation_defaults": {}, "extensions": {}}), encoding="utf-8")
    project = {
        "schema": "sipi.project.v1",
        "project": {"name": "report-test", "extensions": {}},
        "runtime": {"engine_lock": "engine.lock", "extensions": {}},
        "analyses": [
            {
                "id": "link-eye",
                "operation": "link.simulate.v1",
                "backend_selection": {"mode": "compare", "reference": "pybert-python", "candidate": "pybert-rust", "comparison_profile": "default"},
                "payload_schema": "pybert.simulation.v1",
                "payload": {"simulation_input": {"sample_count": 2}},
            }
        ],
        "extensions": {},
    }
    (root / "project.json").write_text(json.dumps(project), encoding="utf-8")


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


def write_driver_project(root: Path) -> None:
    project = {
        "schema": "sipi.project.v1",
        "project": {"name": "driver-test", "extensions": {}},
        "runtime": {"engine_lock": "engine.lock", "extensions": {}},
        "analyses": [
            {
                "id": "channel-response",
                "operation": "link.simulate.v1",
                "backend_selection": {"mode": "strict", "instance": "pybert-python"},
                "payload_schema": "pybert.simulation.v1",
                "payload": {"simulation_input": {"sample_count": 2}},
                "exports": [{"role": "domain_result", "schema": "pybert.native-cli-result.v1"}],
            },
            {
                "id": "link-eye",
                "operation": "link.simulate.v1",
                "backend_selection": {"mode": "strict", "instance": "pybert-python"},
                "payload_schema": "pybert.simulation.v1",
                "payload": {"simulation_input": {"sample_count": 3}},
                "depends_on": ["channel-response"],
                "inputs": {
                    "channel": {
                        "from_analysis": "channel-response",
                        "artifact_role": "domain_result",
                        "expected_schema": "pybert.native-cli-result.v1",
                    }
                },
            },
        ],
        "extensions": {},
    }
    (root / "project.json").write_text(json.dumps(project), encoding="utf-8")


class ReportTests(unittest.TestCase):
    def test_compare_report_matches_identical_backends(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_compare_root(root)
            with SupervisorRegistry(root / "registry.sqlite3") as registry:
                registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
                engine_registry = EngineRegistry(load_engine_lock(root / "engine.lock"))
                resolved = resolve_project(parse_project((root / "project.json").read_text(encoding="utf-8")), root)
                plan = plan_dag(resolved, engine_registry)
                driver = ExecutionDriver(registry, {"pybert": PyBertNativeAdapter()}, options=DriverOptions(artifact_root=root))
                driver.run(resolved, plan, engine_registry, "run-1")
                report = build_run_report(run_id="run-1", resolved=resolved, plan=plan, registry=registry, artifact_root=root)
                self.assertEqual(report["execution_status"], "succeeded")
                section = report["analyses"][0]
                self.assertEqual(section["status"], "succeeded")
                self.assertEqual(section["attempt_count"], 1)
                self.assertTrue(section["comparison"]["matched"])
                self.assertEqual(section["comparison"]["checked_count"], 1)
                self.assertEqual(section["comparison"]["mismatches"], [])

    def test_non_compare_report_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_driver_project(root)
            write_engine_lock(root)
            with SupervisorRegistry(root / "registry.sqlite3") as registry:
                registry.submit_execution(run_id="run-1", project_hash="h1", submission_key="key-1", failure_policy="p")
                engine_registry = EngineRegistry(load_engine_lock(root / "engine.lock"))
                resolved = resolve_project(parse_project((root / "project.json").read_text(encoding="utf-8")), root)
                plan = plan_dag(resolved, engine_registry)
                driver = ExecutionDriver(registry, {"pybert": PyBertNativeAdapter()}, options=DriverOptions(artifact_root=root))
                driver.run(resolved, plan, engine_registry, "run-1")
                report = build_run_report(run_id="run-1", resolved=resolved, plan=plan, registry=registry, artifact_root=root)
                self.assertEqual([section["status"] for section in report["analyses"]], ["succeeded", "succeeded"])
                self.assertEqual(report["provenance"]["engine_lock_sha256"], resolved.engine_lock["sha256"])
                self.assertTrue(report["analyses"][0]["artifacts"])
                self.assertNotIn("comparison", report["analyses"][0])


if __name__ == "__main__":
    unittest.main()
