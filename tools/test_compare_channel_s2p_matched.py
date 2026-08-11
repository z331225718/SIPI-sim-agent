from __future__ import annotations

import math
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from compare_channel_s2p_matched import (
    ComparatorError,
    _compare,
    _environment_hash,
    encode_product_spectrum,
    observer_kernel,
    parse_product_kernel,
    parse_two_port_touchstone_ri,
)


class MatchedS2pComparatorTests(unittest.TestCase):
    def touchstone(self) -> bytes:
        return b"""! Product-owned parser test input only\n# Hz S RI R 50.0\n0 0 0 1 0 1 0 0 0\n1 0 0 0 1 0 1 0 0\n2 0 0 -1 0 -1 0 0 0\n"""

    def test_observer_parses_only_the_narrow_subset_and_produces_kernel(self) -> None:
        spectrum = parse_two_port_touchstone_ri(self.touchstone())
        self.assertEqual(len(spectrum.samples), 3)
        self.assertEqual(spectrum.samples[1][1], complex(0.0, 1.0))
        self.assertEqual(spectrum.samples[1][2], complex(0.0, 1.0))
        encoded = encode_product_spectrum(spectrum)
        self.assertEqual(encoded[:8], b"SIPICHS1")
        interval, kernel = observer_kernel(spectrum)
        self.assertEqual(interval, 0.25)
        self.assertEqual(len(kernel), 4)
        self.assertTrue(all(math.isfinite(value) for value in kernel))

    def test_nonuniform_or_nonmatching_touchstone_is_rejected(self) -> None:
        malformed = self.touchstone().replace(b"2 0", b"3 0")
        with self.assertRaisesRegex(ComparatorError, "uniform"):
            parse_two_port_touchstone_ri(malformed)
        with self.assertRaisesRegex(ComparatorError, "option"):
            parse_two_port_touchstone_ri(self.touchstone().replace(b"RI", b"MA"))

    def test_kernel_comparison_and_binary_output_are_fail_closed(self) -> None:
        passed = _compare([0.0, 1.0], [0.0, 1.00001], 1.0e-9, 1.0e-5)
        self.assertTrue(passed["passed"])
        self.assertLessEqual(passed["max_normalized_error_ratio"], 1.0)
        rejected = _compare([0.0, 1.0], [0.0, 1.01], 1.0e-9, 1.0e-5)
        self.assertFalse(rejected["passed"])
        self.assertGreater(rejected["max_normalized_error_ratio"], 1.0)
        with self.assertRaisesRegex(ComparatorError, "magic"):
            parse_product_kernel(b"invalid")
        with self.assertRaisesRegex(ComparatorError, "non-finite"):
            parse_product_kernel(b"SIPICHK1" + struct.pack("<Qdd", 1, 1.0, float("nan")))
        self.assertEqual(_environment_hash("cargo 1.97"), _environment_hash("cargo 1.97"))
        self.assertNotEqual(_environment_hash("cargo 1.97"), _environment_hash("cargo 1.98"))


if __name__ == "__main__":
    unittest.main()
