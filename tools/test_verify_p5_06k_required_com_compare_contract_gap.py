"""Mutation tests for the additive P5-06k contract-gap verifier."""

from __future__ import annotations

import copy
import os
import unittest
from pathlib import Path

import yaml

from tools import verify_p5_06k_required_com_compare_contract_gap as verifier

EXTERNAL_ROOT = Path(os.environ.get("SIPI_COM_ROOT", str(verifier.ROOT.parent / "COM")))
EXTERNAL_AVAILABLE = (EXTERNAL_ROOT / ".git").exists()


class P506kContractGapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = yaml.safe_load(verifier.EVIDENCE.read_text(encoding="utf-8"))

    def assert_mutation_rejected(self, mutate) -> None:
        candidate = copy.deepcopy(self.document)
        mutate(candidate)
        with self.assertRaises(AssertionError):
            verifier.validate(candidate, verify_references=False)

    def test_baseline_valid(self) -> None:
        result = verifier.validate(self.document)
        self.assertTrue(result["valid"])
        self.assertFalse(result["source_git_object_checked"])

    @unittest.skipUnless(
        EXTERNAL_AVAILABLE,
        "canonical external COM Git checkout is unavailable",
    )
    def test_canonical_source_objects_verified(self) -> None:
        result = verifier.validate(self.document, source_root=EXTERNAL_ROOT)
        self.assertTrue(result["source_git_object_checked"])

    @unittest.skipUnless(
        EXTERNAL_AVAILABLE,
        "canonical external COM Git checkout is unavailable",
    )
    def test_wrong_root_rejected(self) -> None:
        with self.assertRaises(AssertionError):
            verifier.validate(self.document, source_root=verifier.ROOT)

    @unittest.skipUnless(EXTERNAL_AVAILABLE, "canonical external COM Git checkout is unavailable")
    def test_wrong_commit_rejected_by_source_checker(self) -> None:
        candidate = copy.deepcopy(self.document)
        candidate["canonical_agent_com"]["commit"] = "0" * 40
        with self.assertRaises(AssertionError):
            verifier._verify_source_git_objects(candidate, EXTERNAL_ROOT)

    @unittest.skipUnless(EXTERNAL_AVAILABLE, "canonical external COM Git checkout is unavailable")
    def test_wrong_blob_oid_rejected_by_source_checker(self) -> None:
        candidate = copy.deepcopy(self.document)
        candidate["canonical_agent_com"]["object_facts"][0]["git_blob"] = "0" * 40
        with self.assertRaises(AssertionError):
            verifier._verify_source_git_objects(candidate, EXTERNAL_ROOT)

    @unittest.skipUnless(EXTERNAL_AVAILABLE, "canonical external COM Git checkout is unavailable")
    def test_wrong_content_length_rejected_by_source_checker(self) -> None:
        candidate = copy.deepcopy(self.document)
        candidate["canonical_agent_com"]["object_facts"][0]["byte_length"] += 1
        with self.assertRaises(AssertionError):
            verifier._verify_source_git_objects(candidate, EXTERNAL_ROOT)

    @unittest.skipUnless(EXTERNAL_AVAILABLE, "canonical external COM Git checkout is unavailable")
    def test_wrong_content_hash_rejected_by_source_checker(self) -> None:
        candidate = copy.deepcopy(self.document)
        candidate["canonical_agent_com"]["object_facts"][0]["content_sha256"] = "0" * 64
        with self.assertRaises(AssertionError):
            verifier._verify_source_git_objects(candidate, EXTERNAL_ROOT)

    def test_c4_metric_substitution_for_td_iln_rejected(self) -> None:
        self.assert_mutation_rejected(
            lambda doc: doc["required_compare_contract"]["metric_bundle"]["required"][2]["source_aliases"].__setitem__(0, "ICN_mV")
        )

    def test_required_metric_scope_promotion_rejected(self) -> None:
        self.assert_mutation_rejected(
            lambda doc: doc["required_compare_contract"]["metric_bundle"]["observed_c4_surface"].update(
                {"scope": "required_com_compare", "cannot_substitute_for": []}
            )
        )

    def test_checkpoint_tolerance_fabrication_rejected(self) -> None:
        self.assert_mutation_rejected(
            lambda doc: doc["required_compare_contract"]["checkpoint_contract"].__setitem__(
                "status", "closed"
            )
        )

    def test_alignment_closure_rejected(self) -> None:
        self.assert_mutation_rejected(
            lambda doc: doc["required_compare_contract"]["alignment_policy"].__setitem__(
                "status", "selected"
            )
        )

    def test_tolerance_promotion_rejected(self) -> None:
        self.assert_mutation_rejected(
            lambda doc: doc["required_compare_contract"]["tolerance_policy"].__setitem__(
                "status", "complete"
            )
        )

    def test_matlab_execution_claim_rejected(self) -> None:
        self.assert_mutation_rejected(
            lambda doc: doc["scope"].__setitem__("matlab_invoked", True)
        )

    def test_source_identity_mutation_rejected(self) -> None:
        self.assert_mutation_rejected(
            lambda doc: doc["canonical_agent_com"].__setitem__("commit", "0000000")
        )

    def test_reference_inventory_mutation_rejected(self) -> None:
        candidate = copy.deepcopy(self.document)
        candidate["references"][0]["sha256"] = "0" * 64
        with self.assertRaises(AssertionError):
            verifier.validate(candidate)

    def test_audit_hash_mutation_rejected(self) -> None:
        candidate = copy.deepcopy(self.document)
        candidate["audit"]["sha256"] = "0" * 64
        with self.assertRaises(AssertionError):
            verifier.validate(candidate, verify_references=False)


if __name__ == "__main__":
    unittest.main()
