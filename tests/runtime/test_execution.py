from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))

from sipi_contracts import parse_engine_lock, parse_run_request
from sipi_runtime import EngineRegistry, SelectionError, plan_backend_executions, selection_hash


def engine_entry(instance_id: str, *, license_status: str = "authorized_public") -> dict:
    digest = "a" * 64
    return {
        "instance_id": instance_id,
        "engine_family": "fixture",
        "version": "1.0.0",
        "source_commit": "b" * 40,
        "bundle": {"kind": "local_path", "path": "bundles/fixture.whl", "sha256": digest},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": digest},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": digest,
        "license_provenance": {"distribution_status": license_status, "manifest_sha256": digest},
        "bundle_manifest": {"entrypoint": "bin/fixture.exe", "files": [{"relative_path": "bin/fixture.exe", "role": "entrypoint", "sha256": digest, "byte_length": 1}]},
        "extensions": {},
    }


def registry(*entries: dict) -> EngineRegistry:
    lock = {"schema": "sipi.engine-lock.v1", "engines": list(entries), "operation_defaults": {}, "extensions": {}}
    return EngineRegistry(parse_engine_lock(lock))


def run_request(selection: dict, *, payload_artifact: dict | None = None):
    value = {
        "schema": "sipi.run-request.v1",
        "run_id": "run-1",
        "project_id": "project-1",
        "analysis_id": "analysis-1",
        "attempt_id": "attempt-1",
        "operation": "link.simulate.v1",
        "payload_schema": "pybert.simulation.v1",
        "payload": {"source": "fixture"},
        "backend_selection": selection,
        "resource_limits": {"enforcement": "monitor", "wall_time_s": None, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None},
        "randomness": {},
        "artifact_policy": {},
        "extensions": {},
    }
    if payload_artifact is not None:
        value.pop("payload", None)
        value["payload_artifact"] = payload_artifact
    return parse_run_request(value)


def artifact_ref() -> dict:
    return {
        "schema": "sipi.artifact-ref.v1",
        "content_schema": "pybert.simulation.v1",
        "relative_path": "inputs/request.json",
        "mime_type": "application/json",
        "sha256": "a" * 64,
        "byte_length": 1,
        "producer": "fixture.platform",
        "role": "input",
        "extensions": {},
    }


class ExecutionAssemblyTests(unittest.TestCase):
    def test_strict_plans_one_execution_with_injected_hashes(self) -> None:
        reg = registry(engine_entry("pybert-rust"))
        selection = {"mode": "strict", "instance": "pybert-rust"}
        plans = plan_backend_executions(run_request(selection), reg)
        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertEqual(plan.role, "primary")
        request = plan.request.to_wire()
        self.assertEqual(request["engine_instance_id"], "pybert-rust")
        self.assertEqual(request["bundle_hash"], "sha256:" + "a" * 64)
        self.assertEqual(request["selection_hash"], selection_hash(selection))
        self.assertEqual(request["run_id"], "run-1")
        self.assertEqual(request["analysis_id"], "analysis-1")
        self.assertEqual(request["attempt_id"], "attempt-1")
        self.assertEqual(request["backend_execution_id"], "attempt-1-primary")
        self.assertEqual(request["payload"], {"source": "fixture"})

    def test_auto_plans_stable_candidate(self) -> None:
        reg = registry(engine_entry("bad", license_status="blocked_unknown"), engine_entry("good"))
        selection = {"mode": "auto", "candidates": ["bad", "good"], "fallback_on": ["EngineUnavailable", "UnsupportedCapability"]}
        plans = plan_backend_executions(run_request(selection), reg)
        self.assertEqual([(plan.role, plan.request["engine_instance_id"]) for plan in plans], [("primary", "good")])
        self.assertEqual(plans[0].request["selection_hash"], selection_hash(selection))

    def test_compare_plans_reference_and_candidate(self) -> None:
        reg = registry(engine_entry("pybert-python"), engine_entry("pybert-rust"))
        selection = {"mode": "compare", "reference": "pybert-python", "candidate": "pybert-rust", "comparison_profile": "default"}
        plans = plan_backend_executions(run_request(selection), reg)
        self.assertEqual([(plan.role, plan.request["engine_instance_id"]) for plan in plans], [("reference", "pybert-python"), ("candidate", "pybert-rust")])
        self.assertEqual(plans[0].request["backend_execution_id"], "attempt-1-reference")
        self.assertEqual(plans[1].request["backend_execution_id"], "attempt-1-candidate")
        self.assertEqual(plans[0].request["selection_hash"], plans[1].request["selection_hash"])

    def test_bound_inputs_are_forwarded(self) -> None:
        reg = registry(engine_entry("pybert-rust"))
        selection = {"mode": "strict", "instance": "pybert-rust"}
        bound = {"request": artifact_ref()}
        plans = plan_backend_executions(run_request(selection), reg, bound_inputs=bound)
        self.assertEqual(plans[0].request["bound_inputs"]["request"]["relative_path"], "inputs/request.json")

    def test_payload_artifact_mode_uses_artifact_slot(self) -> None:
        reg = registry(engine_entry("pybert-rust"))
        selection = {"mode": "strict", "instance": "pybert-rust"}
        plans = plan_backend_executions(run_request(selection, payload_artifact=artifact_ref()), reg)
        request = plans[0].request.to_wire()
        self.assertNotIn("payload", request)
        self.assertEqual(request["payload_artifact"]["relative_path"], "inputs/request.json")

    def test_unknown_instance_is_engine_unavailable(self) -> None:
        with self.assertRaises(SelectionError) as caught:
            plan_backend_executions(run_request({"mode": "strict", "instance": "missing"}), registry(engine_entry("a")))
        self.assertEqual(caught.exception.category, "EngineUnavailable")


if __name__ == "__main__":
    unittest.main()
