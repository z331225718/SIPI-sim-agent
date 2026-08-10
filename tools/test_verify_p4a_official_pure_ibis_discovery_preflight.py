"""Tests for the P4A official pure-IBIS discovery-only verifier."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4a_official_pure_ibis_discovery", ROOT / "tools" / "verify_p4a_official_pure_ibis_discovery_preflight.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
MANIFEST = ROOT / "docs" / "baselines" / "p4a-official-pure-ibis-discovery-preflight.v1.yaml"


class OfficialPureIbisDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    def test_candidate_stays_discovery_only_without_bytes(self) -> None:
        report = GATE.validate_manifest(self.document)
        self.assertEqual(report["eligibility"], "discovery_only")
        self.assertEqual(report["asset_identity"], "url_only_unresolved")
        self.assertFalse(report["required"])
        self.assertFalse(report["promotion_eligible"])

    def test_rejects_promotion_or_license_upgrade(self) -> None:
        altered = copy.deepcopy(self.document)
        altered["candidates"][0]["required"] = True
        with self.assertRaises(GATE.DiscoveryError):
            GATE.validate_manifest(altered)
        altered = copy.deepcopy(self.document)
        altered["candidates"][0]["license_notice_status"] = "licensed"
        with self.assertRaises(GATE.DiscoveryError):
            GATE.validate_manifest(altered)

    def test_rejects_hash_or_local_asset_path_in_discovery_record(self) -> None:
        altered = copy.deepcopy(self.document)
        altered["candidates"][0]["content_sha256"] = "0" * 64
        with self.assertRaises(GATE.DiscoveryError):
            GATE.validate_manifest(altered)
        altered = copy.deepcopy(self.document)
        altered["candidates"][0]["local_path"] = "C:/private/sample1.ibs"
        with self.assertRaises(GATE.DiscoveryError):
            GATE.validate_manifest(altered)


if __name__ == "__main__":
    unittest.main()
