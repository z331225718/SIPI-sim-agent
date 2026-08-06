from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import (
    AgentSpiceHspiceAdapter,
    BackendOutcome,
    CommandBuilder,
    ProcessResult,
    assemble_backend_result,
    execute_backend,
    invocation,
    platform_error,
)
from sipi_contracts import parse_backend_execution_request

FAKE_ENGINE = ROOT / "tests" / "adapters" / "fixtures" / "fake_engine.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def engine_entry(root: Path, *, instance_id: str = "agent-spice-python") -> dict:
    digest = sha256(FAKE_ENGINE)
    return {
        "instance_id": instance_id,
        "engine_family": "agent-spice",
        "version": "0.1.0",
        "source_commit": "0" * 40,
        "bundle": {"kind": "local_path", "path": "bundles/fake_engine.py", "sha256": digest},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": "2" * 64,
        "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "3" * 64},
        "bundle_manifest": {
            "entrypoint": "fake_engine.py",
            "files": [{"relative_path": "fake_engine.py", "role": "entrypoint", "sha256": digest, "byte_length": FAKE_ENGINE.stat().st_size}],
        },
        "extensions": {},
    }


def install_bundle(root: Path) -> None:
    target = root / "bundles" / "fake_engine.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(FAKE_ENGINE.read_bytes())


def backend_request(**changes):
    value = {
        "schema": "sipi.backend-execution-request.v1",
        "run_id": "run-1",
        "analysis_id": "analysis-1",
        "attempt_id": "attempt-1",
        "backend_execution_id": "backend-1",
        "role": "primary",
        "engine_instance_id": "agent-spice-python",
        "bundle_hash": "sha256:" + sha256(FAKE_ENGINE),
        "operation": "circuit.solve.v1",
        "payload_schema": "agent-spice.hspice.v1",
        "payload": {},
        "bound_inputs": {},
        "resource_limits": {"enforcement": "monitor", "wall_time_s": None, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None},
        "artifact_policy": {},
        "randomness": {},
        "selection_hash": "sha256:selection",
    }
    value.update(changes)
    return parse_backend_execution_request(value)


class FixtureBuilder(CommandBuilder):
    domain_result_schema = "fixture.domain-result.v1"

    def build(self, request, bundle_path, workdir):
        payload = request["payload"]
        argv = [*invocation(bundle_path), "--result-json", str(workdir / "domain-result.json")]
        if payload.get("read"):
            argv += ["--read", str(workdir / payload["read"])]
        if payload.get("fail"):
            argv += ["--fail"]
        if payload.get("sleep_s"):
            argv += ["--sleep", str(payload["sleep_s"])]
        return argv

    def build_outcome(self, request, engine_entry, workdir, process):
        result_path = workdir / "domain-result.json"
        if not result_path.is_file():
            return BackendOutcome(assemble_backend_result(request, status="failed", error=platform_error("ExternalModelFailure", "fixture engine produced no result file")))
        return BackendOutcome(
            assemble_backend_result(
                request,
                status="succeeded",
                domain_result=json.loads(result_path.read_text(encoding="utf-8")),
                domain_result_schema=self.domain_result_schema,
            )
        )


