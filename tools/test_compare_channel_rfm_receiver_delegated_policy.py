from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import compare_channel_rfm_receiver_delegated_policy as comparator  # noqa: E402


def result(selection: str = "delegated_ambiguous_tie_break", lock: str = "policy_selected_not_locked") -> dict:
    return {
        "schema": "test",
        "status": "accepted",
        "phase": 0,
        "phaseSelection": selection,
        "cdrLockState": lock,
        "centerVolts": 0.0,
        "amplitudeVolts": 1.0,
        "frozenTaps": [0.0] * 5,
        "decisions": "+-" * 48,
        "errorCount": 0,
        "berNumerator": 0,
        "berDenominator": 96,
    }


class DelegatedCompareTests(unittest.TestCase):
    def test_identical_policy_selected_results_agree(self) -> None:
        report = comparator.compare_pair(result(), result())
        self.assertEqual(report["status"], "accepted")

    def test_lock_state_or_discrete_drift_fails(self) -> None:
        altered = copy.deepcopy(result())
        altered["cdrLockState"] = "locked"
        self.assertEqual(comparator.compare_pair(result(), altered)["status"], "comparison_failed")
        altered = copy.deepcopy(result())
        altered["decisions"] = "0" + altered["decisions"][1:]
        self.assertEqual(comparator.compare_pair(result(), altered)["status"], "comparison_failed")

    def test_rejection_is_never_agreement(self) -> None:
        rejected = {"schema": "test", "status": "rejected", "reason": "cdr_unqualified"}
        self.assertEqual(comparator.compare_pair(rejected, result())["status"], "receiver_rejected")


if __name__ == "__main__":
    unittest.main()
