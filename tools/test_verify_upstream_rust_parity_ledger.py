from __future__ import annotations

import copy
import unittest

from tools import verify_upstream_rust_parity_ledger as gate


class UpstreamRustParityLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate._load(gate.LEDGER)

    def validate(self, document=None):
        return gate.validate(document=self.document if document is None else document)

    def test_current_ledger_is_open_before_source_admission(self) -> None:
        result = self.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["rows"], 15)
        self.assertEqual(result["current_states"]["source_admitted"], 0)
        self.assertEqual(result["terminal_states"]["rust_parity_accepted"], 0)

    def test_row_omission_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"].pop()
        with self.assertRaisesRegex(gate.LedgerError, "ledger_row_set_invalid"):
            self.validate(mutated)

    def test_duplicate_row_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][1]["id"] = "AS-01"
        with self.assertRaisesRegex(gate.LedgerError, "ledger_rows_duplicate|ledger_row_set_invalid"):
            self.validate(mutated)

    def test_audit_hash_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["evidence_bindings"]["audit_document"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.LedgerError, "audit_binding_hash_drift"):
            self.validate(mutated)

    def test_exact_entrypoint_blob_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["source"]["entrypoint_blob_sha1"] = "0" * 40
        with self.assertRaisesRegex(gate.LedgerError, "entrypoint_binding_drift"):
            self.validate(mutated)

    def test_reachable_module_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["source"]["reachable_modules"].append("src/agent_spice/not-real.py")
        with self.assertRaisesRegex(gate.LedgerError, "reachable_modules_drift"):
            self.validate(mutated)

    def test_source_admission_cannot_skip_per_path_license_approval(self) -> None:
        mutated = copy.deepcopy(self.document)
        row = mutated["rows"][0]
        row["stages"]["source_admitted"] = {"status": "verified", "evidence": ["migration_inventory", "candidate_coverage"]}
        row["current_state"] = "source_admitted"
        with self.assertRaisesRegex(gate.LedgerError, "source_admission_license_pending"):
            self.validate(mutated)

    def test_later_stage_cannot_be_verified_behind_a_blocker(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["stages"]["oracle_bound"] = {"status": "verified", "evidence": ["future"]}
        with self.assertRaisesRegex(gate.LedgerError, "stage_order_violation"):
            self.validate(mutated)

    def test_blocked_stage_must_name_its_missing_evidence(self) -> None:
        mutated = copy.deepcopy(self.document)
        del mutated["rows"][0]["stages"]["branch_frozen"]["missing"]
        with self.assertRaisesRegex(gate.LedgerError, "stage_missing_reason"):
            self.validate(mutated)

    def test_branch_unknown_counts_cannot_be_promoted_from_unknown(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["branch_inventory"]["unknown_counts"] = {"branch": 1, "default": 0, "error": 0, "artifact": 0}
        mutated["rows"][0]["stages"]["branch_frozen"] = {"status": "verified", "evidence": ["future"]}
        with self.assertRaisesRegex(gate.LedgerError, "stage_order_violation"):
            self.validate(mutated)

    def test_terminal_external_retention_requires_authority(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["completion"] = {"status": "closed", "terminal_state": "retained_external_runtime", "authority_evidence": None}
        with self.assertRaisesRegex(gate.LedgerError, "terminal_authority_shape_invalid"):
            self.validate(mutated)

    def test_owner_exclusion_requires_a_real_authority_file(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["completion"] = {
            "status": "closed",
            "terminal_state": "excluded_by_owner",
            "authority_evidence": {
                "kind": "owner_decision",
                "decision_id": "owner-test",
                "path": "docs/baselines/missing-owner-decision.md",
                "sha256": "0" * 64,
                "statement": "test",
            },
        }
        with self.assertRaisesRegex(gate.LedgerError, "terminal_authority_file_missing"):
            self.validate(mutated)

    def test_reserved_pb02_interface_is_not_promoted(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["reserved_evidence_interfaces"]["PB-02"]["status"] = "verified"
        with self.assertRaisesRegex(gate.LedgerError, "reserved_interface_policy_invalid"):
            self.validate(mutated)

    def test_reserved_com03_interface_is_not_promoted(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][13]["reserved_interface"] = "COM-02"
        with self.assertRaisesRegex(gate.LedgerError, "reserved_interface_missing"):
            self.validate(mutated)

    def test_candidate_hash_claim_requires_items(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["candidate_source_hashes"]["status"] = "verified"
        with self.assertRaisesRegex(gate.LedgerError, "candidate_source_hash_shape_invalid"):
            self.validate(mutated)


if __name__ == "__main__":
    unittest.main()
