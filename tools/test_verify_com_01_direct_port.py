import copy
import json
import tempfile
import unittest
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_com_01_direct_port import DEFAULT_MANIFEST, VerificationError, verify


class Com01DifferentialVerifierTests(unittest.TestCase):
    def setUp(self):
        self.document = yaml.safe_load(DEFAULT_MANIFEST.read_text(encoding="utf-8"))

    def mutate_fails(self, mutate):
        document = copy.deepcopy(self.document)
        mutate(document)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.yaml"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with self.assertRaises(VerificationError):
                verify(path)

    def test_current_manifest(self):
        result = verify()
        self.assertEqual(result["scenario_count"], 14)
        self.assertEqual(result["status"], "implementation_materialized_open")

    def test_status_mutation_fails(self):
        self.mutate_fails(lambda document: document.__setitem__("status", "rust_parity_accepted"))

    def test_source_commit_mutation_fails(self):
        self.mutate_fails(lambda document: document["source"].__setitem__("commit", "0" * 40))

    def test_source_path_mutation_fails(self):
        self.mutate_fails(lambda document: document["source"]["source_paths"].pop())

    def test_audit_hash_mutation_fails(self):
        self.mutate_fails(lambda document: document["audit"].__setitem__("sha256", "0" * 64))

    def test_corpus_digest_mutation_fails(self):
        self.mutate_fails(lambda document: document["corpus"].__setitem__("scenario_set_sha256", "0" * 64))

    def test_stage_two_promotion_fails(self):
        self.mutate_fails(
            lambda document: document["runner"].__setitem__(
                "stage_2", "two_run_differential_execution_ready"
            )
        )

    def test_inventory_deletion_fails(self):
        self.mutate_fails(lambda document: document["reachable_inventory"]["open"].pop())

    def test_candidate_source_hash_mutation_fails(self):
        self.mutate_fails(
            lambda document: document["implementation"]["files"][0].__setitem__(
                "sha256", "0" * 64
            )
        )

    def test_safety_budget_mutation_fails(self):
        self.mutate_fails(
            lambda document: document["implementation"]["safety_boundary"].__setitem__(
                "max_count_value", 1000001
            )
        )

    def test_reader_preflight_budget_mutation_fails(self):
        self.mutate_fails(
            lambda document: document["implementation"]["safety_boundary"].__setitem__(
                "xlsx_max_shared_strings_bytes", 8388609
            )
        )

    def test_reader_preflight_source_hash_mutation_fails(self):
        self.mutate_fails(
            lambda document: document["implementation"]["files"][1].__setitem__(
                "sha256", "0" * 64
            )
        )

    def test_shared_reader_review_hash_mutation_fails(self):
        self.mutate_fails(
            lambda document: document["implementation"]["shared_reader_review"][0].__setitem__(
                "sha256", "0" * 64
            )
        )

    def test_raw_evidence_payload_claim_fails(self):
        self.mutate_fails(
            lambda document: document["runner"].__setitem__(
                "complete_materialized_values_stored", True
            )
        )

    def test_nonclaim_deletion_fails(self):
        self.mutate_fails(lambda document: document["non_claims"].remove("no_com_runtime_execution"))

    def test_corpus_contains_no_external_bytes(self):
        corpus = json.loads((DEFAULT_MANIFEST.parent / "com-01-direct-port-corpus.v1.json").read_text())
        self.assertTrue(all("fixture_role" in scenario for scenario in corpus["scenarios"]))
        self.assertTrue(all("bytes" not in scenario for scenario in corpus["scenarios"]))


if __name__ == "__main__":
    unittest.main()
