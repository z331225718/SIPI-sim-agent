"""Mutation tests for the P3B-02 pinned-PyBERT profile blocker."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_p3b_02_pybert_profile_source_audit as gate


class ProfileAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate.load(gate.RECORD)

    def test_current_record_is_valid(self) -> None:
        self.assertTrue(gate.verify(ROOT)["valid"])

    def test_profile_selection_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["decision"]["selected_profile"] = "web_adapter"
        with self.assertRaisesRegex(gate.ProfileAuditError, "decision_invalid"):
            gate.validate_document(value)

    def test_ctle_conflict_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["candidates"]["legacy_desktop"]["ctle"]["peak_magnitude_db"] = 4.0
        with self.assertRaisesRegex(gate.ProfileAuditError, "ctle_conflict_missing"):
            gate.validate_document(value)

    def test_source_blob_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["external_source"]["objects"]["src/pybert/pybert.py"] = "0" * 40
        with self.assertRaisesRegex(gate.ProfileAuditError, "source_objects_invalid"):
            gate.validate_document(value)


if __name__ == "__main__":
    unittest.main()
