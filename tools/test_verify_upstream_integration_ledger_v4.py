"""Mutation coverage for the additive upstream integration ledger v4."""

from __future__ import annotations

import copy
import unittest

from tools import verify_upstream_integration_ledger_v4 as gate


class UpstreamIntegrationLedgerV4Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate._load()

    def test_current_successor_is_valid_and_open(self) -> None:
        self.assertEqual(gate.validate(self.document)["valid"], True)
        self.assertEqual(self.document["summary"]["rows"], 15)
        self.assertEqual(self.document["summary"]["release_ready"], 0)

    def test_schema_is_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["schema"] = "sipi.upstream-integration-ledger.v3"
        with self.assertRaisesRegex(gate.LedgerError, "schema_invalid"):
            gate.validate(mutated)

    def test_top_level_keys_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["unexpected"] = True
        with self.assertRaisesRegex(gate.LedgerError, "top_keys"):
            gate.validate(mutated)

    def test_successor_is_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["successor"]["reason"] = "rewritten"
        with self.assertRaisesRegex(gate.LedgerError, "successor_drift"):
            gate.validate(mutated)

    def test_policy_is_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["policy"]["external_runtime_is_not_parity"] = False
        with self.assertRaisesRegex(gate.LedgerError, "policy_drift"):
            gate.validate(mutated)

    def test_allowed_values_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["allowed_values"]["release_state"].append("released")
        with self.assertRaisesRegex(gate.LedgerError, "allowed_values_drift"):
            gate.validate(mutated)

    def test_candidate_commit_tree_archive_are_locked(self) -> None:
        for field, reason in (("commit", "candidate_commit_drift"), ("tree", "candidate_tree_drift"), ("archive_sha256", "candidate_archive_drift")):
            mutated = copy.deepcopy(self.document)
            mutated["candidate"][field] = "0" * (64 if field == "archive_sha256" else 40)
            with self.assertRaisesRegex(gate.LedgerError, "candidate_archive_sha256_drift" if field == "archive_sha256" else reason):
                gate.validate(mutated)

    def test_candidate_archive_bytes_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["candidate"]["archive_bytes"] += 1
        with self.assertRaisesRegex(gate.LedgerError, "candidate_archive_bytes_drift"):
            gate.validate(mutated)

    def test_three_source_authorities_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["source_authority"]["pybert"]["license"] = "MIT"
        with self.assertRaisesRegex(gate.LedgerError, "source_authority_drift:pybert:license"):
            gate.validate(mutated)

    def test_source_license_hashes_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["source_authority"]["agent_spice"]["license_sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.LedgerError, "source_authority_drift:agent_spice:license_sha256"):
            gate.validate(mutated)

    def test_provenance_order_is_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["provenance_documents"][0], mutated["provenance_documents"][1] = mutated["provenance_documents"][1], mutated["provenance_documents"][0]
        with self.assertRaisesRegex(gate.LedgerError, "provenance_exact"):
            gate.validate(mutated)

    def test_row_omission_and_duplicate_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"].pop()
        with self.assertRaisesRegex(gate.LedgerError, "row_count"):
            gate.validate(mutated)
        mutated = copy.deepcopy(self.document)
        mutated["rows"][1]["id"] = mutated["rows"][0]["id"]
        with self.assertRaisesRegex(gate.LedgerError, "row_set"):
            gate.validate(mutated)

    def test_orthogonal_field_values_are_locked(self) -> None:
        for field, value, reason in (
            ("integration_disposition", "invented", "disposition:AS-01"),
            ("runtime_availability", "portable", "row_policy:AS-05"),
            ("parity_evidence", "accepted", "evidence:AS-03"),
            ("release_state", "released", "release:AS-01"),
        ):
            mutated = copy.deepcopy(self.document)
            row_index = {"runtime_availability": 4, "parity_evidence": 2}.get(field, 0)
            mutated["rows"][row_index][field] = value
            with self.assertRaisesRegex(gate.LedgerError, reason):
                gate.validate(mutated)

    def test_external_as_rows_cannot_be_recast_as_portable(self) -> None:
        for index in (4, 5):
            mutated = copy.deepcopy(self.document)
            mutated["rows"][index]["runtime_availability"] = "portable"
            with self.assertRaisesRegex(gate.LedgerError, f"row_policy:AS-0{index + 1}"):
                gate.validate(mutated)

    def test_numeric_as_rows_cannot_be_promoted(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][2]["parity_evidence"] = "scoped_observation"
        with self.assertRaisesRegex(gate.LedgerError, "row_policy:AS-03"):
            gate.validate(mutated)

    def test_summary_is_recomputed_not_trusted(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["summary"]["direct_rust_port"] += 1
        with self.assertRaisesRegex(gate.LedgerError, "summary_drift"):
            gate.validate(mutated)

    def test_row_key_set_is_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        del mutated["rows"][0]["non_claims"]
        with self.assertRaisesRegex(gate.LedgerError, "row_keys:AS-01"):
            gate.validate(mutated)

    def test_row_non_claims_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["non_claims"].append("invented_claim")
        with self.assertRaisesRegex(gate.LedgerError, "row_non_claims:AS-01"):
            gate.validate(mutated)

    def test_supplemental_sha_is_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["supplemental_evidence"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.LedgerError, "supplemental_sha:pb-02-metallic-grid"):
            gate.validate(mutated)

    def test_supplemental_keys_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["supplemental_evidence"][0]["extra"] = True
        with self.assertRaisesRegex(gate.LedgerError, "supplemental_keys:pb-02-metallic-grid"):
            gate.validate(mutated)

    def test_provenance_keys_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["provenance_documents"][0]["extra"] = True
        with self.assertRaisesRegex(gate.LedgerError, "provenance_keys:0"):
            gate.validate(mutated)

    def test_harness_binding_keys_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["harness"]["mutation_tests"]["extra"] = True
        with self.assertRaisesRegex(gate.LedgerError, "harness_exact"):
            gate.validate(mutated)

    def test_exact_row_policy_blocks_as04_runtime_drift(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][3]["runtime_availability"] = "portable"
        with self.assertRaisesRegex(gate.LedgerError, "row_policy:AS-04"):
            gate.validate(mutated)

    def test_exact_row_policy_blocks_pb04_disposition_drift(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][9]["integration_disposition"] = "direct_rust_port"
        with self.assertRaisesRegex(gate.LedgerError, "row_policy:PB-04"):
            gate.validate(mutated)

    def test_exact_row_policy_blocks_com02_parity_drift(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][12]["parity_evidence"] = "scoped_observation"
        with self.assertRaisesRegex(gate.LedgerError, "row_policy:COM-02"):
            gate.validate(mutated)

    def test_path_escape_and_hash_drift_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["evidence"]["path"] = "../escape.yaml"
        with self.assertRaisesRegex(gate.LedgerError, "row_evidence:AS-01_path"):
            gate.validate(mutated)
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["evidence"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.LedgerError, "row_evidence:AS-01_hash_drift"):
            gate.validate(mutated)

    def test_provenance_and_audit_hashes_are_rejected_when_stale(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["provenance_documents"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.LedgerError, "provenance:0_hash_drift"):
            gate.validate(mutated)
        mutated = copy.deepcopy(self.document)
        mutated["audit"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.LedgerError, "audit_hash_drift"):
            gate.validate(mutated)


if __name__ == "__main__":
    unittest.main()
