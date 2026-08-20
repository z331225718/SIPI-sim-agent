"""Tests for the P4B-01 AMI candidate audit completeness gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_01_ami_candidate_audit_complete as GATE


class AuditCompleteTests(unittest.TestCase):
    def test_current_audit_is_complete(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["elements"], 4)

    def test_preflight_covers_four_elements(self) -> None:
        text = GATE.read_text(GATE.PREFLIGHT)
        for token in ("source_map", "dependency", "exposure", "promotion_eligible"):
            self.assertIn(token, text)

    def test_audit_covers_four_elements(self) -> None:
        text = GATE.read_text(GATE.AUDIT)
        for token in ("quarantine", "dependency", "exposure", "promotion_eligible"):
            self.assertIn(token, text)

    def test_audit_keeps_candidate_unpromoted(self) -> None:
        text = GATE.read_text(GATE.AUDIT)
        self.assertIn("promotion_eligible: false", text)

    def test_files_tracked(self) -> None:
        self.assertTrue(GATE.git_tracked(GATE.PREFLIGHT))
        self.assertTrue(GATE.git_tracked(GATE.AUDIT))


if __name__ == "__main__":
    unittest.main()
