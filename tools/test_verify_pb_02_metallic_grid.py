import copy
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_pb_02_metallic_grid as verifier  # noqa: E402


class VerifyPb02MetallicGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(verifier.EVIDENCE.read_text(encoding="utf-8"))

    def test_current_successor_is_valid(self):
        result = verifier.verify(copy.deepcopy(self.document))
        self.assertTrue(result["valid"], result)

    def test_candidate_commit_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["candidate"]["commit"] = "0" * 40
        result = verifier.verify(document)
        self.assertIn("candidate commit drift", result["blockers"])

    def test_source_map_hash_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["source_map"]["sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("source-map hash drift", result["blockers"])

    def test_near_integral_checkpoint_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["checkpoint"]["grid_cases"]["near_integral_stop"]["expected_grid_hz"] = [0.0, 3.0e9, 6.0e9]
        result = verifier.verify(document)
        self.assertIn("near-integral grid checkpoint drift", result["blockers"])

    def test_global_parity_overclaim_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["claims"]["global_payload_parity"] = True
        result = verifier.verify(document)
        self.assertIn("claims key/value drift", result["blockers"])

    def test_archive_contract_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["candidate"]["archive"]["format"] = "zip"
        result = verifier.verify(document)
        self.assertIn("candidate archive format drift", result["blockers"])

    def test_archive_sha_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["upstream"]["archive_sha256"] = "0" * 64
        result = verifier.verify(document)
        self.assertIn("upstream archive drift", result["blockers"])

    def test_absolute_path_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["audit"]["path"] = "C:\\evidence.md"
        result = verifier.verify(document)
        self.assertIn("audit path drift", result["blockers"])

    def test_harness_sha_mutation_is_rejected(self):
        source_map = yaml.safe_load(verifier.SOURCE_MAP.read_text(encoding="utf-8"))
        source_map["harness_files"][0]["sha256"] = "0" * 64
        blockers = []
        verifier.verify_source_map(source_map, blockers, verifier.DEFAULT_UPSTREAM)
        self.assertIn("harness sha256 drift: tools\\verify_pb_02_metallic_grid.py", blockers)

    def test_checkpoint_oracle_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["checkpoint"]["oracle"] = "pinned_pybert_python_runtime"
        result = verifier.verify(document)
        self.assertIn("checkpoint oracle drift", result["blockers"])

    def test_input_parameter_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["checkpoint"]["input_parameters"]["length_m"] = 0.051
        result = verifier.verify(document)
        self.assertIn("checkpoint input parameter drift", result["blockers"])

    def test_source_map_lane_role_mutation_is_rejected(self):
        source_map = yaml.safe_load(verifier.SOURCE_MAP.read_text(encoding="utf-8"))
        source_map["lane_files"][0]["role"] = "global"
        source_map["lane_files"][0]["classification"] = "global"
        blockers = []
        verifier.verify_source_map(source_map, blockers, verifier.DEFAULT_UPSTREAM)
        self.assertIn("source-map forbidden classification", blockers)
        self.assertIn("source-map lane tuple drift", blockers)

    def test_parent_path_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["source_map"]["path"] = "../pb-02-metallic-grid-source-map.v1.yaml"
        result = verifier.verify(document)
        self.assertIn("source-map path drift", result["blockers"])

    def test_unknown_claim_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["claims"]["promotion_reason"] = "scoped"
        result = verifier.verify(document)
        self.assertIn("claims key/value drift", result["blockers"])


if __name__ == "__main__":
    unittest.main()
