"""Mutation tests for historical selected-S4P source-drift reconciliation."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from verify_p3c_selected_s4p_historical_observation_source_drift import VerificationError, verify_document
BASELINE = ROOT / "docs/baselines/p3c-selected-s4p-historical-observation-source-drift.v1.yaml"


class HistoricalSourceDriftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))

    def rejects(self, mutate) -> None:
        document = copy.deepcopy(self.document)
        mutate(document)
        with self.assertRaises(VerificationError):
            verify_document(document)

    def test_baseline_is_valid(self) -> None:
        self.assertTrue(verify_document(self.document)["valid"])

    def test_history_cannot_be_rewritten_or_current(self) -> None:
        self.rejects(lambda value: value["gates"].__setitem__("historical_records_rewritten", True))
        self.rejects(lambda value: value["gates"].__setitem__("historical_records_current", True))

    def test_candidate_or_release_promotion_rejects(self) -> None:
        self.rejects(lambda value: value["gates"].__setitem__("candidate_waveform_generated", True))
        self.rejects(lambda value: value["gates"].__setitem__("release_ledger_promoted", True))

    def test_drift_record_mutation_rejects(self) -> None:
        self.rejects(lambda value: value["historical_records"][0].__setitem__("expected_error", "anything_else"))


if __name__ == "__main__":
    unittest.main()
