from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_channel_rfm_receiver_semantic_approval import verify_document


class ReceiverSemanticApprovalTests(unittest.TestCase):
    def approval(self) -> dict:
        return copy.deepcopy(yaml.safe_load((ROOT / "docs/baselines/channel-rfm-receiver-semantic-approval.v1.yaml").read_text(encoding="utf-8")))

    def test_current_approval_is_valid_and_external_compare_stays_blocked(self) -> None:
        report = verify_document(self.approval())
        self.assertTrue(report["valid"], report["blockers"])

    def test_anchor_or_external_compare_status_cannot_drift(self) -> None:
        approval = self.approval()
        approval["proposal_anchor"]["commit"] = "main"
        self.assertFalse(verify_document(approval)["valid"])
        approval = self.approval()
        approval["external_compare_status"] = "accepted"
        self.assertFalse(verify_document(approval)["valid"])


if __name__ == "__main__":
    unittest.main()
