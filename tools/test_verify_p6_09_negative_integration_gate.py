"""Tests for the P6-09 negative integration gate verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p6_09_negative_integration_gate as GATE


class NegativeGateTests(unittest.TestCase):
    def test_current_gate_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["fail_closed_surfaces"], 6)

    def test_audit_covers_fail_closed_surfaces(self) -> None:
        audit = GATE.read_text(GATE.AUDIT).lower()
        for token in GATE.AUDIT_TOKENS:
            self.assertIn(token, audit, token)

    def test_rust_test_present(self) -> None:
        rust = GATE.read_text(GATE.RUST_TEST).lower()
        for token in ("record", "publish", "cancel"):
            self.assertIn(token, rust, token)

    def test_files_tracked(self) -> None:
        self.assertTrue(GATE.git_tracked(GATE.AUDIT))
        self.assertTrue(GATE.git_tracked(GATE.RUST_TEST))


if __name__ == "__main__":
    unittest.main()
