import copy
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_pb_01_legacy_leaf as verifier  # noqa: E402


class VerifyPb01LegacyLeafTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(verifier.EVIDENCE.read_text(encoding="utf-8"))
        cls.artifact_schema = verifier.generate_pickle_schema()

    def verify(self, document, artifact_schema=None):
        return verifier.verify(
            document,
            artifact_schema=self.artifact_schema if artifact_schema is None else artifact_schema,
        )

    def test_current_evidence_is_valid(self):
        result = self.verify(copy.deepcopy(self.document))
        self.assertTrue(result["valid"], result)

    def test_runtime_module_hash_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["candidate"]["runtime_module_sha256"] = "0" * 64
        result = self.verify(document)
        self.assertIn("candidate runtime_module_sha256 drift", result["blockers"])

    def test_notice_hash_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["source"]["notice_sha256"] = "0" * 64
        result = self.verify(document)
        self.assertIn("source notice hash drift", result["blockers"])

    def test_safety_tag_policy_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["safety"]["allowed_nested_tags"] = ["!!python/object"]
        result = self.verify(document)
        self.assertIn("safety boundary drift", result["blockers"])

    def test_predecessor_relationship_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["relationship"]["supersedes"] = "all_pb01_branches"
        result = self.verify(document)
        self.assertIn("predecessor relationship drift", result["blockers"])

    def test_fixture_hash_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["fixture"]["sha256"] = "0" * 64
        result = self.verify(document)
        self.assertIn("fixture hash drift", result["blockers"])

    def test_array_set_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["artifact"]["compared_arrays"] = ["chnl_h"]
        result = self.verify(document)
        self.assertIn("compared array set drift", result["blockers"])

    def test_canonical_item_name_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["artifact"]["canonical_item_names"].append("ctle_out")
        result = self.verify(document)
        self.assertIn("canonical item names drift", result["blockers"])

    def test_runtime_pickle_extra_array_key_is_rejected(self):
        artifact_schema = copy.deepcopy(self.artifact_schema)
        artifact_schema["array_keys"].append("ctle_out")
        result = self.verify(copy.deepcopy(self.document), artifact_schema)
        self.assertIn("runtime pickle schema drift", result["blockers"])

    def test_codec_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["artifact"]["rust_codec"] = "opaque"
        result = self.verify(document)
        self.assertIn("Rust codec drift", result["blockers"])

    def test_claim_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["claims"]["exact_upstream_numeric_parity_all_branches"] = True
        result = self.verify(document)
        self.assertIn("claim boundary drift", result["blockers"])

    def test_bound_report_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["oracle"]["bound_report"] = "report.json"
        result = self.verify(document)
        self.assertIn("unbound report must remain explicit", result["blockers"])

    def test_absolute_path_mutation_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["candidate"]["host_path"] = r"C:\Users\host\dirty"
        result = self.verify(document)
        self.assertIn("evidence contains an absolute host path", result["blockers"])


if __name__ == "__main__":
    unittest.main()
