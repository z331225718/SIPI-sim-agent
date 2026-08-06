"""M2 vertical integration: selection -> execution assembly -> adapters -> comparison.

Two fixture PyBERT engines (reference/candidate) run through the real platform
loop: engine.lock registry, runtime selection, backend execution planning,
strict adapter execution with isolated workdirs, artifact handoff, and
profile-driven comparison of the two domain results.
"""

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

from sipi_adapters import PyBertNativeAdapter, execute_backend
from sipi_contracts import parse_engine_lock, parse_run_request
from sipi_runtime import ComparisonProfile, EngineRegistry, Metric, compare_results, plan_backend_executions

FAKE_PYBERT = ROOT / "tests" / "adapters" / "fixtures" / "fake_pybert.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_engine_entry(root: Path, name: str) -> dict:
    bundle_rel = f"bundles/{name}.py"
    target = root / bundle_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(FAKE_PYBERT.read_bytes())
    digest = sha256(target)
    return {
        "instance_id": name,
        "engine_family": "pybert",
        "version": "0.1.0",
        "source_commit": "0" * 40,
        "bundle": {"kind": "local_path", "path": bundle_rel, "sha256": digest},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": "2" * 64,
        "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "3" * 64},
        "bundle_manifest": {
            "entrypoint": f"{name}.py",
            "files": [{"relative_path": f"{name}.py", "role": "entrypoint", "sha256": digest, "byte_length": target.stat().st_size}],
        },
        "extensions": {},
    }


def write_lock(root: Path, entries: list[dict]) -> EngineRegistry:
    lock = {"schema": "sipi.engine-lock.v1", "engines": entries, "operation_defaults": {}, "extensions": {}}
    (root / "engine.lock").write_text(json.dumps(lock), encoding="utf-8")
    return EngineRegistry(parse_engine_lock(lock))


def run_request(selection: dict):
    return parse_run_request(
        {
            "schema": "sipi.run-request.v1",
            "run_id": "run-1",
            "project_id": "project-1",
            "analysis_id": "analysis-1",
            "attempt_id": "attempt-1",
            "operation": "link.simulate.v1",
            "payload_schema": "pybert.simulation.v1",
            "payload": {"simulation_input": {"schema": "pybert.simulation.v1", "source": "fixture", "sample_count": 2}},
            "backend_selection": selection,
            "resource_limits": {"enforcement": "monitor", "wall_time_s": None, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None},
            "randomness": {},
            "artifact_policy": {},
            "extensions": {},
        }
    )


class M2EndToEndTests(unittest.TestCase):
    def test_compare_loop_runs_both_engines_and_compares(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = write_lock(root, [make_engine_entry(root, "pybert-python"), make_engine_entry(root, "pybert-rust")])
            selection = {"mode": "compare", "reference": "pybert-python", "candidate": "pybert-rust", "comparison_profile": "default"}
            plans = plan_backend_executions(run_request(selection), registry)
            self.assertEqual([(plan.role, plan.request["engine_instance_id"]) for plan in plans], [("reference", "pybert-python"), ("candidate", "pybert-rust")])

            artifact_root = root / "artifacts"
            results = []
            for plan in plans:
                result = execute_backend(
                    plan.request,
                    plan.engine_entry,
                    root,
                    builder=PyBertNativeAdapter(),
                    capabilities=PyBertNativeAdapter.capability_entries(),
                    artifact_root=artifact_root / plan.request["backend_execution_id"],
                )
                self.assertEqual(result["status"], "succeeded")
                results.append(result)

            report = compare_results(results[0], results[1], ComparisonProfile("default", (Metric("effective_input.sample_count"),)))
            self.assertTrue(report.matched, report.errors)
            for plan in plans:
                stored = artifact_root / plan.request["backend_execution_id"] / "out" / "meta.json"
                self.assertTrue(stored.is_file())

    def test_strict_loop_single_engine(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = write_lock(root, [make_engine_entry(root, "pybert-rust")])
            plans = plan_backend_executions(run_request({"mode": "strict", "instance": "pybert-rust"}), registry)
            self.assertEqual([(plan.role, plan.request["engine_instance_id"]) for plan in plans], [("primary", "pybert-rust")])
            result = execute_backend(
                plans[0].request,
                plans[0].engine_entry,
                root,
                builder=PyBertNativeAdapter(),
                capabilities=PyBertNativeAdapter.capability_entries(),
                artifact_root=root / "artifacts",
            )
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["domain_result"]["effective_input"]["sample_count"], 2)

    def test_auto_loop_falls_back_and_executes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blocked = make_engine_entry(root, "pybert-python")
            blocked["license_provenance"]["distribution_status"] = "blocked_unknown"
            registry = write_lock(root, [blocked, make_engine_entry(root, "pybert-rust")])
            selection = {"mode": "auto", "candidates": ["pybert-python", "pybert-rust"], "fallback_on": ["EngineUnavailable", "UnsupportedCapability"]}
            plans = plan_backend_executions(run_request(selection), registry)
            self.assertEqual([(plan.role, plan.request["engine_instance_id"]) for plan in plans], [("primary", "pybert-rust")])
            result = execute_backend(
                plans[0].request,
                plans[0].engine_entry,
                root,
                builder=PyBertNativeAdapter(),
                capabilities=PyBertNativeAdapter.capability_entries(),
                artifact_root=root / "artifacts",
            )
            self.assertEqual(result["status"], "succeeded")

    def test_failure_propagates_through_platform_loop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = write_lock(root, [make_engine_entry(root, "pybert-rust")])
            plans = plan_backend_executions(run_request({"mode": "strict", "instance": "pybert-rust"}), registry)
            tampered = dict(plans[0].engine_entry)
            tampered["bundle"] = dict(tampered["bundle"], sha256="f" * 64)
            result = execute_backend(
                plans[0].request,
                tampered,
                root,
                builder=PyBertNativeAdapter(),
                capabilities=PyBertNativeAdapter.capability_entries(),
            )
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"]["category"], "EngineUnavailable")


if __name__ == "__main__":
    unittest.main()
