from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pre_final", ROOT / "tools/run_p3c_external_ads_fixed_pulse_pre_final_spectrum.py")
assert SPEC and SPEC.loader
PRE_FINAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PRE_FINAL)


class PreFinalSpectrumTests(unittest.TestCase):
    def test_exact_member_allowlist_has_two_complete_four_port_surfaces(self) -> None:
        self.assertEqual(PRE_FINAL.EXPECTED_MEMBERS, tuple((row, column) for row in range(1, 5) for column in range(1, 5)))
        self.assertEqual(len(PRE_FINAL.EXPECTED_MEMBERS), 16)

    def test_axis_summary_is_deterministic_and_rejects_nonmonotonic_input(self) -> None:
        first = PRE_FINAL._axis_summary((0.0, 1.0, 2.0), b"test\0")
        second = PRE_FINAL._axis_summary((0.0, 1.0, 2.0), b"test\0")
        self.assertEqual(first, second)
        with self.assertRaisesRegex(PRE_FINAL.PreFinalSpectrumError, "spectrum_axis_not_strictly_increasing"):
            PRE_FINAL._axis_summary((0.0, 1.0, 1.0), b"test\0")

    def test_axis_comparison_preserves_signed_zero_identity(self) -> None:
        self.assertFalse(PRE_FINAL._axis_bits_equal((0.0, 1.0), (-0.0, 1.0)))


if __name__ == "__main__":
    unittest.main()
