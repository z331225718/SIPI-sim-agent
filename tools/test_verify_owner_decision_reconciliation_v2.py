"""Mutation tests for the current owner-decision reconciliation."""

from __future__ import annotations

import copy
import unittest

from tools import verify_owner_decision_reconciliation_v2 as GATE


class OwnerDecisionReconciliationV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = GATE._load(GATE.RECONCILIATION)
        self.request = GATE._load(GATE.CURRENT_REQUEST)
        self.ledger = GATE._load(GATE.LEDGER)
        self.plan = GATE.PLAN.read_text(encoding="utf-8")

    def test_current_state_is_valid(self) -> None:
        result = GATE.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["reconciled_owner_decisions"], 5)
        self.assertEqual(result["current_external_asset_oracle_blockers"], 7)

    def test_rejects_resolved_item_in_current_request(self) -> None:
        request = copy.deepcopy(self.request)
        request["entries"].append({
            "id": "P3B-02",
            "kind": "owner_decision",
            "blocker": "owner_decision",
            "decision_point": "stale",
            "gate": ["tools/verify_owner_decision_reconciliation_v2.py"],
        })
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate_current_request(request, ledger=self.ledger)

    def test_rejects_decision_tampering(self) -> None:
        for item_id in GATE.OWNER_IDS:
            document = copy.deepcopy(self.document)
            decision = next(item for item in document["decisions"] if item["id"] == item_id)
            decision["answer"] = "B"
            with self.subTest(item_id=item_id):
                with self.assertRaises(GATE.ReconciliationError):
                    GATE.validate(document, current_request=self.request, ledger=self.ledger, plan_text=self.plan)

    def test_rejects_p4a_behavior_promotion(self) -> None:
        document = copy.deepcopy(self.document)
        decision = next(item for item in document["decisions"] if item["id"] == "P4A-01")
        decision["recommendation"]["behavior_selection"] = "selected_from_inventory"
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate(document, current_request=self.request, ledger=self.ledger, plan_text=self.plan)

    def test_rejects_waveform_only_generalization(self) -> None:
        document = copy.deepcopy(self.document)
        decision = next(item for item in document["decisions"] if item["id"] == "P3C-01")
        decision["recommendation"]["receiver"] = "arbitrary_closed_eye_fallback"
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate(document, current_request=self.request, ledger=self.ledger, plan_text=self.plan)

    def test_rejects_cdr_04b_clock_source_conflict(self) -> None:
        document = copy.deepcopy(self.document)
        decision = next(item for item in document["decisions"] if item["id"] == "P3B-04")
        decision["recommendation"]["cdr_04b_core"] = "public_clock_source"
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate(document, current_request=self.request, ledger=self.ledger, plan_text=self.plan)

    def test_rejects_ledger_owner_blocker_or_false_promotion(self) -> None:
        ledger = copy.deepcopy(self.ledger)
        next(item for item in ledger["items"] if item["id"] == "P3B-02")["blocker"] = "owner_decision"
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate(self.document, current_request=self.request, ledger=ledger, plan_text=self.plan)

    def test_rejects_open_item_falsely_checked_in_plan(self) -> None:
        plan = self.plan.replace("- [ ] **P3B-02**", "- [x] **P3B-02**", 1)
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate(self.document, current_request=self.request, ledger=self.ledger, plan_text=plan)

    def test_rejects_scoped_closed_item_reopened_in_plan(self) -> None:
        plan = self.plan.replace("- [x] **P3B-04**", "- [ ] **P3B-04**", 1)
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate(self.document, current_request=self.request, ledger=self.ledger, plan_text=plan)

    def test_rejects_reconciled_semantics_gate_reduction(self) -> None:
        for item_id in ("P3B-02", "P4A-01"):
            ledger = copy.deepcopy(self.ledger)
            row = next(item for item in ledger["items"] if item["id"] == item_id)
            row["gate"] = ["tools/verify_owner_decision_reconciliation_v2.py"]
            with self.subTest(item_id=item_id):
                with self.assertRaises(GATE.ReconciliationError):
                    GATE.validate(self.document, current_request=self.request, ledger=ledger, plan_text=self.plan)

    def test_rejects_ledger_item_substitution(self) -> None:
        ledger = copy.deepcopy(self.ledger)
        row = next(item for item in ledger["items"] if item["id"] == "P2-06")
        row["id"] = "P2-FAKE"
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate(self.document, current_request=self.request, ledger=ledger, plan_text=self.plan)

    def test_rejects_duplicate_conflicting_plan_item(self) -> None:
        plan = self.plan + "\n- [x] **P3B-02** conflicting duplicate\n"
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate(self.document, current_request=self.request, ledger=self.ledger, plan_text=plan)


if __name__ == "__main__":
    unittest.main()
