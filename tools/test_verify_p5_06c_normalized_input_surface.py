"""Tests for the P5-06c normalized-input surface verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_06c_normalized_input_surface as GATE


class InputSurfaceTests(unittest.TestCase):
    def test_current_surface_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["in_config"], 82)

    def test_port_order_recorded(self) -> None:
        surface = GATE.load_yaml(GATE.SURFACE)
        self.assertEqual(surface["port_order_observed"], "[ 1 3 2 4 ]")

    def test_config_values_present_for_known_keys(self) -> None:
        surface = GATE.load_yaml(GATE.SURFACE)
        self.assertTrue(surface["keys"]["f_b"]["in_config"])
        self.assertEqual(surface["keys"]["A_ft"]["config_value"], 0.6)

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P5-06c", plan_text)

    def test_rejects_port_order_drift(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        surface = copy.deepcopy(GATE.load_yaml(GATE.SURFACE))
        surface["port_order_observed"] = "[ 1 2 3 4 ]"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "surface.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(surface, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "SURFACE", tmp_path):
                with self.assertRaises(GATE.InputSurfaceError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
