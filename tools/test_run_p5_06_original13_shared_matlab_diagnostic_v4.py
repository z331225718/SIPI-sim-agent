"""Focused tests for the shared MATLAB diagnostic harness."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.run_p5_06_original13_shared_matlab_diagnostic_v4 import stage


class StageTests(unittest.TestCase):
    def test_accepts_exact_summary_stage_for_matching_nonce(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stage.json"
            path.write_text(json.dumps({
                "schema": "sipi.com.final-surface-stage.v3",
                "nonce": "a" * 64,
                "stage": "summary_written",
            }), encoding="utf-8")
            self.assertEqual(stage(path, "a" * 64), "summary_written")

    def test_rejects_extra_key_or_wrong_nonce(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stage.json"
            path.write_text(json.dumps({
                "schema": "sipi.com.final-surface-stage.v3",
                "nonce": "a" * 64,
                "stage": "summary_written",
                "extra": True,
            }), encoding="utf-8")
            self.assertIsNone(stage(path, "a" * 64))
            path.write_text(json.dumps({
                "schema": "sipi.com.final-surface-stage.v3",
                "nonce": "b" * 64,
                "stage": "summary_written",
            }), encoding="utf-8")
            self.assertIsNone(stage(path, "a" * 64))


if __name__ == "__main__":
    unittest.main()
