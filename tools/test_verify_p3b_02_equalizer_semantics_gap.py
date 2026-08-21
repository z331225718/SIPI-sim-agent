"""Mutation tests for the P3B-02 equalizer semantics gap record."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3b_02_equalizer_semantics_gap as gate


class EqualizerSemanticsGapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate._load(gate.RECORD)

    def test_current_gap_and_live_bypass_surface_are_valid(self) -> None:
        result = gate.verify(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["status"], "blocked_missing_stage_semantics")
        self.assertEqual(result["missing_groups"], 3)

    def test_owner_decision_mutations_fail_closed(self) -> None:
        mutations = (
            ("answer", lambda value: value["owner_decision"].__setitem__("answer", "B")),
            ("order", lambda value: value["owner_decision"].__setitem__("stage_order", "RX FFE->RX CTLE")),
            ("tuning", lambda value: value["owner_decision"].__setitem__("auto_tuning", "allowed")),
        )
        for label, mutation in mutations:
            with self.subTest(label=label):
                value = copy.deepcopy(self.document)
                mutation(value)
                with self.assertRaisesRegex(gate.GapEvidenceError, "owner_decision_invalid"):
                    gate.validate_document(value)

    def test_missing_semantics_and_admission_mutations_fail_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["missing_semantics"]["ctle"] = []
        with self.assertRaisesRegex(gate.GapEvidenceError, "missing_semantics_invalid"):
            gate.validate_document(value)

        value = copy.deepcopy(self.document)
        value["admission"]["product_equalizer_implemented"] = True
        with self.assertRaisesRegex(gate.GapEvidenceError, "admission_invalid"):
            gate.validate_document(value)

    def test_surface_and_non_claim_mutations_fail_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["current_surface"]["wire_schema"]["ctle_kinds"] = ["bypass", "fir"]
        with self.assertRaisesRegex(gate.GapEvidenceError, "current_surface_invalid"):
            gate.validate_document(value)

        value = copy.deepcopy(self.document)
        value["non_claims"] = ["not enough"]
        with self.assertRaisesRegex(gate.GapEvidenceError, "non_claims_invalid"):
            gate.validate_document(value)

    def test_decision_hash_is_bound(self) -> None:
        value = copy.deepcopy(self.document)
        value["authority"]["decision_sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.GapEvidenceError, "authority_invalid"):
            gate.validate_document(value)


if __name__ == "__main__":
    unittest.main()
