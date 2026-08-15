from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("or_raw_dtft_charter", ROOT / "tools/verify_p3c_ads_or_product_raw_dtft_charter.py")
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class OrProductRawDtftCharterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load((ROOT / "docs/baselines/p3c-ads-or-product-raw-dtft-charter.v1.yaml").read_text(encoding="utf-8"))

    def test_current_charter_is_authorized_but_not_admitted(self) -> None:
        self.assertEqual(VERIFY.verify(self.document), {"valid": True, "external_payload_authorized": True, "admitted": False})

    def test_payload_authorization_cannot_be_silently_promoted(self) -> None:
        value = copy.deepcopy(self.document)
        value["ads_surface"]["source_payload_read_authorization"] = "caller_selectable"
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify(value)

    def test_causality_or_candidate_promotion_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["admission"]["raw_periodic_response_admitted_as_causal_fir"] = True
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify(value)


if __name__ == "__main__":
    unittest.main()
