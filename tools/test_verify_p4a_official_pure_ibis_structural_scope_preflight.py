"""Tests for the external pure-IBIS structural-scope verifier."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4a_external_ibis_scope", ROOT / "tools" / "verify_p4a_official_pure_ibis_structural_scope_preflight.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
MANIFEST = ROOT / "docs" / "baselines" / "p4a-official-pure-ibis-structural-scope-preflight.v1.yaml"
OWNER_POLICY = ROOT / "docs" / "baselines" / "p4a-official-pure-ibis-owner-policy-authorization.v1.yaml"


class ExternalIbisScopePreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    def test_owner_selection_eligibility_stays_external_and_not_required(self) -> None:
        report = GATE.validate_manifest(self.document)
        self.assertEqual(report["selection_eligibility"], "eligible_for_owner_selection")
        self.assertFalse(report["required"])
        self.assertFalse(report["promotion_eligible"])

    def test_rejects_product_promotion_or_rights_upgrade(self) -> None:
        altered = copy.deepcopy(self.document)
        altered["classification"]["product_asset"] = True
        with self.assertRaises(GATE.ScopeError):
            GATE.validate_manifest(altered)
        altered = copy.deepcopy(self.document)
        altered["classification"]["third_party_rights_status"] = "legal_reviewed"
        with self.assertRaises(GATE.ScopeError):
            GATE.validate_manifest(altered)

    def test_rejects_identity_or_observer_drift(self) -> None:
        altered = copy.deepcopy(self.document)
        altered["asset_identity"]["content_sha256"] = "0" * 64
        with self.assertRaises(GATE.ScopeError):
            GATE.validate_manifest(altered)
        altered = copy.deepcopy(self.document)
        altered["observer"]["product_parser_not_used"] = False
        with self.assertRaises(GATE.ScopeError):
            GATE.validate_manifest(altered)

    def test_rejects_owner_policy_rights_or_scope_upgrade(self) -> None:
        policy = yaml.safe_load(OWNER_POLICY.read_text(encoding="utf-8"))
        altered = copy.deepcopy(policy)
        altered["scope"]["third_party_rights_status"] = "legal_reviewed"
        with self.assertRaises(GATE.ScopeError):
            GATE.validate_owner_policy(altered)
        altered = copy.deepcopy(policy)
        altered["scope"]["prohibited_uses"].remove("redistribution")
        with self.assertRaises(GATE.ScopeError):
            GATE.validate_owner_policy(altered)


if __name__ == "__main__":
    unittest.main()
