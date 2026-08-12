from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_sealed_s4p_gate", ROOT / "tools" / "verify_p3c_sealed_selected_s4p_static_admission.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATE
SPEC.loader.exec_module(GATE)


class SealedSelectedS4pAdmissionTests(unittest.TestCase):
    def document(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-sealed-selected-s4p-static-admission.v1.yaml").read_text(encoding="utf-8"))

    def test_current_document_is_valid(self) -> None:
        self.assertTrue(GATE.verify(self.document())["valid"])

    def test_rejects_caller_override_or_custody_promotion(self) -> None:
        document = self.document()
        document["input_contract"]["metadata_sidecar"] = "required"
        with self.assertRaisesRegex(GATE.VerificationError, "input_invalid"):
            GATE.verify(document)
        document = self.document()
        document["admission"]["external_static_custody_observed"] = True
        with self.assertRaisesRegex(GATE.VerificationError, "promotion_invalid"):
            GATE.verify(document)

    def test_rejects_runtime_promotion_or_missing_exact_custody_blocker(self) -> None:
        document = self.document()
        document["admission"]["candidate_waveform_generated"] = True
        with self.assertRaisesRegex(GATE.VerificationError, "promotion_invalid"):
            GATE.verify(document)
        document = copy.deepcopy(self.document())
        document["blockers"].remove("two_fresh_external_sealed_s4p_custody_observations_missing")
        with self.assertRaisesRegex(GATE.VerificationError, "blocker_missing"):
            GATE.verify(document)


if __name__ == "__main__":
    unittest.main()
