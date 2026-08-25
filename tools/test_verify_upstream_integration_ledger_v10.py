"""Mutation coverage for the v10 additive upstream ledger gate."""

from __future__ import annotations

import copy
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import verify_upstream_integration_ledger_v10 as gate

EXPECTED_VERIFIER_SHA256 = "0df7798920f82296a6f3b287baebc3d8de59e8d143b6d0307d9d9e159809b7f3"


class LedgerV10Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = gate._load()

    def reject(self, document: dict, reason: str = "") -> None:
        with self.assertRaises(gate.LedgerError, msg=reason):
            gate.validate(document)

    def row(self, document: dict, row_id: str) -> dict:
        return next(row for row in document["rows"] if row["id"] == row_id)

    def test_v10_baseline_is_valid(self) -> None:
        self.assertEqual(EXPECTED_VERIFIER_SHA256, gate.EXPECTED_VERIFIER_SHA)
        self.assertEqual(gate.validate(copy.deepcopy(self.document)), {"valid": True, "rows": 15, "release_ready": 0})

    def test_identity_candidate_and_predecessor_are_locked(self) -> None:
        for key in ("schema", "status"):
            mutated = copy.deepcopy(self.document)
            mutated[key] = "drift"
            self.reject(mutated, key)
        for key in ("commit", "tree", "archive_sha256", "archive_bytes"):
            mutated = copy.deepcopy(self.document)
            mutated["candidate"][key] = "0" * 64 if key != "archive_bytes" else 1
            self.reject(mutated, "candidate:" + key)
        mutated = copy.deepcopy(self.document)
        mutated["successor"]["predecessor_sha256"] = "0" * 64
        self.reject(mutated, "predecessor")

    def test_owner_disposition_policy_cannot_be_promoted(self) -> None:
        for row_id in ("AS-01", "AS-02"):
            mutated = copy.deepcopy(self.document)
            self.row(mutated, row_id)["integration_disposition"] = "direct_rust_port"
            self.reject(mutated, row_id + ":excluded")
        mutated = copy.deepcopy(self.document)
        self.row(mutated, "AS-03")["integration_disposition"] = "direct_rust_port"
        self.reject(mutated, "AS-03:retained")
        mutated = copy.deepcopy(self.document)
        self.row(mutated, "PB-04")["integration_disposition"] = "direct_rust_port"
        self.reject(mutated, "PB-04:external")

    def test_as05_as06_scope_controls_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        self.row(mutated, "AS-05")["current_observation"]["staging_source_map"]["path"] = "C:/solver.yaml"
        self.reject(mutated, "AS-05:path")
        mutated = copy.deepcopy(self.document)
        self.row(mutated, "AS-05")["non_claims"].remove("trusted_non_concurrent_roots")
        self.reject(mutated, "AS-05:roots")
        mutated = copy.deepcopy(self.document)
        self.row(mutated, "AS-06")["current_observation"]["external_execution"] = "portable_solver"
        self.reject(mutated, "AS-06:external")
        mutated = copy.deepcopy(self.document)
        self.row(mutated, "AS-06")["parity_evidence"] = "external_blocker_observed"
        self.reject(mutated, "AS-06:parity")

    def test_pb02_diagnostic_cannot_be_promoted_or_bound_to_temp(self) -> None:
        for key, value in (("arrays", "mismatch"), ("metrics", "mismatch"), ("formal_evidence", True), ("temp_report_bound", True), ("global_parity", True)):
            mutated = copy.deepcopy(self.document)
            mutated["rows"][7]["current_observation"]["diagnostic"][key] = value
            self.reject(mutated, "PB-02:diagnostic:" + key)
        mutated = copy.deepcopy(self.document)
        mutated["rows"][7]["current_observation"]["diagnostic"]["report_path"] = "C:/Temp/pb.json"
        self.reject(mutated, "PB-02:temp")

    def test_com02_scoped_winner_and_channel_policy_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][12]["current_observation"]["opaque_winner_final_metrics"] = "global_parity"
        self.reject(mutated, "COM-02:winner")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][12]["current_observation"]["s_parameter_fit"] = "enabled"
        self.reject(mutated, "COM-02:sparam")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][12]["current_observation"]["release"] = True
        self.reject(mutated, "COM-02:release")

    def test_current_observation_hashes_reject_promotion_and_extra_fields(self) -> None:
        mutations = (
            ("AS-06", "numeric_parity", True),
            ("PB-01", "branch_complete", True),
            ("COM-02", "full_entrypoint_parity", True),
            ("AS-04", "extra_path", "docs/extra.json"),
            ("PB-02", "release", True),
            ("PB-04", "capability", "accepted"),
        )
        for row_id, key, value in mutations:
            mutated = copy.deepcopy(self.document)
            self.row(mutated, row_id)["current_observation"][key] = value
            self.reject(mutated, "current_observation_exact:" + row_id)

    def test_source_change_commit_and_evidence_hashes_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["change_commits"]["pb_stage2_duo_semantics"] = "0" * 40
        self.reject(mutated, "commit")
        for index in (0, 2, 7, 12):
            mutated = copy.deepcopy(self.document)
            mutated["rows"][index]["evidence"]["sha256"] = "0" * 64
            self.reject(mutated, "evidence")
        mutated = copy.deepcopy(self.document)
        mutated["current_sources"]["com_source_map"]["sha256"] = "0" * 64
        self.reject(mutated, "source")

    def test_source_and_row_shapes_fail_closed(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["current_sources"] = "bad"
        self.reject(mutated, "sources")
        mutated = copy.deepcopy(self.document)
        mutated["rows"].append(copy.deepcopy(mutated["rows"][0]))
        self.reject(mutated, "rows")
        mutated = copy.deepcopy(self.document)
        mutated["unexpected"] = True
        self.reject(mutated, "top")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][7]["current_observation"]["diagnostic"]["temp_report_bound"] = "false"
        self.reject(mutated, "bool-string")

    def test_summary_and_plan_audit_harness_bindings_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["summary"]["release_ready"] = 1
        self.reject(mutated, "summary")
        mutated = copy.deepcopy(self.document)
        mutated["summary"]["release_ready"] = False
        self.reject(mutated, "summary-type")
        for section in ("plan", "audit"):
            mutated = copy.deepcopy(self.document)
            mutated[section]["sha256"] = "0" * 64
            self.reject(mutated, section)
        mutated = copy.deepcopy(self.document)
        mutated["harness"]["verifier"]["path"] = "tools/verify_upstream_integration_ledger_v9.py"
        self.reject(mutated, "harness-path")

    def test_harness_hashes_cannot_self_declare(self) -> None:
        mutated = copy.deepcopy(self.document)
        verifier = Path(gate.ROOT / "tools/verify_upstream_integration_ledger_v10.py")
        raw_verifier_sha = hashlib.sha256(verifier.read_bytes()).hexdigest()
        mutated["harness"]["verifier"]["sha256"] = raw_verifier_sha
        self.reject(mutated, "verifier-self-declare")
        mutated = copy.deepcopy(self.document)
        mutated["harness"]["mutation_tests"]["sha256"] = raw_verifier_sha
        self.reject(mutated, "mutation-self-declare")

    def test_coordinated_verifier_anchor_drift_still_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        drift = "f" * 64
        mutated["harness"]["verifier"]["sha256"] = drift
        with patch.object(gate, "EXPECTED_VERIFIER_SHA", drift), patch.object(gate, "_declared_test_verifier_sha", return_value=drift):
            self.reject(mutated, "coordinated-verifier-anchor-drift")


if __name__ == "__main__":
    unittest.main()
