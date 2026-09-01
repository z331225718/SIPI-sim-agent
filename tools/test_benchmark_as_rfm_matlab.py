"""Focused validation tests for the AS RFM performance harness."""

from __future__ import annotations

import copy
import unittest

try:
    from tools import benchmark_as_rfm_matlab as bench
except ModuleNotFoundError:  # Direct ``python tools/test_...py`` invocation.
    import benchmark_as_rfm_matlab as bench


def valid_report(*, frequency_count: int = 65_536, response_count: int = 1) -> dict[str, object]:
    return {
        "schema": "sipi.as-performance-rfm-kernel.v1",
        "status": "observed",
        "workload": {
            "frequency_count": frequency_count,
            "response_count": response_count,
            "fmax_hz": 200.0e9,
        },
        "durations_ns": [100, 120, 110, 105, 115],
        "warmup_completed": True,
        "checksum": {
            "sum_real": 1.0,
            "sum_imag": 2.0,
            "sum_abs_squared": 3.0,
            "first_re": 4.0,
            "first_im": 5.0,
        },
    }


class BenchmarkValidationTests(unittest.TestCase):
    def test_validate_report_accepts_integer_timing_samples(self) -> None:
        report = valid_report()
        bench.validate_report(
            report,
            {"frequency_count": 65_536, "response_count": 1, "fmax_hz": 200.0e9, "repetitions": 5},
            "Rust",
        )

    def test_validate_report_accepts_matlab_seconds(self) -> None:
        report = valid_report()
        report.pop("durations_ns")
        report["durations_seconds"] = [1.0e-7, 1.2e-7, 1.1e-7, 1.05e-7, 1.15e-7]
        bench.validate_report(
            report,
            {"frequency_count": 65_536, "response_count": 1, "fmax_hz": 200.0e9, "repetitions": 5},
            "MATLAB",
        )

    def test_validate_report_rejects_workload_shape_drift(self) -> None:
        report = valid_report()
        report["workload"] = copy.deepcopy(report["workload"])
        assert isinstance(report["workload"], dict)
        report["workload"]["frequency_count"] = 65_535
        with self.assertRaises(bench.BenchmarkError):
            bench.validate_report(
                report,
                {"frequency_count": 65_536, "response_count": 1, "fmax_hz": 200.0e9, "repetitions": 5},
                "Rust",
            )

    def test_within_tolerance_rejects_nonmatching_checksum(self) -> None:
        left = {"sum_real": 1.0, "sum_imag": 2.0, "sum_abs_squared": 3.0, "first_re": 4.0, "first_im": 5.0}
        right = dict(left)
        right["sum_real"] = 1.0e-3
        delta = bench.checksum_delta(left, right)
        self.assertFalse(bench.within_tolerance(delta, left, right))


if __name__ == "__main__":
    unittest.main()
