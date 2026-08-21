"""Mutation tests for the P2-06 same-deck measurement replay."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_p2_06_exact_parser_measurement_replay as gate


class ReplayEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate.load(gate.RECORD)

    def test_current_record_is_valid(self) -> None:
        self.assertTrue(gate.verify(ROOT)["valid"])

    def test_comparator_reduction_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["closure"]["sampled_max_reduced_by_comparator"] = True
        with self.assertRaisesRegex(gate.ReplayEvidenceError, "closure_invalid"):
            gate.validate_document(value)

    def test_same_input_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["input"]["same_bytes_supplied_to_oracle_and_product"] = False
        with self.assertRaisesRegex(gate.ReplayEvidenceError, "input_binding_invalid"):
            gate.validate_document(value)

    def test_scope_expansion_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["closure"]["op_or_ac"] = True
        with self.assertRaisesRegex(gate.ReplayEvidenceError, "closure_invalid"):
            gate.validate_document(value)

    def test_report_hash_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["external_report"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.ReplayEvidenceError, "external_report_invalid"):
            gate.validate_document(value)


if __name__ == "__main__":
    unittest.main()
