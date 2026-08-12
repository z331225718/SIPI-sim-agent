from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_s4p_custody_contract", ROOT / "tools" / "verify_p3c_selected_s4p_external_static_custody_observation_contract.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class SelectedS4pCustodyContractTests(unittest.TestCase):
    def document(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-selected-s4p-external-static-custody-observation-contract.v1.yaml").read_text(encoding="utf-8"))

    def test_current_contract_is_valid(self) -> None:
        self.assertTrue(GATE.verify(self.document())["valid"])

    def test_rejects_custody_or_runtime_promotion(self) -> None:
        document = self.document()
        document["admission"]["external_static_custody_observed"] = True
        with self.assertRaisesRegex(GATE.VerificationError, "promotion_invalid"):
            GATE.verify(document)
        document = self.document()
        document["admission"]["analytic_stepping_implemented"] = True
        with self.assertRaisesRegex(GATE.VerificationError, "promotion_invalid"):
            GATE.verify(document)

    def test_rejects_missing_fresh_custody_blocker(self) -> None:
        document = copy.deepcopy(self.document())
        document["blockers"].remove("two_fresh_external_sealed_s4p_custody_observations_missing")
        with self.assertRaisesRegex(GATE.VerificationError, "blocker_invalid"):
            GATE.verify(document)


if __name__ == "__main__":
    unittest.main()
