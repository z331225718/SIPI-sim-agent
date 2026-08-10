from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_channel_rfm_receiver_semantic_charter import _load, verify_document


class ReceiverSemanticCharterTests(unittest.TestCase):
    def charter(self) -> dict:
        return copy.deepcopy(_load(ROOT / "docs/baselines/channel-rfm-receiver-semantic-charter.v1.yaml"))

    def test_current_charter_is_an_explicit_pending_owner_gate(self) -> None:
        report = verify_document(self.charter())
        self.assertTrue(report["valid"], report["blockers"])
        self.assertEqual(report["pending_decision_count"], 6)

    def test_status_decision_or_schema_drift_fails_closed(self) -> None:
        charter = self.charter()
        charter["status"] = "approved"
        self.assertFalse(verify_document(charter)["valid"])
        charter = self.charter()
        charter["pending_decisions"]["dfe_model_and_adaptation"] = "guessed"
        self.assertFalse(verify_document(charter)["valid"])
        charter = self.charter()
        charter["receiver_contract"]["schema_sha256"] = "0" * 64
        self.assertFalse(verify_document(charter)["valid"])

    def test_proposed_model_drift_remains_rejected_while_approval_is_pending(self) -> None:
        charter = self.charter()
        charter["proposed_v1"]["dfe"]["postcursor_taps"] = 4
        self.assertFalse(verify_document(charter)["valid"])
        charter = self.charter()
        charter["proposed_v1"]["approval_required"] = False
        self.assertFalse(verify_document(charter)["valid"])


if __name__ == "__main__":
    unittest.main()
