"""Mutation coverage for the additive upstream integration ledger v5."""

from __future__ import annotations

import copy
import hashlib
import unittest

from tools import verify_upstream_integration_ledger_v5 as gate


EXPECTED_VERIFIER_SHA256 = "218e195715d2f6b8b21e8480f947dad437aa7f141309de8ff981ebd221eee5d7"


class UpstreamIntegrationLedgerV5Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate._load()

    def assert_rejected(self, document: dict, reason: str) -> None:
        with self.assertRaisesRegex(gate.LedgerError, reason):
            gate.validate(document)

    def test_current_snapshot_is_valid_and_open(self) -> None:
        # The ledger/audit files are created together; this test is also the
        # strict post-write gate used by the owner before reporting hashes.
        self.assertEqual(gate.validate(self.document)["valid"], True)
        self.assertEqual(self.document["summary"]["rows"], 15)
        self.assertEqual(self.document["summary"]["release_ready"], 0)
        verifier_path = gate.ROOT / "tools/verify_upstream_integration_ledger_v5.py"
        self.assertEqual(hashlib.sha256(verifier_path.read_bytes()).hexdigest(), EXPECTED_VERIFIER_SHA256)

    def test_fake_promotion_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["summary"]["release_ready"] = 1
        self.assert_rejected(mutated, "summary_drift")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][4]["parity_evidence"] = "scoped_observation"
        self.assert_rejected(mutated, "row_policy:AS-05")

    def test_row_deletion_and_hash_drift_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"].pop()
        self.assert_rejected(mutated, "row_count")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["evidence"]["sha256"] = "0" * 64
        self.assert_rejected(mutated, "row_evidence:AS-01_hash_drift")

    def test_as05_external_parity_cannot_be_promoted(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][4]["parity_evidence"] = "scoped_numeric_mismatch_open"
        self.assert_rejected(mutated, "row_policy:AS-05")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][4]["non_claims"] = ["workflow_observed_only"]
        self.assert_rejected(mutated, "row_non_claims:AS-05")

    def test_pb_vendor_claim_and_com_vtf_claim_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][9]["parity_evidence"] = "scoped_observation"
        self.assert_rejected(mutated, "row_policy:PB-04")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][12]["non_claims"] = ["no_sparam_fit"]
        self.assert_rejected(mutated, "row_non_claims:COM-02")

    def test_supplemental_hash_and_promotion_gates_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["supplemental_evidence"][2]["sha256"] = "0" * 64
        self.assert_rejected(mutated, "supplemental_drift:com-selector-vtf-gap")
        mutated = copy.deepcopy(self.document)
        mutated["supplemental_evidence"][1]["release_promotion"] = True
        self.assert_rejected(mutated, "supplemental_promotion")

    def test_as05_manifest_and_nonclaim_union_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][4]["current_observation"]["sha256"] = "0" * 64
        self.assert_rejected(mutated, "row_current_observation:AS-05_hash_drift")
        mutated = copy.deepcopy(self.document)
        mutated["supplemental_evidence"][0]["non_claims"].pop()
        self.assert_rejected(mutated, "supplemental_non_claims:as05-attested-ngspice")
        for index, row in enumerate(self.document["rows"]):
            mutated = copy.deepcopy(self.document)
            mutated["rows"][index]["non_claims"] = list(row["non_claims"][:-1])
            self.assert_rejected(mutated, f"row_non_claims:{row['id']}")

    def test_malformed_shapes_and_coordinated_self_declaration_fail_closed(self) -> None:
        for field, reason in (("candidate", "candidate_not_mapping"), ("audit", "audit_not_mapping")):
            mutated = copy.deepcopy(self.document)
            mutated[field] = "malformed"
            self.assert_rejected(mutated, reason)
        mutated = copy.deepcopy(self.document)
        mutated["supplemental_evidence"][0] = "malformed"
        self.assert_rejected(mutated, "supplemental_item_not_mapping")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0] = "malformed"
        self.assert_rejected(mutated, "row_not_mapping:AS-01")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["evidence"] = "malformed"
        self.assert_rejected(mutated, "row_evidence:AS-01_not_mapping")
        for field, key, reason in (("candidate", "tree", "candidate_keys"), ("audit", "sha256", "audit_keys")):
            mutated = copy.deepcopy(self.document)
            mutated[field].pop(key)
            self.assert_rejected(mutated, reason)
        mutated = copy.deepcopy(self.document)
        mutated["supplemental_evidence"][0].pop("sha256")
        self.assert_rejected(mutated, "supplemental_keys")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][4].pop("current_observation")
        self.assert_rejected(mutated, "row_keys:AS-05")
        mutated = copy.deepcopy(self.document)
        mutated["harness"]["verifier"] = copy.deepcopy(mutated["harness"]["mutation_tests"])
        self.assert_rejected(mutated, "harness_verifier_path")
        mutated = copy.deepcopy(self.document)
        mutated["audit"]["path"] = "docs/baselines/upstream-integration-ledger.v4.yaml"
        mutated["audit"]["sha256"] = gate._sha(gate.ROOT / mutated["audit"]["path"])
        self.assert_rejected(mutated, "audit_keys")

    def test_same_path_coordinated_content_and_hash_drift_is_rejected(self) -> None:
        audit_path = gate.ROOT / self.document["audit"]["path"]
        audit_bytes = audit_path.read_bytes()
        try:
            audit_path.write_bytes(audit_bytes + b"\ncoordinated ledger/audit mutation\n")
            mutated = copy.deepcopy(self.document)
            mutated["audit"]["sha256"] = gate._sha(audit_path)
            self.assert_rejected(mutated, "audit_anchor")
        finally:
            audit_path.write_bytes(audit_bytes)

        verifier_path = gate.ROOT / self.document["harness"]["verifier"]["path"]
        verifier_bytes = verifier_path.read_bytes()
        try:
            verifier_path.write_bytes(verifier_bytes + b"\n# coordinated harness mutation\n")
            mutated = copy.deepcopy(self.document)
            mutated["harness"]["verifier"]["sha256"] = gate._sha(verifier_path)
            self.assert_rejected(mutated, "verifier_anchor")
        finally:
            verifier_path.write_bytes(verifier_bytes)

    def test_path_escape_and_audit_swap_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["evidence"]["path"] = "../release.yaml"
        self.assert_rejected(mutated, "row_evidence:AS-01_path")
        mutated = copy.deepcopy(self.document)
        mutated["audit"]["path"] = "docs/baselines/upstream-integration-ledger.v4.yaml"
        self.assert_rejected(mutated, "audit_keys")


if __name__ == "__main__":
    unittest.main()
