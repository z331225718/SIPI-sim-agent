"""Mutation tests for the PB-03 18-branch inventory gate."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_pb_03_python_oracle_18_branch as verifier  # noqa: E402


class VerifyPb0318BranchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = yaml.safe_load(verifier.MANIFEST.read_text(encoding="utf-8"))

    def _errors(self, document: dict) -> list[str]:
        return verifier.verify(document)["errors"]

    def test_missing_branch_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["branch_inventory"].pop()
        self.assertTrue(self._errors(document))

    def test_payload_parity_claim_cannot_close(self) -> None:
        document = copy.deepcopy(self.document)
        document["claims"]["python_payload_parity_complete"] = True
        self.assertTrue(self._errors(document))

    def test_nonempty_payload_scope_is_required(self) -> None:
        document = copy.deepcopy(self.document)
        document["python_payload_oracle_missing"] = []
        self.assertTrue(self._errors(document))

    def test_portable_probe_missing_cannot_be_hidden(self) -> None:
        document = copy.deepcopy(self.document)
        document["portable_branch_probe_missing"] = ["legacy.modulation.nrz"]
        self.assertTrue(self._errors(document))

    def test_harness_digest_is_bound(self) -> None:
        document = copy.deepcopy(self.document)
        document["harness"]["oracle"]["sha256"] = "0" * 64
        self.assertTrue(self._errors(document))

    def test_report_sha_run_id_and_nonce_are_bound(self) -> None:
        document = copy.deepcopy(self.document)
        document["corpus"]["reports"][0]["sha256"] = "0" * 64
        self.assertTrue(self._errors(document))

    def test_aggregate_binding_is_loaded(self) -> None:
        document = copy.deepcopy(self.document)
        document["corpus"]["aggregate"]["sha256"] = "0" * 64
        self.assertTrue(self._errors(document))

    def test_archive_identity_is_exact(self) -> None:
        document = copy.deepcopy(self.document)
        document["source"]["candidate_archive_sha256"] = "0" * 64
        self.assertTrue(self._errors(document))

    def test_branch_oracle_status_cannot_be_hidden(self) -> None:
        document = copy.deepcopy(self.document)
        for branch in document["branch_inventory"]:
            if branch["id"] == "legacy.channel.s1p_s4p_differential_renumber":
                branch["oracle"] = {"status": "payload_compared", "case": "nrz-base"}
                break
        self.assertTrue(self._errors(document))

    def test_duo_branch_requires_report_derived_partial_contract(self) -> None:
        branch = next(item for item in self.document["branch_inventory"] if item["id"] == "legacy.modulation.pam4_duo_binary")
        self.assertNotEqual(branch["oracle"].get("status"), "partial")
        contract = verifier.derive_duo_contract(self.document, verifier.ROOT, [])
        self.assertIsNotNone(contract)
        mutated = copy.deepcopy(self.document)
        duo = next(item for item in mutated["branch_inventory"] if item["id"] == "legacy.modulation.pam4_duo_binary")
        duo["oracle"] = contract
        errors = self._errors(mutated)
        self.assertFalse(any("Duo oracle must be an observed partial contract" in error for error in errors))

    def test_duo_partial_field_count_mutation_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        contract = verifier.derive_duo_contract(document, verifier.ROOT, [])
        self.assertIsNotNone(contract)
        duo = next(item for item in document["branch_inventory"] if item["id"] == "legacy.modulation.pam4_duo_binary")
        duo["oracle"] = contract
        duo["oracle"]["compared"]["fields"] = 0
        self.assertTrue(any("Duo oracle must be an observed partial contract" in error for error in self._errors(document)))

    def test_audit_digest_is_bound(self) -> None:
        document = copy.deepcopy(self.document)
        document["audit"]["sha256"] = "0" * 64
        self.assertTrue(self._errors(document))


if __name__ == "__main__":
    unittest.main()
