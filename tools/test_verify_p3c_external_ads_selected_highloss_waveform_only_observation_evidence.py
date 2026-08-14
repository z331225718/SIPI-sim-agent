from __future__ import annotations

import copy
from pathlib import Path
import unittest

import yaml

import verify_p3c_external_ads_selected_highloss_waveform_only_observation_evidence as gate


ROOT = Path(__file__).resolve().parents[1]


class WaveformOnlyEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-external-ads-selected-highloss-waveform-only-observation-evidence.v3.yaml").read_text(encoding="utf-8"))

    def test_observation_shape(self) -> None:
        self.assertTrue(gate.verify_document(self.document)["waveform_nrmse_evaluated"])

    def test_metric_or_gate_mutation_fails_closed(self) -> None:
        document = copy.deepcopy(self.document)
        document["external_observation"]["runs"][0]["waveform_nrmse_bits"] = "0" * 16
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)
        document = copy.deepcopy(self.document)
        document["admission"]["selected_highloss_waveform_only_profile_accepted"] = True
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)

    def test_evidence_leak_fails_closed(self) -> None:
        document = copy.deepcopy(self.document)
        document["non_claims"].append("file://secret")
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)


if __name__ == "__main__":
    unittest.main()
