from __future__ import annotations

import copy
import unittest

from tools import verify_p1_04b_comparison_permission_reconciliation as GATE


class P1ComparisonPermissionReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = GATE._load(GATE.DOCUMENT)
        self.ledger = GATE._load(GATE.LEDGER)
        self.owner_request = GATE._load(GATE.OWNER_REQUEST)

    def test_current_state_is_valid(self) -> None:
        self.assertTrue(GATE.validate()["valid"])

    def test_rejects_any_asset_or_release_promotion(self) -> None:
        for field in (
            "required_profile_selected", "required_profile_accepted", "distribution_authorized",
            "product_input_admitted", "runtime_admitted", "release_admitted",
        ):
            with self.subTest(field=field):
                document = copy.deepcopy(self.document)
                document["state"][field] = True
                with self.assertRaises(GATE.ReconciliationError):
                    GATE.validate(document, ledger=self.ledger, owner_request=self.owner_request)

    def test_rejects_owner_decision_or_wrong_request_kind(self) -> None:
        ledger = copy.deepcopy(self.ledger)
        next(item for item in ledger["items"] if item["id"] == "P1-04B")["blocker"] = "owner_decision"
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate(self.document, ledger=ledger, owner_request=self.owner_request)
        request = copy.deepcopy(self.owner_request)
        next(item for item in request["entries"] if item["id"] == "P1-04B")["kind"] = "owner_decision"
        with self.assertRaises(GATE.ReconciliationError):
            GATE.validate(self.document, ledger=self.ledger, owner_request=request)


if __name__ == "__main__":
    unittest.main()
