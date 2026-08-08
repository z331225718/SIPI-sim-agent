from __future__ import annotations

import hashlib
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

from sipi_adapters import AgentSpiceRfmResponseAdapter
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

REAL_ENGINE = Path(r"C:\Users\z3312\code\agent-spice\native\agent-spice-sim\target\release\agent-spice-sim.exe")
REAL_SOURCE_COMMIT = "5887e9d8fad88381ec5a28851047d2cef0ba49f3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_real_engine() -> bool:
    return REAL_ENGINE.is_file()


def write_real_engine_lock(lock_path: Path, executable: Path) -> None:
    digest = sha256(executable)
    entry = {
        "instance_id": "agent-spice-process",
        "engine_family": "agent-spice",
        "version": "0.1.0",
        "source_commit": REAL_SOURCE_COMMIT,
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
    lock = {"schema": "sipi.engine-lock.v1", "engines": [entry], "operation_defaults": {}, "extensions": {}}
    lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")


@unittest.skipUnless(has_real_engine(), "real agent-spice-sim engine is not built")
class RealEngineVerticalTests(unittest.TestCase):
    def test_rfm_deck_runs_real_engine_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = ROOT / "examples" / "circuit" / "rfm-deck"
            shutil.copytree(example, root, dirs_exist_ok=True)
            (root / "bundles").mkdir(exist_ok=True)
            executable = root / "bundles" / "agent-spice-sim.exe"
            shutil.copy2(REAL_ENGINE, executable)
            write_real_engine_lock(root / "engine.lock", executable)
            rfm = root / "models" / "channel.rfm"
            rfm_digest = sha256(rfm)
            with SupervisorRegistry(root / "registry.sqlite3") as registry:
                engine_registry = EngineRegistry(load_engine_lock(root / "engine.lock"))
                resolved = resolve_project(parse_project((root / "project.json").read_text(encoding="utf-8")), root)
                plan = plan_dag(resolved, engine_registry)
                registry.submit_execution(run_id="run-1", project_hash=resolved.project_hash, submission_key="key-1", failure_policy="block-dependents, continue-independent")
                driver = ExecutionDriver(
                    registry,
                    {"agent-spice": AgentSpiceRfmResponseAdapter()},
                    options=DriverOptions(artifact_root=root),
                )
                report = driver.run(resolved, plan, engine_registry, "run-1")
                self.assertEqual(report["status"], "succeeded")
                self.assertEqual(report["nodes"], {"rfm-deck": "succeeded"})
                run_report = build_run_report(run_id="run-1", resolved=resolved, plan=plan, registry=registry, artifact_root=root)
                self.assertEqual([section["status"] for section in run_report["analyses"]], ["succeeded"])
                rfm_meta = (
                    root
                    / "nodes"
                    / "rfm-deck"
                    / "attempts"
                    / "rfm-deck-attempt-0"
                    / "backends"
                    / "rfm-deck-attempt-0-primary"
                    / "out"
                    / "meta.json"
                )
                self.assertTrue(rfm_meta.is_file())
                meta = json.loads(rfm_meta.read_text(encoding="utf-8"))
                self.assertEqual(meta["schema"], "agent-spice.rfm-response.v1")
                self.assertEqual(meta["fftSize"], 16384)
                self.assertEqual(meta["rfmName"], "channel.rfm")
                response = rfm_meta.parent / "response.bin"
                self.assertTrue(response.is_file())
                expected_bytes = 8 * 2 * meta["frequencyBins"] * len(meta["inputPorts"]) * len(meta["outputPorts"])
                self.assertEqual(response.stat().st_size, expected_bytes)


if __name__ == "__main__":
    unittest.main()
