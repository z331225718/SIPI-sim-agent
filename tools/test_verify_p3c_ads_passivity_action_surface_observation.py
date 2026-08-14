from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("passivity_verifier", ROOT / "tools/verify_p3c_ads_passivity_action_surface_observation.py")
assert SPEC and SPEC.loader
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class PassivityEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(VERIFIER.PATH.read_text(encoding="utf-8"))

    def test_current_evidence_is_valid(self) -> None:
        self.assertTrue(VERIFIER.verify(self.document)["valid"])

    def test_surface_or_gate_mutation_fails_closed(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["external_observation"]["passivity_surface"]["s0_vectorset_count"] = 15
        with self.assertRaises(VERIFIER.VerificationError):
            VERIFIER.verify(changed, current=False)
        changed = copy.deepcopy(self.document)
        changed["admission"]["passivity_algorithm_or_repair_implemented"] = True
        with self.assertRaises(VERIFIER.VerificationError):
            VERIFIER.verify(changed, current=False)


if __name__ == "__main__":
    unittest.main()
