"""Mutation coverage for the additive PB-03 branch probe."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from verify_pb_03_branch_coverage_d3154093 import MATRIX, verify


class VerifyPb03D3154093Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))

    def test_matrix_is_valid_and_open(self) -> None:
        result = verify(self.document)
        self.assertTrue(result["valid"], result)
        self.assertEqual(self.document["portable_missing"], [])
        self.assertFalse(self.document["claims"]["global_row_closed"])

    def test_candidate_identity_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["source"]["candidate_commit"] = "0" * 40
        self.assertFalse(verify(document)["valid"])

    def test_source_hash_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        path = next(iter(document["source"]["source_files"]))
        document["source"]["source_files"][path] = "0" * 64
        self.assertFalse(verify(document)["valid"])

    def test_global_parity_closure_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["claims"]["global_row_closed"] = True
        self.assertFalse(verify(document)["valid"])

    def test_external_blocker_and_oracle_mutations_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["external_blockers"] = []
        self.assertFalse(verify(document)["valid"])

        document = copy.deepcopy(self.document)
        document["verification"]["oracle"] = "passed"
        self.assertFalse(verify(document)["valid"])


if __name__ == "__main__":
    unittest.main()
