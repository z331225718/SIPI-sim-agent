import copy
import tempfile
import unittest
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_com_02_direct_semantic_replay import DEFAULT_MANIFEST, VerificationError, verify


class Com02SemanticReplayVerifierTests(unittest.TestCase):
    def mutate_fails(self, mutate):
        document = yaml.safe_load(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        mutate(document)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with self.assertRaises(VerificationError):
                verify(path)

    def test_current_manifest(self):
        result = verify()
        self.assertEqual(result["source_paths"], 21)
        self.assertTrue(result["evidence_bound"])

    def test_status_mutation_fails(self):
        self.mutate_fails(lambda document: document.__setitem__("status", "parity_closed"))

    def test_fit_policy_mutation_fails(self):
        self.mutate_fails(lambda document: document["contract"].__setitem__("s_parameter_fit", "allowed"))

    def test_portable_branch_mutation_fails(self):
        self.mutate_fails(lambda document: document["contract"]["portable_semantic_branches"].pop())

    def test_source_path_license_mutation_fails(self):
        self.mutate_fails(lambda document: document["source"]["source_paths"][0].__setitem__("license", "BSD-3-Clause"))

    def test_evidence_hash_mutation_fails(self):
        self.mutate_fails(lambda document: document["evidence"]["reports"][0].__setitem__("sha256", "0" * 64))


if __name__ == "__main__":
    unittest.main()
