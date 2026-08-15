from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("paired_verifier", ROOT / "tools/verify_p3c_ads_or_s0_product_paired_transition_observation.py")
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class PairedTransitionEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(VERIFY.PATH.read_text(encoding="utf-8"))

    def test_current_hash_only_evidence_is_valid(self) -> None:
        self.assertTrue(VERIFY.verify(self.document)["valid"])

    def test_transition_digest_and_release_promotion_mutations_fail_closed(self) -> None:
        digest = copy.deepcopy(self.document); digest["external_observation"]["paired_transition"]["paired_delta_sha256"] = "0" * 64
        with self.assertRaisesRegex(VERIFY.VerificationError, "observation"):
            VERIFY.verify(digest, current=False)
        promoted = copy.deepcopy(self.document); promoted["admission"]["release_ledger_promoted"] = True
        with self.assertRaisesRegex(VERIFY.VerificationError, "gates"):
            VERIFY.verify(promoted, current=False)


if __name__ == "__main__":
    unittest.main()
