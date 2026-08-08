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
    BackendOutcome,
    PyBertAgentSpiceResponseAdapter,
    PyBertNativeAdapter,
    execute_backend,
)
from sipi_contracts import parse_backend_execution_request

FAKE_ENGINE = ROOT / "tests" / "adapters" / "fixtures" / "fake_pybert.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def engine_entry(root: Path) -> dict:
    digest = sha256(FAKE_ENGINE)
    return {
        "instance_id": "pybert-rust",
        "engine_family": "pybert",
        "version": "0.1.0",
        "source_commit": "0" * 40,
        "bundle": {"kind": "local_path", "path": "bundles/fake_pybert.py", "sha256": digest},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": "2" * 64,
        "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "3" * 64},
        "bundle_manifest": {
            "entrypoint": "fake_pybert.py",
            "files": [{"relative_path": "fake_pybert.py", "role": "entrypoint", "sha256": digest, "byte_length": FAKE_ENGINE.stat().st_size}],
        },
        "extensions": {},
    }


def backend_request(**changes):
    payload_artifact = changes.pop("payload_artifact", None)
    value = {
        "schema": "sipi.backend-execution-request.v1",
        "run_id": "run-1",
        "analysis_id": "analysis-1",
        "attempt_id": "attempt-1",
        "backend_execution_id": "backend-1",
        "role": "reference",
        "engine_instance_id": "pybert-rust",
        "bundle_hash": "sha256:" + sha256(FAKE_ENGINE),
        "operation": "link.simulate.v1",
        "payload_schema": "pybert.simulation.v1",
        "payload": {"simulation_input": {"schema": "pybert.simulation.v1", "source": "fixture"}},
        "bound_inputs": {},
        "resource_limits": {"enforcement": "monitor", "wall_time_s": None, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None},
        "artifact_policy": {},
        "randomness": {},
        "selection_hash": "sha256:selection",
    }
    value.update(changes)
    if payload_artifact is not None:
        value.pop("payload", None)
        value["payload_artifact"] = payload_artifact
    return parse_backend_execution_request(value)


