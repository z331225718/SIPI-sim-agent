from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import (
    AdapterContractError,
    BackendAdapter,
    require_backend_request,
    require_backend_result,
    validate_pinned_instance,
    validate_result_identity,
)
from sipi_contracts import (
    parse_backend_execution_request,
    parse_backend_execution_result,
    parse_run_request,
    parse_run_result,
)


def backend_request(**changes):
    value = {
        "schema": "sipi.backend-execution-request.v1",
        "run_id": "run-1",
        "analysis_id": "analysis-1",
        "attempt_id": "attempt-1",
        "backend_execution_id": "backend-1",
        "role": "primary",
        "engine_instance_id": "pybert-python",
        "bundle_hash": "sha256:bundle",
        "operation": "link.simulate.v1",
        "payload_schema": "pybert.simulation.v1",
        "payload": {"source": "fixture"},
        "bound_inputs": {},
        "resource_limits": {"enforcement": "monitor", "wall_time_s": None, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None},
        "artifact_policy": {},
        "randomness": {},
        "selection_hash": "sha256:selection",
    }
    value.update(changes)
    return parse_backend_execution_request(value)


def backend_result(req):
    return parse_backend_execution_result(
        {
            "schema": "sipi.backend-execution-result.v1",
            "run_id": req["run_id"],
            "analysis_id": req["analysis_id"],
            "attempt_id": req["attempt_id"],
            "backend_execution_id": req["backend_execution_id"],
            "role": req["role"],
            "engine_instance_id": req["engine_instance_id"],
            "bundle_hash": req["bundle_hash"],
            "operation": req["operation"],
            "payload_schema": req["payload_schema"],
            "status": "succeeded",
            "domain_result_schema": "pybert.simulation.v1",
            "domain_result": {"source": "fixture"},
            "artifacts": [],
            "events": [],
            "warnings": [],
            "timings": {},
            "resource_usage": {"actual_enforcement": {"wall_time_s": "unsupported", "cpu_time_s": "unsupported", "memory_bytes": "unsupported", "process_count": "unsupported", "artifact_bytes": "unsupported"}},
            "error": None,
        }
    )


def run_request():
    return parse_run_request(
        {
            "schema": "sipi.run-request.v1",
            "run_id": "run-1",
            "project_id": "project-1",
            "analysis_id": "analysis-1",
            "attempt_id": "attempt-1",
            "operation": "link.simulate.v1",
            "payload_schema": "pybert.simulation.v1",
            "payload": {"source": "fixture"},
            "backend_selection": {"mode": "strict", "instance": "pybert-python"},
            "resource_limits": {"enforcement": "monitor", "wall_time_s": None, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None},
            "randomness": {},
            "artifact_policy": {},
            "extensions": {},
        }
    )


def artifact():
    return {
        "schema": "sipi.artifact-ref.v1",
        "content_schema": "pybert.output.v1",
        "relative_path": "backends/backend-1/artifacts/result.json",
        "mime_type": "application/json",
        "sha256": "a" * 64,
        "byte_length": 1,
        "producer": "fixture.adapter",
        "role": "domain_result",
        "extensions": {},
    }


def provenance():
    producer = lambda identity, kind, parents: {"id": identity, "kind": kind, "name": "fixture", "version": "1", "commit": None, "build_profile": None, "dirty": False, "bundle_hash": None, "parent_ids": parents}
    return {
        "producers": [producer("fixture.platform", "platform", []), producer("fixture.adapter", "adapter", ["fixture.platform"]), producer("fixture.engine", "engine", ["fixture.adapter"]), producer("fixture.algorithm", "algorithm", ["fixture.engine"])],
        "request": {"schema": "pybert.simulation.v1", "behavior_profile": "fixture", "inputs": [], "resolved_config_sha256": "a" * 64},
        "environment": {"python": None, "rust": None, "os": "windows", "cpu": "fixture", "blas": None, "thread_count": 1, "dependency_locks": []},
        "randomness": {"seed": None, "array_sources": []},
        "policies": {"fallback": [], "conditioning": [], "repairs": [], "truncations": [], "approximations": []},
        "extensions": {},
    }


def run_result():
    return parse_run_result(
        {
            "schema": "sipi.run-result.v1",
            "run_id": "run-1",
            "analysis_id": "analysis-1",
            "attempt_id": "attempt-1",
            "operation": "link.simulate.v1",
            "payload_schema": "pybert.simulation.v1",
            "status": "succeeded",
            "selection_requested": {"mode": "strict", "instance": "pybert-python"},
            "backend_executions": [{"backend_execution_id": "backend-1", "role": "primary", "engine_instance_id": "pybert-python", "bundle_hash": "sha256:bundle", "status": "succeeded", "domain_result_schema": "pybert.simulation.v1", "domain_result": {"source": "fixture"}, "artifacts": [artifact()], "error": None}],
            "fallback_trace": [],
            "comparison": {},
            "metrics_summary": {},
            "artifacts": [],
            "events": [],
            "warnings": [],
            "provenance": provenance(),
            "timings": {},
            "resource_usage": {"actual_enforcement": {"wall_time_s": "unsupported", "cpu_time_s": "unsupported", "memory_bytes": "unsupported", "process_count": "unsupported", "artifact_bytes": "unsupported"}},
            "error": None,
            "extensions": {},
        }
    )


class AdapterSpiTests(unittest.TestCase):
    def test_backend_envelope_types_are_enforced(self) -> None:
        request = backend_request()
        self.assertIs(require_backend_request(request), request)
        with self.assertRaises(AdapterContractError):
            require_backend_request(run_request())

        result = backend_result(request)
        self.assertIs(require_backend_result(result), result)
        with self.assertRaises(AdapterContractError):
            require_backend_result(run_result())

    def test_pinned_instance_mismatch_is_rejected(self) -> None:
        request = backend_request()
        validate_pinned_instance(request, "pybert-python")
        with self.assertRaises(AdapterContractError):
            validate_pinned_instance(request, "agent-spice-process")

    def test_result_identity_mismatch_is_rejected(self) -> None:
        request = backend_request()
        validate_result_identity(request, backend_result(request))
        other = backend_request(run_id="run-2")
        with self.assertRaises(AdapterContractError):
            validate_result_identity(request, backend_result(other))

    def test_backend_adapter_protocol_is_runtime_checkable(self) -> None:
        class DummyAdapter:
            def execute(self, request):
                return backend_result(request)

        self.assertIsInstance(DummyAdapter(), BackendAdapter)
        self.assertNotIsInstance(object(), BackendAdapter)


if __name__ == "__main__":
    unittest.main()
