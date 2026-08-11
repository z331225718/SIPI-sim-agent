"""Product-owned tests for the bounded P7-03a ZIP admission scanner."""

from __future__ import annotations

import hashlib
import importlib.util
import io
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p7_archive", ROOT / "tools" / "verify_p7_release_archive.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class ReleaseArchiveTests(unittest.TestCase):
    @staticmethod
    def policy() -> dict:
        return {
            "schema": GATE.POLICY_SCHEMA,
            "max_archive_bytes": 1024 * 1024,
            "max_entries": 2,
            "max_entry_bytes": 512 * 1024,
            "max_total_uncompressed_bytes": 512 * 1024,
            "max_compression_ratio": 100,
            "entries": [
                {"path": "sipi.exe", "role": "main_executable", "required": True, "digest_source": "composition_stage"},
                {"path": "LICENSE", "role": "mit_license", "required": True, "digest_source": "source_tree"},
            ],
        }

    @staticmethod
    def bundle(entries: list[tuple[str | zipfile.ZipInfo, bytes]]) -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries:
                archive.writestr(name, data)
        return output.getvalue()

    def scan(self, entries: list[tuple[str | zipfile.ZipInfo, bytes]]) -> list[dict]:
        executable = b"product-owned-binary"
        license_text = b"MIT product-owned license"
        data = self.bundle(entries)
        return GATE.scan_zip(
            data,
            GATE.parse_policy(self.policy()),
            hashlib.sha256(executable).hexdigest(),
            hashlib.sha256(license_text).hexdigest(),
        )

    def test_exact_two_entry_capsule_is_admitted(self) -> None:
        report = self.scan([("sipi.exe", b"product-owned-binary"), ("LICENSE", b"MIT product-owned license")])
        self.assertEqual([entry["role"] for entry in report], ["main_executable", "mit_license"])

    def test_unknown_python_or_vendor_entry_is_rejected(self) -> None:
        with self.assertRaises(GATE.ArchiveError):
            self.scan([
                ("sipi.exe", b"product-owned-binary"),
                ("LICENSE", b"MIT product-owned license"),
                ("python311.dll", b"not admitted"),
            ])

    def test_windows_path_bypass_and_case_collision_are_rejected(self) -> None:
        with self.assertRaises(GATE.ArchiveError):
            self.scan([("sipi.exe", b"product-owned-binary"), ("C:\\LICENSE", b"MIT product-owned license")])
        with self.assertRaises(GATE.ArchiveError):
            self.scan([
                ("sipi.exe", b"product-owned-binary"),
                ("LICENSE", b"MIT product-owned license"),
                ("license", b"duplicate"),
            ])

    def test_link_and_identity_drift_are_rejected(self) -> None:
        link = zipfile.ZipInfo("LICENSE")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(GATE.ArchiveError):
            self.scan([("sipi.exe", b"product-owned-binary"), (link, b"ignored")])
        with self.assertRaises(GATE.ArchiveError):
            self.scan([("sipi.exe", b"drifted"), ("LICENSE", b"MIT product-owned license")])

    def test_policy_is_closed_and_external_reports_are_exclusive(self) -> None:
        invalid = self.policy()
        invalid["entries"].append({"path": "NOTICE", "role": "notice", "required": True, "digest_source": "other"})
        with self.assertRaises(GATE.ArchiveError):
            GATE.parse_policy(invalid)
        with self.assertRaises(GATE.ArchiveError):
            GATE.require_external(ROOT / "archive-report.json", ROOT)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "report.json"
            destination.write_text("existing", encoding="utf-8")
            with self.assertRaises(GATE.ArchiveError):
                GATE.write_new_external_report(destination, ROOT, {"schema": GATE.SCHEMA})

    def test_composition_binding_rejects_unassessed_static_pe_drift(self) -> None:
        digest = "a" * 64
        report = {
            "schema": GATE.COMPOSITION_SCHEMA,
            "evidence_status": "incomplete",
            "promotion_status": "blocked",
            "source_build": {
                "commit": "b" * 40,
                "tree": "c" * 40,
                "target": "x86_64-pc-windows-msvc",
                "cargo_lock_sha256": digest,
                "toolchain_sha256": digest,
                "twin_report_sha256": digest,
                "staged_binary_sha256": digest,
                "staged_binary_bytes": 7,
            },
            "dependency_inventory": [],
            "notice_license_gaps": [],
            "static_pe": {
                "layout_report_sha256": digest,
                "machine": "amd64",
                "normal_imports": ["kernel32.dll"],
                "delay_imports": "not_present_in_layout_observation",
                "dynamic_load_closure": "not_assessed",
                "runtime_dependency_closure": "not_assessed",
            },
            "limitations": [],
        }
        self.assertEqual(GATE.parse_composition(report)["commit"], "b" * 40)
        report["static_pe"]["dynamic_load_closure"] = "complete"
        with self.assertRaises(GATE.ArchiveError):
            GATE.parse_composition(report)


if __name__ == "__main__":
    unittest.main()
