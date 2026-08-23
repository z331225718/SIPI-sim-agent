from __future__ import annotations

import copy
import unittest

from tools import verify_upstream_rust_candidate_coverage_v2 as gate


class UpstreamRustCandidateCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate._load(gate.EVIDENCE)

    def validate(self, document=None, **kwargs):
        return gate.validate(
            document=self.document if document is None else document,
            source_roots={},
            **kwargs,
        )

    def test_current_audit_is_open_and_complete_in_shape(self) -> None:
        result = self.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["rows"], 15)
        self.assertEqual(result["candidate_counts"]["partial_surface"], 15)
        self.assertEqual(result["candidate_counts"]["absent"], 0)

    def test_all_pinned_source_objects_and_module_hashes_validate(self) -> None:
        result = gate.validate(
            document=self.document,
            source_roots=gate.UPSTREAM_ROOT_HINTS,
        )
        self.assertEqual(result["source_git_objects_checked"], ["agent_com", "agent_spice", "pybert"])

    def test_row_omission_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["entries"].pop()
        with self.assertRaisesRegex(gate.CoverageError, "row_count_invalid"):
            self.validate(mutated)

    def test_duplicate_or_unknown_row_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["entries"][1]["id"] = "AS-01"
        with self.assertRaisesRegex(gate.CoverageError, "row_set_invalid"):
            self.validate(mutated)

    def test_candidate_path_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["entries"][0]["candidate"]["surfaces"][0]["path"] = "crates/sipi-channel/src/lib.rs"
        with self.assertRaisesRegex(gate.CoverageError, "candidate_hash_drift|candidate_path_missing"):
            self.validate(mutated)

    def test_candidate_hash_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["entries"][0]["candidate"]["surfaces"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.CoverageError, "candidate_hash_drift"):
            self.validate(mutated)

    def test_self_test_cannot_be_reclassified_as_parity(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["entries"][0]["candidate"]["self_test_only"] = False
        with self.assertRaisesRegex(gate.CoverageError, "self_test_flag_invalid"):
            self.validate(mutated)

    def test_profile_only_row_cannot_be_promoted(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["entries"][4]["candidate"]["completion"] = "rust_parity_accepted"
        with self.assertRaisesRegex(gate.CoverageError, "candidate_promoted"):
            self.validate(mutated)

    def test_external_transport_cannot_be_reclassified_as_direct_parity(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["entries"][1]["candidate"]["classification"] = "direct_surface"
        with self.assertRaisesRegex(gate.CoverageError, "candidate_class_drift"):
            self.validate(mutated)

    def test_integration_surface_path_and_hash_are_bound(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["integration_surfaces"]["product_cli_registry"]["path"] = "crates/sipi-cli/src/lib.rs"
        with self.assertRaisesRegex(gate.CoverageError, "integration_surface_path_drift"):
            self.validate(mutated)

        mutated = copy.deepcopy(self.document)
        mutated["integration_surfaces"]["pybert_adapter"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.CoverageError, "candidate_hash_drift"):
            self.validate(mutated)

    def test_external_transport_omission_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        del mutated["entries"][0]["external_transport"]
        with self.assertRaisesRegex(gate.CoverageError, "external_transport_missing"):
            self.validate(mutated)

    def test_external_transport_cannot_claim_product_capability(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["entries"][0]["external_transport"]["product_capability"] = "claimed"
        with self.assertRaisesRegex(gate.CoverageError, "external_transport_drift"):
            self.validate(mutated)

    def test_caller_runtime_cannot_claim_pinned_source_attestation(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["entries"][0]["external_transport"]["runtime_source_attestation"] = "verified"
        with self.assertRaisesRegex(gate.CoverageError, "external_transport_drift"):
            self.validate(mutated)

    def test_external_transport_coverage_marker_is_required(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["entries"][0]["coverage"].remove("process_external_adapter_and_product_cli_route")
        with self.assertRaisesRegex(gate.CoverageError, "external_transport_coverage_missing"):
            self.validate(mutated)

    def test_stale_pre_route_role_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["entries"][0]["candidate"]["surfaces"][0]["role"] = "cli_manifest_without_fit_route"
        with self.assertRaisesRegex(gate.CoverageError, "stale_route_claim"):
            self.validate(mutated)

    def test_reachable_module_omission_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["entries"][0]["upstream"]["reachable_modules"].append("src/agent_spice/sparam/not_real.py")
        with self.assertRaisesRegex(gate.CoverageError, "reachable_module_unbound"):
            self.validate(mutated)

    def test_upstream_blob_drift_is_rejected_when_source_is_available(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["source_objects"]["agent_spice"]["modules"][0]["blob_sha1"] = "0" * 40
        with self.assertRaisesRegex(gate.CoverageError, "source_blob_drift"):
            gate.validate(document=mutated, source_roots=gate.UPSTREAM_ROOT_HINTS)

    def test_accounted_surface_omission_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["accounted_surfaces"]["pybert"].pop()
        with self.assertRaisesRegex(gate.CoverageError, "accounted_surface_set_drift"):
            self.validate(mutated)

    def test_audit_hash_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["audit_document"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.CoverageError, "audit_hash_drift"):
            self.validate(mutated)


if __name__ == "__main__":
    unittest.main()
