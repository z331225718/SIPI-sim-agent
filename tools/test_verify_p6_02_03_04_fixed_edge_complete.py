"""Tests for the P6-02/03/04 fixed edge completeness gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p6_02_03_04_fixed_edge_complete as GATE


class FixedEdgeTests(unittest.TestCase):
    def test_current_edge_is_complete(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["items"], 3)

    def test_spec_covers_direct_launch_stimulus(self) -> None:
        spec = GATE.read_text(GATE.SPEC)
        for token in ("DirectLaunch", "voltage_in", "causal-FIR"):
            self.assertIn(token, spec)

    def test_identity_record_has_sha256(self) -> None:
        record = GATE.read_text(GATE.RECORD_AUDIT).lower()
        self.assertTrue("sha-256" in record or "sha256" in record)

    def test_attempt_audit_covers_cancel_and_artifact(self) -> None:
        attempt = GATE.read_text(GATE.ATTEMPT_AUDIT).lower()
        for token in ("cancel", "artifact"):
            self.assertIn(token, attempt)

    def test_project_run_row_bound(self) -> None:
        publication = GATE.load_yaml(GATE.PUBLICATION)
        project = next((r for r in publication["rows"] if r.get("id") == "project-run"), None)
        self.assertIsNotNone(project)
        self.assertEqual(project["acceptance_state"], "specified")

    def test_files_present(self) -> None:
        for relative in (GATE.SPEC, GATE.EDGE_AUDIT, GATE.RECORD_AUDIT, GATE.ATTEMPT_AUDIT):
            self.assertTrue((ROOT / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main()
