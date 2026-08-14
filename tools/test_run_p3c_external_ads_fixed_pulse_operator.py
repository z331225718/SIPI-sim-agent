from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fixed_pulse", ROOT / "tools/run_p3c_external_ads_fixed_pulse_operator.py")
assert SPEC and SPEC.loader
PULSE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PULSE)


class FixedPulseTests(unittest.TestCase):
    def test_fixed_netlist_has_only_the_authorized_operator_topology(self) -> None:
        netlist = PULSE.build_netlist()
        PULSE.assert_fixed_netlist(netlist)
        self.assertIn("V_Source:SOURCE_P", netlist)
        self.assertIn("V_Source:SOURCE_M", netlist)
        self.assertIn("V_Tran=pwl(time", netlist)
        self.assertIn("ImpMaxFreq=40000000000 Hz", netlist)
        self.assertIn("ImpDeltaFreq=39062500 Hz", netlist)
        self.assertNotIn("PRBSsrc", netlist)

    def test_fixed_pulse_lies_strictly_between_strobe_points(self) -> None:
        self.assertEqual(PULSE.PULSE_END_INDEX - PULSE.PULSE_START_INDEX, 32)
        self.assertEqual(PULSE.PULSE_START_INDEX, 16_353)
        self.assertAlmostEqual(PULSE.PULSE_START_SECONDS, 511 * PULSE.UI_SECONDS + PULSE.DT_SECONDS / 2.0)
        self.assertLess(PULSE.PULSE_START_SECONDS, PULSE.PULSE_START_INDEX * PULSE.DT_SECONDS)
        self.assertGreater(PULSE.PULSE_START_SECONDS, (PULSE.PULSE_START_INDEX - 1) * PULSE.DT_SECONDS)


if __name__ == "__main__":
    unittest.main()
