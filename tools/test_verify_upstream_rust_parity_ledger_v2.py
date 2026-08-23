"""Mutation tests for the immutable-bound parity ledger successor."""

from __future__ import annotations

import copy
import unittest

from tools import verify_upstream_rust_parity_ledger_v2 as gate


class UpstreamRustParityLedgerV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate._load(gate.LEDGER)

    def validate(self, document=None):
        return gate.validate(self.document if document is None else document)

    def test_current_successor_is_valid_and_keeps_every_row_open(self) -> None:
        result = self.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["rows"], 15)
        self.assertEqual(result["completion_open"], 15)
        self.assertEqual(result["current_bound_rows"], 12)
        self.assertEqual(result["no_new_evidence_rows"], 3)

    def test_row_omission_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"].pop()
        with self.assertRaisesRegex(gate.LedgerError, "ledger_row_set_invalid"):
            self.validate(mutated)

    def test_unknown_row_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["id"] = "AS-99"
        with self.assertRaisesRegex(gate.LedgerError, "ledger_row_set_invalid"):
            self.validate(mutated)

    def test_evidence_commit_parent_and_tree_are_bound(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["evidence_commit"]["parent_preparation_commit"] = "0" * 40
        with self.assertRaisesRegex(gate.LedgerError, "evidence_commit_identity_drift"):
            self.validate(mutated)

        mutated = copy.deepcopy(self.document)
        mutated["evidence_commit"]["tree"] = "0" * 40
        with self.assertRaisesRegex(gate.LedgerError, "evidence_tree_drift"):
            self.validate(mutated)

    def test_candidate_archive_and_source_authority_are_bound(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["candidate"]["archive_sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.LedgerError, "candidate_binding_drift"):
            self.validate(mutated)

        mutated = copy.deepcopy(self.document)
        mutated["source_authority"]["pybert"]["license"] = "MIT"
        with self.assertRaisesRegex(gate.LedgerError, "source_authority_drift"):
            self.validate(mutated)

    def test_predecessor_hash_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["successor"]["predecessor"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.LedgerError, "predecessor_hash_drift"):
            self.validate(mutated)

    def test_candidate_coverage_hash_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["evidence_bindings"]["candidate_coverage_v2"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.LedgerError, "candidate_coverage_v2_hash_drift"):
            self.validate(mutated)

    def test_manifest_path_and_hash_are_bound(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][1]["evidence"]["manifest"]["path"] = "docs/baselines/not-the-manifest.yaml"
        with self.assertRaisesRegex(gate.LedgerError, "manifest:AS-02_path_drift"):
            self.validate(mutated)

        mutated = copy.deepcopy(self.document)
        mutated["rows"][1]["evidence"]["manifest"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.LedgerError, "manifest:AS-02_hash_drift"):
            self.validate(mutated)

    def test_current_bound_row_cannot_use_worktree_overlay(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][1]["evidence"]["candidate_source"]["overlay_current_worktree"] = True
        with self.assertRaisesRegex(gate.LedgerError, "row_worktree_overlay_present:AS-02"):
            self.validate(mutated)

    def test_completion_and_product_capability_cannot_be_promoted(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][1]["completion"] = "closed"
        with self.assertRaisesRegex(gate.LedgerError, "row_completion_promoted:AS-02"):
            self.validate(mutated)

        mutated = copy.deepcopy(self.document)
        mutated["rows"][1]["product_capability"] = "claimed"
        with self.assertRaisesRegex(gate.LedgerError, "row_product_capability_promoted:AS-02"):
            self.validate(mutated)

    def test_pb03_fixed_fixture_scope_cannot_be_globalized(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][8]["scope"]["global_row_parity"] = True
        with self.assertRaisesRegex(gate.LedgerError, "pb03_global_scope_promoted"):
            self.validate(mutated)

    def test_com_metadata_only_boundary_is_required(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][12]["upstream_runtime"] = "executed"
        with self.assertRaisesRegex(gate.LedgerError, "com_metadata_only_missing:COM-02"):
            self.validate(mutated)

    def test_no_new_rows_cannot_be_rebound_as_current(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["evidence"]["manifest"] = {
            "path": "docs/baselines/as-02-fit-sparam-cascade-direct-port.v2.yaml",
            "sha256": "0" * 64,
            "bound_to_evidence_commit": True,
        }
        with self.assertRaisesRegex(gate.LedgerError, "unexpected_current_manifest:AS-01"):
            self.validate(mutated)

    def test_forbidden_promotion_value_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][1]["non_claims"].append("rust_parity_accepted")
        with self.assertRaisesRegex(gate.LedgerError, "forbidden_promotion_term:AS-02"):
            self.validate(mutated)


if __name__ == "__main__":
    unittest.main()
