from __future__ import annotations

import copy
from pathlib import Path
import unittest
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3c_external_ads_reference_metric_observation_evidence as gate




class MetricObservationEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-external-ads-reference-metric-observation-evidence.v1.yaml").read_text(encoding="utf-8"))

    def test_baseline_shape(self) -> None:
        self.assertEqual(gate.verify_document(self.document)["metric_evaluation"], "rejected")

    def test_non_contract_cli_failure_cannot_be_observed(self) -> None:
        document = copy.deepcopy(self.document)
        document["external_observation"]["report_outcome"]["runs"][0]["exit_code"] = 5
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)

    def test_rejected_metric_cannot_promote_acceptance(self) -> None:
        document = copy.deepcopy(self.document)
        document["admission"]["candidate_waveform_eye_tie_metrics_accepted"] = True
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)

    def test_clean_archive_tree_cannot_drift(self) -> None:
        document = copy.deepcopy(self.document)
        document["external_observation"]["clean_archive_tree"] = "0" * 40
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)


if __name__ == "__main__":
    unittest.main()

