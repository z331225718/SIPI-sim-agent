from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_contracts import parse_capabilities_certified, parse_engine_lock

FAKE_ENGINE = ROOT / "tests" / "adapters" / "fixtures" / "fake_engine.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def engine_entry(root: Path, *, os_name: str = "windows", architecture: str = "x86_64", declarations: list | None = None) -> dict:
    digest = sha256(FAKE_ENGINE)
    return {
        "instance_id": "managed-worker-fixture",
        "engine_family": "fixture",
        "version": "0.1.0",
        "source_commit": "0" * 40,
        "bundle": {"kind": "local_path", "path": "bundles/fake_engine.py", "sha256": digest},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
        "runtime": {"kind": "python", "os": os_name, "architecture": architecture, "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": "2" * 64,
        "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "3" * 64},
        "bundle_manifest": {"entrypoint": "fake_engine.py", "files": [{"relative_path": "fake_engine.py", "role": "entrypoint", "sha256": digest, "byte_length": FAKE_ENGINE.stat().st_size}]},
        "extensions": {"sipi.m2.certified": declarations or []},
    }


def declaration(**changes) -> dict:
    value = {
        "operation": "circuit.solve.v1",
        "payload_schema": "agent-spice.hspice.v1",
        "behavior_profile": "default",
        "role": "reference",
        "execution_mode": "managed_worker",
        "evidence_refs": ["g2b-windows-managed-worker-v1:wall_time", "g2b-windows-managed-worker-v1:memory", "g2b-windows-managed-worker-v1:cpu_time", "g2b-windows-managed-worker-v1:process_count", "g2b-windows-managed-worker-v1:artifact_bytes"],
        "resource_enforcement": {"wall_time_s": "hard", "cpu_time_s": "hard", "memory_bytes": "hard", "process_count": "hard", "artifact_bytes": "hard"},
        "certified_at": "2026-08-08",
        "expires_at": "2027-08-08",
    }
    value.update(changes)
    return value


def build_catalog(root: Path) -> int:
    import subprocess

    result = subprocess.run([sys.executable, str(ROOT / "tools" / "build_m3_capabilities_certified.py"), "--root", str(root)], capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


class BuildM3CapabilitiesCertifiedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        target = self.root / "bundles" / "fake_engine.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(FAKE_ENGINE.read_bytes())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_lock(self, entries: list[dict]) -> None:
        (self.root / "engine.lock").write_text(json.dumps({"schema": "sipi.engine-lock.v1", "engines": entries, "operation_defaults": {}, "extensions": {}}), encoding="utf-8")

    def test_windows_managed_worker_hard_enforcement_is_certified_with_g2b_evidence(self) -> None:
        self.write_lock([engine_entry(self.root, declarations=[declaration()])])
        code, output = build_catalog(self.root)
        self.assertEqual(code, 0, output)
        catalog = json.loads((self.root / "docs" / "baselines" / "capabilities.certified.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["advertise"], True)
        self.assertEqual(len(catalog["entries"]), 1)
        entry = catalog["entries"][0]
        self.assertEqual(entry["resource_enforcement"]["memory_bytes"], "hard")
        self.assertEqual(entry["platform"], {"os": "windows", "architecture": "x86_64"})
        self.assertEqual(entry["execution_mode"], "managed_worker")
        parse_capabilities_certified(catalog, producer=True)

    def test_hard_enforcement_off_windows_managed_worker_is_rejected(self) -> None:
        self.write_lock([engine_entry(self.root, os_name="linux", declarations=[declaration()])])
        code, output = build_catalog(self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("hard wall_time_s is only certified on Windows x86_64 managed worker", output)

    def test_hard_field_without_g2b_fixture_evidence_is_rejected(self) -> None:
        decl = declaration()
        decl["evidence_refs"] = ["g2b-windows-managed-worker-v1:wall_time", "g2b-windows-managed-worker-v1:memory", "g2b-windows-managed-worker-v1:cpu_time", "g2b-windows-managed-worker-v1:process_count"]
        self.write_lock([engine_entry(self.root, declarations=[decl])])
        code, output = build_catalog(self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("hard artifact_bytes requires G2b fault fixture evidence", output)

    def test_linux_hard_enforcement_absent_from_windows_only_catalog(self) -> None:
        decl = declaration()
        decl["resource_enforcement"] = {"wall_time_s": "hard", "cpu_time_s": "monitor", "memory_bytes": "unsupported", "process_count": "unsupported", "artifact_bytes": "unsupported"}
        decl["evidence_refs"] = ["g2b-windows-managed-worker-v1:wall_time"]
        self.write_lock([engine_entry(self.root, declarations=[decl])])
        code, output = build_catalog(self.root)
        self.assertEqual(code, 0, output)
        catalog = json.loads((self.root / "docs" / "baselines" / "capabilities.certified.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["entries"][0]["resource_enforcement"]["wall_time_s"], "hard")
        self.assertEqual(catalog["entries"][0]["resource_enforcement"]["cpu_time_s"], "monitor")


if __name__ == "__main__":
    unittest.main()
