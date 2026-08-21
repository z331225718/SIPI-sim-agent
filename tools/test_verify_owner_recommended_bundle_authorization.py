"""Mutation tests for the recommended-bundle owner authorization."""

from __future__ import annotations

import copy
import unittest

from tools import verify_owner_recommended_bundle_authorization as GATE


class OwnerRecommendedBundleAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = GATE._load(GATE.DOCUMENT)

    def test_current_document_is_valid(self) -> None:
        self.assertTrue(GATE.validate()["valid"])

    def test_rejects_decision_drift(self) -> None:
        for key in ("D1", "D2", "D4", "D5", "D6", "E3", "E4"):
            document = copy.deepcopy(self.document)
            document["decisions"][key] = "B"
            with self.subTest(key=key), self.assertRaises(GATE.AuthorizationError):
                GATE.validate(document)

    def test_rejects_tolerance_or_alignment_drift(self) -> None:
        for key, value in (("absolute_tolerance_db", 1.0), ("alignment", "best_fit")):
            document = copy.deepcopy(self.document)
            document["decisions"]["D3"][key] = value
            with self.subTest(key=key), self.assertRaises(GATE.AuthorizationError):
                GATE.validate(document)

    def test_rejects_redistribution_promotion(self) -> None:
        document = copy.deepcopy(self.document)
        document["external_boundary"]["third_party_bytes_in_release"] = "allowed"
        with self.assertRaises(GATE.AuthorizationError):
            GATE.validate(document)

    def test_rejects_release_oracle_promotion(self) -> None:
        document = copy.deepcopy(self.document)
        document["non_claims"].remove("p7_release_gates_remain_blocked")
        with self.assertRaises(GATE.AuthorizationError):
            GATE.validate(document)


if __name__ == "__main__":
    unittest.main()
