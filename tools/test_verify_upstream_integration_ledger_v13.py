"""Mutation coverage for the v13 additive upstream integration ledger gate."""

from __future__ import annotations

import copy
import unittest

from tools import verify_upstream_integration_ledger_v13 as gate

EXPECTED_VERIFIER_SHA256 = "c0868125d23f3aed6c052167800c95ef48b110ac99be856f3cf725344ace8edc"


class LedgerV13Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = gate._load()

    def row(self, document: dict, row_id: str) -> dict:
        return next(row for row in document["rows"] if row["id"] == row_id)

    def reject(self, document: dict, reason: str = "") -> None:
        with self.assertRaises(gate.LedgerError, msg=reason):
            gate.validate(document)

    def test_v13_baseline_and_harness_anchor(self) -> None:
        self.assertEqual(EXPECTED_VERIFIER_SHA256, gate.EXPECTED_VERIFIER_SHA)
        self.assertEqual(gate.validate(copy.deepcopy(self.document)), {"valid": True, "rows": 15, "release_ready": 0})

    def test_successor_candidate_and_archive_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["successor"]["predecessor_sha256"] = "0" * 64
        self.reject(mutated, "predecessor")
        for key in ("commit", "tree", "archive_sha256", "archive_bytes"):
            mutated = copy.deepcopy(self.document)
            mutated["candidate"][key] = 1 if key == "archive_bytes" else "0" * (40 if key == "commit" else 64)
            self.reject(mutated, "candidate:" + key)

    def test_current_formal_evidence_bindings_are_locked(self) -> None:
        mutations = (
            ("AS-03", "formal_manifest", "sha256"),
            ("PB-01", "formal_manifest", "sha256"),
            ("COM-01", "formal_manifest", "sha256"),
            ("COM-03", "formal_manifest", "sha256"),
        )
        for row_id, section, key in mutations:
            mutated = copy.deepcopy(self.document)
            self.row(mutated, row_id)["current_observation"][section][key] = "0" * 64
            self.reject(mutated, row_id + ":" + section)
        for row_id, key, value in (
            ("AS-03", "status", "passed_numeric"),
            ("PB-01", "pb01_duo_blocked", False),
            ("PB-02", "pb02_blocked_case_count", 0),
            ("COM-01", "parity_claim", "complete_com_parity"),
            ("COM-03", "matched_case_count", 22),
        ):
            mutated = copy.deepcopy(self.document)
            self.row(mutated, row_id)["current_observation"][key] = value
            self.reject(mutated, row_id + ":" + key)

    def test_as03_numeric_scope_cannot_be_promoted(self) -> None:
        for key, value in (("real_bits", 5), ("differing_real_bits", 0), ("max_ulp", 0), ("numeric_parity", True), ("global_parity", True), ("release_ready", True), ("no_s_parameter_fit", False)):
            mutated = copy.deepcopy(self.document)
            self.row(mutated, "AS-03")["current_observation"][key] = value
            self.reject(mutated, "AS-03:" + key)
        for claim in ("blocked_numeric_semantics", "max_one_ulp_is_not_acceptance", "no_numeric_parity", "no_s_parameter_fit"):
            mutated = copy.deepcopy(self.document)
            self.row(mutated, "AS-03")["non_claims"].remove(claim)
            self.reject(mutated, "AS-03:nonclaim:" + claim)

    def test_pb_matrix_counts_and_release_gate_are_locked(self) -> None:
        for row_id, key, value in (("PB-01", "pb01_passed_case_count", 6), ("PB-01", "fresh_replays_consistent", False), ("PB-01", "pb02_blocked_case_count", 5), ("PB-02", "fresh_replay_count", 1), ("PB-02", "whole_payload_parity", True), ("PB-02", "release_ready", True)):
            mutated = copy.deepcopy(self.document)
            self.row(mutated, row_id)["current_observation"][key] = value
            self.reject(mutated, "PB:" + row_id + ":" + key)
        mutated = copy.deepcopy(self.document)
        self.row(mutated, "PB-01")["non_claims"].remove("pb01_duo_binary_blocked")
        self.reject(mutated, "PB-01:nonclaim")

    def test_com_current_scoped_statuses_cannot_be_promoted(self) -> None:
        for row_id in ("COM-01", "COM-03"):
            for key, value in (("acceptance", True), ("complete_com_parity", True), ("global_migration_row_closed", True), ("product_capability_promoted", True), ("release_ready", True), ("no_s_parameter_fit", False), ("channel_policy", "multi_pass_sparam_fit")):
                mutated = copy.deepcopy(self.document)
                self.row(mutated, row_id)["current_observation"][key] = value
                self.reject(mutated, row_id + ":" + key)
        mutated = copy.deepcopy(self.document)
        self.row(mutated, "COM-01")["non_claims"].remove("no_complete_com_parity")
        self.reject(mutated, "COM-01:nonclaim")

    def test_as05_owner_exclusion_and_channel_policy_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        self.row(mutated, "AS-05")["current_observation"]["owner_decision"] = "required"
        self.reject(mutated, "AS-05:owner")
        mutated = copy.deepcopy(self.document)
        self.row(mutated, "AS-05")["current_observation"]["xyce_xdm_extension"] = "implemented"
        self.reject(mutated, "AS-05:xyce")
        mutated = copy.deepcopy(self.document)
        mutated["policy"]["s_parameter_fit"] = "allowed"
        self.reject(mutated, "policy:s-fit")
        mutated = copy.deepcopy(self.document)
        mutated["policy"]["channel_policy"] = "multi_pass_sparam_fit"
        self.reject(mutated, "policy:channel")

    def test_plan_audit_sources_and_harness_hashes_are_locked(self) -> None:
        for section in ("plan", "audit"):
            mutated = copy.deepcopy(self.document)
            mutated[section]["sha256"] = "0" * 64
            self.reject(mutated, section)
        for key in ("as03_power_wave_replay", "pb_portable_matrix_formal", "com01_fingerprint_stage2", "com03_current_replay"):
            mutated = copy.deepcopy(self.document)
            mutated["current_sources"][key]["sha256"] = "0" * 64
            self.reject(mutated, "source:" + key)
        mutated = copy.deepcopy(self.document)
        mutated["harness"]["verifier"]["path"] = "tools/verify_upstream_integration_ledger_v12.py"
        self.reject(mutated, "harness:path")
        mutated = copy.deepcopy(self.document)
        mutated["harness"]["mutation_tests"]["sha256"] = "0" * 64
        self.reject(mutated, "harness:hash")

    def test_shape_and_exact_types_fail_closed(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"].append(copy.deepcopy(mutated["rows"][0]))
        self.reject(mutated, "row-count")
        mutated = copy.deepcopy(self.document)
        mutated["summary"]["release_ready"] = False
        self.reject(mutated, "summary:type")
        mutated = copy.deepcopy(self.document)
        mutated["candidate"]["archive_bytes"] = float(mutated["candidate"]["archive_bytes"])
        self.reject(mutated, "candidate:type")
        mutated = copy.deepcopy(self.document)
        mutated["unexpected"] = True
        self.reject(mutated, "top-keys")

    def test_unsafe_paths_fail_closed(self) -> None:
        for path in ("../outside", "/absolute", "C:/outside", "docs\\outside", "temp/report.json"):
            self.assertFalse(gate._safe(path))
        mutated = copy.deepcopy(self.document)
        mutated["current_sources"]["com03_current_replay"]["path"] = "../outside"
        self.reject(mutated, "unsafe-path")


if __name__ == "__main__":
    unittest.main()
