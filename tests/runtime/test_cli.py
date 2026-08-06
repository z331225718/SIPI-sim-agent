from __future__ import annotations

import contextlib
import hashlib
import io
import json
import platform
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "sipi-cli" / "src"))

from sipi_cli.__main__ import capabilities, doctor, main


def engine_entry(instance_id: str = "test.engine", *, bundle: dict | None = None, license_status: str = "authorized_public") -> dict:
    digest = "a" * 64
    return {
        "instance_id": instance_id,
        "engine_family": "test",
        "version": "1",
        "source_commit": "0" * 40,
        "bundle": bundle or {"kind": "local_path", "path": "marker.exe", "sha256": digest},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
        "runtime": {"kind": "native", "os": "windows", "architecture": "x86_64", "python_abi": None, "rust_target": "x86_64-pc-windows-msvc"},
        "dependency_lock_sha256": "2" * 64,
        "license_provenance": {"distribution_status": license_status, "manifest_sha256": "3" * 64},
        "bundle_manifest": {"entrypoint": "marker.exe", "files": [{"relative_path": "marker.exe", "role": "entrypoint", "sha256": digest, "byte_length": 9}]},
        "extensions": {},
    }


def write_lock(root: Path, engines: list[dict]) -> None:
    payload = {"schema": "sipi.engine-lock.v1", "engines": engines, "operation_defaults": {}, "extensions": {}}
    (root / "engine.lock").write_text(json.dumps(payload), encoding="utf-8")


