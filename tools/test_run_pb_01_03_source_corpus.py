"""Focused mechanical tests for the PB-01/PB-03 archive replay harness."""

from __future__ import annotations

import unittest

from tools import run_pb_01_03_source_corpus as runner


class SourceCorpusRunnerTests(unittest.TestCase):
    def test_pb03_cases_are_exact_and_distinct(self) -> None:
        base = b"ctle_enable: false\npeak_mag: 1.7\ngain: 0.1\n"
        self.assertEqual(runner.pb03_input(base, "pb03_baseline"), base)
        self.assertEqual(
            runner.pb03_input(base, "pb03_analytic_ctle"),
            b"ctle_enable: true\npeak_mag: 4.0\ngain: 0.1\n",
        )
        self.assertEqual(
            runner.pb03_input(base, "pb03_gain_rejected"),
            b"ctle_enable: false\npeak_mag: 1.7\ngain: 1.1\n",
        )

    def test_unknown_pb03_case_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unknown PB-03 case"):
            runner.pb03_input(b"gain: 0.1\n", "made_up")

    def test_contract_constants_are_deliberately_bounded(self) -> None:
        self.assertEqual(len(runner.PB01_NAMES), 23)
        self.assertEqual(runner.PB01_NAMES[-1], "tx_out")
        self.assertEqual((runner.PB01_RTOL, runner.PB01_ATOL), (1.0e-6, 1.0e-7))
        self.assertEqual((runner.PB03_RTOL, runner.PB03_ATOL), (1.0e-9, 1.0e-12))
        self.assertEqual(
            runner.PB03_EXCLUSIONS,
            (
                "$.input_file",
                "$.backend_metadata.run_id",
                "$.backend_metadata.engine.build",
                "$.diagnostics.events[].runId",
            ),
        )


if __name__ == "__main__":
    unittest.main()
