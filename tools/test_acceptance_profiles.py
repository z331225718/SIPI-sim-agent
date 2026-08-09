from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_acceptance_profiles import _load, verify_document


class AcceptanceProfileTests(unittest.TestCase):
    def document(self) -> dict:
        return copy.deepcopy(_load(ROOT / "acceptance-profiles.v1.yaml"))

    def test_current_inventory_is_candidate_only(self) -> None:
        report = verify_document(self.document())
        self.assertTrue(report["valid"], report["blockers"])
        self.assertEqual(report["profile_count"], 4)
        self.assertEqual(report["required_profile_count"], 0)

    def test_unknown_fields_and_unsafe_paths_fail_closed(self) -> None:
        invalid = self.document()
        invalid["unknown"] = True
        self.assertFalse(verify_document(invalid)["valid"])
        invalid = self.document()
        invalid["profiles"][0]["source"]["path"] = "C:/Users/private.s2p"
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("source anchor" in item for item in report["blockers"]))

    def test_candidate_cannot_be_promoted_without_required_decision(self) -> None:
        invalid = self.document()
        invalid["profiles"][0]["acceptance"]["status"] = "required"
        invalid["profiles"][0]["acceptance"]["required_by"] = "owner-decision"
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("candidate acceptance" in item for item in report["blockers"]))

    def test_duplicate_legacy_asset_and_bad_hash_fail_closed(self) -> None:
        invalid = self.document()
        invalid["profiles"].append(copy.deepcopy(invalid["profiles"][0]))
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("duplicate profile" in item for item in report["blockers"]))
        invalid = self.document()
        invalid["profiles"][0]["assets"][0]["content_sha256"] = "0" * 63
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("asset is invalid" in item for item in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
