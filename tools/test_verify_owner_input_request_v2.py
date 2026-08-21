"""Tests for the current external-only owner-input request."""

from __future__ import annotations

import copy
import unittest

from tools import verify_owner_decision_reconciliation_v2 as GATE


class CurrentOwnerInputRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = GATE._load(GATE.CURRENT_REQUEST)
        self.ledger = GATE._load(GATE.LEDGER)

    def test_current_request_has_exactly_ten_external_blockers(self) -> None:
        result = GATE.validate_current_request(self.request, ledger=self.ledger)
        self.assertTrue(result["valid"])
        self.assertEqual({entry["id"] for entry in self.request["entries"]}, set(GATE.EXTERNAL_IDS))
        self.assertEqual(len(self.request["entries"]), 10)
        self.assertEqual(result["owner_decision"], 0)

    def test_new_external_rows_preserve_delegated_discretion_without_profile_selection(self) -> None:
        points = {entry["id"]: entry["decision_point"] for entry in self.request["entries"]}
        for item_id in ("P3B-02", "P3C-03", "P4A-03", "P4B-02"):
            self.assertIn("owner", points[item_id])
            self.assertIn("no mechanically unique", points[item_id])

    def test_rejects_owner_decision_entry(self) -> None:
        request = copy.deepcopy(self.request)
        request["entries"][0]["kind"] = "owner_decision"
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate_current_request(request, ledger=self.ledger)

    def test_rejects_gate_drift(self) -> None:
        request = copy.deepcopy(self.request)
        request["entries"][0]["gate"] = ["tools/verify_owner_decision_reconciliation_v2.py"]
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate_current_request(request, ledger=self.ledger)

    def test_rejects_synchronized_request_and_ledger_gate_substitution(self) -> None:
        request = copy.deepcopy(self.request)
        ledger = copy.deepcopy(self.ledger)
        replacement = ["tools/verify_owner_decision_reconciliation_v2.py"]
        request["entries"][0]["gate"] = replacement
        next(item for item in ledger["items"] if item["id"] == "P1-04B")["gate"] = replacement
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate_current_request(request, ledger=ledger)

    def test_rejects_ledger_total_open_drift(self) -> None:
        ledger = copy.deepcopy(self.ledger)
        ledger["total_open"] = 1
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate_current_request(self.request, ledger=ledger)

    def test_rejects_external_decision_point_substitution(self) -> None:
        request = copy.deepcopy(self.request)
        request["entries"][0]["decision_point"] = "trusted directory is enough"
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate_current_request(request, ledger=self.ledger)

    def test_rejects_nonclaim_removal_or_substitution(self) -> None:
        for replacement in (["bogus"], self.request["non_claims"][:-1]):
            request = copy.deepcopy(self.request)
            request["non_claims"] = replacement
            with self.subTest(replacement=replacement):
                with self.assertRaises(GATE.ReconciliationError):
                    GATE.validate_current_request(request, ledger=self.ledger)


if __name__ == "__main__":
    unittest.main()
