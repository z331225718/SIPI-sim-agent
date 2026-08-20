from __future__ import annotations

import copy
from pathlib import Path
import unittest
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3c_selected_oob_zero_extension_sensitivity_observation_evidence as gate




class OobSensitivityObservationEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(
            (ROOT / "docs/baselines/p3c-selected-oob-zero-extension-sensitivity-observation-evidence.v1.yaml").read_text(encoding="utf-8")
        )

    def test_baseline_shape(self) -> None:
        self.assertTrue(gate.verify_document(self.document)["oob_sensitivity_observed"])

    def test_variant_result_and_policy_promotion_cannot_change(self) -> None:
        document = copy.deepcopy(self.document)
        document["external_observation"]["strict_gt_40ghz_positive_zero"]["waveform_nrmse_bits"] = "0" * 16
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)
        document = copy.deepcopy(self.document)
        document["admission"]["zero_oob_variant_admitted_as_product_policy"] = True
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)

    def test_freshness_and_leak_cannot_change(self) -> None:
        document = copy.deepcopy(self.document)
        document["external_observation"]["source_manifest_sha256s"][1] = document["external_observation"]["source_manifest_sha256s"][0]
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)
        document = copy.deepcopy(self.document)
        document["non_claims"].append("C:\\external\\payload")
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)


if __name__ == "__main__":
    unittest.main()

