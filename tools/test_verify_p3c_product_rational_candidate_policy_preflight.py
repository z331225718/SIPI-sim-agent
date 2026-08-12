from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_rational_policy_gate", ROOT / "tools" / "verify_p3c_product_rational_candidate_policy_preflight.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATE
SPEC.loader.exec_module(GATE)


class RationalCandidatePolicyPreflightTests(unittest.TestCase):
    def document(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-product-rational-candidate-policy-preflight.v1.yaml").read_text(encoding="utf-8"))

    def test_current_document_is_valid(self) -> None:
        self.assertTrue(GATE.verify(self.document())["valid"])

    def test_rejects_ads_grid_or_waveform_as_product_input(self) -> None:
        document = self.document()
        document["input_boundary"]["ads_n2048_grid_product_input"] = "allowed"
        with self.assertRaisesRegex(GATE.VerificationError, "input_boundary"):
            GATE.verify(document)
        document = self.document()
        document["input_boundary"]["ads_waveform_or_adaptive_output_product_input"] = "allowed"
        with self.assertRaisesRegex(GATE.VerificationError, "input_boundary"):
            GATE.verify(document)

    def test_rejects_unfrozen_fit_or_execution_policy(self) -> None:
        document = self.document()
        document["pending_fit_policy"]["initial_poles"] = "default"
        with self.assertRaisesRegex(GATE.VerificationError, "fit_not_pending"):
            GATE.verify(document)
        document = self.document()
        document["pending_execution_policy"]["source_between_strobes"] = "linear"
        with self.assertRaisesRegex(GATE.VerificationError, "execution_not_pending"):
            GATE.verify(document)

    def test_rejects_executor_promotion_and_missing_blocker(self) -> None:
        document = self.document()
        document["admission"]["executor_admission"] = True
        with self.assertRaisesRegex(GATE.VerificationError, "promotion"):
            GATE.verify(document)
        document = copy.deepcopy(self.document())
        document["blockers"].remove("out_of_band_policy_missing")
        with self.assertRaisesRegex(GATE.VerificationError, "blocker_missing"):
            GATE.verify(document)


if __name__ == "__main__":
    unittest.main()
