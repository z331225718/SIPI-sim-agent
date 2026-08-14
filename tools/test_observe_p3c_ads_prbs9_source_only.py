"""Unit checks for source-only diagnostics without ADS invocation."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_only_observer", ROOT / "tools/observe_p3c_ads_prbs9_source_only.py")
assert SPEC and SPEC.loader
OBSERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OBSERVER)


class SourceOnlyObserverTests(unittest.TestCase):
    def test_projection_is_half_scale_and_right_continuous(self) -> None:
        values = OBSERVER.projected_loaded_differential()
        self.assertEqual(len(values), OBSERVER.runner.TOTAL_SAMPLES)
        self.assertTrue(all(value in (-0.5, 0.5) for value in values))
        self.assertEqual(values[0], values[31])

    def test_perfect_observation_has_zero_nrmse(self) -> None:
        expected = OBSERVER.projected_loaded_differential()
        result = OBSERVER.summary(expected, expected, [0.0] * len(expected), range(OBSERVER.THIRD_START, OBSERVER.runner.TOTAL_SAMPLES))
        self.assertEqual(result["nrmse_bits"], "0000000000000000")
        self.assertEqual(result["sample_count"], OBSERVER.PERIOD_SAMPLES)


if __name__ == "__main__":
    unittest.main()
