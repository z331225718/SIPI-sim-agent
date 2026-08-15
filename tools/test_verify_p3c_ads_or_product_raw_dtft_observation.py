from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("or_raw_observation", ROOT / "tools/verify_p3c_ads_or_product_raw_dtft_observation.py")
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class OriginalRawEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-ads-or-product-raw-dtft-observation-evidence.v1.yaml").read_text(encoding="utf-8"))

    def test_current_evidence_passes(self) -> None:
        self.assertEqual(VERIFY.verify(self.document), {"valid": True, "ads_or_nodes": 4096, "accepted": False, "audit": "blocked"})

    def test_axis_or_delta_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["external_observation"]["product_raw_dtft"]["delta_max_index"] = 2
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify(value, current=False)

    def test_causal_admission_promotion_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["admission"]["raw_periodic_response_admitted_as_causal_fir"] = True
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify(value, current=False)


if __name__ == "__main__":
    unittest.main()
