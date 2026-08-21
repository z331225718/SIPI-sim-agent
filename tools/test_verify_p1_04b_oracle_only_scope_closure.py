"""Mutation tests for the P1-04B oracle-only scope closure."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import yaml

from tools import verify_p1_04b_oracle_only_scope_closure as gate


class P104BOracleOnlyScopeClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = yaml.safe_load(gate.EVIDENCE.read_text(encoding="utf-8"))

    def assert_invalid(self, mutate) -> None:
        candidate = copy.deepcopy(self.document)
        mutate(candidate)
        with self.assertRaises(gate.ScopeClosureError):
            gate.validate(candidate)

    def test_current_scope_is_valid(self) -> None:
        result = gate.validate(self.document)
        self.assertTrue(result["valid"])
        self.assertEqual(result["asset_count"], 14)
        self.assertEqual(result["required_by_required_count"], 9)
        self.assertEqual(result["legacy_schema_ids"], 0)

    def test_missing_asset_responsibility_fails_closed(self) -> None:
        self.assert_invalid(lambda doc: doc["asset_responsibilities"].pop())

    def test_duplicate_asset_responsibility_fails_closed(self) -> None:
        self.assert_invalid(lambda doc: doc["asset_responsibilities"].__setitem__(1, copy.deepcopy(doc["asset_responsibilities"][0])))

    def test_required_by_gate_mutation_fails_closed(self) -> None:
        self.assert_invalid(lambda doc: doc["asset_responsibilities"][0].__setitem__("gate", "P4B-02"))

    def test_manifest_required_label_is_not_profile_selection(self) -> None:
        self.assert_invalid(lambda doc: doc["manifest"]["required_asset_ids"].pop())

    def test_distribution_promotion_fails_closed(self) -> None:
        self.assert_invalid(lambda doc: doc["rights_retention"].__setitem__("distribution_authorized", True))

    def test_comparison_permission_cannot_widen(self) -> None:
        self.assert_invalid(lambda doc: doc["comparison_permission"].__setitem__("redistribution", True))

    def test_product_materialization_cannot_be_claimed(self) -> None:
        self.assert_invalid(lambda doc: doc["closure"].__setitem__("product_materialization", True))

    def test_worktree_materialization_fails_closed(self) -> None:
        with patch.object(gate, "_worktree_materialized_asset_paths", return_value=["fixtures/agent-spice-python-fixtures/case.cir"]):
            with self.assertRaisesRegex(gate.ScopeClosureError, "legacy_fixture_worktree_materialized"):
                gate.validate(self.document)

    def test_external_blocker_cannot_be_removed(self) -> None:
        self.assert_invalid(lambda doc: doc["external_blockers"].pop())

    def test_external_profile_cannot_be_promoted(self) -> None:
        self.assert_invalid(lambda doc: doc["external_blockers"][0]["profile"].__setitem__("selected", "forged-profile"))

    def test_rights_loss_is_rejected(self) -> None:
        self.assert_invalid(lambda doc: doc["rights_retention"].__setitem__("rights_lost", True))

    def test_audit_hash_binding_fails_closed(self) -> None:
        self.assert_invalid(lambda doc: doc["audit"].__setitem__("sha256", "0" * 64))


if __name__ == "__main__":
    unittest.main()
