from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_fixed_pole_gate", ROOT / "tools" / "verify_p3c_fixed_pole_rational_identification_core.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATE
SPEC.loader.exec_module(GATE)


class FixedPoleRationalIdentificationTests(unittest.TestCase):
    def document(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-fixed-pole-rational-identification-core.v1.yaml").read_text(encoding="utf-8"))

    def test_current_document_is_valid(self) -> None:
        self.assertTrue(GATE.verify(self.document())["valid"])

    def test_rejects_ads_input_and_promotion(self) -> None:
        document = self.document()
        document["input_boundary"]["ads_grid_or_waveform_input"] = "allowed"
        with self.assertRaisesRegex(GATE.VerificationError, "input_boundary"):
            GATE.verify(document)
        document = self.document()
        document["admission"]["candidate_waveform_generated"] = True
        with self.assertRaisesRegex(GATE.VerificationError, "promotion"):
            GATE.verify(document)

    def test_rejects_relocation_or_missing_execution_blocker(self) -> None:
        document = self.document()
        document["algorithm"]["pole_relocation"] = "allowed"
        with self.assertRaisesRegex(GATE.VerificationError, "algorithm"):
            GATE.verify(document)
        document = copy.deepcopy(self.document())
        document["blockers"].remove("out_of_band_continuation_or_band_limit_policy_missing")
        with self.assertRaisesRegex(GATE.VerificationError, "blocker_missing"):
            GATE.verify(document)


if __name__ == "__main__":
    unittest.main()
