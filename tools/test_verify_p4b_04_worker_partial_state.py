"""Tests for the P4B-04 worker partial-state gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_04_worker_partial_state as GATE


class WorkerStateTests(unittest.TestCase):
    def test_current_partial_state_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["delivered"], 3)
        self.assertEqual(result["not_claimed"], 4)

    def test_delivered_surfaces_present(self) -> None:
        audit = GATE.read_text(GATE.AUDIT)
        for token in GATE.DELIVERED_TOKENS:
            self.assertIn(token, audit)

    def test_disclaimer_present(self) -> None:
        audit = GATE.read_text(GATE.AUDIT).lower()
        self.assertIn("this is not", audit)

    def test_not_claimed_tokens_listed(self) -> None:
        self.assertEqual(len(GATE.NOT_CLAIMED_TOKENS), 4)
        self.assertIn("sandbox", GATE.NOT_CLAIMED_TOKENS)
        self.assertIn("dependency closure", GATE.NOT_CLAIMED_TOKENS)

    def test_audit_tracked(self) -> None:
        self.assertTrue(GATE.git_tracked(GATE.AUDIT))


if __name__ == "__main__":
    unittest.main()
