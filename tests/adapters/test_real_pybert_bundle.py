from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import PyBertNativeAdapter, execute_backend
from sipi_contracts import parse_backend_execution_request

PYBERT_WHEEL = Path(r"C:\Users\z3312\orca\workspaces\Py-bert-agent\master\dist\py_bert_agent-0.1.0-py3-none-any.whl")
NATIVE_WHEEL = Path(r"C:\Users\z3312\orca\workspaces\Py-bert-agent\master\native\pybert-python\dist\pybert_native-0.1.0-cp311-abi3-win_amd64.whl")

PIP_DEPENDENCIES = (
    "numpy==2.2.6",
    "scipy==1.15.3",
    "scikit-rf==1.10.0",
    "pyyaml==6.0.3",
    "click==8.4.2",
    "pychopmarg==3.1.2",
    "pyibis-ami==9.2.0",
    "parsec==3.17",
    "pydantic==2.13.4",
    "fastapi==0.141.1",
    "uvicorn==0.52.1",
    "jinja2==3.1.6",
    "python-multipart==0.0.32",
    "starlette==0.52.1",
)

SIMULATION_INPUT = {
    "schema": "pybert.simulation.v1",
    "runId": "sipi-native-smoke",
    "modulation": "nrz",
    "pattern": {"kind": "prbs", "order": 7, "seed": 17},
    "timebase": {"sampleInterval": 1.0e-12, "samplesPerUi": 2, "dataRate": 500.0e9, "nbits": 16},
    "channel": {
        "kind": "impulse_response",
        "value": {
            "sampleInterval": 1.0e-12,
            "impulseResponseVoltsPerSecond": [1.0e12, 0.25e12],
            "sourceImpedance": 50.0,
            "loadImpedance": 50.0,
        },
    },
    "tx": {"amplitude": 0.5, "ffe": {"enabled": False, "weights": [], "cursorPosition": 0}},
    "rx": {"nativeCtleEnabled": False, "dfeTaps": 0, "viterbiEnabled": False},
    "analysis": {"statisticalEye": None, "includeJitter": False, "includeBathtub": False},
    "limits": {"maxTotalSamples": 50_000_000, "maxMemoryBytes": 2 * 1024 * 1024 * 1024, "maxDistributionStates": 200_000},
    "externalModels": [],
    "legacyOptions": {},
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_real_wheels() -> bool:
    return PYBERT_WHEEL.is_file() and NATIVE_WHEEL.is_file()


def engine_entry(root: Path) -> dict:
    wheels = []
    for wheel in (PYBERT_WHEEL, NATIVE_WHEEL):
        target = root / "bundles" / wheel.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(wheel, target)
        wheels.append(target)
    primary = wheels[0]
    with zipfile.ZipFile(primary) as archive:
        entry_data = archive.read("pybert/cli.py")
    entry_bytes = len(entry_data)
    manifest_files = [
        {"relative_path": "pybert/cli.py", "role": "entrypoint", "sha256": hashlib.sha256(entry_data).hexdigest(), "byte_length": entry_bytes},
        {"relative_path": f"bundles/{wheels[1].name}", "role": "dependency", "sha256": sha256(wheels[1]), "byte_length": wheels[1].stat().st_size},
    ]
    return {
        "instance_id": "pybert-python",
        "engine_family": "pybert",
        "version": "0.1.0",
        "source_commit": "8fbd4fe3e542929b18c44f67d0cf59f251f4faca",
        "bundle": {"kind": "local_path", "path": f"bundles/{primary.name}", "sha256": sha256(primary)},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},        "dependency_lock_sha256": "2" * 64,
        "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "3" * 64},
        "bundle_manifest": {"entrypoint": "pybert/cli.py", "files": manifest_files},
        "extensions": {
            "sipi.m2.console-script": "pybert",
            "sipi.m2.pip-dependencies": list(PIP_DEPENDENCIES),
        },
    }


def backend_request(**changes):
    value = {
        "schema": "sipi.backend-execution-request.v1",
        "run_id": "run-1",
        "analysis_id": "analysis-1",
        "attempt_id": "attempt-1",
        "backend_execution_id": "backend-1",
        "role": "reference",
        "engine_instance_id": "pybert-python",
        "bundle_hash": "sha256:bundle",
        "operation": "link.simulate.v1",
        "payload_schema": "pybert.simulation.v1",
        "payload": {"simulation_input": SIMULATION_INPUT},
        "bound_inputs": {},
        "resource_limits": {"enforcement": "monitor", "wall_time_s": 300, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None},
        "artifact_policy": {},
        "randomness": {},
        "selection_hash": "sha256:selection",
    }
    value.update(changes)
    return parse_backend_execution_request(value)


@unittest.skipUnless(has_real_wheels(), "real pybert wheels are not built")
class RealPyBertBundleTests(unittest.TestCase):
    def test_real_pybert_wheels_run_in_managed_venv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = execute_backend(
                backend_request(),
                engine_entry(root),
                root,
                builder=PyBertNativeAdapter(),
                artifact_root=root / "artifacts",
            )
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["domain_result_schema"], "pybert.native-cli-result.v1")
            meta = result["domain_result"]
            self.assertEqual(meta["schema"], "pybert.native-cli-result.v1")
            self.assertEqual(meta["effective_input"]["runId"], "sipi-native-smoke")
            self.assertEqual(meta["backend_metadata"]["engine"]["backend"], "rust")
            refs = {item["relative_path"]: item for item in result["artifacts"]}
            self.assertEqual(set(refs), {"out/meta.json", "out/arrays.npz"})
            stored = root / "artifacts" / "out" / "arrays.npz"
            self.assertTrue(stored.is_file())
            self.assertEqual(sha256(stored), refs["out/arrays.npz"]["sha256"])


if __name__ == "__main__":
    unittest.main()
