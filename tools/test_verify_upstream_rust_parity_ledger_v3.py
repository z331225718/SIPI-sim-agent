"""Mutation tests for the immutable-bound upstream Rust parity ledger v3."""

from __future__ import annotations

import copy
import unittest

from tools import verify_upstream_rust_parity_ledger_v3 as gate


class UpstreamRustParityLedgerV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate._load(gate.LEDGER)

    def validate(self, document=None):
        return gate.validate(self.document if document is None else document)

    def test_current_successor_is_valid_and_keeps_all_rows_open(self) -> None:
        result = self.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["rows"], 15)
        self.assertEqual(result["completion_open"], 15)
        self.assertEqual(result["current_evidence_rows"], 13)
        self.assertEqual(result["historical_only_rows"], 2)

    def test_row_omission_and_duplicate_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"].pop()
        with self.assertRaisesRegex(gate.LedgerError, "ledger_row_set_invalid"):
            self.validate(mutated)

        mutated = copy.deepcopy(self.document)
        mutated["rows"][1]["id"] = mutated["rows"][0]["id"]
        with self.assertRaisesRegex(gate.LedgerError, "row_duplicate"):
            self.validate(mutated)

    def test_evidence_commit_tree_and_archive_are_bound(self) -> None:
        for field, reason in (("commit", "evidence_commit_identity_drift"), ("tree", "evidence_commit_identity_drift"), ("archive_sha256", "evidence_archive_drift")):
            mutated = copy.deepcopy(self.document)
            mutated["evidence_commit"][field] = "0" * (64 if field == "archive_sha256" else 40)
            with self.assertRaisesRegex(gate.LedgerError, reason):
                self.validate(mutated)

    def test_predecessor_and_governance_hashes_are_bound(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["successor"]["predecessor"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.LedgerError, "predecessor_hash_drift"):
            self.validate(mutated)

        mutated = copy.deepcopy(self.document)
        mutated["evidence_bindings"]["product_boundary"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.LedgerError, "product_boundary_hash_drift"):
            self.validate(mutated)

    def test_manifest_and_audit_path_hash_are_bound(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["evidence"]["manifest"]["path"] = "docs/baselines/not-the-manifest.yaml"
        with self.assertRaisesRegex(gate.LedgerError, "manifest:AS-01_path_drift"):
            self.validate(mutated)

        mutated = copy.deepcopy(self.document)
        mutated["rows"][1]["evidence"]["audit"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.LedgerError, "audit_binding_drift:AS-02"):
            self.validate(mutated)

    def test_source_archive_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][1]["source_binding"]["candidate_archive_sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.LedgerError, "source_binding_drift:AS-02"):
            self.validate(mutated)

        mutated = copy.deepcopy(self.document)
        mutated["rows"][6]["source_binding"]["candidate_commit"] = "0" * 40
        with self.assertRaisesRegex(gate.LedgerError, "source_binding_drift:PB-01"):
            self.validate(mutated)

    def test_pb_scoped_pass_cannot_be_globalized(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][6]["scope"]["global_row_parity"] = True
        with self.assertRaisesRegex(gate.LedgerError, "pb_scope_promoted:PB-01"):
            self.validate(mutated)

    def test_pb03_oracle_and_com_candidate_parity_remain_blocked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][8]["scope"]["oracle"] = "passed"
        with self.assertRaisesRegex(gate.LedgerError, "pb03_scope_promoted"):
            self.validate(mutated)

        mutated = copy.deepcopy(self.document)
        mutated["rows"][12]["scope"]["candidate_vs_upstream_parity"] = "accepted"
        with self.assertRaisesRegex(gate.LedgerError, "com_scope_promoted:COM-02"):
            self.validate(mutated)

    def test_historical_rows_cannot_be_rebound(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][11]["evidence"]["historical_manifest"]["bound_to_evidence_commit"] = True
        with self.assertRaisesRegex(gate.LedgerError, "historical_rebound:COM-01"):
            self.validate(mutated)

        mutated = copy.deepcopy(self.document)
        mutated["rows"][13]["evidence"]["historical_audit"]["path"] = "docs/baselines/other-audit.md"
        with self.assertRaisesRegex(gate.LedgerError, "historical_audit_binding_drift:COM-03"):
            self.validate(mutated)

    def test_completion_and_product_capability_cannot_be_promoted(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["completion"] = "closed"
        with self.assertRaisesRegex(gate.LedgerError, "row_completion_promoted:AS-01"):
            self.validate(mutated)

        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["product_capability"] = "claimed"
        with self.assertRaisesRegex(gate.LedgerError, "row_product_capability_promoted:AS-01"):
            self.validate(mutated)


if __name__ == "__main__":
    unittest.main()
