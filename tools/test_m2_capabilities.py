from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE_ENGINE = ROOT / "tests" / "adapters" / "fixtures" / "fake_engine.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def engine_entry(root: Path, *, license_status: str = "authorized_public", declarations: list | None = None) -> dict:
    digest = sha256(FAKE_ENGINE)
    return {
        "instance_id": "pybert-rust",
        "engine_family": "pybert",
        "version": "0.1.0",
        "source_commit": "0" * 40,
        "bundle": {"kind": "local_path", "path": "bundles/fake_engine.py", "sha256": digest},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": "2" * 64,
        "license_provenance": {"distribution_status": license_status, "manifest_sha256": "3" * 64},
        "bundle_manifest": {"entrypoint": "fake_engine.py", "files": [{"relative_path": "fake_engine.py", "role": "entrypoint", "sha256": digest, "byte_length": FAKE_ENGINE.stat().st_size}]},
        "extensions": {"sipi.m2.certified": declarations or []},
    }


def write_lock(root: Path, entries: list[dict]) -> None:
    payload = {"schema": "sipi.engine-lock.v1", "engines": entries, "operation_defaults": {}, "extensions": {}}
    (root / "engine.lock").write_text(json.dumps(payload), encoding="utf-8")


def install_bundle(root: Path) -> None:
    target = root / "bundles" / "fake_engine.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(FAKE_ENGINE.read_bytes())


def declaration(**changes) -> dict:
    value = {
        "operation": "link.simulate.v1",
        "payload_schema": "pybert.simulation.v1",
        "behavior_profile": "default",
        "role": "candidate",
        "evidence_refs": ["fixture:pybert-rust-smoke"],
        "certified_at": "2026-08-06",
        "expires_at": "2027-08-06",
    }
    value.update(changes)
    return value


def run_tool(name: str, root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(ROOT / "tools" / name), "--root", str(root)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class M2CapabilitiesTests(unittest.TestCase):
    def test_generator_writes_catalog_and_verifier_accepts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            write_lock(root, [engine_entry(root, declarations=[declaration()])])
            build = run_tool("build_m2_capabilities_certified.py", root)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            catalog = root / "docs" / "baselines" / "capabilities.certified.v1.json"
            self.assertTrue(catalog.is_file())
            verify = run_tool("verify_m2_capabilities_certified.py", root)
            self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
            self.assertIn("valid", verify.stdout)

    def test_generator_refuses_without_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            write_lock(root, [engine_entry(root)])
            build = run_tool("build_m2_capabilities_certified.py", root)
            self.assertEqual(build.returncode, 0)
            self.assertFalse((root / "docs" / "baselines" / "capabilities.certified.v1.json").is_file())
            self.assertIn("no certified capabilities", build.stdout)

    def test_generator_refuses_blocked_license(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            write_lock(root, [engine_entry(root, license_status="blocked_unknown", declarations=[declaration()])])
            build = run_tool("build_m2_capabilities_certified.py", root)
            self.assertEqual(build.returncode, 0)
            self.assertFalse((root / "docs" / "baselines" / "capabilities.certified.v1.json").is_file())

    def test_generator_rejects_hard_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            write_lock(
                root,
                [engine_entry(root, declarations=[declaration(resource_enforcement={"wall_time_s": "hard", "cpu_time_s": "unsupported", "memory_bytes": "unsupported", "process_count": "unsupported", "artifact_bytes": "unsupported"})])],
            )
            build = run_tool("build_m2_capabilities_certified.py", root)
            self.assertNotEqual(build.returncode, 0)

    def test_verifier_rejects_hard_enforcement_and_missing_engine(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_bundle(root)
            write_lock(root, [engine_entry(root, declarations=[declaration()])])
            run_tool("build_m2_capabilities_certified.py", root)
            catalog = root / "docs" / "baselines" / "capabilities.certified.v1.json"
            payload = json.loads(catalog.read_text(encoding="utf-8"))
            payload["entries"][0]["resource_enforcement"]["wall_time_s"] = "hard"
            catalog.write_text(json.dumps(payload), encoding="utf-8")
            verify = run_tool("verify_m2_capabilities_certified.py", root)
            self.assertNotEqual(verify.returncode, 0)

            payload["entries"][0]["resource_enforcement"]["wall_time_s"] = "unsupported"
            payload["entries"][0]["engine_instance"] = "missing-engine"
            catalog.write_text(json.dumps(payload), encoding="utf-8")
            verify = run_tool("verify_m2_capabilities_certified.py", root)
            self.assertNotEqual(verify.returncode, 0)


if __name__ == "__main__":
    unittest.main()
