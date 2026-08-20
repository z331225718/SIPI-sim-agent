from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_channel_rfm_receiver_readiness as GATE


class RfmReceiverReadinessTests(unittest.TestCase):
    def readiness(self) -> dict:
        return copy.deepcopy(GATE._load(ROOT / "docs/baselines/channel-rfm-receiver-readiness.v1.yaml"))

    def inventory(self) -> dict:
        return copy.deepcopy(GATE._load(ROOT / "acceptance-profiles.v1.yaml"))

    def historical_inventory(self) -> dict:
        inventory = self.inventory()
        acceptance = inventory["profiles"][1]["acceptance"]
        acceptance["status"] = "required_blocked_missing_receiver_semantics"
        acceptance["tolerance_policy_ref"] = "docs/baselines/channel-rfm-receiver-semantic-approval.v1.yaml"
        return inventory

    def test_live_inventory_delegated_state_is_bound_to_approved_amendment(self) -> None:
        # The live inventory advanced to the owner-approved delegated-policy
        # agreement state (amendment approved 2026-08-11); the readiness
        # verifier accepts it only while the amendment binding is intact.
        report = GATE.verify_document(self.readiness(), self.inventory())
        self.assertTrue(report["valid"], report["blockers"])

    def test_delegated_state_requires_approved_amendment(self) -> None:
        # A missing amendment must fail closed under the delegated state.
        inventory = self.inventory()
        inventory["profiles"][1]["acceptance"]["tolerance_policy_ref"] = "docs/baselines/missing-amendment.v1.yaml"
        with mock.patch.object(GATE, "DELEGATED_AMENDMENT_REF", "docs/baselines/missing-amendment.v1.yaml"):
            report = GATE.verify_document(self.readiness(), inventory)
            self.assertFalse(report["valid"])
            self.assertTrue(any("delegated phase amendment missing" in item for item in report["blockers"]))

    def test_delegated_state_rejects_unapproved_amendment(self) -> None:
        # An amendment whose status is not approved_delegated_policy must
        # fail closed under the delegated state.
        document = GATE._load(ROOT / GATE.DELEGATED_AMENDMENT_REF)
        document["status"] = "proposed"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "amendment.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            inventory = self.inventory()
            inventory["profiles"][1]["acceptance"]["tolerance_policy_ref"] = str(tmp_path)
            with mock.patch.object(GATE, "DELEGATED_AMENDMENT_REF", str(tmp_path)):
                report = GATE.verify_document(self.readiness(), inventory)
                self.assertFalse(report["valid"])
                self.assertTrue(any("binding is invalid" in item for item in report["blockers"]))

    def test_historical_record_is_required_but_semantically_blocked(self) -> None:
        report = GATE.verify_document(self.readiness(), self.historical_inventory())
        self.assertTrue(report["valid"], report["blockers"])
        self.assertEqual(report["required_profile_count"], 1)
        self.assertEqual(report["missing_semantics_count"], 8)

    def test_required_decision_and_identity_drift_fail_closed(self) -> None:
        readiness = self.readiness()
        readiness["owner_decision"]["required_by"] = "different-decision"
        report = GATE.verify_document(readiness, self.historical_inventory())
        self.assertFalse(report["valid"])
        self.assertTrue(any("required decision" in item for item in report["blockers"]))
        readiness = self.readiness()
        readiness["candidate_identity"]["content_sha256"] = "0" * 64
        report = GATE.verify_document(readiness, self.historical_inventory())
        self.assertFalse(report["valid"])
        self.assertTrue(any("identity" in item for item in report["blockers"]))

    def test_external_contract_and_semantics_must_stay_pinned_and_missing(self) -> None:
        readiness = self.readiness()
        readiness["external_observation"]["current_to_voltage_sign"] = 1
        report = GATE.verify_document(readiness, self.historical_inventory())
        self.assertFalse(report["valid"])
        self.assertTrue(any("external observation" in item for item in report["blockers"]))
        readiness = self.readiness()
        readiness["missing_semantics"]["dfe_tap_order_cursor_units_sign_and_initial_state"] = "guessed"
        report = GATE.verify_document(readiness, self.historical_inventory())
        self.assertFalse(report["valid"])
        self.assertTrue(any("receiver semantics" in item for item in report["blockers"]))

    def test_evidence_anchor_must_exist_and_match_the_inventory(self) -> None:
        readiness = self.readiness()
        readiness["external_observation"]["evidence_ref"] = "docs/baselines/audits/missing.md#missing"
        report = GATE.verify_document(readiness, self.historical_inventory())
        self.assertFalse(report["valid"])
        self.assertTrue(any("external observation" in item for item in report["blockers"]))
        inventory = self.historical_inventory()
        inventory["profiles"][1]["evidence_refs"] = ["docs/baselines/audits/2026-08-08-m5.md#m5b-03c"]
        report = GATE.verify_document(self.readiness(), inventory)
        self.assertFalse(report["valid"])
        self.assertTrue(any("receiver evidence" in item for item in report["blockers"]))

    def test_inventory_required_status_cannot_drift(self) -> None:
        inventory = self.historical_inventory()
        inventory["profiles"][1]["acceptance"]["status"] = "candidate"
        inventory["profiles"][1]["acceptance"]["required_by"] = None
        report = GATE.verify_document(self.readiness(), inventory)
        self.assertFalse(report["valid"])
        self.assertTrue(any("required profile" in item for item in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
