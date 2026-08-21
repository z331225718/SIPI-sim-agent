"""Tests for the PLAN open-items gate coverage verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_plan_open_items_gate_coverage as GATE


class CoverageTests(unittest.TestCase):
    def test_current_plan_and_ledger_have_tracked_coverage(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["items"], 24)
        self.assertGreater(result["gates"], 0)
        self.assertEqual(result["coverage_scope"], "tracked_gate_inventory_only")
        self.assertEqual(result["executed_gates"], 0)
        self.assertEqual(result["execution_claim"], "not_evaluated_by_this_verifier")

    def test_mapping_is_derived_from_ledger(self) -> None:
        expected = GATE._ledger_gate_map(GATE._read_ledger(ROOT))
        self.assertEqual(GATE.OPEN_ITEM_GATES, expected)

    def test_plan_ledger_mismatch_is_rejected(self) -> None:
        with mock.patch.object(GATE, "_plan_open_items", return_value=["P9-99"]):
            with self.assertRaisesRegex(GATE.CoverageError, "plan_ledger_item_mismatch"):
                GATE.validate(ROOT)

    def test_plan_integrity_rejects_concatenated_checklists(self) -> None:
        with mock.patch.object(
            Path,
            "read_text",
            return_value="- [ ] **P9-99** first - [x] **P9-98** second\n",
        ):
            with self.assertRaisesRegex(GATE.CoverageError, "plan_checklists_concatenated"):
                GATE._plan_open_items(ROOT)

    def test_untracked_gate_is_rejected(self) -> None:
        ledger = {
            "schema": "sipi.plan-remaining-items.ledger.v1",
            "total_open": 1,
            "items": [{"id": "P9-99", "gate": ["tools/verify_untracked.py"]}],
        }
        with mock.patch.object(GATE, "_read_ledger", return_value=ledger), \
             mock.patch.object(GATE, "_plan_open_items", return_value=["P9-99"]), \
             mock.patch.object(GATE, "_tracked_paths", return_value=set()):
            with self.assertRaisesRegex(GATE.CoverageError, "gate_untracked"):
                GATE.validate(ROOT)

    def test_duplicate_gate_is_rejected(self) -> None:
        ledger = {
            "schema": "sipi.plan-remaining-items.ledger.v1",
            "total_open": 1,
            "items": [{"id": "P9-99", "gate": ["tools/verify_x.py", "tools/verify_x.py"]}],
        }
        with mock.patch.object(GATE, "_read_ledger", return_value=ledger), \
             mock.patch.object(GATE, "_plan_open_items", return_value=["P9-99"]), \
             mock.patch.object(GATE, "_tracked_paths", return_value={"tools/verify_x.py"}):
            with self.assertRaisesRegex(GATE.CoverageError, "item_gate_duplicate"):
                GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
