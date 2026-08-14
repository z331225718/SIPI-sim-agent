from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pre_final_observer", ROOT / "tools/observe_p3c_ads_pre_final_spectrum_comparison.py")
assert SPEC and SPEC.loader
OBSERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OBSERVER)


class PreFinalObserverTests(unittest.TestCase):
    def test_inventory_is_limited_to_runner_predecessor_and_observer(self) -> None:
        self.assertEqual(
            {path.as_posix() for path in OBSERVER.INVENTORY},
            {
                "tools/run_p3c_external_ads_fixed_pulse_passivity_surface.py",
                "tools/run_p3c_external_ads_fixed_pulse_pre_final_spectrum.py",
                "tools/observe_p3c_ads_pre_final_spectrum_comparison.py",
            },
        )

    def test_axis_summary_rejects_missing_digest(self) -> None:
        with self.assertRaisesRegex(OBSERVER.ObservationError, "axis_summary_shape"):
            OBSERVER._axis_summary({"point_count": 2})


if __name__ == "__main__":
    unittest.main()
