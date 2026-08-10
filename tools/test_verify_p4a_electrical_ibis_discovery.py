"""Tests for the P4A electrical-load and IBIS discovery verifier."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4a_electrical_discovery", ROOT / "tools" / "verify_p4a_electrical_ibis_discovery.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
MANIFEST = ROOT / "docs" / "baselines" / "p4a-electrical-ibis-discovery.v1.yaml"


class ElectricalIbisDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    def test_candidate_is_deliberately_blocked_on_capacitor_placement(self) -> None:
        report = GATE.validate_manifest(self.document)
        self.assertEqual(report["c_load_placement"], "pending_owner_choice")
        self.assertFalse(report["required"])
        self.assertFalse(report["promotion_eligible"])

    def test_rejects_implicit_capacitor_placement_or_profile_promotion(self) -> None:
        altered = copy.deepcopy(self.document)
        altered["electrical_load_candidate"]["load_capacitance"]["placement"] = "each_leg_to_reference"
        with self.assertRaises(GATE.DiscoveryError):
            GATE.validate_manifest(altered)
        altered = copy.deepcopy(self.document)
        altered["electrical_load_candidate"]["required"] = True
        with self.assertRaises(GATE.DiscoveryError):
            GATE.validate_manifest(altered)

    def test_rejects_external_path_or_usable_unverified_public_asset(self) -> None:
        altered = copy.deepcopy(self.document)
        altered["local_candidates"][1]["tracked_path"] = "C:/private/minimal.ibs"
        with self.assertRaises(GATE.DiscoveryError):
            GATE.validate_manifest(altered)
        altered = copy.deepcopy(self.document)
        altered["public_discovery"][0]["status"] = "usable"
        with self.assertRaises(GATE.DiscoveryError):
            GATE.validate_manifest(altered)


if __name__ == "__main__":
    unittest.main()
