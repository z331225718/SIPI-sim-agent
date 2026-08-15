from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("s0_product_dtft_verify", ROOT / "tools/verify_p3c_ads_s0_product_bounded_dtft_observation.py")
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class S0ProductDtftEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-ads-s0-product-bounded-dtft-observation-evidence.v1.yaml").read_text(encoding="utf-8"))

    def test_current_evidence_passes(self) -> None:
        self.assertEqual(VERIFY.verify(self.document), {"valid": True, "ads_s0_nodes": 1024, "accepted": False, "audit": "pending"})

    def test_dtft_delta_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["external_observation"]["product_bounded_dtft"]["delta_max_index"] = 105
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify(value, current=False)

    def test_cause_attribution_promotion_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["admission"]["causality_or_interpolation_cause_identified"] = True
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify(value, current=False)


if __name__ == "__main__":
    unittest.main()
