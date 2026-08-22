import copy
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_pb_01_direct_port as verifier  # noqa: E402


class VerifyPb01DirectPortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(verifier.EVIDENCE.read_text(encoding="utf-8"))

    def test_current_evidence_is_valid(self):
        result = verifier.verify(copy.deepcopy(self.document))
        self.assertTrue(result["valid"], result)

    def test_source_commit_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["source"]["commit"] = "0" * 40
        result = verifier.verify(document)
        self.assertIn("source.commit drift", result["blockers"])

    def test_branch_backend_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["branch_inventory"]["backend_selection"]["requested_backend"] = "auto"
        result = verifier.verify(document)
        self.assertIn("branch inventory drift: backend_selection", result["blockers"])

    def test_default_result_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["branch_inventory"]["artifacts"]["default_result_path"] = "case.json"
        result = verifier.verify(document)
        self.assertIn("branch inventory drift: artifacts", result["blockers"])

    def test_supersession_relationship_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["relationship"]["executable_leaf_branch_complete"] = True
        result = verifier.verify(document)
        self.assertIn("supersession relationship drift", result["blockers"])

    def test_candidate_module_hash_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["candidate"]["module_sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("candidate.module_sha256 drift", result["blockers"])

    def test_runner_hash_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["oracle_runner"]["prepare_sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("oracle runner.prepare_sha256 drift", result["blockers"])

    def test_claim_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["claims"]["exact_upstream_numeric_parity"] = True
        result = verifier.verify(document)
        self.assertIn("claim boundary drift", result["blockers"])

    def test_audit_hash_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["audit"]["sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("audit hash binding drift", result["blockers"])

    def test_absolute_path_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["candidate"]["host_path"] = r"C:\Users\host\dirty"
        result = verifier.verify(document)
        self.assertIn("evidence contains an absolute host path", result["blockers"])


if __name__ == "__main__":
    unittest.main()
