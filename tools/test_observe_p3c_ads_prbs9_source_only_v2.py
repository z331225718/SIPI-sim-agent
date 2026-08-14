"""Unit checks for the fixed finite-edge source-only projection."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_only_observer_v2", ROOT / "tools/observe_p3c_ads_prbs9_source_only_v2.py")
assert SPEC and SPEC.loader
OBSERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OBSERVER)


class SourceOnlyObserverV2Tests(unittest.TestCase):
    def test_projection_keeps_sample_zero_and_uses_prior_at_later_boundaries(self) -> None:
        values = OBSERVER.projected_loaded_differential_v2()
        symbols = [-0.5 if bit == "0" else 0.5 for bit in OBSERVER.runner.prbs9_period()]
        osr = OBSERVER.runner.SAMPLES_PER_UI
        period = OBSERVER.runner.PERIOD_BITS * osr
        self.assertEqual(len(values), OBSERVER.runner.TOTAL_SAMPLES)
        self.assertEqual(values[0], symbols[0])
        self.assertEqual(values[osr - 1], symbols[0])
        self.assertEqual(values[osr], symbols[0])
        self.assertEqual(values[osr + 1], symbols[1])
        self.assertEqual(values[period], symbols[-1])
        self.assertEqual(values[period + 1], symbols[0])

    def test_perfect_observation_has_zero_nrmse(self) -> None:
        expected = OBSERVER.projected_loaded_differential_v2()
        result = OBSERVER.summary(
            expected,
            expected,
            [0.0] * len(expected),
            range(OBSERVER.THIRD_START, OBSERVER.runner.TOTAL_SAMPLES),
        )
        self.assertEqual(result["nrmse_bits"], "0000000000000000")
        self.assertEqual(result["sample_count"], OBSERVER.PERIOD_SAMPLES)


if __name__ == "__main__":
    unittest.main()
