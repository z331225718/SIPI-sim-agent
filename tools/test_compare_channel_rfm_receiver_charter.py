"""Product-owned tests for receiver charter comparison math and rejection policy."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_channel_rfm_receiver_charter as compare  # noqa: E402


def accepted(schema: str) -> dict:
    return {
        "schema": schema,
        "status": "accepted",
        "phase": 3,
        "locked": True,
        "centerVolts": 0.0,
        "amplitudeVolts": 1.0,
        "frozenTaps": [0.0] * 5,
        "decisions": "+-" * 48,
        "errorCount": 0,
        "berNumerator": 0,
        "berDenominator": 96,
    }


class ReceiverCharterComparisonTests(unittest.TestCase):
    def test_matching_observables_are_accepted(self) -> None:
        result = compare.compare_result_pair(
            accepted("sipi.receiver-charter-evaluator.v1"),
            accepted("sipi.receiver-observer-runner.v1"),
        )
        self.assertEqual(result["status"], "accepted")
        self.assertTrue(result["continuous"]["passed"])

    def test_discrete_and_continuous_drift_fail_closed(self) -> None:
        evaluator = accepted("sipi.receiver-charter-evaluator.v1")
        product = accepted("sipi.receiver-observer-runner.v1")
        product["decisions"] = "-" + product["decisions"][1:]
        self.assertEqual(compare.compare_result_pair(evaluator, product)["status"], "comparison_failed")
        product = accepted("sipi.receiver-observer-runner.v1")
        product["frozenTaps"][2] = 1.0e-3
        self.assertEqual(compare.compare_result_pair(evaluator, product)["status"], "comparison_failed")

    def test_matching_rejections_are_not_an_equivalence_pass(self) -> None:
        result = compare.compare_result_pair(
            {"schema": "sipi.receiver-charter-evaluator.v1", "status": "rejected", "reason": "cdr_ambiguous"},
            {"schema": "sipi.receiver-observer-runner.v1", "status": "rejected", "reason": "CdrAmbiguous"},
        )
        self.assertEqual(result["status"], "receiver_rejected")


if __name__ == "__main__":
    unittest.main()
