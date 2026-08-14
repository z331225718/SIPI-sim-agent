from __future__ import annotations

import copy
from pathlib import Path
import unittest

import yaml

import verify_p3c_selected_truncation_waveform_sensitivity_core as gate


ROOT = Path(__file__).resolve().parents[1]


class TruncationSensitivityCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-selected-truncation-waveform-sensitivity-core.v1.yaml").read_text(encoding="utf-8"))
        self.source = (ROOT / "crates/sipi-p3c/src/p3c_truncation_waveform_sensitivity_v1.rs").read_text(encoding="utf-8")

    def test_baseline(self) -> None:
        self.assertTrue(gate.verify_document(self.document, self.source)["valid"])

    def test_gate_and_fft_mutations_reject(self) -> None:
        document = copy.deepcopy(self.document)
        document["admission"]["bounded_causal_response_admitted_as_kernel"] = True
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(document, self.source)
        with self.assertRaises(gate.VerificationError):
            gate.verify_document(self.document, self.source + "\nFftPlanner")


if __name__ == "__main__":
    unittest.main()
