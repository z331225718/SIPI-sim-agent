"""Mutation tests for the PB stage 2 evidence verifier."""

from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_pb_stage2_native_semantics import MANIFEST, ROOT, verify


class PbStage2NativeSemanticsVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    def assert_valid(self, document: dict) -> None:
        result = verify(document, root=ROOT)
        self.assertTrue(result["valid"], result)

    def assert_invalid(self, document: dict, message: str) -> None:
        result = verify(document, root=ROOT)
        self.assertFalse(result["valid"], result)
        self.assertTrue(any(message in error for error in result["errors"]), result)

    def test_manifest_is_valid(self) -> None:
        self.assert_valid(copy.deepcopy(self.document))

    def test_upstream_identity_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["source"]["upstream_commit"] = "0" * 40
        self.assert_invalid(document, "upstream commit drift")

    def test_source_hash_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["source"]["source_files"][
            "crates/sipi-pybert-direct/src/simulation.rs"
        ] = "0" * 64
        self.assert_invalid(document, "manifest hash mismatch")

    def test_branch_set_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["branches"].pop()
        self.assert_invalid(document, "branch set drift")

    def test_external_compare_claim_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["verification"]["external_compare"] = "passed"
        self.assert_invalid(document, "external compare must remain explicitly not run")

    def test_status_promotion_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["status"] = "closed"
        self.assert_invalid(document, "status must remain pending_immutable_external_replay")

    def test_complete_typed_output_gate_false_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["claims"]["complete_typed_output_gate"] = False
        self.assert_invalid(document, "claim value drift: complete_typed_output_gate")

    def test_extra_claim_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["claims"]["oracle_parity"] = False
        self.assert_invalid(document, "claims key set drift")

    def test_fake_branch_test_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["branches"][0]["test"] = "native_branch_matrix::fake_test"
        self.assert_invalid(document, "branch test tuple drift")

    def test_boolean_string_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["claims"]["complete_typed_output_gate"] = "true"
        self.assert_invalid(document, "claim type drift: complete_typed_output_gate")

    def test_coordinated_branch_payload_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["branches"][0]["id"] = "modulation.pam4"
        document["branches"][0]["test"] = (
            "native_branch_matrix::native_request_reaches_all_modulation_branches"
        )
        self.assert_invalid(document, "branch set drift")

    def test_coordinated_status_and_claim_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["status"] = "closed"
        document["claims"]["complete_typed_output_gate"] = False
        self.assert_invalid(document, "status must remain pending_immutable_external_replay")

    def test_non_claim_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["non_claims"].remove("global_row_closed")
        self.assert_invalid(document, "non_claims drift")

    def test_harness_sha256s_bind_physical_files(self) -> None:
        for record in self.document["harness"].values():
            path = ROOT / record["path"]
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                record["sha256"],
            )

    def test_audit_hash_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["audit"]["sha256"] = "0" * 64
        self.assert_invalid(document, "manifest audit hash mismatch")


if __name__ == "__main__":
    unittest.main()
