from __future__ import annotations

import copy
from pathlib import Path
import unittest
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3c_external_ads_reference_metric_rejection_reason_evidence as gate




class MetricRejectionReasonEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-external-ads-reference-metric-rejection-reason-evidence.v1.yaml").read_text(encoding="utf-8"))

    def test_baseline_shape(self) -> None:
        self.assertEqual(gate.verify_document(self.document)["direct_metric_core_reason"], "zero_reference_eye_width")

    def test_reason_cannot_be_rewritten(self) -> None:
        document = copy.deepcopy(self.document)
        document["external_observation"]["report_outcome"]["runs"][0]["direct_core_reason"] = "crossing_missing_reference"
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)

    def test_cli_envelope_identity_cannot_be_dropped(self) -> None:
        document = copy.deepcopy(self.document)
        del document["external_observation"]["report_outcome"]["runs"][0]["cli_stderr_sha256"]
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)

    def test_reason_observation_cannot_promote_metric_acceptance(self) -> None:
        document = copy.deepcopy(self.document)
        document["admission"]["candidate_waveform_eye_tie_metrics_accepted"] = True
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)

    def test_historical_drift_binding_cannot_be_relaxed(self) -> None:
        document = copy.deepcopy(self.document)
        document["supersedes_historical_observation"]["current_verifier_result"] = "valid"
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)


if __name__ == "__main__":
    unittest.main()