class ProcessAdapterTests(unittest.TestCase):
    def test_success_runs_isolated_engine_and_materializes_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            deck = root / "inputs" / "deck.sp"
            deck.parent.mkdir(parents=True)
            deck.write_text(".title fixture\n", encoding="utf-8")
            request = backend_request(
                payload={"read": "inputs/deck.sp"},
                bound_inputs={
                    "deck": {
                        "schema": "sipi.artifact-ref.v1",
                        "content_schema": "agent-spice.hspice.v1",
                        "relative_path": "inputs/deck.sp",
                        "mime_type": "text/plain",
                        "sha256": sha256(deck),
                        "byte_length": deck.stat().st_size,
                        "producer": "fixture.platform",
                        "role": "input",
                        "extensions": {},
                    }
                },
            )
            result = execute_backend(request, engine_entry(root), root, builder=FixtureBuilder())
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["domain_result_schema"], "fixture.domain-result.v1")
        self.assertEqual(result["domain_result"]["read_content"], ".title fixture\n")
        self.assertIsNone(result["domain_result"]["env_pythonpath"])
        self.assertEqual(result["domain_result"]["py_no_user_site"], "1")
        self.assertNotEqual(result["domain_result"]["cwd"], str(root.resolve()))

    def test_bound_input_hash_mismatch_is_input_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            deck = root / "inputs" / "deck.sp"
            deck.parent.mkdir(parents=True)
            deck.write_text(".title fixture\n", encoding="utf-8")
            request = backend_request(
                payload={},
                bound_inputs={
                    "deck": {
                        "schema": "sipi.artifact-ref.v1",
                        "content_schema": "agent-spice.hspice.v1",
                        "relative_path": "inputs/deck.sp",
                        "mime_type": "text/plain",
                        "sha256": "f" * 64,
                        "byte_length": deck.stat().st_size,
                        "producer": "fixture.platform",
                        "role": "input",
                        "extensions": {},
                    }
                },
            )
            result = execute_backend(request, engine_entry(root), root, builder=FixtureBuilder())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "InputNotFound")
        self.assertEqual(result["error"]["cause"]["kind"], "AdapterContractError")

    def test_nonzero_exit_is_failed_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            request = backend_request(payload={"fail": True})
            result = execute_backend(request, engine_entry(root), root, builder=FixtureBuilder())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "ExternalModelFailure")
        self.assertIn("fixture engine failed", result["error"]["message"])

    def test_wall_time_timeout_is_timeout_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            request = backend_request(payload={"sleep_s": 5}, resource_limits={"enforcement": "monitor", "wall_time_s": 0.1, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None})
            result = execute_backend(request, engine_entry(root), root, builder=FixtureBuilder())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "Timeout")
        self.assertEqual(result["error"]["resource"], "wall_time_s")

    def test_bundle_verification_failures_are_engine_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            request = backend_request()
            entry = engine_entry(root)
            entry["bundle"] = {"kind": "https_url", "url": "https://example.invalid/bundle", "sha256": sha256(FAKE_ENGINE)}
            result = execute_backend(request, entry, root, builder=FixtureBuilder())
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"]["category"], "EngineUnavailable")

            (root / "bundles" / "fake_engine.py").unlink()
            result = execute_backend(request, engine_entry(root), root, builder=FixtureBuilder())
            self.assertEqual(result["error"]["category"], "EngineUnavailable")

            install_bundle(root)
            entry = engine_entry(root)
            entry["bundle"]["sha256"] = "f" * 64
            result = execute_backend(request, entry, root, builder=FixtureBuilder())
            self.assertEqual(result["error"]["category"], "EngineUnavailable")

            entry = engine_entry(root)
            entry["bundle"]["path"] = "../escape.py"
            result = execute_backend(request, entry, root, builder=FixtureBuilder())
            self.assertEqual(result["error"]["category"], "EngineUnavailable")

    def test_hspice_command_builder_constructs_real_cli_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            workdir = root / "work"
            deck = workdir / "inputs" / "deck.sp"
            deck.parent.mkdir(parents=True)
            deck.write_text(".title fixture\n", encoding="utf-8")
            request = backend_request(payload={"deck": "inputs/deck.sp", "backend": "native"})
            argv = AgentSpiceHspiceAdapter().build(request, root / "bundles" / "fake_engine.py", workdir)
        self.assertEqual(argv[:3], [sys.executable, "-I", str(root / "bundles" / "fake_engine.py")])
        self.assertEqual(argv[3:7], ["run-hspice", str(deck), "--backend", "native"])
        self.assertEqual(argv[7:10], ["--output-root", str(workdir / "out"), "--execute"])

    def test_unsupported_backend_is_unsupported_capability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            request = backend_request(payload={"deck": "deck.sp", "backend": "bogus"})
            result = execute_backend(request, engine_entry(root), root, builder=AgentSpiceHspiceAdapter())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "UnsupportedCapability")
        self.assertEqual(result["error"]["cause"]["kind"], "UnsupportedCapabilityError")

    def test_deck_path_escape_is_invalid_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            request = backend_request(payload={"deck": "../escape.sp"})
            result = execute_backend(request, engine_entry(root), root, builder=AgentSpiceHspiceAdapter())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "InvalidRequest")

    def test_hspice_missing_deck_is_input_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            request = backend_request(payload={"deck": "inputs/missing.sp"})
            result = execute_backend(request, engine_entry(root), root, builder=AgentSpiceHspiceAdapter())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "InputNotFound")

    def test_hspice_result_assembly_reads_run_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workdir = root / "work"
            case_dir = workdir / "out" / "deck" / "deck__base"
            case_dir.mkdir(parents=True)
            (case_dir / "run_summary.json").write_text(json.dumps({"exit_code": 0, "measures": {"vout": 1.0}}), encoding="utf-8")
            request = backend_request(payload={"deck": "deck.sp"})
            result = AgentSpiceHspiceAdapter().build_outcome(
                request,
                engine_entry(root),
                workdir,
                ProcessResult(returncode=0, stdout="", stderr="", elapsed_s=0.1, timed_out=False),
            )
        self.assertEqual(result.result["status"], "succeeded")
        self.assertEqual(result.result["domain_result_schema"], "agent-spice.hspice-run-summary.v1")
        self.assertEqual(result.result["domain_result"]["measures"], {"vout": 1.0})


if __name__ == "__main__":
    unittest.main()
