import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

import verify_as_01_fit_sparam_direct_port as verifier


class VerifyAs01FitSparamDirectPortTests(unittest.TestCase):
    def setUp(self):
        self.document = yaml.safe_load(verifier.DEFAULT_MANIFEST.read_text(encoding="utf-8"))

    def verify_mutated(self, document):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.yaml"
            path.write_text(
                yaml.safe_dump(document, sort_keys=False),
                encoding="utf-8",
            )
            with self.assertRaises(verifier.VerificationError):
                verifier.verify(path)

    def test_schema_mutation_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["schema"] = "sipi.agent-spice-as-01-direct-port.v0"
        self.verify_mutated(mutated)

    def test_status_overclaim_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["status"] = "rust_parity_accepted"
        self.verify_mutated(mutated)

    def test_source_blob_mutation_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["source"]["reachable_source_paths"][0]["content_sha256"] = "0" * 64
        self.verify_mutated(mutated)

    def test_public_option_mutation_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["contract"]["public_options"].pop()
        self.verify_mutated(mutated)

    def test_oracle_overclaim_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["oracle"]["report_payloads_committed"] = True
        self.verify_mutated(mutated)

    def test_audit_hash_mutation_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["implementation"]["audit"]["sha256"] = "0" * 64
        self.verify_mutated(mutated)

    def test_non_claim_mutation_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["non_claims"].remove("no_numeric_parity")
        self.verify_mutated(mutated)

    def test_runtime_budget_mutation_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["runtime_support"]["budgets"]["real_matrix_cells"] += 1
        self.verify_mutated(mutated)

    def test_unsupported_artifact_claim_mutation_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["runtime_support"]["artifacts_written"].append("spice_subcircuit")
        self.verify_mutated(mutated)

    def test_path_identity_atomicity_mutation_rejected(self):
        mutated = copy.deepcopy(self.document)
        mutated["runtime_support"]["path_identity_preflight"]["failure_atomicity"] = "best_effort"
        self.verify_mutated(mutated)


if __name__ == "__main__":
    unittest.main()
