from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p3c_static_custody_evidence", ROOT / "tools" / "verify_p3c_selected_s4p_external_static_custody_evidence.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class SelectedS4pStaticCustodyEvidenceTests(unittest.TestCase):
    def document(self) -> dict:
        return yaml.safe_load((ROOT / "docs" / "baselines" / "p3c-selected-s4p-external-static-custody-evidence.v1.yaml").read_text(encoding="utf-8"))

    def test_current_evidence_is_valid(self) -> None:
        self.assertTrue(GATE.verify(self.document())["valid"])

    def test_rejects_report_or_runtime_promotion(self) -> None:
        document = self.document()
        document["external_observation"]["fresh_custody_runs"] = 1
        with self.assertRaisesRegex(GATE.VerificationError, "observation_invalid"):
            GATE.verify(document)
        document = self.document()
        document["admission"]["analytic_stepping_implemented"] = True
        with self.assertRaisesRegex(GATE.VerificationError, "promotion_invalid"):
            GATE.verify(document)

    def test_rejects_stale_custody_blocker(self) -> None:
        document = copy.deepcopy(self.document())
        document["blockers"].append("two_fresh_external_sealed_s4p_v2_custody_observations_missing")
        with self.assertRaisesRegex(GATE.VerificationError, "stale_blocker"):
            GATE.verify(document)


if __name__ == "__main__":
    unittest.main()
