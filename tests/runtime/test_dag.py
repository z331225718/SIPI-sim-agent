from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))

from sipi_contracts import parse_engine_lock, parse_project
from sipi_runtime import (
    DagCycleError,
    EngineRegistry,
    ResolvedAnalysis,
    ResolvedInputBinding,
    ResolvedProject,
    SelectionError,
    cache_identity,
    plan_dag,
    resolve_project,
)


def engine_entry(instance_id: str) -> dict:
    digest = "1" * 64
    return {
        "instance_id": instance_id,
        "engine_family": "pybert",
        "version": "0.1.0",
        "source_commit": "0" * 40,
        "bundle": {"kind": "local_path", "path": f"bundles/{instance_id}.py", "sha256": digest},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "2" * 64},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": "3" * 64,
        "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "4" * 64},
        "bundle_manifest": {
            "entrypoint": f"{instance_id}.py",
            "files": [{"relative_path": f"{instance_id}.py", "role": "entrypoint", "sha256": digest, "byte_length": 1}],
        },
        "extensions": {},
    }


def registry(*instances: str) -> EngineRegistry:
    lock = {"schema": "sipi.engine-lock.v1", "engines": [engine_entry(instance) for instance in instances], "operation_defaults": {}, "extensions": {}}
    return EngineRegistry(parse_engine_lock(lock))


def analysis(id: str, depends_on=(), required=True, payload=None):
    return {
        "id": id,
        "operation": "link.simulate.v1",
        "backend_selection": {"mode": "strict", "instance": "pybert-python"},
        "payload_schema": "pybert.simulation.v1",
        "payload": payload if payload is not None else {"case": id},
        "depends_on": list(depends_on),
        "required": required,
    }


def resolved_project(directory: Path, analyses: list[dict]) -> ResolvedProject:
    (directory / "engine.lock").write_text("{}", encoding="utf-8")
    raw = {
        "schema": "sipi.project.v1",
        "project": {"name": "dag-test", "extensions": {}},
        "runtime": {"engine_lock": "engine.lock", "extensions": {}},
        "analyses": analyses,
        "extensions": {},
    }
    return resolve_project(parse_project(raw), directory)


class DagPlanningTests(unittest.TestCase):
    def test_topological_order_diamond(self):
        with tempfile.TemporaryDirectory() as directory:
            resolved = resolved_project(
                Path(directory),
                [
                    analysis("a"),
                    analysis("b", depends_on=["a"]),
                    analysis("c", depends_on=["a"]),
                    analysis("d", depends_on=["b", "c"]),
                ],
            )
            plan = plan_dag(resolved, registry("pybert-python"))
            self.assertEqual(plan.order[0], "a")
            self.assertEqual(plan.order[-1], "d")
            self.assertLess(plan.order.index("b"), plan.order.index("d"))
            self.assertLess(plan.order.index("c"), plan.order.index("d"))
            self.assertEqual(plan.project_hash, resolved.project_hash)

    def test_cycle_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            resolved = resolved_project(
                Path(directory),
                [analysis("a", depends_on=["c"]), analysis("b", depends_on=["a"]), analysis("c", depends_on=["b"])],
            )
            with self.assertRaises(DagCycleError):
                plan_dag(resolved, registry("pybert-python"))

    def test_effective_required_closure_covers_required_upstreams(self):
        with tempfile.TemporaryDirectory() as directory:
            resolved = resolved_project(
                Path(directory),
                [
                    analysis("a", required=False),
                    analysis("b", depends_on=["a"], required=True),
                    analysis("c", required=False),
                ],
            )
            plan = plan_dag(resolved, registry("pybert-python"))
            effective = {node.analysis_id for node in plan.nodes if node.effective_required}
            self.assertEqual(effective, {"a", "b"})
            self.assertNotIn("c", effective)

    def test_unknown_instance_fails_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            resolved = resolved_project(Path(directory), [analysis("a")])
            with self.assertRaises(SelectionError):
                plan_dag(resolved, registry("other-engine"))

    def test_plan_nodes_carry_selection_hash_and_execution_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            resolved = resolved_project(Path(directory), [analysis("a")])
            plan = plan_dag(resolved, registry("pybert-python"))
            node = plan.by_id["a"]
            self.assertTrue(node.selection_hash.startswith("sha256:"))
            self.assertEqual(node.execution_modes, ("primary:pybert-python:sha256:" + "1" * 64,))


class CacheIdentityTests(unittest.TestCase):
    def _analysis(self, analysis_id="a"):
        return ResolvedAnalysis(
            analysis_id=analysis_id,
            operation="link.simulate.v1",
            payload_schema="pybert.simulation.v1",
            payload={"case": analysis_id},
            payload_artifact=None,
            payload_sha256="p" * 64,
            backend_selection={"mode": "strict", "instance": "pybert-python"},
            selection_source="analysis",
            depends_on=("upstream",),
            required=True,
            inputs=(ResolvedInputBinding(name="channel", from_analysis="upstream", artifact_role="channel-response", expected_schema="agent-spice.rfm-response.v1"),),
            exports=(),
        )

    def test_identity_is_stable_and_content_sensitive(self):
        analysis = self._analysis()
        base = dict(selection_hash="sha256:" + "0" * 64, bundle_hashes=("b1",))
        self.assertEqual(cache_identity(analysis, **base), cache_identity(analysis, **base))
        self.assertNotEqual(cache_identity(analysis, **base), cache_identity(replace(analysis, payload_sha256="q" * 64), **base))
        self.assertNotEqual(cache_identity(analysis, **base), cache_identity(analysis, selection_hash="sha256:" + "1" * 64, bundle_hashes=("b1",)))
        self.assertNotEqual(cache_identity(analysis, **base), cache_identity(analysis, selection_hash=base["selection_hash"], bundle_hashes=("b2",)))

    def test_bundle_hash_order_is_irrelevant(self):
        analysis = self._analysis()
        base = dict(selection_hash="sha256:" + "0" * 64)
        self.assertEqual(cache_identity(analysis, **base, bundle_hashes=("b1", "b2")), cache_identity(analysis, **base, bundle_hashes=("b2", "b1")))

    def test_upstream_content_hash_participates(self):
        analysis = self._analysis()
        base = dict(selection_hash="sha256:" + "0" * 64, bundle_hashes=("b1",))
        self.assertNotEqual(
            cache_identity(analysis, **base, bound_input_hashes={"channel": "u1"}),
            cache_identity(analysis, **base, bound_input_hashes={"channel": "u2"}),
        )

    def test_execution_ids_and_analysis_id_are_excluded(self):
        base = dict(selection_hash="sha256:" + "0" * 64, bundle_hashes=("b1",))
        self.assertEqual(cache_identity(self._analysis("a"), **base), cache_identity(self._analysis("b"), **base))


if __name__ == "__main__":
    unittest.main()
