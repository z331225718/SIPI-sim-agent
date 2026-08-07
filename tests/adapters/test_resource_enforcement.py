from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import (
    BackendOutcome,
    CommandBuilder,
    MANAGED_HARD_ENFORCEMENT,
    assemble_backend_result,
    execute_backend,
    preflight,
    run_process,
)
from sipi_contracts import parse_backend_execution_request

from test_process_adapter import backend_request, engine_entry, install_bundle


def backend_request_required(**changes):
    request = backend_request(
        resource_limits={
            "enforcement": "required",
            "wall_time_s": 30,
            "cpu_time_s": None,
            "memory_bytes": None,
            "process_count": None,
            "artifact_bytes": None,
        }
    )
    wire = request.to_wire()
    wire["resource_limits"].update(changes)
    return parse_backend_execution_request(wire)


class NoopBuilder(CommandBuilder):
    domain_result_schema = "fixture.domain-result.v1"

    def build(self, request, bundle_path, workdir):
        return [sys.executable, "-c", "pass"]

    def build_outcome(self, request, engine_entry, workdir, process):
        return BackendOutcome(assemble_backend_result(request, status="succeeded", domain_result={}, domain_result_schema=self.domain_result_schema))


class OversizedArtifactBuilder(NoopBuilder):
    def build_outcome(self, request, engine_entry, workdir, process):
        return BackendOutcome(
            assemble_backend_result(
                request,
                status="succeeded",
                domain_result={},
                domain_result_schema=self.domain_result_schema,
                artifacts=(
                    {
                        "schema": "sipi.artifact-ref.v1",
                        "content_schema": "fixture.data.v1",
                        "relative_path": "out/big.bin",
                        "mime_type": "application/octet-stream",
                        "role": "data",
                        "producer": "fixture",
                        "sha256": "a" * 64,
                        "byte_length": 4096,
                        "extensions": {},
                    },
                ),
            )
        )


class ManagedEnforcementTests(unittest.TestCase):
    def test_posix_preexec_applies_memory_and_cpu_limits(self):
        if os.name == "nt":
            self.skipTest("POSIX-only rlimit path")
        import subprocess

        from sipi_adapters.process import _posix_rlimit_preexec

        preexec = _posix_rlimit_preexec({"memory_bytes": 512 * 1024 * 1024, "cpu_time_s": 7})
        self.assertIsNotNone(preexec)
        script = "import resource; print(resource.getrlimit(resource.RLIMIT_AS)[0], resource.getrlimit(resource.RLIMIT_CPU)[1])"
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            preexec_fn=preexec,
        )
        values = [int(value) for value in result.stdout.split()]
        self.assertEqual(values[0], 512 * 1024 * 1024)
        self.assertEqual(values[1], 7)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object path")
    def test_memory_limit_reports_resource_violation(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_process(
                [sys.executable, "-c", "x = bytearray(512 * 1024 * 1024)"],
                workdir=Path(directory),
                env=os.environ,
                wall_time_s=30,
                resource_limits={"memory_bytes": 128 * 1024 * 1024},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.resource_violation, "memory_bytes")

    @unittest.skipUnless(os.name == "nt", "Windows Job Object path")
    def test_cpu_time_limit_terminates_busy_process(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_process(
                [sys.executable, "-c", "while True: pass"],
                workdir=Path(directory),
                env=os.environ,
                wall_time_s=30,
                resource_limits={"cpu_time_s": 1.0},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.resource_violation, "cpu_time_s")

    @unittest.skipUnless(os.name == "nt", "Windows Job Object path")
    def test_process_count_limit_blocks_child_creation(self):
        script = "import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']).wait()"
        with tempfile.TemporaryDirectory() as directory:
            result = run_process(
                [sys.executable, "-c", script],
                workdir=Path(directory),
                env=os.environ,
                wall_time_s=30,
                resource_limits={"process_count": 1},
            )
            self.assertNotEqual(result.returncode, 0)

    def test_artifact_bytes_limit_rejects_oversized_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            request = backend_request_required(artifact_bytes=1024)
            result = execute_backend(
                request,
                engine_entry(root),
                root,
                builder=OversizedArtifactBuilder(),
                artifact_root=root / "out",
            )
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"]["category"], "ResourceLimit")
            self.assertEqual(result["error"]["resource"], "artifact_bytes")

    def test_required_success_reports_hard_actual_enforcement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            request = backend_request_required(wall_time_s=30)
            result = execute_backend(
                request,
                engine_entry(root),
                root,
                builder=NoopBuilder(),
            )
            self.assertEqual(result["status"], "succeeded")
            actual = result["resource_usage"]["actual_enforcement"]
            self.assertEqual(actual["wall_time_s"], "hard")
            self.assertEqual(actual["artifact_bytes"], "unsupported")

    def test_preflight_accepts_managed_hard_and_rejects_unsupported(self):
        from sipi_adapters import AdapterCapability

        entries = (AdapterCapability(operation="circuit.solve.v1", payload_schema="agent-spice.hspice.v1", domain_result_schemas=(), behavior_profile="default", role="reference", execution_mode="process"),)
        request = backend_request_required(memory_bytes=1024)
        preflight(request, entries, platform_enforcement={"wall_time_s": "hard", "memory_bytes": "hard"})
        request = backend_request_required(cpu_time_s=1)
        with self.assertRaises(Exception) as context:
            preflight(request, entries, platform_enforcement={"wall_time_s": "hard"})
        self.assertIn("cpu_time_s", str(context.exception))

    def test_managed_enforcement_matrix_is_os_honest(self):
        matrix = MANAGED_HARD_ENFORCEMENT
        if os.name == "nt":
            self.assertEqual(matrix["nt"]["process_count"], "hard")
            self.assertEqual(matrix["nt"]["memory_bytes"], "hard")
        else:
            self.assertEqual(matrix["posix"]["process_count"], "unsupported")
            self.assertEqual(matrix["posix"]["memory_bytes"], "hard")
        self.assertEqual(matrix["nt"]["wall_time_s"], "hard")
        self.assertEqual(matrix["posix"]["artifact_bytes"], "hard")


if __name__ == "__main__":
    unittest.main()
