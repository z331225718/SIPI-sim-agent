"""Focused tests for the AS-03 diagnostic corpus protocol."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools import probe_as03_openblas_oracle as probe


class ProbeCorpusTests(unittest.TestCase):
    def test_case_dimensions_categories_and_shape(self) -> None:
        document = probe.make_cases()
        self.assertEqual(document["schema"], probe.CASE_SCHEMA)
        self.assertEqual(document["dimensions"], [1, 2, 3, 4, 8, 16, 32])
        self.assertEqual(len(document["cases"]), 21)
        for case in document["cases"]:
            self.assertEqual(len(case["s_bits"]), case["n"] ** 2)
            self.assertIn(case["category"], {"well_conditioned", "pivot", "near_singular"})

    def test_case_corpus_digest_is_stable(self) -> None:
        self.assertEqual(probe._sha(probe._canonical(probe.make_cases())), "970eb4cef460a8d774dfd0ff6accc26de7b915bf528bcb877043a6a1488308dd")

    def test_all_f64_bits_are_finite_and_fixed_width(self) -> None:
        for case in probe.make_cases()["cases"]:
            for cell in case["s_bits"]:
                self.assertRegex(cell["re_bits"], r"^[0-9a-f]{16}$")
                self.assertRegex(cell["im_bits"], r"^[0-9a-f]{16}$")
                self.assertTrue(probe._unbits(cell["re_bits"]) == probe._unbits(cell["re_bits"]))

    def test_compare_exact_synthetic_results(self) -> None:
        cases = probe.make_cases()
        outputs = {
            "schema": "synthetic",
            "cases": [
                {
                    "id": case["id"],
                    "n": case["n"],
                    "status": "accepted",
                    "condition_bits": "3ff0000000000000",
                    "matrix_bits": case["s_bits"],
                }
                for case in cases["cases"]
            ],
        }
        result = probe.compare_outputs(cases, outputs, copy.deepcopy(outputs))
        self.assertTrue(result["matrix_bit_exact"])
        self.assertEqual(result["exact_case_count"], 21)
        self.assertEqual(result["max_ulp"], 0)
        self.assertIsNone(result["first_difference"])

    def test_compare_reports_first_bit_difference(self) -> None:
        cases = probe.make_cases()
        outputs = {
            "cases": [
                {
                    "id": case["id"],
                    "n": case["n"],
                    "status": "accepted",
                    "condition_bits": "3ff0000000000000",
                    "matrix_bits": copy.deepcopy(case["s_bits"]),
                }
                for case in cases["cases"]
            ]
        }
        outputs["cases"][0]["matrix_bits"][0]["re_bits"] = "3ff0000000000001"
        result = probe.compare_outputs(cases, outputs, copy.deepcopy(outputs))
        self.assertTrue(result["matrix_bit_exact"])
        candidate = copy.deepcopy(outputs)
        candidate["cases"][0]["matrix_bits"][0]["re_bits"] = "3ff0000000000000"
        result = probe.compare_outputs(cases, outputs, candidate)
        self.assertFalse(result["matrix_bit_exact"])
        self.assertEqual(result["first_difference"]["case_id"], "n01-well_conditioned")
        self.assertEqual(result["first_difference"]["ulp"], 1)

    def test_compare_rejects_case_set_drift(self) -> None:
        cases = probe.make_cases()
        outputs = {"cases": []}
        with self.assertRaisesRegex(RuntimeError, "case set drift"):
            probe.compare_outputs(cases, outputs, outputs)

    def test_marker_protocol_rejects_ambiguous_output(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "missing or ambiguous"):
            probe._parse_marker(b"AS03_OPENBLAS_ORACLE_NUMPY_V1={}\nAS03_OPENBLAS_ORACLE_NUMPY_V1={}\n", probe.PYTHON_MARKER)

    def test_path_grammar_rejects_absolute_and_traversal(self) -> None:
        for value in (r"C:\repo\x", "/repo/x", r"\\server\share\x", "../x", r"a\..\x"):
            with self.assertRaises(RuntimeError):
                probe._safe_relative(value)
        self.assertEqual(probe._safe_relative(r"docs\baselines\x.json"), Path("docs", "baselines", "x.json"))

    def test_report_validation_is_fail_closed(self) -> None:
        result = probe.validate_report(
            {
                "schema": probe.REPORT_SCHEMA,
                "status": "wrong",
                "integrity_gate": "passed",
                "parity_claim": True,
                "numeric_parity": True,
            }
        )
        self.assertIn("report status", result)
        self.assertIn("report claims", result)
        self.assertIn("corpus shape", result)

    def test_source_match_uses_bytes_and_sha(self) -> None:
        expected = ("deadbeef", 3, "a" * 64)
        self.assertTrue(probe._source_match({"bytes": 3, "sha256": "a" * 64}, expected))
        self.assertFalse(probe._source_match({"bytes": 4, "sha256": "a" * 64}, expected))
        self.assertFalse(probe._source_match({"bytes": 3, "sha256": "b" * 64}, expected))

    def test_rust_probe_is_private_and_path_free(self) -> None:
        self.assertIn("as03_openblas_oracle_corpus_probe_v1", probe.RUST_PROBE_SUFFIX)
        self.assertNotIn("C:\\", probe.RUST_PROBE_SUFFIX)
        self.assertNotIn("crate::", probe.RUST_PROBE_SUFFIX)


if __name__ == "__main__":
    unittest.main()
