from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("common_node_verify", ROOT / "tools/verify_p3c_ads_pre_final_common_node_observation.py")
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class CommonNodeEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-ads-pre-final-common-node-observation-evidence.v1.yaml").read_text(encoding="utf-8"))

    def test_current_evidence_passes(self) -> None:
        self.assertEqual(VERIFY.verify(self.document), {"valid": True, "common_nodes": 1024, "accepted": False})

    def test_common_node_mapping_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["external_observation"]["common_node_comparison"]["mapping"] = "nearest_bin"
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify(value, current=False)

    def test_passivity_promotion_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["admission"]["passivity_correction_surface_delta_evaluated"] = True
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify(value, current=False)


if __name__ == "__main__":
    unittest.main()
