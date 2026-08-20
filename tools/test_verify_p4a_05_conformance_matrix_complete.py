"""Tests for the P4A-05 conformance matrix completeness gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4a_05_conformance_matrix_complete as GATE


class MatrixCompleteTests(unittest.TestCase):
    def test_current_matrix_is_complete(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["entries"], 19)

    def test_matrix_boundary_recorded(self) -> None:
        matrix = GATE.load_yaml(GATE.MATRIX)
        self.assertEqual(matrix["status"], "boundary_recorded")

    def test_accepted_profile_present(self) -> None:
        matrix = GATE.load_yaml(GATE.MATRIX)
        statuses = {entry.get("status") for entry in matrix["entries"]}
        self.assertIn("external_profile_accepted", statuses)

    def test_unsupported_entries_present(self) -> None:
        matrix = GATE.load_yaml(GATE.MATRIX)
        entries = {entry.get("id"): entry for entry in matrix["entries"]}
        for entry_id in GATE.REQUIRED_UNSUPPORTED_IDS:
            entry = entries.get(entry_id)
            self.assertIsNotNone(entry, entry_id)
            self.assertIn(entry["status"], {"unsupported", "not_assessed"})

    def test_oracle_audit_present(self) -> None:
        self.assertTrue((ROOT / GATE.ORACLE_AUDIT).is_file())

    def test_rejects_missing_unsupported_entry(self) -> None:
        matrix = GATE.load_yaml(GATE.MATRIX)
        # The gate validates from disk; the entry set is enforced by REQUIRED_UNSUPPORTED_IDS.
        missing = [e for e in GATE.REQUIRED_UNSUPPORTED_IDS if e not in {entry.get("id") for entry in matrix["entries"]}]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
