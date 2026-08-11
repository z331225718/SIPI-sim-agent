"""Product-owned tests for the independent delegated receiver evaluator."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_fixed_receiver_delegated_policy as evaluator  # noqa: E402


def bits() -> list[bool]:
    return [index % 2 == 0 for index in range(128)]


def waveform(phase: int = 3, amplitude: float = 1.0) -> list[float]:
    values = [0.0] * 1024
    for index, bit in enumerate(bits()):
        values[phase + 8 * index] = amplitude if bit else -amplitude
    return values


class DelegatedPolicyEvaluatorTests(unittest.TestCase):
    def test_unique_phase_retains_lock_semantics(self) -> None:
        result = evaluator.evaluate(waveform(), bits())
        self.assertEqual(result["phase"], 3)
        self.assertEqual(result["phaseSelection"], "unique_locked")
        self.assertEqual(result["cdrLockState"], "locked")

    def test_ambiguous_candidates_use_lowest_phase_without_lock_claim(self) -> None:
        values = waveform(0)
        for index in range(128):
            values[1 + 8 * index] = values[8 * index]
        result = evaluator.evaluate(values, bits())
        self.assertEqual(result["phase"], 0)
        self.assertEqual(result["phaseSelection"], "delegated_ambiguous_tie_break")
        self.assertEqual(result["cdrLockState"], "policy_selected_not_locked")
        self.assertEqual(result["berDenominator"], 96)

    def test_unqualified_signal_remains_rejected(self) -> None:
        with self.assertRaisesRegex(evaluator.PolicyRejection, "cdr_unqualified"):
            evaluator.evaluate(waveform(amplitude=0.0), bits())


if __name__ == "__main__":
    unittest.main()
