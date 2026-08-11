from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from compare_tran_rc_pulse import ComparatorError, _array_hash, _compare, parse_oracle_result, parse_product_harness


class TranRcPulseComparatorTests(unittest.TestCase):
    def oracle_document(self) -> dict:
        return {
            "schema": "agent-spice.sim-result.v1",
            "points": [
                {"analysis": "op", "x": 0.0, "values": {"in": 0.0, "out": 0.0}},
                *[
                    {"analysis": "tran", "x": time, "values": {"in": voltage_in, "out": voltage_out}}
                    for time, voltage_in, voltage_out in zip([0.0, 1.0e-6, 2.0e-6, 3.0e-6], [0.0, 0.0, 1.0, 1.0], [0.0, 0.0, 0.001, 0.002], strict=True)
                ],
            ],
        }

    def harness_document(self) -> dict:
        return {
            "schema": "sipi.tran.rc-pulse-harness.v1",
            "profileId": "tran-rc-pulse-v1",
            "timeSeconds": [0.0, 1.0e-6, 2.0e-6, 3.0e-6],
            "voltageInVolts": [0.0, 0.0, 1.0, 1.0],
            "voltageOutVolts": [0.0, 0.0, 0.001, 0.002],
        }

    def test_parses_only_scoped_oracle_points_and_product_schema(self) -> None:
        oracle = parse_oracle_result(self.oracle_document())
        product = parse_product_harness(self.harness_document())
        self.assertEqual(oracle.time, product.time)
        self.assertEqual(oracle.voltage_in, product.voltage_in)
        self.assertEqual(oracle.voltage_out, product.voltage_out)
        self.assertNotEqual(_array_hash(oracle.voltage_out), _array_hash([0.0, 0.0, 0.001, 0.003]))

    def test_fail_closed_for_wrong_grid_nonfinite_and_extra_product_fields(self) -> None:
        wrong_grid = self.oracle_document()
        wrong_grid["points"][2]["x"] = 1.5e-6
        with self.assertRaisesRegex(ComparatorError, "time grid"):
            parse_oracle_result(wrong_grid)
        nonfinite = self.oracle_document()
        nonfinite["points"][3]["values"]["out"] = float("nan")
        with self.assertRaisesRegex(ComparatorError, "finite"):
            parse_oracle_result(nonfinite)
        extra = self.harness_document()
        extra["legacyFallback"] = False
        with self.assertRaisesRegex(ComparatorError, "schema"):
            parse_product_harness(extra)

    def test_comparison_reports_maximum_error_and_rejects_wrong_scale(self) -> None:
        accepted = _compare("v(out)", [0.0, 1.0], [0.0, 1.0005], 2.0e-6, 5.0e-4)
        self.assertTrue(accepted["passed"])
        self.assertEqual(accepted["worst_index"], 1)
        self.assertGreaterEqual(accepted["allowed_error_at_worst_index"], accepted["max_absolute_error"])
        rejected = _compare("v(out)", [0.0, 1.0], [0.0, 1.01], 2.0e-6, 5.0e-4)
        self.assertFalse(rejected["passed"])

    def test_json_fixtures_are_only_test_local(self) -> None:
        encoded = json.dumps(self.harness_document(), sort_keys=True)
        self.assertIn("sipi.tran.rc-pulse-harness.v1", encoded)
        self.assertNotIn("rc.cir", encoded)


if __name__ == "__main__":
    unittest.main()
