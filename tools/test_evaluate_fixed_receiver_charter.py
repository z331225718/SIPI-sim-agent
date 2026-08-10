"""Product-owned synthetic tests for the independent charter evaluator."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_fixed_receiver_charter as evaluator  # noqa: E402


def bits() -> list[bool]:
    return [index % 2 == 0 for index in range(128)]


def waveform(phase: int = 3, amplitude: float = 1.0) -> list[float]:
    values = [0.0] * 1024
    for index, bit in enumerate(bits()):
        values[phase + 8 * index] = amplitude if bit else -amplitude
    return values


class CharterEvaluatorTests(unittest.TestCase):
    def test_clean_product_owned_input_has_exact_receiver_observables(self) -> None:
        result = evaluator.evaluate(waveform(), bits())
        self.assertEqual(result["phase"], 3)
        self.assertTrue(result["locked"])
        self.assertEqual(result["decisions"], "+-" * 48)
        self.assertEqual(result["errorCount"], 0)
        self.assertEqual(result["berDenominator"], 96)

    def test_ambiguous_phase_amplitude_and_invalid_bits_are_rejected(self) -> None:
        tied = waveform(0)
        for index in range(128):
            tied[1 + 8 * index] = tied[8 * index]
        with self.assertRaisesRegex(evaluator.CharterRejection, "cdr_ambiguous"):
            evaluator.evaluate(tied, bits())
        with self.assertRaisesRegex(evaluator.CharterRejection, "amplitude_too_small"):
            evaluator.evaluate(waveform(amplitude=1.0e-7), bits())
        with self.assertRaisesRegex(evaluator.CharterRejection, "128"):
            evaluator.evaluate(waveform(), bits()[:-1])

    def test_erasure_is_an_error_with_zero_feedback_and_processing_continues(self) -> None:
        values = waveform(4)
        values[4 + 8 * 32] = 0.0
        result = evaluator.evaluate(values, bits())
        self.assertEqual(result["decisions"][0], "0")
        self.assertEqual(len(result["decisions"]), 96)
        self.assertEqual(result["errorCount"], 1)


if __name__ == "__main__":
    unittest.main()
