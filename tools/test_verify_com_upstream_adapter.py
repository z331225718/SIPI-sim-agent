import copy
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

from verify_com_upstream_adapter import DEFAULT_MANIFEST, VerificationError, verify


class ComUpstreamAdapterVerifierTests(unittest.TestCase):
    def setUp(self):
        self.document = yaml.safe_load(DEFAULT_MANIFEST.read_text(encoding="utf-8"))

    def verify_mutation(self, mutate):
        mutated = copy.deepcopy(self.document)
        mutate(mutated)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.yaml"
            path.write_text(yaml.safe_dump(mutated, sort_keys=False), encoding="utf-8")
            with self.assertRaises(VerificationError):
                verify(path)

    def test_current_manifest_structure(self):
        result = verify()
        self.assertEqual(result["source_bindings"], 12)
        self.assertEqual(result["workflows"], ["COM-01", "COM-02", "COM-03", "COM-04"])
        self.assertFalse(result["agent_com_verified"])

    def test_source_commit_mutation_fails(self):
        self.verify_mutation(lambda document: document["upstream"].__setitem__("commit", "0" * 40))

    def test_operation_deletion_fails(self):
        self.verify_mutation(lambda document: document["adapter"].__setitem__("operations", ["run"]))

    def test_workflow_deletion_fails(self):
        self.verify_mutation(lambda document: document.__setitem__("workflows", document["workflows"][:3]))

    def test_consumption_claim_mutation_fails(self):
        self.verify_mutation(lambda document: document["consumption_audit"].__setitem__("unimplemented_fields", []))

    def test_parity_claim_mutation_fails(self):
        self.verify_mutation(lambda document: document.__setitem__("non_claims", [claim for claim in document["non_claims"] if claim != "no_rust_parity_acceptance"]))

    def test_process_tree_policy_mutation_fails(self):
        self.verify_mutation(lambda document: document["adapter"]["bounded_io"].__setitem__("windows_termination", "direct_kill_only"))

    def test_argv_policy_mutation_fails(self):
        self.verify_mutation(lambda document: document["adapter"]["bounded_io"].__setitem__("argv_bytes", "partial"))

    def test_artifact_link_policy_mutation_fails(self):
        self.verify_mutation(lambda document: document["adapter"]["bounded_io"].__setitem__("output_root_and_ancestors", "canonicalize_only"))

    def test_working_directory_policy_mutation_fails(self):
        self.verify_mutation(lambda document: document["adapter"]["working_directory"].__setitem__("process_current_dir", "ignored"))

    def test_designated_output_boundary_mutation_fails(self):
        self.verify_mutation(
            lambda document: document["adapter"]["designated_output_boundary"].__setitem__(
                "log_file_and_progress_jsonl", "unbounded"
            )
        )

    def test_runtime_nonclaim_removal_fails(self):
        self.verify_mutation(
            lambda document: document.__setitem__(
                "non_claims",
                [
                    claim
                    for claim in document["non_claims"]
                    if claim != "no_runtime_source_attestation"
                ],
            )
        )

    def test_artifact_entry_bound_mutation_fails(self):
        self.verify_mutation(lambda document: document["adapter"]["bounded_io"].__setitem__("artifact_entries", "regular_only_unbounded_count"))

    def test_public_profile_admission_mutation_fails(self):
        self.verify_mutation(lambda document: document["adapter"]["public_workflow_profile_admission"].__setitem__("custom", "implicit_r480_reader"))

    def test_process_containment_setup_mutation_fails(self):
        self.verify_mutation(lambda document: document["adapter"]["windows_process_containment"].__setitem__("setup_failure", "bare_process_fallback"))

    def test_process_wrap_checksum_mutation_fails(self):
        self.verify_mutation(lambda document: document["adapter"]["windows_process_containment"].__setitem__("registry_checksum", "0" * 64))


if __name__ == "__main__":
    unittest.main()
