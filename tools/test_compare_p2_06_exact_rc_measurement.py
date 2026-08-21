"""Focused parser tests for the P2-06 same-deck comparator."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import compare_p2_06_exact_rc_measurement as comparator


class ExactMeasurementComparatorTests(unittest.TestCase):
    def test_exact_input_is_seven_ascii_lines(self) -> None:
        self.assertEqual(len(comparator.DECK), 143)
        self.assertEqual(len(comparator.DECK.decode("ascii").splitlines()), 7)
        self.assertIn(b".measure TRAN vmax MAX V(out)\n", comparator.DECK)

    def test_oracle_measurement_is_read_from_result_container(self) -> None:
        measurement = comparator.parse_oracle_measurement(
            {"measurements": [{"analysis": "tran", "name": "vmax", "value": 0.25}]}
        )
        self.assertEqual(measurement["value_volts"], 0.25)
        self.assertEqual(measurement["source_path"], "SimulationResult.measurements[0]")

    def test_missing_or_nonfinite_oracle_measurement_fails_closed(self) -> None:
        for value in ({}, {"measurements": []}, {"measurements": [{"analysis": "tran", "name": "vmax", "value": float("nan")}]},):
            with self.subTest(value=value), self.assertRaises(comparator.CompareError):
                comparator.parse_oracle_measurement(value)


if __name__ == "__main__":
    unittest.main()