class PyBertAdapterTests(unittest.TestCase):
    def install_bundle(self, root: Path) -> None:
        target = root / "bundles" / "fake_pybert.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(FAKE_ENGINE.read_bytes())

    def test_command_builder_constructs_sim_native_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workdir = root / "work"
            workdir.mkdir()
            argv = PyBertNativeAdapter().build(backend_request(), root / "bundles" / "fake_pybert.py", workdir)
        self.assertEqual(argv[0:3], [sys.executable, "-I", str(root / "bundles" / "fake_pybert.py")])
        self.assertEqual(argv[3], "sim-native")
        self.assertTrue(Path(argv[4]).is_relative_to(workdir))
        self.assertEqual(argv[5:8], ["--output-dir", str(workdir / "out")])

    def test_success_hands_artifacts_to_artifact_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.install_bundle(root)
            artifact_root = root / "artifacts"
            result = execute_backend(
                backend_request(),
                engine_entry(root),
                root,
                builder=PyBertNativeAdapter(),
                artifact_root=artifact_root,
            )
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["domain_result_schema"], "pybert.native-cli-result.v1")
            self.assertEqual(result["domain_result"]["effective_input"]["schema"], "pybert.simulation.v1")
            refs = {item["relative_path"]: item for item in result["artifacts"]}
            self.assertEqual(set(refs), {"out/meta.json", "out/arrays.npz"})
            for relative, ref in refs.items():
                stored = artifact_root / relative
                self.assertTrue(stored.is_file())
                self.assertEqual(sha256(stored), ref["sha256"])
                self.assertEqual(stored.stat().st_size, ref["byte_length"])

    def test_artifacts_without_artifact_root_are_internal_invariant(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.install_bundle(root)
            result = execute_backend(backend_request(), engine_entry(root), root, builder=PyBertNativeAdapter())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "InternalInvariant")

    def test_payload_artifact_handoff_is_unsupported_capability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.install_bundle(root)
            request = backend_request(
                payload={},
                payload_artifact={
                    "schema": "sipi.artifact-ref.v1",
                    "content_schema": "pybert.simulation.v1",
                    "relative_path": "inputs/request.json",
                    "mime_type": "application/json",
                    "sha256": "a" * 64,
                    "byte_length": 1,
                    "producer": "fixture.platform",
                    "role": "input",
                    "extensions": {},
                },
            )
            result = execute_backend(request, engine_entry(root), root, builder=PyBertNativeAdapter())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "UnsupportedCapability")

    def test_missing_artifact_handoff_is_internal_invariant(self) -> None:
        class MissingHandoffBuilder(PyBertNativeAdapter):
            def build_outcome(self, request, engine_entry, workdir, process):
                outcome = super().build_outcome(request, engine_entry, workdir, process)
                return BackendOutcome(outcome.result, artifact_paths=())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.install_bundle(root)
            result = execute_backend(
                backend_request(),
                engine_entry(root),
                root,
                builder=MissingHandoffBuilder(),
                artifact_root=root / "artifacts",
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "InternalInvariant")

    def test_engine_failure_is_external_model_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.install_bundle(root)
            request = backend_request(payload={"simulation_input": {"fail": True}})
            result = execute_backend(request, engine_entry(root), root, builder=PyBertNativeAdapter())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "ExternalModelFailure")

    def test_current_drive_handoff_materializes_the_exact_rfm_artifact_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.install_bundle(root)
            metadata = root / "inputs" / "rfm-meta.json"
            response = root / "inputs" / "rfm-response.bin"
            metadata.parent.mkdir(parents=True)
            metadata.write_text('{"schema":"agent-spice.rfm-response.v1"}', encoding="utf-8")
            response.write_bytes(b"rfm-response")
            response_digest = sha256(response)
            request = backend_request(
                payload_schema="pybert.agent-spice-current-driven-link-request.v1",
                payload={
                    "schema": "pybert.agent-spice-current-driven-link-request.v1",
                    "input_ports": [1],
                    "output_ports": [1],
                    "input_currents_a": [[3.0] * 8],
                    "current_to_voltage_sign": -1,
                    "output_port_index": 0,
                    "rx_filter_impulse": [1.0],
                    "sample_interval_s": 2.5e-10,
                    "samples_per_ui": 4,
                    "n_taps": 2,
                    "gain": 0.25,
                    "delta_t": 1.0e-12,
                    "alpha": 0.0,
                    "ui_seconds": 1.0e-9,
                    "decision_scaler": 1.0,
                },
                bound_inputs={
                    "rfm_metadata": {
                        "schema": "sipi.artifact-ref.v1",
                        "content_schema": "agent-spice.rfm-response.v1",
                        "relative_path": "inputs/rfm-meta.json",
                        "mime_type": "application/json",
                        "sha256": sha256(metadata),
                        "byte_length": metadata.stat().st_size,
                        "producer": "agent-spice-process",
                        "role": "rfm-response",
                        "extensions": {},
                    },
                    "rfm_response": {
                        "schema": "sipi.artifact-ref.v1",
                        "content_schema": "agent-spice.rfm-response-binary.v1",
                        "relative_path": "inputs/rfm-response.bin",
                        "mime_type": "application/octet-stream",
                        "sha256": response_digest,
                        "byte_length": response.stat().st_size,
                        "producer": "agent-spice-process",
                        "role": "data",
                        "extensions": {},
                    },
                },
            )
            result = execute_backend(
                request,
                engine_entry(root),
                root,
                builder=PyBertAgentSpiceResponseAdapter(),
                artifact_root=root / "artifacts",
            )

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(
            result["domain_result_schema"],
            "pybert.agent-spice-current-driven-link-cli-result.v1",
        )
        self.assertEqual(
            result["domain_result"]["platform_rfm_artifacts"]["rfm_response"]["sha256"],
            response_digest,
        )


if __name__ == "__main__":
    unittest.main()
