from __future__ import annotations

import copy
import unittest

from tools import verify_p7_08_owner_decision_reconciliation as GATE


class P7OwnerDecisionReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = GATE._load(GATE.DOCUMENT)
        self.ledger = GATE._load(GATE.LEDGER)
        self.owner_request = GATE._load(GATE.OWNER_REQUEST)
        self.plan = GATE.PLAN.read_text(encoding="utf-8")

    def test_current_state_is_valid(self) -> None:
        self.assertTrue(GATE.validate()["valid"])

    def test_rejects_any_release_or_retirement_promotion(self) -> None:
        for field in (
            "required_profile_accepted", "same_batch_drift_gate_removal",
            "release_license_fresh_machine_gates", "path_deletion_performed",
            "drift_gate_removed", "release_admitted",
        ):
            with self.subTest(field=field):
                document = copy.deepcopy(self.document)
                document["state"][field] = True
                with self.assertRaises(GATE.ReconciliationError):
                    GATE.validate(document, ledger=self.ledger, owner_request=self.owner_request, plan_text=self.plan)

    def test_rejects_stale_owner_request_or_ledger_class(self) -> None:
        request = copy.deepcopy(self.owner_request)
        request["entries"].append({"id": "P7-08"})
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate(self.document, ledger=self.ledger, owner_request=request, plan_text=self.plan)
        ledger = copy.deepcopy(self.ledger)
        next(item for item in ledger["items"] if item["id"] == "P7-08")["blocker"] = "owner_decision"
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate(self.document, ledger=ledger, owner_request=self.owner_request, plan_text=self.plan)

    def test_rejects_pending_signature_reintroduced_in_plan(self) -> None:
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate(
                self.document,
                ledger=self.ledger,
                owner_request=self.owner_request,
                plan_text=self.plan + "\napproval_state pending_owner_signature\n",
            )


if __name__ == "__main__":
    unittest.main()
