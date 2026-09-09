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
    @unittest.skipIf(np is None, "NumPy is needed by the ADS evidence verifier")
    def test_report_artifacts_are_versioned_without_loosening_old_receipts(self):
        try:
            import verify_channel_native_ads_bench as verifier
        except ModuleNotFoundError as error:
            if error.name.startswith("keysight"):
                self.skipTest("ADS SDK is not installed")
            raise
        for physical in (False, True):
            names = ["request.json", "meta.json", "arrays.npz", "waveforms.csv", "channel-impulse.csv", "report.html"]
            if physical:
                names.append("frequency-response.csv")
            receipt = {"channel_policy": "physical-voltage-v1" if physical else "pb-02-compat",
                       "artifacts": dict.fromkeys(names)}
            verifier.validate_candidate_artifact_names(receipt)
            receipt["artifacts"]["channel-report.js"] = None
            with self.assertRaises(AssertionError):
                verifier.validate_candidate_artifact_names(receipt)
            receipt["report_data_policy"] = "all_waveform_and_impulse_samples_embedded; original_f64; at_most_4096_contiguous_samples_per_view; no_decimation"
            verifier.validate_candidate_artifact_names(receipt)
            for mutate in (lambda r: r["artifacts"].pop("channel-report.js"),
                           lambda r: r["artifacts"].update(unsealed=None),
                           lambda r: r.update(report_data_policy="silent_decimation")):
                changed = copy.deepcopy(receipt)
                mutate(changed)
                with self.assertRaises(AssertionError):
                    verifier.validate_candidate_artifact_names(changed)

    def test_report_does_not_promote_ac_control_to_transient_qualification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bench.render_summary(root, {"schema": "sipi.channel.ads-physical-bench-result.v3", "status": "failed", "cases": []})
            page = (root / "report.html").read_text(encoding="utf-8")
            self.assertIn("ADS AC material control", page)
            self.assertIn("does not qualify the ADS Transient convolution model", page)
            self.assertIn("failed / acceptance: false", page)

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
            self.assertIn("ForceS_Params=yes", text)
            self.assertIn("R:DC_SOURCE_AND_LINE", text)
            if case["name"] == "lossy-metallic":
                self.assertIn("TL:LINE input 0 output 0", text)
                self.assertIn("V=1/(c0*sqrt(L_PER_M*C_PER_M))", text)
                self.assertNotIn(" F=0", text)
                self.assertNotIn("W_Element", text)
                self.assertIn("W_SAFE=max(2*pi*freq,1e-12)", text)
                self.assertIn("R_PER_M=real(R_COMPLEX)", text)
                self.assertNotIn("_PER_M=pwl(freq", text)
            self.assertIn("V_RelTol=1e-11", text)
            self.assertIn("TruncTol=0.1 ChargeTol=1e-22", text)
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

    @unittest.skipIf(np is None, "NumPy is needed for numerical ADS-bench checks")
    def test_versioned_reference_preserves_legacy_and_exact_dc_is_independent(self):
        old = bench.initial_plan()
        old.update(schema=bench.LEGACY_SCHEMA, reference=copy.deepcopy(bench.LEGACY_REFERENCE))
        bench.validate_plan(old)
        text, _ = bench.netlist(old["cases"][-1]["request"], old["reference"])
        self.assertIn("W_Element:LINE", text)
        self.assertNotIn("ForceS_Params", text)
        self.assertNotIn("DC_CONTROL", text)
        old.update(reference=copy.deepcopy(bench.REFERENCE))
        with self.assertRaises(ValueError):
            bench.validate_plan(old)
        f = np.array([0.0, 1e9, 2e9])
        raw = {"ac__output": np.array([0.8, 0.3j, -0.6j]), "ac__dc_load": np.array([1., 0.5, 0.5]),
               "ac__dc_source": np.full(3, 2, dtype=complex)}
        before = raw["ac__output"].copy()
        actual = bench.physical_ac_reference(raw, "ac", f, bench.REFERENCE)
        np.testing.assert_array_equal(actual, [1., 0.3j, -0.6j])
        np.testing.assert_array_equal(raw["ac__output"], before)
        np.testing.assert_array_equal(bench.physical_ac_reference(raw, "ac", f, bench.LEGACY_REFERENCE), before)
        # A bad DC solve fails the unchanged all-point gate; it is not dropped.
        raw["ac__dc_load"][0] = 0.5
        bad = bench.physical_ac_reference(raw, "ac", f, bench.REFERENCE)
        self.assertEqual(bench.gate(actual, bad, {"absolute": 1e-9, "relative": 1e-8})["failed_points"], 1)
        for invalid in (np.array([1., 2., 3.]), np.array([0., 0., 2.])):
            with self.assertRaises(ValueError):
                bench.physical_ac_reference(raw, "ac", invalid, bench.REFERENCE)
        request = bench.initial_plan()["cases"][-1]["request"]
        request["channel"]["value"].update(dcResistanceOhmPerM=0, sourceImpedance=35, loadImpedance=90)
        self.assertEqual(bench.material_transfer(request, f, exact_dc=True)[0], 180 / 125)

    @unittest.skipIf(np is None, "NumPy is needed for versioned netlist checks")
    def test_v2_material_table_and_solver_settings_are_not_silently_upgraded(self):
        plan = bench.initial_plan("physical-voltage-v1")
        plan.update(schema=bench.TABLE_SCHEMA, reference=copy.deepcopy(bench.TABLE_REFERENCE))
        bench.validate_plan(plan)
        text, rows = bench.netlist(plan["cases"][-1]["request"], plan["reference"])
        self.assertEqual(len(rows), 513)
        self.assertIn("R_PER_M=pwl(freq", text)
        self.assertIn("TruncTol=7 ChargeTol=1e-16", text)
        self.assertIn("V_RelTol=1e-9", text)
        self.assertNotIn("W_SAFE", text)
        plan["reference"] = copy.deepcopy(bench.REFERENCE)
        with self.assertRaises(ValueError):
            bench.validate_plan(plan)

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
            lambda p: p.update(candidate_channel_policy="unknown"),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                plan = copy.deepcopy(base)
                mutate(plan)
                with self.assertRaises(ValueError):
                    bench.validate_plan(plan)

    def test_physical_candidate_policy_is_explicit_and_does_not_change_oracle_inputs(self):
        default = bench.initial_plan()
        physical = bench.initial_plan("physical-voltage-v1")
        bench.validate_plan(physical)
        self.assertNotIn("candidate_channel_policy", default)
        self.assertEqual(physical["candidate_channel_policy"], "physical-voltage-v1")
        for key in ("cases", "reference", "voltage_tolerance", "transfer_tolerance", "repeats"):
            self.assertEqual(default[key], physical[key], key)
        with self.assertRaises(ValueError):
            bench.initial_plan("unknown")
        physical.update(schema=bench.LEGACY_SCHEMA, reference=bench.LEGACY_REFERENCE)
        with self.assertRaises(ValueError):
            bench.validate_plan(physical)

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

    @unittest.skipIf(np is None, "NumPy is needed by the ADS evidence verifier")
    def test_physical_transform_diagnostic_preserves_origin_and_window_without_changing_td_gates(self):
        try:
            import verify_channel_native_ads_bench as verifier
        except ModuleNotFoundError as error:
            if error.name.startswith("keysight"):
                self.skipTest("ADS SDK is not installed")
            raise
        plan = bench.initial_plan("physical-voltage-v1")
        for raised_cosine in (False, True):
            with self.subTest(raised_cosine=raised_cosine):
                request = copy.deepcopy(plan["cases"][0]["request"])
                request["channel"]["value"].update(applyRaisedCosineWindow=raised_cosine)
                f = bench.frequencies(request)
                n = 2 * (len(f) - 1)
                kernel = np.zeros(n)
                if raised_cosine:
                    request["channel"]["value"]["lengthM"] = 0
                    ac = np.ones(len(f), dtype=complex)
                    windowed = 0.5 * (1 + np.cos(2 * np.pi * np.arange(len(f)) / n))
                    windowed[-1] = 0
                    kernel[0], kernel[1], kernel[-1] = 0.5, 0.25, 0.25
                else:
                    ac = np.exp(-2j * np.pi * f * 250e-12)
                    windowed = ac
                    kernel[128] = 1
                tx = np.repeat(np.asarray(request["pattern"]["bits"]) * 2 - 1, request["timebase"]["samplesPerUi"]) * request["tx"]["amplitude"]
                arrays = {"physical_channel_windowed_re": windowed.real.copy(), "physical_channel_windowed_im": windowed.imag.copy(),
                          "channel_impulse_v_per_v": kernel.copy(), "channel_output_v": np.convolve(tx, kernel)[:len(tx)]}
                original_plan = copy.deepcopy(plan)
                before = ac.copy()
                good = verifier.physical_transform_diagnostic(request, arrays, ac, plan)
                self.assertTrue(good["passed"])
                self.assertFalse(good["acceptance"])
                self.assertIn("not continuous-time ADS Transient", good["scope"])
                self.assertEqual(plan, original_plan)
                np.testing.assert_array_equal(ac, before)
                for key in arrays:
                    bad_arrays = {name: values.copy() for name, values in arrays.items()}
                    bad_arrays[key][0] += 0.1
                    bad = verifier.physical_transform_diagnostic(request, bad_arrays, ac, plan)
                    self.assertFalse(bad["passed"], key)
                arrays["channel_impulse_v_per_v"] = np.roll(kernel, 1)
                self.assertFalse(verifier.physical_transform_diagnostic(request, arrays, ac, plan)["gates"]["origin_preserving_kernel"]["passed"])

    @unittest.skipIf(np is None, "NumPy is needed by the ADS evidence verifier")
    def test_incomplete_verification_is_explicit_and_empty_selection_cannot_pass(self):
        try:
            import verify_channel_native_ads_bench as verifier
        except ModuleNotFoundError as error:
            if error.name.startswith("keysight"):
                self.skipTest("ADS SDK is not installed")
            raise
        for invalid in (None, "unknown_selection", "duplicate_selection", "missing_cases", "wrong_result_version"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan = bench.initial_plan()
                names = [case["name"] for case in plan["cases"]]
                bench.write_json(root / "plan.json", plan)
                (root / "runner-source.py").write_text("# structural test fixture\n", encoding="ascii")
                selected = ["missing"] if invalid == "unknown_selection" else [names[0]] * 2 if invalid == "duplicate_selection" else []
                bench.write_json(root / "bindings.json", {"plan_sha256": bench.digest(root / "plan.json"),
                    "script_sha256": bench.digest(root / "runner-source.py"), "selected_cases": selected})
                bench.write_json(root / "result.json", {"schema": "sipi.channel.ads-physical-bench-result." + ("v2" if invalid == "wrong_result_version" else "v3"),
                    "planned_cases": names, "all_plan_cases_selected": True,
                    "acceptance": False, "status": "failed", "cases": [] if invalid == "missing_cases" else [
                        {"name": name, "runs": [], "passed": False, "error": "fixture timeout"} for name in names]})
                with self.assertRaises(AssertionError):
                    verifier.verify(root)
                if invalid is not None:
                    with self.assertRaises(AssertionError):
                        verifier.verify(root, allow_incomplete=True)
                else:
                    proof = verifier.verify(root, allow_incomplete=True)
                    self.assertEqual(proof["verification_scope"], "completed_runs_only")
                    self.assertEqual(len(proof["incomplete_cases"]), 7)
                    for flag in ("complete_bench_verified", "verified_artifact_chain", "sdk_reexport_exact",
                                 "all_pointwise_gates_recomputed", "completed_run_gates_recomputed", "acceptance"):
                        self.assertFalse(proof[flag], flag)


if __name__ == "__main__":
    unittest.main()
