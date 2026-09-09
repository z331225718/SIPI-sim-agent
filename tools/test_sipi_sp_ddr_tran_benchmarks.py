"""Test suite for SIPI SP, DDR, and TRAN benchmark generator and output report."""

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "results/sipi-benchmarks-sp-ddr-tran-20260910"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class SipiSpDdrTranBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result_path = BENCH_DIR / "result.json"
        cls.report_path = BENCH_DIR / "report.html"
        if not cls.result_path.is_file() or not cls.report_path.is_file():
            raise unittest.SkipTest("Benchmark directory not yet generated")
        with cls.result_path.open(encoding="utf-8") as f:
            cls.result = json.load(f)

    def test_result_schema_and_case_count(self):
        self.assertEqual(self.result["schema"], "sipi.benchmarks.sp-ddr-tran.v1")
        self.assertEqual(len(self.result["cases"]), 8)
        self.assertTrue(len(self.result["sipi_executable_sha256"]) >= 16)

    def test_artifacts_exist_and_hashes_match(self):
        artifacts = self.result["artifacts"]
        self.assertGreaterEqual(len(artifacts), 16)
        for name, expected_hash in artifacts.items():
            path = BENCH_DIR / name
            self.assertTrue(path.is_file(), f"Missing artifact: {name}")
            self.assertGreater(path.stat().st_size, 0, f"Empty artifact: {name}")
            actual_hash = digest(path)
            self.assertEqual(actual_hash, expected_hash, f"Hash mismatch on {name}")

    def test_report_html_contains_all_domains_and_sections(self):
        html = self.report_path.read_text(encoding="utf-8")
        self.assertIn("S-Parameter", html)
        self.assertIn("DDR Interface", html)
        self.assertIn("Transient & PDN", html)
        self.assertIn("Broadband Lossy Microstrip", html)
        self.assertIn("Via Stub Resonant Notch", html)
        self.assertIn("4-Port Mixed-Mode Decomposition", html)
        self.assertIn("DDR4-3200 DQ Rx Mask Compliance", html)
        self.assertIn("DDR5-6400 4-Tap DFE vs JEDEC Mask", html)
        self.assertIn("TDR Impedance Profile Reconstruction", html)
        self.assertIn("PDN Decoupling Impedance Profile", html)
        self.assertIn("Core Rail Dynamic Current Droop", html)

    def test_case_1_lossy_microstrip(self):
        c1 = next(c for c in self.result["cases"] if c["name"] == "Broadband Lossy Microstrip")
        self.assertTrue(c1["passivity_passed"])
        self.assertTrue(c1["reciprocity_passed"])
        self.assertGreater(c1["max_il_db"], 5.0)

    def test_case_2_resonant_stub_notch(self):
        c2 = next(c for c in self.result["cases"] if c["name"] == "Via Stub Resonant Notch")
        self.assertAlmostEqual(c2["notch_frequency_ghz"], 15.0, delta=0.2)
        self.assertGreater(c2["notch_depth_db"], 20.0)

    def test_case_4_and_5_ddr_compliance(self):
        c4 = next(c for c in self.result["cases"] if c["name"] == "DDR4-3200 DQ Rx Mask Compliance")
        self.assertTrue(c4["jedec_passed"])
        self.assertGreater(c4["voltage_margin_mv"], 0.0)

        c5 = next(c for c in self.result["cases"] if c["name"] == "DDR5-6400 4-Tap DFE vs JEDEC Mask")
        self.assertFalse(c5["unequalized_passed"])
        self.assertTrue(c5["dfe_equalized_passed"])

    def test_case_6_7_8_tran_and_pdn(self):
        c6 = next(c for c in self.result["cases"] if c["name"] == "TDR Impedance Profile Reconstruction")
        self.assertAlmostEqual(c6["nominal_z0_ohms"], 50.0, delta=0.1)
        self.assertAlmostEqual(c6["mismatched_step_ohms"], 75.0, delta=0.5)

        c7 = next(c for c in self.result["cases"] if c["name"] == "PDN Decoupling Impedance Profile")
        self.assertAlmostEqual(c7["target_impedance_mohm"], 4.25, places=2)

        c8 = next(c for c in self.result["cases"] if c["name"] == "Core Rail Dynamic Current Droop")
        self.assertTrue(c8["passed"])
        self.assertLessEqual(c8["max_droop_mv"], c8["allowed_droop_mv"])


if __name__ == "__main__":
    unittest.main()
