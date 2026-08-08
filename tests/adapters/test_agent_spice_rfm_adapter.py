from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import AgentSpiceRfmResponseAdapter, execute_backend
from sipi_contracts import parse_backend_execution_request

REAL_ENGINE = Path(r"C:\Users\z3312\code\agent-spice\native\agent-spice-sim\target\release\agent-spice-sim.exe")
REAL_RFM = Path(r"C:\Users\z3312\code\agent-spice\native\AgentSpice.Engine\fixtures\one_port.rfm")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_real_engine() -> bool:
    return REAL_ENGINE.is_file() and REAL_RFM.is_file()


def engine_entry(root: Path, executable: Path) -> dict:
    digest = sha256(executable)
    return {
        "instance_id": "agent-spice-process",
        "engine_family": "agent-spice",
        "version": "0.1.0",
        "source_commit": "5887e9d8fad88381ec5a28851047d2cef0ba49f3",
        "bundle": {"kind": "local_path", "path": "bundles/agent-spice-sim.exe", "sha256": digest},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
        "runtime": {"kind": "native", "os": "windows", "architecture": "x86_64", "python_abi": None, "rust_target": "x86_64-pc-windows-msvc"},
        "dependency_lock_sha256": "2" * 64,
        "license_provenance": {"distribution_status": "authorized_private", "manifest_sha256": "3" * 64},
        "bundle_manifest": {
            "entrypoint": "agent-spice-sim.exe",
            "files": [{"relative_path": "agent-spice-sim.exe", "role": "entrypoint", "sha256": digest, "byte_length": executable.stat().st_size}],
        },
        "extensions": {},
    }


def backend_request(**changes):
    value = {
        "schema": "sipi.backend-execution-request.v1",
        "run_id": "run-1",
        "analysis_id": "analysis-1",
        "attempt_id": "attempt-1",
        "backend_execution_id": "backend-1",
        "role": "reference",
        "engine_instance_id": "agent-spice-process",
        "bundle_hash": "sha256:bundle",
        "operation": "circuit.solve.v1",
        "payload_schema": "sipi.adapter.agent-spice.rfm-response-request.v1",
        "payload": {"rfm": "models/channel.rfm", "fft_size": 16384, "dt": 1e-12},
        "bound_inputs": {},
        "resource_limits": {"enforcement": "monitor", "wall_time_s": 120, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None},
        "artifact_policy": {},
        "randomness": {},
        "selection_hash": "sha256:selection",
    }
    value.update(changes)
    return parse_backend_execution_request(value)


@unittest.skipUnless(has_real_engine(), "real agent-spice-sim engine is not built")
class AgentSpiceRfmResponseAdapterTests(unittest.TestCase):
    def test_live_rfm_response_runs_real_engine_and_hands_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bundles").mkdir(parents=True)
            executable = root / "bundles" / "agent-spice-sim.exe"
            shutil.copy2(REAL_ENGINE, executable)
            models = root / "models"
            models.mkdir()
            shutil.copy2(REAL_RFM, models / "channel.rfm")
            rfm_digest = sha256(models / "channel.rfm")
            result = execute_backend(
                backend_request(
                    bound_inputs={
                        "rfm": {
                            "schema": "sipi.artifact-ref.v1",
                            "content_schema": "agent-spice.rfm-model.v1",
                            "relative_path": "models/channel.rfm",
                            "mime_type": "application/octet-stream",
                            "sha256": rfm_digest,
                            "byte_length": (models / "channel.rfm").stat().st_size,
                            "producer": "example",
                            "role": "rfm-model",
                            "extensions": {},
                        }
                    }
                ),
                engine_entry(root, executable),
                root,
                builder=AgentSpiceRfmResponseAdapter(),
                artifact_root=root / "artifacts",
            )
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["domain_result_schema"], "agent-spice.rfm-response.v1")
            meta = result["domain_result"]
            self.assertEqual(meta["schema"], "agent-spice.rfm-response.v1")
            self.assertEqual(meta["fftSize"], 16384)
            self.assertEqual(meta["rfmName"], "channel.rfm")
            self.assertEqual(meta["layout"], "frequency-major,output-major,input-major,re-im,f64-le")
            self.assertIn("frequencyBins", meta)
            self.assertIn("inputPorts", meta)
            refs = {item["relative_path"]: item for item in result["artifacts"]}
            self.assertEqual(set(refs), {"out/meta.json", "out/response.bin"})
            expected_bytes = 8 * 2 * meta["frequencyBins"] * len(meta["inputPorts"]) * len(meta["outputPorts"])
            stored = root / "artifacts" / "out" / "response.bin"
            self.assertTrue(stored.is_file())
            self.assertEqual(stored.stat().st_size, expected_bytes)
            self.assertEqual(sha256(stored), refs["out/response.bin"]["sha256"])

    def test_missing_rfm_model_is_contract_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bundles").mkdir(parents=True)
            executable = root / "bundles" / "agent-spice-sim.exe"
            shutil.copy2(REAL_ENGINE, executable)
            (root / "models").mkdir()
            result = execute_backend(backend_request(), engine_entry(root, executable), root, builder=AgentSpiceRfmResponseAdapter())
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"]["category"], "InputNotFound")
            self.assertIn("rfm model is missing", result["error"]["message"])

    def test_missing_dt_is_contract_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bundles").mkdir(parents=True)
            executable = root / "bundles" / "agent-spice-sim.exe"
            shutil.copy2(REAL_ENGINE, executable)
            (root / "models").mkdir()
            result = execute_backend(
                backend_request(payload={"rfm": "models/channel.rfm", "fft_size": 16384}),
                engine_entry(root, executable),
                root,
                builder=AgentSpiceRfmResponseAdapter(),
            )
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"]["category"], "InvalidRequest")
            self.assertIn("positive dt", result["error"]["message"])

    def test_invalid_fft_size_is_contract_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bundles").mkdir(parents=True)
            executable = root / "bundles" / "agent-spice-sim.exe"
            shutil.copy2(REAL_ENGINE, executable)
            result = execute_backend(
                backend_request(payload={"rfm": "models/channel.rfm", "fft_size": -1, "dt": 1e-12}),
                engine_entry(root, executable),
                root,
                builder=AgentSpiceRfmResponseAdapter(),
            )
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"]["category"], "InvalidRequest")


if __name__ == "__main__":
    unittest.main()
