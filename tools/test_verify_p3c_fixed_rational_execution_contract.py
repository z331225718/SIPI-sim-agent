from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_fixed_rational_execution_gate", ROOT / "tools" / "verify_p3c_fixed_rational_execution_contract.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATE
SPEC.loader.exec_module(GATE)


class FixedRationalExecutionContractTests(unittest.TestCase):
    def document(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-fixed-rational-execution-contract.v1.yaml").read_text(encoding="utf-8"))

    def test_current_document_is_valid(self) -> None:
        self.assertTrue(GATE.verify(self.document())["valid"])

    def test_rejects_fake_realness_or_ads_equivalence(self) -> None:
        document = self.document()
        document["model_contract"]["pole_residue_realness"]["fitting"] = "complex_fit_then_average"
        with self.assertRaisesRegex(GATE.VerificationError, "model_invalid"):
            GATE.verify(document)
        document = self.document()
        document["out_of_band_policy"]["ads_equivalence_claim"] = "allowed"
        with self.assertRaisesRegex(GATE.VerificationError, "out_of_band_invalid"):
            GATE.verify(document)

    def test_rejects_runtime_shortcuts_and_promotion(self) -> None:
        document = self.document()
        document["recurrence_policy"]["adaptive_step"] = "allowed"
        with self.assertRaisesRegex(GATE.VerificationError, "recurrence_invalid"):
            GATE.verify(document)
        document = self.document()
        document["admission"]["candidate_waveform_generated"] = True
        with self.assertRaisesRegex(GATE.VerificationError, "promotion_invalid"):
            GATE.verify(document)

    def test_rejects_missing_hardening_or_predecessor_drift(self) -> None:
        document = copy.deepcopy(self.document())
        document["blockers"].remove("real_constrained_fixed_pole_fit_hardening_missing")
        with self.assertRaisesRegex(GATE.VerificationError, "blocker_missing"):
            GATE.verify(document)
        document = self.document()
        document["predecessor_bindings"]["fixed_pole_identification_sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.VerificationError, "predecessor_drift"):
            GATE.verify(document)


if __name__ == "__main__":
    unittest.main()
