"""Numerical/transport guards; run with an existing NumPy-equipped Python."""

import copy
from pathlib import Path
import tempfile
import unittest

try:
    import numpy as np
except ImportError:
    np = None

import run_channel_native_ads_bench as bench


class ChannelBenchTests(unittest.TestCase):
    @unittest.skipIf(np is None, "NumPy is needed for numerical ADS-bench checks")
    def test_default_matrix_and_full_grids(self):
        plan = bench.initial_plan()
        bench.validate_plan(plan)
        self.assertEqual(len(plan["cases"]), 7)
        self.assertEqual(plan["repeats"], 2)
        self.assertFalse(plan["acceptance"])
        for case in plan["cases"]:
            request = case["request"]
            text, material = bench.netlist(request)
            frequency = bench.frequencies(request)
            self.assertEqual(len(material), len(frequency))
            self.assertEqual(text.count(" Pt="), len(frequency))
            self.assertEqual(request["pattern"]["bit_count"], len(request["pattern"]["bits"]))
            self.assertNotIn("bitCount", request["pattern"])
            self.assertIn("Vdc=0 V Vac=2 V", text)
            self.assertIn("UseInitCond=no", text)
            self.assertNotIn("Values=[", text)
            if case["name"] == "lossy-metallic":
                self.assertIn("W_Element:LINE input 0 output 0", text)
                self.assertNotIn('#uselib "ckt" , "W_Element"', text)
        self.assertEqual(len(bench.frequencies(plan["cases"][0]["request"])), 513)

    @unittest.skipIf(np is None, "NumPy is needed for numerical ADS-bench checks")
    def test_material_table_is_the_declared_line_not_a_candidate_response(self):
        request = bench.initial_plan()["cases"][0]["request"]
        rows = np.array(bench.rlgc_rows(request, np.array([0, 1e9, 64e9])))
        np.testing.assert_array_equal(rows[:, 1], 0)
        np.testing.assert_array_equal(rows[:, 3], 0)
        np.testing.assert_allclose(rows[:, 2], 100 / 200e6, rtol=1e-15)
        np.testing.assert_allclose(rows[:, 4], 1 / (100 * 200e6), rtol=1e-15)
        # Electrical delay and impedance follow independently from L and C.
        np.testing.assert_allclose(np.sqrt(rows[:, 2] * rows[:, 4]) * 0.05, 250e-12, rtol=1e-15)
        np.testing.assert_allclose(np.sqrt(rows[:, 2] / rows[:, 4]), 100, rtol=1e-15)
        frequency = np.array([0, 1e9, 2e9, 64e9])
        np.testing.assert_allclose(bench.material_transfer(request, frequency), np.exp(-2j * np.pi * frequency * 250e-12), atol=1e-13, rtol=1e-13)
        request["channel"]["value"]["dcResistanceOhmPerM"] = 20
        dc = bench.material_transfer(request, np.array([0.0]))
        np.testing.assert_allclose(dc, 200 / (200 + 20 * 0.05), atol=1e-15, rtol=1e-15)

    def test_invalid_plans_cannot_weaken_scope_or_move_time_keys(self):
        base = bench.initial_plan()
        mutations = [
            lambda p: p.update(acceptance=True),
            lambda p: p.update(repeats=1),
            lambda p: p.update(time_key_absolute_tolerance_s=1e-12),
            lambda p: p["reference"].update(ads_clock_origin_ui=5),
            lambda p: p["voltage_tolerance"].update(absolute=float("nan")),
            lambda p: p["voltage_tolerance"].pop("relative"),
            lambda p: p["transfer_tolerance"].update(absolute=True),
            lambda p: p["cases"][0].update(name="../escape"),
            lambda p: p["cases"][0]["request"]["timebase"].update(samplesPerUi=1.5),
            lambda p: p["cases"][0]["request"]["channel"]["value"].update(sampleInterval=1e-12),
            lambda p: p["cases"][0]["request"]["channel"]["value"].update(frequencyStepHz=1e6),
            lambda p: p["cases"][1]["request"]["channel"]["value"].update(frequencyMaxHz=1e20),
            lambda p: p["cases"][0]["request"]["pattern"]["bits"].__setitem__(0, True),
            lambda p: p["cases"][0]["request"]["tx"]["ffe"].update(enabled=True),
            lambda p: p["cases"][0]["request"]["rx"].update(dfeTaps=1),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                plan = copy.deepcopy(base)
                mutate(plan)
                with self.assertRaises(ValueError):
                    bench.validate_plan(plan)

    @unittest.skipIf(np is None, "NumPy is needed for numerical ADS-bench checks")
    def test_gate_never_aligns_scales_discards_or_accepts_nonfinite(self):
        tolerance = {"absolute": 0.125, "relative": 0.0}
        reference = np.array([0.0, 1.0, 0.0, -1.0])
        boundary = reference + 0.125
        self.assertTrue(bench.gate(reference, boundary, tolerance)["passed"])
        boundary[0] = np.nextafter(0.125, float("inf"))
        result = bench.gate(reference, boundary, tolerance)
        self.assertFalse(result["passed"])
        self.assertEqual(result["failed_points"], 1)
        self.assertEqual(result["points"], 4)
        self.assertFalse(bench.gate(reference, np.roll(reference, 1), tolerance)["passed"])
        self.assertFalse(bench.gate(reference, reference * 2, tolerance)["passed"])
        for other in (reference[:2], np.array([0, 1, float("nan"), -1]), np.array([0, 1, float("inf"), -1])):
            with self.assertRaises(ValueError):
                bench.gate(reference, other, tolerance)
        with self.assertRaises(ValueError):
            bench.gate(np.array([]), np.array([]), tolerance)
        self.assertTrue(bench.gate(np.array([1j]), np.array([1j]), tolerance)["passed"])

    def test_json_is_exclusive_and_rejects_duplicates_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            bench.write_json(path, bench.initial_plan())
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                bench.write_json(path, {})
            self.assertEqual(path.read_bytes(), before)
            bench.validate_plan(bench.read_json(path))
            for index, text in enumerate(['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}']):
                invalid = Path(directory) / f"bad-{index}.json"
                invalid.write_text(text, encoding="ascii")
                with self.assertRaises(ValueError):
                    bench.read_json(invalid)


if __name__ == "__main__":
    unittest.main()
