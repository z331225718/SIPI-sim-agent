from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pre_final_verify", ROOT / "tools/verify_p3c_ads_pre_final_spectrum_comparison_observation.py")
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class PreFinalEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-ads-pre-final-spectrum-comparison-observation-evidence.v1.yaml").read_text(encoding="utf-8"))

    def test_current_evidence_passes(self) -> None:
        self.assertEqual(VERIFY.verify(self.document), {"valid": True, "axis_comparable": False, "accepted": False})

    def test_axis_count_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["external_observation"]["pre_final_axis_comparison"]["s0"]["point_count"] = 4096
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify(value, current=False)

    def test_delta_gate_promotion_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["admission"]["full_matrix_delta_observed"] = True
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify(value, current=False)


if __name__ == "__main__":
    unittest.main()