def local_lock(root: Path, *, license_status: str = "authorized_public") -> tuple[Path, str, dict]:
    marker = root / "marker.exe"
    marker.write_text("do not run", encoding="utf-8")
    digest = hashlib.sha256(marker.read_bytes()).hexdigest()
    entry = engine_entry(bundle={"kind": "local_path", "path": "marker.exe", "sha256": digest}, license_status=license_status)
    entry["bundle_manifest"]["files"][0]["sha256"] = digest
    entry["bundle_manifest"]["files"][0]["byte_length"] = marker.stat().st_size
    write_lock(root, [entry])
    return marker, digest, entry


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main(list(args))
        return status, stdout.getvalue()

    def engine_lock_check(self, report: dict) -> dict:
        return next(item for item in report["checks"] if item["id"] == "engine_lock")

    def test_capabilities_never_advertises_baseline(self) -> None:
        status, output = self.run_cli("capabilities", "--root", str(ROOT), "--format", "json")
        payload = json.loads(output)
        self.assertEqual(status, 0)
        self.assertEqual(payload["source"]["status"], "absent")
        self.assertEqual(payload["advertised"], [])

    def test_doctor_json_is_one_document_and_is_read_only(self) -> None:
        status, output = self.run_cli("doctor", "--root", str(ROOT), "--format", "json")
        payload = json.loads(output)
        self.assertEqual(status, 1)
        self.assertEqual(payload["command"], "doctor")
        self.assertEqual([check["id"] for check in payload["checks"]], ["toolchains", "engine_lock", "schemas", "fixtures"])

    def test_invalid_engine_lock_and_missing_files_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "engine.lock").write_text("not json", encoding="utf-8")
            report = doctor(root)
        checks = {item["id"]: item for item in report["checks"]}
        self.assertEqual(checks["engine_lock"]["status"], "invalid")
        self.assertEqual(checks["schemas"]["status"], "ok")

    def test_https_catalog_does_not_enable_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "docs" / "baselines"
            catalog.mkdir(parents=True)
            (catalog / "capabilities.certified.v1.json").write_text('{"advertised":["fiction"]}', encoding="utf-8")
            report = capabilities(root, "fiction")
        self.assertEqual(report["source"]["status"], "invalid")
        self.assertEqual(report["advertised"], [])

    def test_engine_lock_is_nonexecuting_and_reports_unverified_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker, digest, entry = local_lock(root)
            report = doctor(root)
            check = self.engine_lock_check(report)
            self.assertEqual(check["status"], "ok")
            self.assertEqual(marker.read_text(encoding="utf-8"), "do not run")
            self.assertEqual(check["details"]["engines"][0]["actual_sha256"], digest)

            entry["bundle"] = {"kind": "https_url", "url": "https://example.invalid/bundle", "sha256": digest}
            write_lock(root, [entry])
            remote = doctor(root)
            remote_check = self.engine_lock_check(remote)
            self.assertEqual(remote_check["status"], "not_checked")

    def test_empty_engine_lock_is_reported_and_unhealthy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_lock(root, [])
            status, output = self.run_cli("doctor", "--root", str(root), "--format", "json")
        payload = json.loads(output)
        self.assertEqual(status, 1)
        self.assertEqual(self.engine_lock_check(payload)["status"], "empty")
        self.assertEqual(payload["overall"], "issues")

    def test_https_only_engine_lock_is_unverified_and_unhealthy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            digest = hashlib.sha256(b"x").hexdigest()
            entry = engine_entry(bundle={"kind": "https_url", "url": "https://example.invalid/bundle", "sha256": digest})
            write_lock(root, [entry])
            status, output = self.run_cli("doctor", "--root", str(root), "--format", "json")
        payload = json.loads(output)
        self.assertEqual(status, 1)
        self.assertEqual(self.engine_lock_check(payload)["status"], "not_checked")
        self.assertEqual(payload["overall"], "issues")

    def test_bundle_sha_mismatch_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker, digest, _ = local_lock(root)
            write_lock(root, [engine_entry(bundle={"kind": "local_path", "path": "marker.exe", "sha256": "f" * 64})])
            report = doctor(root)
        check = self.engine_lock_check(report)
        self.assertEqual(check["status"], "mismatch")
        engine = check["details"]["engines"][0]
        self.assertEqual(engine["actual_sha256"], digest)

    def test_blocked_license_is_propagated_to_top_level(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local_lock(root, license_status="blocked_unknown")
            report = doctor(root)
        check = self.engine_lock_check(report)
        self.assertEqual(check["status"], "blocked")
        self.assertEqual(check["details"]["engines"][0]["license_status"], "blocked_unknown")

    def test_authority_path_escape_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schemas = root / "schemas"
            schemas.mkdir()
            authority = {"schemas": [{"source_of_truth": {"kind": "local_json_schema", "path": "../escape.json"}}]}
            (schemas / "authority.v1.yaml").write_text(json.dumps(authority), encoding="utf-8")
            report = doctor(root)
        check = next(item for item in report["checks"] if item["id"] == "schemas")
        self.assertEqual(check["status"], "missing")
        self.assertIn("../escape.json", check["details"]["missing"])

    def test_invalid_authority_document_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schemas = root / "schemas"
            schemas.mkdir()
            (schemas / "authority.v1.yaml").write_text("not json", encoding="utf-8")
            report = doctor(root)
        check = next(item for item in report["checks"] if item["id"] == "schemas")
        self.assertEqual(check["status"], "invalid")

    def test_fixture_manifest_schema_and_availability_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = root / "fixtures"
            fixtures.mkdir()
            (fixtures / "manifest.v1.json").write_text(json.dumps({"schema": "wrong", "assets": []}), encoding="utf-8")
            report = doctor(root)
        check = next(item for item in report["checks"] if item["id"] == "fixtures")
        self.assertEqual(check["status"], "invalid")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = root / "fixtures"
            fixtures.mkdir()
            (fixtures / "manifest.v1.json").write_text(json.dumps({"schema": "sipi.fixture-manifest.v1", "assets": [{"availability": "mystery"}]}), encoding="utf-8")
            report = doctor(root)
        check = next(item for item in report["checks"] if item["id"] == "fixtures")
        self.assertEqual(check["status"], "partial")
        self.assertEqual(check["details"]["unknown_availability"], ["mystery"])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = root / "fixtures"
            fixtures.mkdir()
            (fixtures / "manifest.v1.json").write_text(json.dumps({"schema": "sipi.fixture-manifest.v1", "assets": [{"availability": "present"}], "open_coverage": [{"location": {}}]}), encoding="utf-8")
            report = doctor(root)
        check = next(item for item in report["checks"] if item["id"] == "fixtures")
        self.assertEqual(check["status"], "partial")
        self.assertEqual(check["details"]["open_coverage"], 1)

    def test_certified_catalog_present_but_unrecognized_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "docs" / "baselines"
            catalog.mkdir(parents=True)
            (catalog / "capabilities.certified.v1.json").write_text('{"advertised":["fiction"]}', encoding="utf-8")
            status, output = self.run_cli("capabilities", "--root", str(root), "--format", "json")
        payload = json.loads(output)
        self.assertEqual(status, 1)
        self.assertEqual(payload["source"]["status"], "invalid")
        self.assertEqual(payload["advertised"], [])

    def test_toolchains_reports_declared_unchecked_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os_name = {"win32": "windows", "darwin": "macos"}.get(sys.platform, sys.platform)
            machine = platform.machine().lower()
            architecture = "x86_64" if machine in {"amd64", "x86_64"} else machine
            lock = (
                f'platform = "{os_name}-{architecture}"\n'
                f'[python]\nselected_version = "{platform.python_version()}"\n'
                '[rust]\ntoolchain = "1.97.0-x86_64-pc-windows-msvc"\n'
            )
            (root / "toolchains.lock").write_text(lock, encoding="utf-8")
            report = doctor(root)
        check = next(item for item in report["checks"] if item["id"] == "toolchains")
        self.assertEqual(check["status"], "partial")
        tools = {item["name"]: item for item in check["details"]["tools"]}
        self.assertEqual(tools["python"]["status"], "ok")
        self.assertEqual(tools["rust"]["status"], "not_checked")
        self.assertFalse(tools["rust"]["checked"])

    def test_missing_toolchain_lock_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = doctor(Path(directory))
        check = next(item for item in report["checks"] if item["id"] == "toolchains")
        self.assertEqual(check["status"], "missing")


if __name__ == "__main__":
    unittest.main()
