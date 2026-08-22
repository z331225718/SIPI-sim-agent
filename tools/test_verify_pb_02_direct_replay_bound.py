import copy
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_pb_02_direct_replay_bound as verifier  # noqa: E402


class VerifyPb02DirectReplayBoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(verifier.EVIDENCE.read_text(encoding="utf-8"))

    def test_current_bound_evidence_is_valid(self):
        result = verifier.verify(copy.deepcopy(self.document))
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["reports"], 2)

    def test_candidate_commit_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["candidate"]["commit"] = "0" * 40
        result = verifier.verify(document)
        self.assertIn("candidate.commit drift", result["blockers"])

    def test_candidate_inventory_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["candidate"]["inventory_sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("candidate.inventory_sha256 drift", result["blockers"])

    def test_report_hash_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["reports"]["first"]["sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("report binding drift: first", result["blockers"])

    def test_report_nonce_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["reports"]["second"]["fresh_run_nonce"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("report binding drift: second", result["blockers"])

    def test_toolchain_extra_key_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["toolchain"]["cargo"]["path"] = "C:\\Users\\host\\cargo.exe"
        result = verifier.verify(document)
        self.assertIn("evidence.toolchain.cargo key set drift", result["blockers"])
        self.assertIn("evidence contains an absolute host path", result["blockers"])

    def test_toolchain_drift_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["toolchain"]["rustc"]["version_output_sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("evidence.toolchain.rustc identity drift", result["blockers"])

    def test_distinct_gate_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["distinct_gate"]["unique_fresh_run_nonces"] = False
        result = verifier.verify(document)
        self.assertIn("distinct gate drift", result["blockers"])

    def test_logical_member_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["logical_arrays"]["members"]["rx_output_v.npy"]["f64_sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("evidence logical members.rx_output_v.npy digest drift", result["blockers"])

    def test_wrapper_parity_boundary_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["wrapper_boundary"]["uncompressed_npz_writer"] = "upstream_native_semantics"
        result = verifier.verify(document)
        self.assertIn("wrapper boundary drift", result["blockers"])

    def test_audit_hash_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["audit"]["sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("audit hash binding drift", result["blockers"])

    def test_release_claim_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["claims"]["release_approval"] = True
        result = verifier.verify(document)
        self.assertIn("claim boundary drift", result["blockers"])

    def test_aggregate_binding_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["aggregate"]["sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("aggregate binding drift", result["blockers"])


if __name__ == "__main__":
    unittest.main()
