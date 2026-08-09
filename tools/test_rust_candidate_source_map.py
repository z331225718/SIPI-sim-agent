from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_rust_candidate_source_map import _load, verify_document


class RustCandidateSourceMapTests(unittest.TestCase):
    def document(self) -> dict:
        return copy.deepcopy(_load(ROOT / "rust-candidate-source-map.v1.yaml"))

    def test_current_inventory_is_complete_and_quarantined(self) -> None:
        report = verify_document(self.document())
        self.assertTrue(report["valid"], report["blockers"])
        self.assertEqual(report["native_entry_count"], 36)
        self.assertEqual(report["unknown_count"], 36)

    def test_missing_or_mutated_native_entry_fails_closed(self) -> None:
        invalid = self.document()
        invalid["inventory"]["entries"].pop(next(iter(invalid["inventory"]["entries"])))
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("do not match" in item for item in report["blockers"]))

        invalid = self.document()
        entry = next(iter(invalid["inventory"]["entries"].values()))
        entry["content_sha256"] = "0" * 64
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("do not match" in item for item in report["blockers"]))

    def test_unknown_entry_cannot_claim_evidence_or_escape_quarantine(self) -> None:
        invalid = self.document()
        entry = next(iter(invalid["inventory"]["entries"].values()))
        entry["direct_mit_sources"] = ["unverified"]
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("cannot claim" in item for item in report["blockers"]))

        invalid = self.document()
        entry = next(iter(invalid["inventory"]["entries"].values()))
        entry["boundary_class"] = "product_candidate"
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("classification" in item for item in report["blockers"]))

    def test_boundary_and_unknown_fields_fail_closed(self) -> None:
        invalid = self.document()
        invalid["boundary_ref"]["sha256"] = "0" * 64
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("boundary_ref hash mismatch" in item for item in report["blockers"]))

        invalid = self.document()
        invalid["inventory"]["extra"] = True
        report = verify_document(invalid)
        self.assertFalse(report["valid"])
        self.assertTrue(any("inventory is invalid" in item for item in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
