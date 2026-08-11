from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from verify_channel_rfm_receiver_delegated_phase_amendment import verify  # noqa: E402


class DelegatedPhaseAmendmentTests(unittest.TestCase):
    def amendment(self) -> dict:
        return yaml.safe_load((ROOT / "docs/baselines/channel-rfm-receiver-delegated-phase-amendment.v1.yaml").read_text(encoding="utf-8"))

    def test_current_amendment_is_a_profile_scoped_non_lock_policy(self) -> None:
        report = verify(self.amendment())
        self.assertTrue(report["valid"], report["blockers"])

    def test_policy_or_authority_drift_fails_closed(self) -> None:
        amendment = copy.deepcopy(self.amendment())
        amendment["phase_policy"]["ambiguous_selection"] = "highest_phase_index"
        self.assertFalse(verify(amendment)["valid"])
        amendment = copy.deepcopy(self.amendment())
        amendment["approved_by"] = "user"
        self.assertFalse(verify(amendment)["valid"])
        amendment = copy.deepcopy(self.amendment())
        amendment["unexpected"] = True
        self.assertFalse(verify(amendment)["valid"])


if __name__ == "__main__":
    unittest.main()
