from __future__ import annotations

import copy
from pathlib import Path
import unittest
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3c_selected_s4p_candidate_observation_evidence as gate




class CandidateEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-selected-s4p-candidate-observation-evidence.v1.yaml").read_text(encoding="utf-8"))

    def test_baseline_shape(self) -> None:
        self.assertTrue(gate.verify_document(self.document)["candidate_observed"])

    def test_candidate_gate_cannot_promote_reference(self) -> None:
        document = copy.deepcopy(self.document)
        document["admission"]["external_reference_binding_evaluated"] = True
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)

    def test_digest_or_drift_token_cannot_change(self) -> None:
        document = copy.deepcopy(self.document)
        document["external_observation"]["outcome"]["third_period_sha256"] = "0" * 64
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)
        document = copy.deepcopy(self.document)
        document["historical_predecessor"]["exact_token"] = "accepted"
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document)


if __name__ == "__main__":
    unittest.main()

