from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_explicit_sweep", ROOT / "tools" / "observe_p3c_ads_explicit_convolution_sweep.py")
assert SPEC and SPEC.loader
SWEEP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SWEEP
SPEC.loader.exec_module(SWEEP)


class ExplicitConvolutionSweepTests(unittest.TestCase):
    def test_allowlisted_grids_have_exact_fmax_relation(self) -> None:
        self.assertEqual(SWEEP.delta_frequency_hz(512), 156_250_000.0)
        self.assertEqual(SWEEP.delta_frequency_hz(1024), 78_125_000.0)
        self.assertEqual(SWEEP.delta_frequency_hz(2048), 39_062_500.0)
        self.assertEqual(SWEEP.delta_frequency_hz(4096), 19_531_250.0)
        self.assertEqual(SWEEP.delta_frequency_hz(8192), 9_765_625.0)
        self.assertEqual(SWEEP.delta_frequency_hz(16384), 4_882_812.5)
        with self.assertRaisesRegex(SWEEP.SweepError, "grid_length"):
            SWEEP.delta_frequency_hz(32768)

    def test_explicit_netlist_fixes_only_authorized_convolution_knobs(self) -> None:
        runner = SWEEP.load_runner()
        netlist = SWEEP.build_explicit_netlist(runner, grid_length=8192)
        self.assertIn("ImpMaxFreq=40000000000 Hz", netlist)
        self.assertIn("ImpDeltaFreq=9765625 Hz", netlist)
        self.assertIn("ImpMode=1", netlist)
        self.assertNotIn("ami", netlist.lower())
        self.assertNotIn("ibis", netlist.lower())
        self.assertNotIn(".dll", netlist.lower())

    def test_nrmse_is_unaligned_and_fail_closed(self) -> None:
        self.assertEqual(SWEEP.relative_nrmse([1.0, -1.0], [1.0, -1.0]), 0.0)
        self.assertGreater(SWEEP.relative_nrmse([1.0, -1.0], [-1.0, 1.0]), 1.0)
        with self.assertRaisesRegex(SWEEP.SweepError, "norm"):
            SWEEP.relative_nrmse([0.0, 0.0], [0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
