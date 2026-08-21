"""Mutation tests for the P2-06 exact RC measurement evidence."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p2_06_exact_rc_measurement_implementation as gate


class ExactRcMeasurementEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate.load(gate.RECORD)

    def test_current_record_and_source_are_valid(self) -> None:
        self.assertEqual(
            gate.verify(ROOT),
            {
                "valid": True,
                "status": "implemented_exact_profile_external_measurement_not_bound",
            },
        )

    def test_scope_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["implementation"]["accepted_order"].insert(-1, ".op")
        with self.assertRaisesRegex(gate.ExactRcEvidenceError, "record_content_invalid"):
            gate.validate_document(value)

    def test_completion_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["completion"]["p2_06_scoped_close"] = True
        with self.assertRaisesRegex(gate.ExactRcEvidenceError, "record_content_invalid"):
            gate.validate_document(value)

    def test_compare_scope_mutation_fails_closed(self) -> None:
        value = gate.load(gate.COMPARE_RECORD)
        value["closure"]["generic_spice_or_mna"] = True
        self.assertNotEqual(value, gate.expected_compare())

    def test_hash_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["implementation"]["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.ExactRcEvidenceError, "record_content_invalid"):
            gate.validate_document(value)


if __name__ == "__main__":
    unittest.main()
