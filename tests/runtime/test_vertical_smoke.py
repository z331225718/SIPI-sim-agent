from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import PyBertNativeAdapter
from sipi_adapters.process import BackendOutcome, CommandBuilder, assemble_backend_result, invocation, platform_error
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


class AgentSpiceRfmStubAdapter(CommandBuilder):
    domain_result_schema = "agent-spice.rfm-response.v1"

    @classmethod
    def capability_entries(cls):
        from sipi_adapters import AdapterCapability

        return (
            AdapterCapability(
                operation="circuit.solve.v1",
                payload_schema="sipi.adapter.agent-spice.rfm-response-request.v1",
                domain_result_schemas=(cls.domain_result_schema,),
                behavior_profile="default",
                role="reference",
                execution_mode="process",
            ),
        )

    def build(self, request, bundle_path, workdir):
        import json as _json

        input_path = workdir / "input.json"
        input_path.write_text(_json.dumps(dict(request.to_wire()["payload"]), sort_keys=True), encoding="utf-8")
        return [*invocation(bundle_path), str(input_path), "--output-dir", str(workdir / "out")]

    def build_outcome(self, request, engine_entry, workdir, process):
        import hashlib

        meta_path = workdir / "out" / "meta.json"
        if not meta_path.is_file():
            return BackendOutcome(assemble_backend_result(request, status="failed", error=platform_error("ExternalModelFailure", "no meta.json")))
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        artifact = {
            "schema": "sipi.artifact-ref.v1",
            "content_schema": self.domain_result_schema,
            "relative_path": "out/meta.json",
            "mime_type": "application/json",
            "sha256": hashlib.sha256(meta_path.read_bytes()).hexdigest(),
            "byte_length": meta_path.stat().st_size,
            "producer": request["engine_instance_id"],
            "role": "rfm-response",
            "extensions": {},
        }
        return BackendOutcome(
            assemble_backend_result(request, status="succeeded", domain_result=meta, domain_result_schema=self.domain_result_schema, artifacts=(artifact,)),
            artifact_paths=(meta_path,),
        )


class VerticalSmokeTests(unittest.TestCase):
    def test_rfm_to_link_vertical_smoke(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = ROOT / "examples" / "channel" / "rfm-to-link"
            shutil.copytree(example, root, dirs_exist_ok=True)
            with SupervisorRegistry(root / "registry.sqlite3") as registry:
                engine_registry = EngineRegistry(load_engine_lock(root / "engine.lock"))
                resolved = resolve_project(parse_project((root / "project.json").read_text(encoding="utf-8")), root)
                plan = plan_dag(resolved, engine_registry)
                registry.submit_execution(run_id="run-1", project_hash=resolved.project_hash, submission_key="key-1", failure_policy="block-dependents, continue-independent")
                driver = ExecutionDriver(
                    registry,
                    {"agent-spice": AgentSpiceRfmStubAdapter(), "pybert": PyBertNativeAdapter()},
                    options=DriverOptions(artifact_root=root),
                )
                report = driver.run(resolved, plan, engine_registry, "run-1")
                self.assertEqual(report["status"], "succeeded")
                self.assertEqual(report["nodes"], {"rfm-response": "succeeded", "link-eye": "succeeded"})
                run_report = build_run_report(run_id="run-1", resolved=resolved, plan=plan, registry=registry, artifact_root=root)
                self.assertEqual([section["status"] for section in run_report["analyses"]], ["succeeded", "succeeded"])
                link = run_report["analyses"][1]
                self.assertEqual(link["analysis_id"], "link-eye")
                self.assertTrue(link["artifacts"])
                rfm_meta = root / "nodes" / "rfm-response" / "attempts" / "rfm-response-attempt-0" / "backends" / "rfm-response-attempt-0-primary" / "out" / "meta.json"
                self.assertTrue(rfm_meta.is_file())
                self.assertEqual(json.loads(rfm_meta.read_text(encoding="utf-8"))["schema"], "agent-spice.rfm-response.v1")


if __name__ == "__main__":
    unittest.main()
