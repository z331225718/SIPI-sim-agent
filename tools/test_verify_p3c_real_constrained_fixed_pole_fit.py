from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_real_constrained_gate", ROOT / "tools" / "verify_p3c_real_constrained_fixed_pole_fit.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATE
SPEC.loader.exec_module(GATE)


class RealConstrainedFixedPoleFitTests(unittest.TestCase):
    def document(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-real-constrained-fixed-pole-fit.v1.yaml").read_text(encoding="utf-8"))

    def test_current_document_is_valid(self) -> None:
        self.assertTrue(GATE.verify(self.document())["valid"])

    def test_rejects_unconstrained_or_postfit_realness_shortcuts(self) -> None:
        document = self.document()
        document["algorithm"]["coefficient_basis"] = "complex_qr_then_average"
        with self.assertRaisesRegex(GATE.VerificationError, "algorithm_invalid"):
            GATE.verify(document)
        document = self.document()
        document["algorithm"]["residue_average_projection_or_imaginary_discard"] = "allowed"
        with self.assertRaisesRegex(GATE.VerificationError, "algorithm_invalid"):
            GATE.verify(document)

    def test_rejects_stepping_promotion_and_contract_drift(self) -> None:
        document = self.document()
        document["admission"]["analytic_stepping_implemented"] = True
        with self.assertRaisesRegex(GATE.VerificationError, "promotion_invalid"):
            GATE.verify(document)
        document = copy.deepcopy(self.document())
        document["execution_contract_sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.VerificationError, "contract_drift"):
            GATE.verify(document)

    def test_rejects_missing_sealed_s4p_blocker(self) -> None:
        document = self.document()
        document["blockers"].remove("selected_external_s4p_artifact_admission_missing")
        with self.assertRaisesRegex(GATE.VerificationError, "blocker_missing"):
            GATE.verify(document)


if __name__ == "__main__":
    unittest.main()
