from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_channel_rfm_receiver_required_decision import _load, verify_document


class RequiredReceiverDecisionTests(unittest.TestCase):
    def documents(self) -> tuple[dict, dict, dict]:
        return (
            copy.deepcopy(_load(ROOT / "docs/baselines/channel-rfm-receiver-required-decision.v1.yaml")),
            copy.deepcopy(_load(ROOT / "acceptance-profiles.v1.yaml")),
            copy.deepcopy(_load(ROOT / "docs/baselines/channel-rfm-receiver-readiness.v1.yaml")),
        )

    def historical_inventory(self, inventory: dict) -> dict:
        inventory["profiles"][1]["acceptance"]["status"] = "required_blocked_missing_receiver_semantics"
        return inventory

    def test_live_inventory_has_advanced_beyond_the_historical_required_decision(self) -> None:
        decision, inventory, readiness = self.documents()
        report = verify_document(decision, inventory, readiness)
        self.assertFalse(report["valid"])
        self.assertIn("inventory does not carry the same scope-limited required decision", report["blockers"])

    def test_historical_decision_is_required_but_scope_limited(self) -> None:
        decision, inventory, readiness = self.documents()
        report = verify_document(decision, self.historical_inventory(inventory), readiness)
        self.assertTrue(report["valid"], report["blockers"])

    def test_scope_or_cross_record_drift_fails_closed(self) -> None:
        decision, inventory, readiness = self.documents()
        decision["scope"] = "general-rfm-receiver"
        self.assertFalse(verify_document(decision, self.historical_inventory(inventory), readiness)["valid"])
        decision, inventory, readiness = self.documents()
        inventory["profiles"][1]["acceptance"]["status"] = "required_pending_preflight"
        self.assertFalse(verify_document(decision, inventory, readiness)["valid"])
        decision, inventory, readiness = self.documents()
        readiness["owner_decision"]["decision"] = "pending"
        self.assertFalse(verify_document(decision, self.historical_inventory(inventory), readiness)["valid"])


if __name__ == "__main__":
    unittest.main()
