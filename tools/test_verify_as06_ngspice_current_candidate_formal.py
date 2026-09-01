"""Focused mutation checks for the AS-06 current-candidate formal verifier."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import verify_as06_ngspice_current_candidate_formal as verifier


ROOT = Path(__file__).resolve().parents[1]


def load_report(index: int) -> dict:
    return json.loads((ROOT / verifier.REPORTS[index]).read_text(encoding="utf-8"))


class As06CurrentCandidateFormalTests(unittest.TestCase):
    def test_known_reports_build_the_scoped_aggregate(self) -> None:
        aggregate = verifier._aggregate_documents(
            tuple(ROOT / path for path in verifier.REPORTS)
        )
        self.assertEqual(aggregate["status"], verifier.STATUS)
        self.assertEqual(aggregate["result"], verifier.RESULT)

    def test_report_schema_drift_is_rejected(self) -> None:
        report = load_report(0)
        report["schema"] = "other"
        with self.assertRaisesRegex(ValueError, "header"):
            verifier._validate_report(report, verifier.RUNS[0])

    def test_cross_run_nonce_reuse_is_rejected(self) -> None:
        first = load_report(0)
        second = load_report(1)
        second["fresh_run_nonce"] = first["fresh_run_nonce"]
        first_path = ROOT / verifier.REPORTS[0]
        second_path = ROOT / verifier.REPORTS[1]
        original_loader = verifier._load_json

        def substituted(path: Path):
            if path == second_path:
                raw = json.dumps(second, sort_keys=True, indent=2).encode("utf-8") + b"\n"
                return second, raw, verifier._sha_bytes(raw)
            return original_loader(path)

        verifier._load_json = substituted
        try:
            with self.assertRaisesRegex(ValueError, "fresh_run_nonce"):
                verifier._aggregate_documents((first_path, second_path))
        finally:
            verifier._load_json = original_loader

    def test_absolute_path_is_rejected(self) -> None:
        report = copy.deepcopy(load_report(0))
        report["physical"]["rust_stdout"]["basename"] = r"C:\\Users\\unsafe.log"
        with self.assertRaisesRegex(ValueError, "basename"):
            verifier._validate_report(report, verifier.RUNS[0])


if __name__ == "__main__":
    unittest.main()
