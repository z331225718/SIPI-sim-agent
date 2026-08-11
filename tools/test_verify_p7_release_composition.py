"""Product-owned unit tests for the P7-02a composition preflight."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p7_composition", ROOT / "tools" / "verify_p7_release_composition.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def digest(value: str) -> str:
    return value * 64


def oid(value: str) -> str:
    return value * 40


class ReleaseCompositionTests(unittest.TestCase):
    def twin(self) -> dict:
        build = {"binary_bytes": 7, "binary_sha256": digest("a"), "cargo_version_sha256": digest("b"), "rustc_version_sha256": digest("c")}
        return {"schema": GATE.TWIN_SCHEMA, "status": "identical", "commit": oid("d"), "tree": oid("e"), "lock_sha256": digest("f"), "toolchain_sha256": digest("0"), "rustflags_sha256": digest("1"), "target": "x86_64-pc-windows-msvc", "build_a": build, "build_b": dict(build), "comparison": {"size_match": True, "digest_match": True}, "limitations": []}

    def layout(self) -> dict:
        return {"schema": GATE.LAYOUT_SCHEMA, "status": "layout_conformant", "policySha256": digest("2"), "inventorySha256": digest("3"), "executableSha256": digest("a"), "executableBytes": 7, "machine": "amd64", "normalImports": ["kernel32.dll"], "delayImportDirectoryPresent": False, "smoke": [], "limitations": []}

    def test_twin_requires_exact_identity(self) -> None:
        document = self.twin()
        document["build_b"]["binary_sha256"] = digest("9")
        with self.assertRaises(GATE.PreflightError):
            GATE.parse_twin_report(document)

    def test_layout_rejects_delay_import_observation(self) -> None:
        document = self.layout()
        document["delayImportDirectoryPresent"] = True
        with self.assertRaises(GATE.PreflightError):
            GATE.parse_layout_report(document)

    def test_locked_inventory_records_unclassified_and_pending_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock = ('[[package]]\nname = "alpha"\nversion = "1.0.0"\nsource = "registry+https://example.invalid"\nchecksum = "' + digest("a") + '"\n\n[[package]]\nname = "beta"\nversion = "2.0.0"\n').encode("utf-8")
            inventory, gaps = GATE.locked_inventory(lock, {"alpha": {"id": "rust-alpha", "declared_license": "pending-observation", "review_status": "pending", "notice_status": "pending"}})
        self.assertEqual(len(inventory), 2)
        self.assertIn("pending_manifest_review:rust-alpha", gaps)
        self.assertIn("unclassified_locked_package:beta@2.0.0", gaps)

    def test_report_destination_is_external_and_exclusive(self) -> None:
        with self.assertRaises(GATE.PreflightError):
            GATE.require_external(ROOT / "report.json", ROOT)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "report.json"
            destination.write_text("existing", encoding="utf-8")
            with self.assertRaises(GATE.PreflightError):
                GATE.write_new_external_report(destination, ROOT, {"schema": GATE.SCHEMA})


if __name__ == "__main__":
    unittest.main()
