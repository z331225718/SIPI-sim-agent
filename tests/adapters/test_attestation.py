from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import AttestationError, execute_backend, verify_engine_bundle, verify_wheel_bundle
from sipi_contracts import parse_backend_execution_request


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wheel_files() -> dict[str, bytes]:
    return {
        "fixture_pkg/__init__.py": b"VALUE = 1\n",
        "fixture_pkg-0.1.0.dist-info/METADATA": b"Metadata-Version: 2.1\nName: fixture\nVersion: 0.1.0\n",
        "fixture_pkg-0.1.0.dist-info/entry_points.txt": b"[console_scripts]\nfixture = fixture_pkg:main\n",
    }


def build_wheel(root: Path, *, files: dict[str, bytes] | None = None) -> Path:
    wheel = root / "bundles" / "fixture-0.1.0-py3-none-any.whl"
    wheel.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in (files or wheel_files()).items():
            archive.writestr(name, data)
    return wheel


def engine_entry(root: Path) -> dict:
    wheel = root / "bundles" / "fixture-0.1.0-py3-none-any.whl"
    if not wheel.is_file():
        build_wheel(root)
    files = wheel_files()
    manifest_files = [
        {
            "relative_path": name,
            "role": "entrypoint" if name == "fixture_pkg/__init__.py" else ("library" if name.endswith(".py") else "data"),
            "sha256": sha256_bytes(data),
            "byte_length": len(data),
        }
        for name, data in files.items()
    ]
    return {
        "instance_id": "fixture-wheel",
        "engine_family": "fixture",
        "version": "0.1.0",
        "source_commit": "0" * 40,
        "bundle": {"kind": "local_path", "path": "bundles/fixture-0.1.0-py3-none-any.whl", "sha256": sha256(wheel)},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": "2" * 64,
        "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "3" * 64},
        "bundle_manifest": {"entrypoint": "fixture_pkg/__init__.py", "files": manifest_files},
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
        "engine_instance_id": "fixture-wheel",
        "bundle_hash": "sha256:bundle",
        "operation": "circuit.solve.v1",
        "payload_schema": "fixture.schema.v1",
        "payload": {},
        "bound_inputs": {},
        "resource_limits": {"enforcement": "monitor", "wall_time_s": None, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None},
        "artifact_policy": {},
        "randomness": {},
        "selection_hash": "sha256:selection",
    }
    value.update(changes)
    return parse_backend_execution_request(value)


class AttestationTests(unittest.TestCase):
    def test_wheel_attestation_verifies_all_manifest_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attestation = verify_wheel_bundle(engine_entry(root), root)
            self.assertEqual(attestation.entrypoint, "fixture_pkg/__init__.py")
            self.assertEqual(set(attestation.verified_files), set(wheel_files()))
            self.assertEqual(attestation.license_status, "authorized_public")
            self.assertEqual(attestation.capabilities_sha256, "1" * 64)
            self.assertEqual(attestation.to_wire()["instance_id"], "fixture-wheel")

    def test_verify_engine_bundle_accepts_attested_wheel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = verify_engine_bundle(engine_entry(root), root)
            self.assertEqual(path.suffix, ".whl")

    def test_tampered_inner_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = dict(wheel_files())
            files["fixture_pkg/__init__.py"] = b"VALUE = 2\n"
            build_wheel(root, files=files)
            entry = engine_entry(root)
            with self.assertRaises(AttestationError) as caught:
                verify_wheel_bundle(entry, root)
            self.assertIn("hash mismatch", str(caught.exception))

    def test_missing_manifest_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = engine_entry(root)
            entry["bundle_manifest"]["files"].append(
                {"relative_path": "fixture_pkg/missing.py", "role": "library", "sha256": "f" * 64, "byte_length": 1}
            )
            with self.assertRaises(AttestationError) as caught:
                verify_wheel_bundle(entry, root)
            self.assertIn("missing inside wheel", str(caught.exception))

    def test_wheel_without_metadata_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = dict(wheel_files())
            del files["fixture_pkg-0.1.0.dist-info/METADATA"]
            build_wheel(root, files=files)
            entry = engine_entry(root)
            with self.assertRaises(AttestationError) as caught:
                verify_wheel_bundle(entry, root)
            self.assertIn("METADATA", str(caught.exception))

    def test_bundle_sha_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = engine_entry(root)
            entry["bundle"]["sha256"] = "f" * 64
            with self.assertRaises(AttestationError) as caught:
                verify_wheel_bundle(entry, root)
            self.assertIn("sha256 mismatch", str(caught.exception))

    def test_https_bundle_is_rejected_at_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = engine_entry(root)
            entry["bundle"] = {"kind": "https_url", "url": "https://example.invalid/fixture.whl", "sha256": "f" * 64}
            with self.assertRaises(AttestationError) as caught:
                verify_wheel_bundle(entry, root)
            self.assertIn("https_url", str(caught.exception))

    def test_path_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = engine_entry(root)
            entry["bundle"]["path"] = "../escape.whl"
            with self.assertRaises(AttestationError) as caught:
                verify_wheel_bundle(entry, root)
            self.assertIn("escapes", str(caught.exception))

    def test_unsafe_archive_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = dict(wheel_files())
            files["../evil.py"] = b"evil"
            build_wheel(root, files=files)
            entry = engine_entry(root)
            with self.assertRaises(AttestationError) as caught:
                verify_wheel_bundle(entry, root)
            self.assertIn("unsafe archive entry", str(caught.exception))

    def test_single_file_bundle_attestation_regression(self) -> None:
        fake_engine = ROOT / "tests" / "adapters" / "fixtures" / "fake_engine.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "bundles" / "fake_engine.py"
            target.parent.mkdir(parents=True)
            target.write_bytes(fake_engine.read_bytes())
            digest = sha256(target)
            entry = {
                "instance_id": "single-file",
                "engine_family": "fixture",
                "version": "1",
                "source_commit": "0" * 40,
                "bundle": {"kind": "local_path", "path": "bundles/fake_engine.py", "sha256": digest},
                "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
                "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
                "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
                "dependency_lock_sha256": "2" * 64,
                "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "3" * 64},
                "bundle_manifest": {"entrypoint": "fake_engine.py", "files": [{"relative_path": "fake_engine.py", "role": "entrypoint", "sha256": digest, "byte_length": target.stat().st_size}]},
                "extensions": {},
            }
            path = verify_engine_bundle(entry, root)
            self.assertEqual(path.suffix, ".py")

    def test_execute_backend_requires_console_script_without_running_engine(self) -> None:
        class NeverBuilder:
            def build(self, request, bundle_path, workdir):
                raise AssertionError("engine must not run for wheel bundles yet")

            def build_outcome(self, request, engine_entry, workdir, process):
                raise AssertionError("engine must not run for wheel bundles yet")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = execute_backend(backend_request(), engine_entry(root), root, builder=NeverBuilder())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "UnsupportedCapability")
        self.assertIn("console-script", result["error"]["message"])


if __name__ == "__main__":
    unittest.main()
