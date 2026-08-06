from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import AgentComRunAdapter, execute_backend
from sipi_contracts import parse_backend_execution_request

FAKE_ENGINE = ROOT / "tests" / "adapters" / "fixtures" / "fake_com8023.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def engine_entry(root: Path) -> dict:
    digest = sha256(FAKE_ENGINE)
    return {
        "instance_id": "agent-com-process",
        "engine_family": "agent-com",
        "version": "0.1.0",
        "source_commit": "0" * 40,
        "bundle": {"kind": "local_path", "path": "bundles/fake_com8023.py", "sha256": digest},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": "2" * 64,
        "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "3" * 64},
        "bundle_manifest": {
            "entrypoint": "fake_com8023.py",
            "files": [{"relative_path": "fake_com8023.py", "role": "entrypoint", "sha256": digest, "byte_length": FAKE_ENGINE.stat().st_size}],
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
        "role": "primary",
        "engine_instance_id": "agent-com-process",
        "bundle_hash": "sha256:" + sha256(FAKE_ENGINE),
        "operation": "com.r480.run.v1",
        "payload_schema": "agent-com.r480.v1",
        "payload": {"config": "inputs/config.xlsx", "thru": "inputs/thru.s4p"},
        "bound_inputs": {},
        "resource_limits": {"enforcement": "monitor", "wall_time_s": None, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None},
        "artifact_policy": {},
        "randomness": {},
        "selection_hash": "sha256:selection",
    }
    value.update(changes)
    return parse_backend_execution_request(value)


def input_artifact(root: Path, relative: str, content: bytes) -> dict:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "schema": "sipi.artifact-ref.v1",
        "content_schema": "agent-com.r480.v1",
        "relative_path": relative,
        "mime_type": "application/octet-stream",
        "sha256": sha256(path),
        "byte_length": len(content),
        "producer": "fixture.platform",
        "role": "input",
        "extensions": {},
    }


class AgentComAdapterTests(unittest.TestCase):
    def install_bundle(self, root: Path) -> None:
        target = root / "bundles" / "fake_com8023.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(FAKE_ENGINE.read_bytes())

    def test_command_builder_constructs_com8023_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workdir = root / "work"
            (workdir / "inputs").mkdir(parents=True)
            config = workdir / "inputs" / "config.xlsx"
            thru = workdir / "inputs" / "thru.s4p"
            fext = workdir / "inputs" / "fext.s4p"
            config.write_bytes(b"xlsx")
            thru.write_bytes(b"s4p")
            fext.write_bytes(b"s4p")
            request = backend_request(payload={"config": "inputs/config.xlsx", "thru": "inputs/thru.s4p", "fext": ["inputs/fext.s4p"], "no_plots": True})
            argv = AgentComRunAdapter().build(request, root / "bundles" / "fake_com8023.py", workdir)
        self.assertEqual(argv[0:3], [sys.executable, "-I", str(root / "bundles" / "fake_com8023.py")])
        self.assertEqual(argv[3:10], ["run", "--config", str(config), "--thru", str(thru), "--output-dir", str(workdir / "out")])
        self.assertEqual(argv[10:12], ["--fext", str(fext)])
        self.assertEqual(argv[12:], ["--no-plots"])

    def test_success_hands_artifacts_to_artifact_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.install_bundle(root)
            config_ref = input_artifact(root, "inputs/config.xlsx", b"xlsx-bytes")
            thru_ref = input_artifact(root, "inputs/thru.s4p", b"s4p-bytes")
            artifact_root = root / "artifacts"
            request = backend_request(bound_inputs={"config": config_ref, "thru": thru_ref})
            result = execute_backend(
                request,
                engine_entry(root),
                root,
                builder=AgentComRunAdapter(),
                artifact_root=artifact_root,
            )
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["domain_result_schema"], "agent-com.result-v1")
            self.assertEqual(result["domain_result"]["source_revision"], "r480")
            refs = {item["relative_path"]: item for item in result["artifacts"]}
            self.assertEqual(set(refs), {"out/result.json", "out/diagnostics.npz", "out/report.html"})
            for relative, ref in refs.items():
                stored = artifact_root / relative
                self.assertTrue(stored.is_file())
                self.assertEqual(sha256(stored), ref["sha256"])
                self.assertEqual(stored.stat().st_size, ref["byte_length"])

    def test_missing_config_is_input_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.install_bundle(root)
            result = execute_backend(backend_request(), engine_entry(root), root, builder=AgentComRunAdapter())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "InputNotFound")

    def test_config_escape_is_invalid_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.install_bundle(root)
            request = backend_request(payload={"config": "../config.xlsx", "thru": "inputs/thru.s4p"})
            result = execute_backend(request, engine_entry(root), root, builder=AgentComRunAdapter())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "InvalidRequest")

    def test_missing_result_json_is_external_model_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.install_bundle(root)
            config_ref = input_artifact(root, "inputs/config.xlsx", b"NO_RESULT-xlsx")
            thru_ref = input_artifact(root, "inputs/thru.s4p", b"s4p-bytes")
            request = backend_request(bound_inputs={"config": config_ref, "thru": thru_ref})
            result = execute_backend(request, engine_entry(root), root, builder=AgentComRunAdapter(), artifact_root=root / "artifacts")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "ExternalModelFailure")

    def test_engine_failure_is_external_model_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.install_bundle(root)
            config_ref = input_artifact(root, "inputs/config.xlsx", b"FAIL-xlsx")
            thru_ref = input_artifact(root, "inputs/thru.s4p", b"s4p-bytes")
            request = backend_request(bound_inputs={"config": config_ref, "thru": thru_ref})
            result = execute_backend(request, engine_entry(root), root, builder=AgentComRunAdapter())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "ExternalModelFailure")


if __name__ == "__main__":
    unittest.main()
