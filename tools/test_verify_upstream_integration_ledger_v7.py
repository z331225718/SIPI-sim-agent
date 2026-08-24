"""Mutation coverage for the v7 additive upstream ledger gate."""

from __future__ import annotations

import copy
import unittest

from tools import verify_upstream_integration_ledger_v7 as gate

EXPECTED_VERIFIER_SHA256 = "772d409710dbdedaf30e8771ca8d02bc38523375484c5c63144c3cd712347049"

class UpstreamIntegrationLedgerV7Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate._load()

    def reject(self, document: dict, reason: str) -> None:
        with self.assertRaisesRegex(gate.LedgerError, reason):
            gate.validate(document)

    def test_current_snapshot_is_open_and_inherits_v6(self) -> None:
        self.assertEqual(gate.validate(self.document), {"valid": True, "rows": 15, "release_ready": 0})
        self.assertEqual(self.document["successor"]["predecessor_sha256"], gate.V6_SHA)
        self.assertEqual(self.document["summary"]["release_ready"], 0)
        verifier_path = gate.ROOT / "tools/verify_upstream_integration_ledger_v7.py"
        self.assertEqual(gate._sha(verifier_path), EXPECTED_VERIFIER_SHA256)

    def test_fake_close_and_release_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["summary"]["release_ready"] = 1
        self.reject(mutated, "summary")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][12]["parity_evidence"] = "scoped_observation"
        self.reject(mutated, "row_policy:COM-02")

    def test_row_deletion_hash_and_path_escape_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"].pop()
        self.reject(mutated, "row_count|row_identity")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["evidence"]["sha256"] = "0" * 64
        self.reject(mutated, "evidence_exact:AS-01")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["evidence"]["path"] = "../release.yaml"
        self.reject(mutated, "evidence_exact:AS-01")

    def test_as06_build_claim_and_pb_vendor_claims_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][5]["non_claims"] = ["no_release"]
        self.reject(mutated, "nonclaims:AS-06")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][9]["parity_evidence"] = "scoped_observation"
        self.reject(mutated, "row_policy:PB-04")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][9]["non_claims"] = ["no_release"]
        self.reject(mutated, "nonclaims:PB-04")

    def test_as04_pb_inventory_and_com_public_claims_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][3]["current_observation"]["path"] = "C:/source-map.yaml"
        self.reject(mutated, "current_observation:AS-04")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][6]["current_observation"]["sha256"] = "0" * 64
        self.reject(mutated, "current_observation:PB-01")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][12]["non_claims"].remove("no_public_accm_e2e")
        self.reject(mutated, "nonclaims:COM-02")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][12]["non_claims"].append("public_accm_parity")
        self.reject(mutated, "nonclaims:COM-02")

    def test_com_fit_dc_accm_and_upstream_claims_are_rejected(self) -> None:
        for claim in ("no_sparam_fit", "no_public_accm_e2e", "no_clean_upstream_numeric_replay"):
            mutated = copy.deepcopy(self.document)
            mutated["rows"][12]["non_claims"].remove(claim)
            self.reject(mutated, "nonclaims:COM-02")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][12]["non_claims"] = list(mutated["rows"][12]["non_claims"]) + ["full_upstream_parity"]
        # Unknown promotion language is not an allowed non-claim vocabulary.
        self.reject(mutated, "nonclaims:COM-02")

    def test_source_predecessor_audit_and_harness_drift_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["successor"]["predecessor_sha256"] = "0" * 64
        self.reject(mutated, "successor")
        mutated = copy.deepcopy(self.document)
        mutated["current_sources"]["com_source_map"]["sha256"] = "0" * 64
        self.reject(mutated, "source:com_source_map")
        mutated = copy.deepcopy(self.document)
        mutated["audit"]["path"] = "../audit.md"
        self.reject(mutated, "audit_shape|audit")
        mutated = copy.deepcopy(self.document)
        mutated["harness"]["verifier"]["path"] = "tools/verify_upstream_integration_ledger_v6.py"
        self.reject(mutated, "harness_verifier_hash|harness_paths|harness_verifier")

    def test_malformed_nested_shapes_fail_closed(self) -> None:
        for field in ("rows", "current_sources", "source_authority", "harness"):
            mutated = copy.deepcopy(self.document)
            mutated[field] = "malformed"
            self.reject(mutated, "row_shape:AS-01|sources_keys|source_authority|harness_shape|plan_hash|TypeError")

    def test_exact_evidence_and_current_observation_maps_are_locked(self) -> None:
        for index, row in enumerate(self.document["rows"]):
            mutated = copy.deepcopy(self.document)
            mutated["rows"][index]["evidence"]["path"] = "docs/baselines/other.yaml"
            self.reject(mutated, "evidence_exact:" + row["id"])
            if "current_observation" in row:
                mutated = copy.deepcopy(self.document)
                mutated["rows"][index]["current_observation"]["sha256"] = "0" * 64
                self.reject(mutated, "current_observation:" + row["id"])

    def test_nonclaims_are_ordered_and_extra_claims_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["non_claims"] = list(reversed(mutated["rows"][0]["non_claims"]))
        self.reject(mutated, "nonclaims:AS-01")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][12]["non_claims"].append("full_upstream_parity")
        self.reject(mutated, "nonclaims:COM-02")

    def test_windows_absolute_and_unc_paths_are_rejected(self) -> None:
        for path in ("C:/release.yaml", "//server/share/release.yaml", "\\\\server\\share\\release.yaml"):
            mutated = copy.deepcopy(self.document)
            mutated["rows"][0]["evidence"]["path"] = path
            self.reject(mutated, "evidence_exact:AS-01")

    def test_duplicate_and_unknown_top_level_keys_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"][0]["non_claims"].append("no_release")
        self.reject(mutated, "nonclaims:AS-01")
        mutated = copy.deepcopy(self.document)
        mutated["unexpected"] = True
        self.reject(mutated, "top_keys")

    def test_candidate_and_archive_controls_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["candidate"]["archive_bytes"] += 1
        self.reject(mutated, "candidate")
        mutated = copy.deepcopy(self.document)
        mutated["candidate"]["autocrlf"] = False
        self.reject(mutated, "candidate")

    def test_candidate_policy_and_summary_reject_bool_as_int(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["candidate"]["archive_bytes"] = True
        self.reject(mutated, "candidate_types")
        mutated = copy.deepcopy(self.document)
        mutated["policy"]["new_domain_features_allowed"] = 0
        self.reject(mutated, "policy_types")
        mutated = copy.deepcopy(self.document)
        mutated["summary"]["release_ready"] = False
        self.reject(mutated, "summary_types")

    def test_plan_binding_and_coordinated_drift_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["plan"]["sha256"] = "0" * 64
        self.reject(mutated, "plan")
        mutated = copy.deepcopy(self.document)
        mutated["plan"]["path"] = "../PLAN.md"
        self.reject(mutated, "plan_shape")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][3]["non_claims"].remove("no_numeric_parity")
        self.reject(mutated, "nonclaims:AS-04")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][7]["non_claims"].remove("no_current_numeric_replay")
        self.reject(mutated, "nonclaims:PB-02")

        plan_path = gate.ROOT / "PLAN.md"
        original = plan_path.read_bytes()
        try:
            plan_path.write_bytes(original + b"\ncoordinated promotion mutation\n")
            mutated = copy.deepcopy(self.document)
            mutated["plan"]["sha256"] = gate._sha(plan_path)
            self.reject(mutated, "plan_anchor")
        finally:
            plan_path.write_bytes(original)

    def test_source_and_authority_shapes_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["source_authority"]["agent_com"]["license"] = "BSD"
        self.reject(mutated, "source_authority_values")
        mutated = copy.deepcopy(self.document)
        mutated["current_sources"]["pb_ami_source_map"] = "bad"
        self.reject(mutated, "source:pb_ami_source_map")

    def test_audit_content_and_hash_cannot_self_declare(self) -> None:
        audit_path = gate.ROOT / self.document["audit"]["path"]
        original = audit_path.read_bytes()
        try:
            audit_path.write_bytes(original + b"\ncoordinated mutation\n")
            mutated = copy.deepcopy(self.document)
            mutated["audit"]["sha256"] = gate._sha(audit_path)
            self.reject(mutated, "audit_anchor")
        finally:
            audit_path.write_bytes(original)

    def test_harness_content_and_hash_cannot_self_declare(self) -> None:
        path = gate.ROOT / self.document["harness"]["verifier"]["path"]
        original = path.read_bytes()
        try:
            path.write_bytes(original + b"\n# coordinated mutation\n")
            mutated = copy.deepcopy(self.document)
            mutated["harness"]["verifier"]["sha256"] = gate._sha(path)
            self.reject(mutated, "harness_verifier_anchor")
        finally:
            path.write_bytes(original)

    def test_verifier_and_mutation_anchors_reject_coordinated_drift(self) -> None:
        verifier_path = gate.ROOT / self.document["harness"]["verifier"]["path"]
        verifier_bytes = verifier_path.read_bytes()
        try:
            verifier_path.write_bytes(verifier_bytes + b"\n# verifier coordinated drift\n")
            mutated = copy.deepcopy(self.document)
            mutated["harness"]["verifier"]["sha256"] = gate._sha(verifier_path)
            self.assertNotEqual(gate._sha(verifier_path), EXPECTED_VERIFIER_SHA256)
            self.reject(mutated, "harness_verifier_anchor")
        finally:
            verifier_path.write_bytes(verifier_bytes)

        mutation_path = gate.ROOT / self.document["harness"]["mutation_tests"]["path"]
        mutation_bytes = mutation_path.read_bytes()
        try:
            mutation_path.write_bytes(mutation_bytes + b"\n# mutation coordinated drift\n")
            mutated = copy.deepcopy(self.document)
            mutated["harness"]["mutation_tests"]["sha256"] = gate._sha(mutation_path)
            self.reject(mutated, "harness_mutation_anchor")
        finally:
            mutation_path.write_bytes(mutation_bytes)

    def test_malformed_audit_harness_and_current_values_are_ledger_errors(self) -> None:
        for path in (("audit", "bad"), ("harness", "bad"), ("current_sources", "bad")):
            mutated = copy.deepcopy(self.document)
            mutated[path[0]] = path[1]
            with self.assertRaises(gate.LedgerError):
                gate.validate(mutated)


if __name__ == "__main__":
    unittest.main()
