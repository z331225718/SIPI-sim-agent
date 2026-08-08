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
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import AgentSpiceRfmResponseAdapter, PyBertNativeAdapter
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

AGENT_SPICE_ENGINE = Path(r"C:\Users\z3312\code\agent-spice\native\agent-spice-sim\target\release\agent-spice-sim.exe")
AGENT_SPICE_COMMIT = "5887e9d8fad88381ec5a28851047d2cef0ba49f3"
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_real_engines() -> bool:
    return AGENT_SPICE_ENGINE.is_file() and PYBERT_WHEEL.is_file() and NATIVE_WHEEL.is_file()


def write_real_engine_lock(lock_path: Path, executable: Path) -> None:
    digest = sha256(executable)
    entry = {
        "instance_id": "agent-spice-process",
        "engine_family": "agent-spice",
        "version": "0.1.0",
        "source_commit": AGENT_SPICE_COMMIT,
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
    entry2 = _pybert_entry()
    lock = {"schema": "sipi.engine-lock.v1", "engines": [entry, entry2], "operation_defaults": {}, "extensions": {}}
    lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")


def _pybert_entry() -> dict:
    with zipfile.ZipFile(PYBERT_WHEEL) as archive:
        entry_data = archive.read("pybert/cli.py")
    return {
        "instance_id": "pybert-python",
        "engine_family": "pybert",
        "version": "0.1.0",
        "source_commit": "8fbd4fe3e542929b18c44f67d0cf59f251f4faca",
        "bundle": {"kind": "local_path", "path": "bundles/py_bert_agent-0.1.0-py3-none-any.whl", "sha256": sha256(PYBERT_WHEEL)},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "4" * 64},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": "5" * 64,
        "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "6" * 64},
        "bundle_manifest": {
            "entrypoint": "pybert/cli.py",
            "files": [
                {"relative_path": "pybert/cli.py", "role": "entrypoint", "sha256": hashlib.sha256(entry_data).hexdigest(), "byte_length": len(entry_data)},
                {"relative_path": "bundles/pybert_native-0.1.0-cp311-abi3-win_amd64.whl", "role": "dependency", "sha256": sha256(NATIVE_WHEEL), "byte_length": NATIVE_WHEEL.stat().st_size},
            ],
        },
        "extensions": {
            "sipi.m2.console-script": "pybert",
            "sipi.m2.pip-dependencies": list(PIP_DEPENDENCIES),
        },
    }


@unittest.skipUnless(has_real_engines(), "real agent-spice + pybert engines are not built")
class TwoEngineVerticalTests(unittest.TestCase):
    def test_rfm_to_link_runs_both_real_engines_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = ROOT / "examples" / "channel" / "rfm-to-link"
            shutil.copytree(example, root, dirs_exist_ok=True)
            (root / "bundles").mkdir(exist_ok=True)
            shutil.copy2(AGENT_SPICE_ENGINE, root / "bundles" / "agent-spice-sim.exe")
            shutil.copy2(PYBERT_WHEEL, root / "bundles" / "py_bert_agent-0.1.0-py3-none-any.whl")
            shutil.copy2(NATIVE_WHEEL, root / "bundles" / "pybert_native-0.1.0-cp311-abi3-win_amd64.whl")
            write_real_engine_lock(root / "engine.lock", root / "bundles" / "agent-spice-sim.exe")
            with SupervisorRegistry(root / "registry.sqlite3") as registry:
                engine_registry = EngineRegistry(load_engine_lock(root / "engine.lock"))
                resolved = resolve_project(parse_project((root / "project.json").read_text(encoding="utf-8")), root)
                plan = plan_dag(resolved, engine_registry)
                registry.submit_execution(run_id="run-1", project_hash=resolved.project_hash, submission_key="key-1", failure_policy="block-dependents, continue-independent")
                driver = ExecutionDriver(
                    registry,
                    {"agent-spice": AgentSpiceRfmResponseAdapter(), "pybert": PyBertNativeAdapter()},
                    options=DriverOptions(artifact_root=root),
                )
                report = driver.run(resolved, plan, engine_registry, "run-1")
                self.assertEqual(report["status"], "succeeded")
                self.assertEqual(report["nodes"], {"rfm-response": "succeeded", "link-eye": "succeeded"})
                run_report = build_run_report(run_id="run-1", resolved=resolved, plan=plan, registry=registry, artifact_root=root)
                self.assertEqual([section["status"] for section in run_report["analyses"]], ["succeeded", "succeeded"])
                rfm_meta = (
                    root
                    / "nodes"
                    / "rfm-response"
                    / "attempts"
                    / "rfm-response-attempt-0"
                    / "backends"
                    / "rfm-response-attempt-0-primary"
                    / "out"
                    / "meta.json"
                )
                self.assertTrue(rfm_meta.is_file())
                self.assertEqual(json.loads(rfm_meta.read_text(encoding="utf-8"))["schema"], "agent-spice.rfm-response.v1")
                link_meta = (
                    root
                    / "nodes"
                    / "link-eye"
                    / "attempts"
                    / "link-eye-attempt-0"
                    / "backends"
                    / "link-eye-attempt-0-primary"
                    / "out"
                    / "meta.json"
                )
                self.assertTrue(link_meta.is_file())
                link = json.loads(link_meta.read_text(encoding="utf-8"))
                self.assertEqual(link["schema"], "pybert.native-cli-result.v1")
                self.assertEqual(link["backend_metadata"]["engine"]["backend"], "rust")
                arrays = root / "nodes" / "link-eye" / "attempts" / "link-eye-attempt-0" / "backends" / "link-eye-attempt-0-primary" / "out" / "arrays.npz"
                self.assertTrue(arrays.is_file())


if __name__ == "__main__":
    unittest.main()
