"""Mutation tests for the P5-09 retired-wording product-report binding."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from tools import verify_p5_09b_com_behavior_replica_wording_retirement as GATE


class P509WordingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = GATE._load(GATE.SPEC)
        self.evidence = GATE._load(GATE.EVIDENCE)

    def test_current_contract_is_valid(self) -> None:
        result = GATE.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["closure"], "superseded")
        self.assertEqual(result["wording_scope"], "retired_unpublished_candidate")
        self.assertEqual(result["product_capability"], "bounded_artifact_execution_only")
        self.assertEqual(result["behavioral_replication"], "not_claimed")
        self.assertFalse(result["product_acceptance"])

    def test_real_product_report_is_bound(self) -> None:
        self.assertEqual(self.spec["consumer"]["symbol"], "ComRunArtifactExecutionReportV1")
        self.assertEqual(self.spec["consumer"]["producer"], "execute_com_run_artifact_v1")
        self.assertEqual(
            self.spec["consumer"]["semantics_status"],
            "product_owned_bounded_execution_complete",
        )
        self.assertEqual(self.spec["consumer"]["behavioral_replication_status"], "not_claimed")

    def test_candidate_wording_is_retired_not_promoted(self) -> None:
        self.assertEqual(self.spec["status"], "candidate_wording_retired_product_report_bound")
        self.assertEqual(self.spec["scope"]["product_behavior_replica"], "retired_unpublished_candidate")
        self.assertEqual(self.spec["wording"]["capability_label"], "bounded_artifact_execution")

    def _assert_rejects_positive_claim(self, claim: str) -> None:
        spec = copy.deepcopy(self.spec)
        spec["wording"]["report_claim"] = claim
        with patch.dict(GATE.EXPECTED_WORDING, {"report_claim": claim}):
            with self.assertRaisesRegex(GATE.P509Error, "forbidden_positive_wording"):
                GATE.validate_spec(spec)

    def test_rejects_certification_and_conformance_claims(self) -> None:
        for claim in (
            "IEEE-certified COM capability.",
            "Official reference implementation for COM.",
            "COM conformance result.",
            "Release-ready COM capability.",
        ):
            with self.subTest(claim=claim):
                self._assert_rejects_positive_claim(claim)

    def test_rejects_equivalence_match_and_acceptance_claims(self) -> None:
        for claim in (
            "Equivalent to the COM reference.",
            "Matches the COM reference.",
            "Passes the COM acceptance check.",
        ):
            with self.subTest(claim=claim):
                self._assert_rejects_positive_claim(claim)

    def test_rejects_completed_behavioral_replication_claim(self) -> None:
        self._assert_rejects_positive_claim("Completed behavioral replication of the selected profile.")

    def test_rejects_consumer_drift(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["consumer"]["symbol"] = "MissingReport"
        with self.assertRaisesRegex(GATE.P509Error, "consumer_binding_invalid"):
            GATE.validate_spec(spec)

    def test_rejects_product_report_hash_drift(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["bindings"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.P509Error, "evidence_binding_metadata_invalid"):
            GATE.validate_evidence(evidence)

    def test_rejects_external_acceptance_promotion(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["expected_scope"]["product_acceptance"] = True
        with self.assertRaisesRegex(GATE.P509Error, "evidence_scope_invalid"):
            GATE.validate_evidence(evidence)

    def test_rejects_contract_hash_drift(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["contract"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.P509Error, "evidence_contract_binding_invalid"):
            GATE.validate_evidence(evidence)


if __name__ == "__main__":
    unittest.main()
