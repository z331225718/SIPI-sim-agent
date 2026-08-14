"""Mutation tests for the 04ag waveform-only historical source-drift record."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest

import yaml

from verify_p3c_external_ads_selected_highloss_waveform_only_historical_source_drift import VerificationError, verify_document


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/baselines/p3c-external-ads-selected-highloss-waveform-only-historical-source-drift.v1.yaml"


class WaveformOnlyHistoricalSourceDriftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))

    def rejects(self, mutate) -> None:
        document = copy.deepcopy(self.document)
        mutate(document)
        with self.assertRaises(VerificationError):
            verify_document(document)

    def test_baseline_is_fail_closed(self) -> None:
        result = verify_document(self.document)
        self.assertTrue(result["valid"])
        self.assertFalse(result["current_external_binding_evaluated"])

    def test_history_and_current_binding_cannot_be_promoted(self) -> None:
        self.rejects(lambda value: value["gates"].__setitem__("historical_record_current", True))
        self.rejects(lambda value: value["gates"].__setitem__("current_external_reference_binding_evaluated", True))
        self.rejects(lambda value: value["gates"].__setitem__("selected_highloss_waveform_only_profile_accepted", True))

    def test_drift_binding_and_leak_mutations_fail(self) -> None:
        self.rejects(lambda value: value["historical_record"].__setitem__("expected_error", "anything_else"))
        self.rejects(lambda value: value["blockers"].remove("waveform_only_product_source_drift"))
        self.rejects(lambda value: value["non_claims"].append("file://private"))


if __name__ == "__main__":
    unittest.main()
