"""Mutation tests for the narrow P5-09 wording contract."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from tools import verify_p5_09_com_behavior_replica_wording as GATE


class P509WordingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = GATE._load(GATE.SPEC)
        self.evidence = GATE._load(GATE.EVIDENCE)

    def test_current_contract_is_valid(self) -> None:
        result = GATE.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["closure"], "scoped_wording_only")
        self.assertFalse(result["product_acceptance"])
        self.assertFalse(result["promotion"])
        self.assertEqual(result["wording_scope"], "candidate_only")
        self.assertEqual(result["behavioral_replication"], "not_claimed")
        self.assertEqual(result["product_capability"], "not_claimed")

    def test_candidate_wording_does_not_claim_replication_or_product_capability(self) -> None:
        self.assertEqual(self.spec["status"], "scoped_closed_wording_only")
        self.assertEqual(self.spec["scope"]["behavioral_replication"], "not_claimed")
        self.assertEqual(self.spec["scope"]["product_capability"], "not_claimed")
        self.assertIn("no completed behavioral replication is claimed", self.spec["wording"]["report_claim"])

    def _assert_rejects_positive_claim(self, claim: str) -> None:
        spec = copy.deepcopy(self.spec)
        spec["wording"]["report_claim"] = claim
        # Keep the mutation on the policy's canonical field so the test reaches
        # the forbidden-pattern gate rather than only the canonical-value gate.
        with patch.dict(GATE.EXPECTED_WORDING, {"report_claim": claim}):
            with self.assertRaisesRegex(GATE.P509Error, "forbidden_positive_wording"):
                GATE.validate_spec(spec)

    def test_rejects_ieee_certified_claim(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["wording"]["report_claim"] = "IEEE-certified COM capability."
        with self.assertRaises(GATE.P509Error):
            GATE.validate_spec(spec)

    def test_rejects_official_reference_implementation_claim(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["wording"]["capability_description"] = "Official reference implementation for COM."
        with self.assertRaises(GATE.P509Error):
            GATE.validate_spec(spec)

    def test_rejects_conformance_claim(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["wording"]["report_title"] = "COM conformance report"
        with self.assertRaises(GATE.P509Error):
            GATE.validate_spec(spec)

    def test_rejects_release_claim(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["wording"]["capability_description"] = "Release-ready COM capability."
        with self.assertRaises(GATE.P509Error):
            GATE.validate_spec(spec)

    def test_rejects_standards_compliant_claim(self) -> None:
        for claim in (
            "IEEE standards-compliant COM capability.",
            "IEEE/standards compliant COM capability.",
            "Standards-compliant COM capability.",
        ):
            with self.subTest(claim=claim):
                self._assert_rejects_positive_claim(claim)

    def test_rejects_validated_approved_qualified_claims(self) -> None:
        for adjective in ("Validated", "Approved", "Qualified"):
            with self.subTest(adjective=adjective):
                self._assert_rejects_positive_claim(f"{adjective} COM capability.")

    def test_rejects_equivalent_match_and_pass_claims(self) -> None:
        for claim in (
            "Equivalent to the COM reference.",
            "Matches the COM reference.",
            "Passes the COM acceptance check.",
        ):
            with self.subTest(claim=claim):
                self._assert_rejects_positive_claim(claim)

    def test_rejects_completed_behavioral_replication_claim(self) -> None:
        self._assert_rejects_positive_claim("Completed behavioral replication of the selected profile.")

    def test_rejects_external_oracle_blocker_removal(self) -> None:
        spec = copy.deepcopy(self.spec)
        spec["scope"]["external_oracle"] = "observed"
        with self.assertRaises(GATE.P509Error):
            GATE.validate_spec(spec)

    def test_rejects_bound_publication_drift(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["bindings"][1]["sha256"] = "0" * 64
        with self.assertRaises(GATE.P509Error):
            GATE.validate_evidence(evidence)

    def test_rejects_contract_hash_drift(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["contract"]["sha256"] = "0" * 64
        with self.assertRaises(GATE.P509Error):
            GATE.validate_evidence(evidence)


if __name__ == "__main__":
    unittest.main()
