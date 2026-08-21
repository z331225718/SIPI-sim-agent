"""Mutation tests for the P3B-02 typed-semantics evidence gate."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_p3b_02_pybert_semantics as gate


class TypedSemanticsEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate._load(gate.RECORD)

    def test_current_record_and_pinned_objects_are_valid(self) -> None:
        result = gate.verify(ROOT, Path(r"C:\Users\z3312\code\Py-bert-agent"))
        self.assertTrue(result["valid"])
        self.assertEqual(result["profile_required"], "external_asset_oracle")

    def test_product_hash_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["product"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gate.SemanticsEvidenceError, "product_source_hash_drift"):
            gate.verify_document(value)

    def test_source_marker_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["external_source"]["objects"]["src/pybert/models/bert.py"]["markers"][0] = "not_a_source_marker"
        with self.assertRaisesRegex(gate.SemanticsEvidenceError, "source_object_invalid"):
            gate.validate_document(value)

    def test_profile_selection_mutation_fails_closed(self) -> None:
        value = copy.deepcopy(self.document)
        value["profile_status"]["selected_profile"] = "legacy_desktop"
        with self.assertRaisesRegex(gate.SemanticsEvidenceError, "profile_status_invalid"):
            gate.validate_document(value)

    def test_wire_surface_remains_bypass_only(self) -> None:
        result = gate.verify(ROOT)
        self.assertEqual(result["status"], "observed_product_semantics_external_profile_required")


if __name__ == "__main__":
    unittest.main()
