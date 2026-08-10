"""Tests for P4A external pure-IBIS identity and custody preflight."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4a_official_pure_ibis_identity", ROOT / "tools" / "verify_p4a_official_pure_ibis_license_identity_preflight.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
MANIFEST = ROOT / "docs" / "baselines" / "p4a-official-pure-ibis-license-identity-preflight.v1.yaml"


class OfficialPureIbisIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    def test_record_stays_external_with_unverified_rights(self) -> None:
        report = GATE.validate_manifest(self.document)
        self.assertEqual(report["rights_status"], "unverified")
        self.assertEqual(report["selection_eligibility"], "blocked_license_and_custody")
        self.assertFalse(report["promotion_eligible"])

    def test_rejects_legal_or_product_promotion(self) -> None:
        altered = copy.deepcopy(self.document)
        altered["legal_observation"]["rights_status"] = "legal_reviewed"
        with self.assertRaises(GATE.PreflightError):
            GATE.validate_manifest(altered)
        altered = copy.deepcopy(self.document)
        altered["classification"]["required"] = True
        with self.assertRaises(GATE.PreflightError):
            GATE.validate_manifest(altered)

    def test_rejects_path_or_content_material(self) -> None:
        altered = copy.deepcopy(self.document)
        altered["custody"]["temporary_path"] = "C:/private/sample1.ibs"
        with self.assertRaises(GATE.PreflightError):
            GATE.validate_manifest(altered)
        altered = copy.deepcopy(self.document)
        altered["identity"]["bytes"] = "not allowed"
        with self.assertRaises(GATE.PreflightError):
            GATE.validate_manifest(altered)


if __name__ == "__main__":
    unittest.main()
