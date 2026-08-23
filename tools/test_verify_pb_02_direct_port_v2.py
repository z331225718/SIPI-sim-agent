import copy
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_pb_02_direct_port_v2 as verifier  # noqa: E402


class VerifyPb02DirectPortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(verifier.EVIDENCE.read_text(encoding="utf-8"))

    def test_current_evidence_is_valid(self):
        result = verifier.verify(copy.deepcopy(self.document))
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["source_paths"], 16)
        self.assertEqual(result["fresh_runs"], 0)

    def test_pinned_git_objects_and_copied_bytes_are_valid(self):
        result = verifier.verify(copy.deepcopy(self.document), source=verifier.DEFAULT_UPSTREAM)
        self.assertTrue(result["valid"], result)
        self.assertTrue(result["source_git_objects_checked"])

    def test_source_commit_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["source"]["commit"] = "0" * 40
        result = verifier.verify(document)
        self.assertIn("source commit drift", result["blockers"])

    def test_source_blob_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["direct_port_files"]["files"]["native/pybert-core/src/analysis.rs"]["blob_sha1"] = "0" * 40
        result = verifier.verify(document)
        self.assertIn("Git blob binding drift: native/pybert-core/src/analysis.rs", result["blockers"])

    def test_adapted_crate_root_provenance_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["direct_port_files"]["adapted_files"]["native/pybert-core/src/lib.rs"]["source_sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("adapted source binding drift: native/pybert-core/src/lib.rs:source_sha256", result["blockers"])

    def test_artifact_contract_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["artifact_contract"]["output_files"] = ["meta.json"]
        result = verifier.verify(document)
        self.assertIn("artifact contract drift: output_files", result["blockers"])

    def test_replay_hash_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["fresh_replay"]["historical_observation"]["product_arrays_npz_sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("historical product NPZ hash drift", result["blockers"])

    def test_parity_overclaim_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["parity"]["all_uncovered_input_branches_remain_open"] = False
        result = verifier.verify(document)
        self.assertIn("parity claim drift: all_uncovered_input_branches_remain_open", result["blockers"])

    def test_audit_hash_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["audit"]["sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("audit hash binding drift", result["blockers"])

    def test_python_extension_copy_policy_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["python_extension_boundary"]["copied_or_built_into_product"] = True
        result = verifier.verify(document)
        self.assertIn("Python boundary drift: copied_or_built_into_product", result["blockers"])

    def test_non_claim_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["non_claims"] = []
        result = verifier.verify(document)
        self.assertTrue(any("required non-claim missing" in blocker for blocker in result["blockers"]))


if __name__ == "__main__":
    unittest.main()
