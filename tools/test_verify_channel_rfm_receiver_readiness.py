from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_channel_rfm_receiver_readiness import _load, verify_document


class RfmReceiverReadinessTests(unittest.TestCase):
    def readiness(self) -> dict:
        return copy.deepcopy(_load(ROOT / "docs/baselines/channel-rfm-receiver-readiness.v1.yaml"))

    def inventory(self) -> dict:
        return copy.deepcopy(_load(ROOT / "acceptance-profiles.v1.yaml"))

    def historical_inventory(self) -> dict:
        inventory = self.inventory()
        acceptance = inventory["profiles"][1]["acceptance"]
        acceptance["status"] = "required_blocked_missing_receiver_semantics"
        acceptance["tolerance_policy_ref"] = "docs/baselines/channel-rfm-receiver-semantic-approval.v1.yaml"
        return inventory

    def test_live_inventory_has_advanced_beyond_the_historical_readiness_record(self) -> None:
        report = verify_document(self.readiness(), self.inventory())
        self.assertFalse(report["valid"])
        self.assertIn("required profile must remain oracle-only and blocked", report["blockers"])

    def test_historical_record_is_required_but_semantically_blocked(self) -> None:
        report = verify_document(self.readiness(), self.historical_inventory())
        self.assertTrue(report["valid"], report["blockers"])
        self.assertEqual(report["required_profile_count"], 1)
        self.assertEqual(report["missing_semantics_count"], 8)

    def test_required_decision_and_identity_drift_fail_closed(self) -> None:
        readiness = self.readiness()
        readiness["owner_decision"]["required_by"] = "different-decision"
        report = verify_document(readiness, self.historical_inventory())
        self.assertFalse(report["valid"])
        self.assertTrue(any("required decision" in item for item in report["blockers"]))
        readiness = self.readiness()
        readiness["candidate_identity"]["content_sha256"] = "0" * 64
        report = verify_document(readiness, self.historical_inventory())
        self.assertFalse(report["valid"])
        self.assertTrue(any("identity" in item for item in report["blockers"]))

    def test_external_contract_and_semantics_must_stay_pinned_and_missing(self) -> None:
        readiness = self.readiness()
        readiness["external_observation"]["current_to_voltage_sign"] = 1
        report = verify_document(readiness, self.historical_inventory())
        self.assertFalse(report["valid"])
        self.assertTrue(any("external observation" in item for item in report["blockers"]))
        readiness = self.readiness()
        readiness["missing_semantics"]["dfe_tap_order_cursor_units_sign_and_initial_state"] = "guessed"
        report = verify_document(readiness, self.historical_inventory())
        self.assertFalse(report["valid"])
        self.assertTrue(any("receiver semantics" in item for item in report["blockers"]))

    def test_evidence_anchor_must_exist_and_match_the_inventory(self) -> None:
        readiness = self.readiness()
        readiness["external_observation"]["evidence_ref"] = "docs/baselines/audits/missing.md#missing"
        report = verify_document(readiness, self.historical_inventory())
        self.assertFalse(report["valid"])
        self.assertTrue(any("external observation" in item for item in report["blockers"]))
        inventory = self.historical_inventory()
        inventory["profiles"][1]["evidence_refs"] = ["docs/baselines/audits/2026-08-08-m5.md#m5b-03c"]
        report = verify_document(self.readiness(), inventory)
        self.assertFalse(report["valid"])
        self.assertTrue(any("receiver evidence" in item for item in report["blockers"]))

    def test_inventory_required_status_cannot_drift(self) -> None:
        inventory = self.historical_inventory()
        inventory["profiles"][1]["acceptance"]["status"] = "candidate"
        inventory["profiles"][1]["acceptance"]["required_by"] = None
        report = verify_document(self.readiness(), inventory)
        self.assertFalse(report["valid"])
        self.assertTrue(any("required profile" in item for item in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
