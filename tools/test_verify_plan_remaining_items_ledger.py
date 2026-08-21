"""Tests for the PLAN remaining-items ledger verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_plan_remaining_items_ledger as GATE


class LedgerTests(unittest.TestCase):
    def test_ledger_matches_plan(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["items"], 24)

    def test_ledger_items_equal_plan_open_items(self) -> None:
        ledger = GATE.load_yaml(GATE.LEDGER)
        ledger_ids = {entry["id"] for entry in ledger["items"]}
        plan_ids = GATE.plan_open_items(ROOT)
        self.assertEqual(ledger_ids, plan_ids)

    def test_all_blocker_classes_valid(self) -> None:
        ledger = GATE.load_yaml(GATE.LEDGER)
        for entry in ledger["items"]:
            self.assertIn(entry["blocker"], GATE.BLOCKER_CLASSES, entry["id"])

    def test_every_item_has_existing_gate(self) -> None:
        ledger = GATE.load_yaml(GATE.LEDGER)
        for entry in ledger["items"]:
            for gate in entry["gate"]:
                self.assertTrue((ROOT / gate).is_file(), f"{entry['id']}: {gate}")

    def test_current_classes_are_allowed_and_owner_decision_is_absent(self) -> None:
        ledger = GATE.load_yaml(GATE.LEDGER)
        classes = {entry["blocker"] for entry in ledger["items"]}
        self.assertTrue(classes <= GATE.BLOCKER_CLASSES)
        self.assertNotIn("owner_decision", classes)


if __name__ == "__main__":
    unittest.main()
