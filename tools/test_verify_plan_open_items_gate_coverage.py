"""Tests for the PLAN open-items gate coverage verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_plan_open_items_gate_coverage as GATE


class CoverageTests(unittest.TestCase):
    def test_all_open_items_have_gates(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["items"], 46)
        self.assertEqual(result["gates"], 359)

    def test_every_open_item_mapped(self) -> None:
        expected = set(GATE.OPEN_ITEM_GATES)
        self.assertGreaterEqual(len(expected), 46)
        self.assertIn("P1-04B", expected)
        self.assertIn("P7-09", expected)
        self.assertIn("P4A-01", expected)
        self.assertIn("P6-10", expected)
        self.assertEqual(set(GATE.OPEN_ITEM_GATES), expected)

    def test_each_item_has_nonempty_gate_list(self) -> None:
        for item, gates in GATE.OPEN_ITEM_GATES.items():
            self.assertTrue(isinstance(gates, list) and gates, item)

    def test_all_gates_exist_on_disk(self) -> None:
        for item, gates in GATE.OPEN_ITEM_GATES.items():
            for gate in gates:
                self.assertTrue((ROOT / gate).is_file(), f"{item}: {gate} missing")


if __name__ == "__main__":
    unittest.main()