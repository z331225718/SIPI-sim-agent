from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from verify_channel_rfm_receiver_erasure_amendment import verify_document


class ErasureAmendmentTests(unittest.TestCase):
    def document(self) -> dict:
        return copy.deepcopy(yaml.safe_load((ROOT / "docs/baselines/channel-rfm-receiver-erasure-amendment.v1.yaml").read_text(encoding="utf-8")))

    def test_current_amendment_is_valid(self) -> None:
        self.assertTrue(verify_document(self.document())["valid"])

    def test_feedback_or_anchor_drift_is_rejected(self) -> None:
        value = self.document()
        value["amendment_spec"]["erasure_feedback_symbol"] = -1.0
        self.assertFalse(verify_document(value)["valid"])
        value = self.document()
        value["base_approval_anchor"]["commit"] = "main"
        self.assertFalse(verify_document(value)["valid"])


if __name__ == "__main__":
    unittest.main()
