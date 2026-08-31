from __future__ import annotations

import copy
import unittest

from tools.compare_com_tdiln_matrix_diagnostic import compare


def vector(seed: float) -> dict[str, float | int]:
    return {
        "length": 3,
        "first": seed,
        "last": seed + 2.0,
        "minimum": seed,
        "maximum": seed + 2.0,
        "sum": seed * 3.0 + 3.0,
        "sum_squares": seed * seed + (seed + 1.0) ** 2 + (seed + 2.0) ** 2,
    }


def documents() -> tuple[dict, dict]:
    matlab_tdiln = {
        "fom": 1.0,
        "fom_pdf": 2.0,
        "snr_isi_fom": 3.0,
        "snr_isi_fom_pdf": 4.0,
        "time": vector(1.0),
        "iln": vector(2.0),
        "reference_pr": vector(3.0),
        "fitted_pr": vector(4.0),
    }
    matlab = {
        "schema": "sipi.com.tdiln-matrix-diagnostic.v1",
        "diagnostic_only": True,
        "core_duration_seconds": 10.0,
        "case_count": 1,
        "cases": [{"case_index": 0, "com_db": 5.0, "erl_db": 6.0, "tdiln_applicable": True, "tdiln_inapplicable_reason": None, "fom_tdiln": 4.0, "tdiln": matlab_tdiln}],
    }
    rust = {
        "cases": [{
            "case_index": 0,
            "metrics": {"COM_dB": 5.0, "ERL": 6.0, "FOM_TDILN": 4.0},
            "diagnostics": {"tdiln": {
                "fom_v": 1.0,
                "fom_pdf_v": 2.0,
                "snr_isi_fom_db": 3.0,
                "snr_isi_fom_pdf_db": 4.0,
                "vector_summaries": {
                    "time": vector(1.0),
                    "iln": vector(2.0),
                    "reference_pr": vector(3.0),
                    "fitted_pr": vector(4.0),
                    "iln_db": vector(5.0),
                },
            }},
        }],
    }
    return matlab, rust


class TdilnMatrixDiagnosticComparisonTests(unittest.TestCase):
    def test_matching_receipts_and_faster_rust_pass(self) -> None:
        matlab, rust = documents()
        report = compare(matlab, rust, rust_wall_seconds=9.0, tolerance=1.0e-9)
        self.assertEqual(report["status"], "passed_diagnostic")
        self.assertTrue(report["timing"]["rust_not_slower"])

    def test_slower_rust_blocks_even_when_numeric_receipts_match(self) -> None:
        matlab, rust = documents()
        report = compare(matlab, rust, rust_wall_seconds=10.1, tolerance=1.0e-9)
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["timing"]["rust_not_slower"])

    def test_vector_length_drift_blocks(self) -> None:
        matlab, rust = documents()
        rust = copy.deepcopy(rust)
        rust["cases"][0]["diagnostics"]["tdiln"]["vector_summaries"]["iln"]["length"] = 4
        report = compare(matlab, rust, rust_wall_seconds=9.0, tolerance=1.0e-9)
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["cases"][0]["vector_summaries"]["iln"]["length_equal"])

    def test_equal_infinite_erl_is_observed_not_rejected(self) -> None:
        matlab, rust = documents()
        matlab["cases"][0]["erl_db"] = "+Inf"
        rust["cases"][0]["metrics"]["ERL"] = "inf"
        report = compare(matlab, rust, rust_wall_seconds=9.0, tolerance=1.0e-9)
        self.assertEqual(report["status"], "passed_diagnostic")
        self.assertEqual(
            report["cases"][0]["scalar_special_tokens"]["erl_db"],
            {"matlab": "+Inf", "rust": "+Inf", "equal": True},
        )

    def test_source_inapplicable_tdiln_requires_rust_to_omit_it(self) -> None:
        matlab, rust = documents()
        matlab["cases"][0].update({
            "tdiln_applicable": False,
            "tdiln_inapplicable_reason": "source_did_not_emit_FOM_TDILN_and_TD_ILN",
            "fom_tdiln": None,
            "tdiln": None,
        })
        rust["cases"][0]["metrics"]["FOM_TDILN"] = None
        rust["cases"][0]["diagnostics"]["tdiln"] = None
        report = compare(matlab, rust, rust_wall_seconds=9.0, tolerance=1.0e-9)
        self.assertEqual(report["status"], "passed_diagnostic")
        self.assertEqual(report["tdiln_applicable_case_count"], 0)
        self.assertTrue(report["cases"][0]["rust_tdiln_absent"])

    def test_source_inapplicable_tdiln_blocks_a_rust_payload(self) -> None:
        matlab, rust = documents()
        matlab["cases"][0].update({
            "tdiln_applicable": False,
            "tdiln_inapplicable_reason": "source_did_not_emit_FOM_TDILN_and_TD_ILN",
            "fom_tdiln": None,
            "tdiln": None,
        })
        report = compare(matlab, rust, rust_wall_seconds=9.0, tolerance=1.0e-9)
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["cases"][0]["rust_tdiln_absent"])

    def test_missing_summary_field_is_rejected(self) -> None:
        matlab, rust = documents()
        del rust["cases"][0]["diagnostics"]["tdiln"]["vector_summaries"]["time"]["sum"]
        with self.assertRaisesRegex(ValueError, "key set drift"):
            compare(matlab, rust, rust_wall_seconds=9.0, tolerance=1.0e-9)


if __name__ == "__main__":
    unittest.main()
