"""Contract tests for the five-workbook MATLAB source-warning aggregate."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.aggregate_com_source_warning_observation import aggregate


def trace() -> dict:
    return {
        "schema": "sipi.com.interp-sparam-input-trace.v1", "status": "captured",
        "element_count": 8001, "first_real": 0.0, "first_imaginary": 0.0,
        "last_real": 0.0, "last_imaginary": 0.0, "sum_real": 0.0,
        "sum_imaginary": 0.0, "maximum_magnitude": 1.0, "mean_unwrapped_phase_step": 0.1,
        "positive_mean_phase_step": True,
    }


def anti_stack() -> dict:
    return {
        "schema": "sipi.com.source-warning-stack.v1", "status": "captured",
        "frames": [
            {"name": "warning", "line": 55},
            {"name": "interp_Sparam", "line": 6337},
            {"name": "s21_to_impulse_DC", "line": 10110},
            {"name": "get_TDR", "line": 5427},
            {"name": "process_sxp", "line": 8408},
            {"name": "com_ieee8023_480", "line": 332},
            {"name": "sipi_com_tdiln_matrix_diagnostic_v1", "line": 51},
        ],
    }


def no_stack() -> dict:
    return {"schema": "sipi.com.source-warning-stack.v1", "status": "not_requested"}


def report(index: int) -> dict:
    events = [{"sequence": 1, "identifier": "", "source_line": 6337, "source_stack": anti_stack(), "source_trace": trace()}]
    if index in (8, 10, 12):
        events = [
            {"sequence": sequence, "identifier": "COM:read_s4p:MaxFreqTooLow", "source_line": 9715, "source_stack": no_stack(), "source_trace": {"schema": "sipi.com.interp-sparam-input-trace.v1", "status": "not_requested"}}
            for sequence in range(1, 4)
        ] + [{"sequence": 4, "identifier": "", "source_line": 6337, "source_stack": anti_stack(), "source_trace": trace()}]
    return {
        "schema": "sipi.com.source-warning-observation-run.v1", "diagnostic_only": True,
        "non_claims": ["not_rust_parity", "not_complete_warning_catalog", "not_release_evidence"],
        "source_commit_unverified": True, "matlab_harness_sha256": "a" * 64,
        "matlab_launch": "python_engine_noFigureWindows_singleCompThread", "status": "passed_observation",
        "records": [{"workbook_index": index, "workbook": f"workbook-{index}", "status": "passed_observation", "matlab_summary_sha256": f"{index:064x}", "core_duration_seconds": 1.0, "events": events}],
    }


class AggregateSourceWarningObservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def reports(self) -> list[tuple[Path, dict]]:
        values = []
        for index in (0, 2, 8, 10, 12):
            path = Path(self.temporary.name) / f"report-{index}.json"
            value = report(index)
            path.write_text(json.dumps(value), encoding="utf-8")
            values.append((path, value))
        return values

    def test_exact_corpus_passes(self) -> None:
        self.assertEqual(aggregate(self.reports())["status"], "passed_observation")

    def test_order_and_trace_drift_are_rejected(self) -> None:
        reports = self.reports()
        drift = copy.deepcopy(reports)
        drift[2][1]["records"][0]["events"][0]["source_line"] = 6337
        with self.assertRaisesRegex(ValueError, "order"):
            aggregate(drift)
        drift = self.reports()
        drift[0][1]["records"][0]["events"][0]["source_trace"]["positive_mean_phase_step"] = False
        with self.assertRaisesRegex(ValueError, "predicate"):
            aggregate(drift)

    def test_stack_identity_drift_is_rejected(self) -> None:
        reports = self.reports()
        reports[0][1]["records"][0]["events"][0]["source_stack"]["frames"][3]["name"] = "wrong_stage"
        with self.assertRaisesRegex(ValueError, "stack identity"):
            aggregate(reports)

    def test_harness_or_index_set_drift_is_rejected(self) -> None:
        reports = self.reports()
        reports[-1][1]["matlab_harness_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "harness"):
            aggregate(reports)
        reports = self.reports()[:-1]
        with self.assertRaisesRegex(ValueError, "five reports"):
            aggregate(reports)


if __name__ == "__main__":
    unittest.main()
