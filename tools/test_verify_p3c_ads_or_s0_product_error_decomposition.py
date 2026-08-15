from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("error_decomposition", ROOT / "tools/verify_p3c_ads_or_s0_product_error_decomposition.py")
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class ErrorDecompositionEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(VERIFY.PATH.read_text(encoding="utf-8"))

    def test_hash_only_facts_verify(self) -> None:
        self.assertTrue(VERIFY.verify(self.document)["valid"])

    def test_cross_term_and_release_mutation_fail_closed(self) -> None:
        changed = copy.deepcopy(self.document); changed["external_observation"]["decomposition"]["cross_term_bits"] = "0" * 16
        with self.assertRaisesRegex(VERIFY.VerificationError, "cross_term"):
            VERIFY.verify(changed)
        changed = copy.deepcopy(self.document); changed["admission"]["release_ledger_promoted"] = True
        with self.assertRaisesRegex(VERIFY.VerificationError, "gates"):
            VERIFY.verify(changed)


if __name__ == "__main__":
    unittest.main()
