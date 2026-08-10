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

    def test_current_record_is_owner_selection_ready_but_not_required(self) -> None:
        report = verify_document(self.readiness(), self.inventory())
        self.assertTrue(report["valid"], report["blockers"])
        self.assertEqual(report["required_profile_count"], 0)
        self.assertEqual(report["missing_semantics_count"], 8)

    def test_required_promotion_and_identity_drift_fail_closed(self) -> None:
        readiness = self.readiness()
        readiness["owner_decision"]["required_by"] = "silent-promotion"
        report = verify_document(readiness, self.inventory())
        self.assertFalse(report["valid"])
        self.assertTrue(any("owner decision" in item for item in report["blockers"]))
        readiness = self.readiness()
        readiness["candidate_identity"]["content_sha256"] = "0" * 64
        report = verify_document(readiness, self.inventory())
        self.assertFalse(report["valid"])
        self.assertTrue(any("identity" in item for item in report["blockers"]))

    def test_external_contract_and_semantics_must_stay_pinned_and_missing(self) -> None:
        readiness = self.readiness()
        readiness["external_observation"]["current_to_voltage_sign"] = 1
        report = verify_document(readiness, self.inventory())
        self.assertFalse(report["valid"])
        self.assertTrue(any("external observation" in item for item in report["blockers"]))
        readiness = self.readiness()
        readiness["missing_semantics"]["dfe_tap_order_cursor_units_sign_and_initial_state"] = "guessed"
        report = verify_document(readiness, self.inventory())
        self.assertFalse(report["valid"])
        self.assertTrue(any("receiver semantics" in item for item in report["blockers"]))

    def test_inventory_candidate_status_cannot_drift(self) -> None:
        inventory = self.inventory()
        inventory["profiles"][1]["acceptance"]["status"] = "required_pending_preflight"
        inventory["profiles"][1]["acceptance"]["required_by"] = "silent-promotion"
        report = verify_document(self.readiness(), inventory)
        self.assertFalse(report["valid"])
        self.assertTrue(any("candidate profile" in item for item in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
