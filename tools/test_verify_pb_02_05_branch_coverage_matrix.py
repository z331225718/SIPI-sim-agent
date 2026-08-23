import copy
import unittest

import yaml

import verify_pb_02_05_branch_coverage_matrix as verifier


class VerifyPb0205BranchCoverageMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(verifier.MATRIX.read_text(encoding="utf-8"))

    def test_matrix_is_valid_and_content_addressed(self):
        result = verifier.verify(self.document)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["portable_missing"], [])

    def test_portable_missing_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["portable_missing"] = ["PB-05/metadata"]
        result = verifier.verify(document)
        self.assertFalse(result["valid"])

    def test_hash_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        path = next(iter(document["source"]["source_files"]))
        document["source"]["source_files"][path] = "0" * 64
        result = verifier.verify(document)
        self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()
