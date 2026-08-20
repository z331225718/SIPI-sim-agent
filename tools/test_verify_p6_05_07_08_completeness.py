"""Tests for P6-05/P6-07/P6-08 completeness gates."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p6_05_command_manifest_single_source as G05
import verify_p6_07_ai_conformance_surface as G07
import verify_p6_08_report_inspect_metadata_only as G08


class P6ManifestTests(unittest.TestCase):
    def test_p6_05_valid(self) -> None:
        result = G05.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertTrue(result["single_source"])

    def test_p6_05_project_run_row(self) -> None:
        publication = G05.load_yaml(G05.PUBLICATION)
        row = next((r for r in publication["rows"] if r.get("id") == "project-run"), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["command_id"], "project.run")
        self.assertEqual(row["acceptance_state"], "specified")

    def test_p6_05_manifest_audit(self) -> None:
        audit = G05.read_text(G05.MANIFEST_AUDIT)
        self.assertIn("sipi.command-manifest.v1", audit)


class P6AiTests(unittest.TestCase):
    def test_p6_07_valid(self) -> None:
        result = G07.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["distinctions"], 3)

    def test_p6_07_audit_tokens(self) -> None:
        audit = G07.read_text(G07.AUDIT).lower()
        for token in G07.REQUIRED_TOKENS:
            self.assertIn(token, audit)

    def test_p6_07_audit_tracked(self) -> None:
        self.assertTrue(G07.git_tracked(G07.AUDIT))


class P6ReportTests(unittest.TestCase):
    def test_p6_08_valid(self) -> None:
        result = G08.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertTrue(result["metadata_only"])

    def test_p6_08_row(self) -> None:
        publication = G08.load_yaml(G08.PUBLICATION)
        row = next((r for r in publication["rows"] if r.get("id") == "report-inspect"), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["command_id"], "report.inspect")
        self.assertEqual(row["product_surface"], "available")

    def test_p6_08_audit_tokens(self) -> None:
        audit = G08.read_text(G08.AUDIT)
        for token in ("integrity", "metadata", "hash"):
            self.assertIn(token, audit)


if __name__ == "__main__":
    unittest.main()
