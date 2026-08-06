from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import (
    AgentComRunAdapter,
    AgentSpiceHspiceAdapter,
    PyBertNativeAdapter,
    UnsupportedCapabilityError,
    build_engine_capabilities,
    execute_backend,
    preflight,
)
from sipi_contracts import parse_backend_execution_request

FAKE_ENGINE = ROOT / "tests" / "adapters" / "fixtures" / "fake_engine.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backend_request(**changes):
    value = {
        "schema": "sipi.backend-execution-request.v1",
        "run_id": "run-1",
        "analysis_id": "analysis-1",
        "attempt_id": "attempt-1",
        "backend_execution_id": "backend-1",
        "role": "primary",
        "engine_instance_id": "agent-spice-python",
        "bundle_hash": "sha256:" + sha256(FAKE_ENGINE),
        "operation": "circuit.solve.v1",
        "payload_schema": "agent-spice.hspice.v1",
        "payload": {},
        "bound_inputs": {},
        "resource_limits": {"enforcement": "monitor", "wall_time_s": None, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None},
        "artifact_policy": {},
        "randomness": {},
        "selection_hash": "sha256:selection",
    }
    value.update(changes)
    return parse_backend_execution_request(value)


class CapabilityTests(unittest.TestCase):
    def test_all_adapters_declare_valid_capability_documents(self) -> None:
        for adapter, operation in (
            (AgentSpiceHspiceAdapter, "circuit.solve.v1"),
            (PyBertNativeAdapter, "link.simulate.v1"),
            (AgentComRunAdapter, "com.r480.run.v1"),
        ):
            document = build_engine_capabilities(engine_instance_id="test-engine", bundle_hash="sha256:bundle", entries=adapter.capability_entries())
            self.assertEqual(document["schema"], "sipi.engine-capabilities.v1")
            self.assertEqual(document["capabilities"][0]["operation"], operation)

    def test_preflight_accepts_supported_request(self) -> None:
        preflight(backend_request(), AgentSpiceHspiceAdapter.capability_entries())

    def test_preflight_rejects_unsupported_operation(self) -> None:
        with self.assertRaises(UnsupportedCapabilityError):
            preflight(backend_request(operation="network.fit.v1"), AgentSpiceHspiceAdapter.capability_entries())

    def test_preflight_rejects_unsupported_payload_schema(self) -> None:
        with self.assertRaises(UnsupportedCapabilityError):
            preflight(backend_request(payload_schema="other.schema.v1"), AgentSpiceHspiceAdapter.capability_entries())

    def test_preflight_rejects_required_enforcement_without_hard_mode(self) -> None:
        request = backend_request(
            resource_limits={"enforcement": "required", "wall_time_s": 5, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None}
        )
        with self.assertRaises(UnsupportedCapabilityError) as caught:
            preflight(request, AgentSpiceHspiceAdapter.capability_entries())
        self.assertIn("wall_time_s", str(caught.exception))

    def test_preflight_accepts_required_enforcement_without_limit(self) -> None:
        request = backend_request(
            resource_limits={"enforcement": "required", "wall_time_s": None, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None}
        )
        preflight(request, AgentSpiceHspiceAdapter.capability_entries())

    def test_execute_backend_preflight_fails_closed_before_running(self) -> None:
        class FixtureBuilder:
            def build(self, request, bundle_path, workdir):
                raise AssertionError("engine must not run when preflight rejects")

            def build_outcome(self, request, engine_entry, workdir, process):
                raise AssertionError("engine must not run when preflight rejects")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "bundles" / "fake_engine.py"
            target.parent.mkdir(parents=True)
            target.write_bytes(FAKE_ENGINE.read_bytes())
            entry = {
                "instance_id": "agent-spice-python",
                "engine_family": "agent-spice",
                "version": "1",
                "source_commit": "0" * 40,
                "bundle": {"kind": "local_path", "path": "bundles/fake_engine.py", "sha256": sha256(FAKE_ENGINE)},
                "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
                "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
                "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
                "dependency_lock_sha256": "2" * 64,
                "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "3" * 64},
                "bundle_manifest": {"entrypoint": "fake_engine.py", "files": [{"relative_path": "fake_engine.py", "role": "entrypoint", "sha256": sha256(FAKE_ENGINE), "byte_length": FAKE_ENGINE.stat().st_size}]},
                "extensions": {},
            }
            result = execute_backend(
                backend_request(operation="network.fit.v1"),
                entry,
                root,
                builder=FixtureBuilder(),
                capabilities=AgentSpiceHspiceAdapter.capability_entries(),
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "UnsupportedCapability")


if __name__ == "__main__":
    unittest.main()
