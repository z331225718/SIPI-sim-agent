"""Tests for the P2-06 stage-compare coverage record verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p2_06_stage_compare_coverage as GATE


class StageCoverageTests(unittest.TestCase):
    def test_current_record_is_valid(self) -> None:
        record = GATE.load_json(GATE.RECORD)
        result = GATE.validate(record, ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["stages"], 4)

    def test_record_covers_all_four_stages(self) -> None:
        record = GATE.load_json(GATE.RECORD)
        self.assertEqual(set(record["stages"]), GATE.REQUIRED_STAGES)

    def test_parsed_circuit_not_applicable_in_current_surface(self) -> None:
        record = GATE.load_json(GATE.RECORD)
        self.assertEqual(record["stages"]["parsed_circuit"]["status"], "not_applicable_current_surface")

    def test_measurements_not_implemented(self) -> None:
        record = GATE.load_json(GATE.RECORD)
        self.assertEqual(record["stages"]["measurements"]["status"], "not_implemented")

    def test_waveforms_covered_observables(self) -> None:
        record = GATE.load_json(GATE.RECORD)
        self.assertEqual(record["stages"]["waveforms"]["observables"], ["time", "v(in)", "v(out)"])

    def test_current_evidence_binds_v4_record(self) -> None:
        record = GATE.load_json(GATE.RECORD)
        current = record["current_evidence"]
        self.assertEqual(current["archive_commit"], "538b5dd08f734e5558b1179083c3d24a95aba02f")
        self.assertEqual(current["replay_count"], 2)

    def test_historical_evidence_keeps_drift_markers(self) -> None:
        record = GATE.load_json(GATE.RECORD)
        statuses = {entry["status"] for entry in record["historical_evidence"]}
        self.assertIn("source_drift_historical", statuses)

    def test_rejects_stage_drift(self) -> None:
        record = GATE.load_json(GATE.RECORD)
        record["stages"]["parsed_circuit"]["status"] = "covered"
        with self.assertRaises(GATE.StageCoverageError):
            GATE.validate(record, ROOT)

    def test_rejects_evidence_drift(self) -> None:
        record = GATE.load_json(GATE.RECORD)
        record["current_evidence"]["replay_count"] = 3
        with self.assertRaises(GATE.StageCoverageError):
            GATE.validate(record, ROOT)

    def test_rejects_missing_drift_marker(self) -> None:
        record = GATE.load_json(GATE.RECORD)
        for entry in record["historical_evidence"]:
            entry["status"] = "historical"
        with self.assertRaises(GATE.StageCoverageError):
            GATE.validate(record, ROOT)


if __name__ == "__main__":
    unittest.main()
