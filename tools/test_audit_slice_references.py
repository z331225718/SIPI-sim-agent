"""Tests for the session slice reference audit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import audit_slice_references as GATE


class SliceAuditTests(unittest.TestCase):
    def test_all_session_slices_are_consistent(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["slices"], 9)
        self.assertGreater(result["files_checked"], 0)

    def test_every_slice_has_verifier_test_and_audit(self) -> None:
        for slice_ in GATE.SLICES:
            for kind in ("verifier", "test", "audit"):
                self.assertTrue(slice_.get(kind), f"{slice_['id']} missing {kind}")

    def test_plan_contains_every_marker(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        for slice_ in GATE.SLICES:
            self.assertIn(slice_["plan_marker"], plan_text, slice_["id"])

    def test_rejects_missing_file(self) -> None:
        with mock.patch.object(GATE, "SLICES", [dict(GATE.SLICES[0], audit="docs/baselines/audits/missing-audit.md")]):
            with self.assertRaises(GATE.SliceAuditError):
                GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
