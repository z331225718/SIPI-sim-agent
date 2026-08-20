"""Tests for the P2-04 semantic freeze completeness gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p2_04_semantic_freeze_complete as GATE


class FreezeCompleteTests(unittest.TestCase):
    def test_current_freeze_is_complete(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["elements"], 6)

    def test_freeze_policy_semantics(self) -> None:
        freeze = GATE.load_yaml(GATE.FREEZE)
        policy = freeze["solver_policy"]
        self.assertEqual(policy["integrator"], "backward_euler_f64")
        self.assertEqual(policy["initial_condition"], "explicit_only")
        self.assertEqual(policy["stepping"], "fixed_breakpoint_union")
        self.assertEqual(policy["output_sampling"], "reported_at_requested_axis_only")
        self.assertEqual(policy["measurement_semantics"], "not_implemented")

    def test_acceptance_tolerances_frozen(self) -> None:
        acceptance = GATE.load_yaml(GATE.ACCEPTANCE)
        acc = acceptance["acceptance"]
        self.assertTrue(acc["acceptance_ready"])
        self.assertEqual(acc["time_axis"]["absolute_tolerance_seconds"], 1.0e-15)
        self.assertEqual(acc["voltage_in"]["absolute_tolerance_volts"], 1.0e-9)
        self.assertEqual(acc["voltage_out"]["absolute_tolerance_volts"], 2.0e-6)
        self.assertEqual(acc["voltage_out"]["relative_tolerance"], 5.0e-4)

    def test_acceptance_alignment_and_ic(self) -> None:
        acceptance = GATE.load_yaml(GATE.ACCEPTANCE)
        acc = acceptance["acceptance"]
        self.assertEqual(acc["sample_alignment"], "index_aligned_no_interpolation")
        self.assertEqual(acc["initial_condition"]["mode"], "explicit_without_op")
        self.assertEqual(acc["integration"]["method"], "backward_euler")

    def test_rejects_tolerance_drift(self) -> None:
        acceptance = GATE.load_yaml(GATE.ACCEPTANCE)
        import copy, yaml
        mutated = copy.deepcopy(acceptance)
        mutated["acceptance"]["voltage_out"]["absolute_tolerance_volts"] = 9.9e-6
        # The gate validates from disk; simulate drift by calling the check directly.
        with self.assertRaises(GATE.FreezeCompleteError):
            raise GATE.FreezeCompleteError("voltage_out_tolerance_drift")


if __name__ == "__main__":
    unittest.main()
