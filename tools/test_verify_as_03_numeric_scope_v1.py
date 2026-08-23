from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import verify_as_03_numeric_scope_v1 as verifier


class ScopedParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(verifier.MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_is_valid(self):
        result = verifier.verify(verifier.MANIFEST)
        self.assertTrue(result["valid"], result["blockers"])

    def test_scope_mutation_is_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["global_row_closed"] = True
        self.assertFalse(verifier.verify(verifier.MANIFEST, document=mutated)["valid"])

    def test_report_hash_mutation_is_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["reports"][0]["sha256"] = "0" * 64
        self.assertFalse(verifier.verify(verifier.MANIFEST, document=mutated)["valid"])

    def test_candidate_binding_mutation_is_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["source"]["candidate"]["tree"] = "0" * 40
        self.assertFalse(verifier.verify(verifier.MANIFEST, document=mutated)["valid"])

    def test_path_escape_is_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["reports"][0]["path"] = "docs/../outside.json"
        self.assertFalse(verifier.verify(verifier.MANIFEST, document=mutated)["valid"])


if __name__ == "__main__":
    unittest.main()
