# -*- coding: utf-8 -*-
"""Tests for the P4A-03d typed model-declaration core verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4a_03d_model_declaration as GATE


class ModelDeclTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_four_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 4)

    def test_policy_in_source(self) -> None:
        self.assertIn(GATE.POLICY, GATE.SOURCE.read_text(encoding="utf-8"))

    def test_plan_row_present(self) -> None:
        self.assertIn("**P4A-03d", GATE.PLAN.read_text(encoding="utf-8"))

    def test_evidence_matched_and_count(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(evidence["status"], "matched_hash_bound")
        self.assertEqual(evidence["entries"][0]["product_declaration_count"], 67)
        self.assertTrue(evidence["entries"][0]["matched"])
        types = evidence["entries"][0]["product_model_types"]
        self.assertEqual(types, {"IO": 40, "Input": 27})

    def test_io_canonicalization_note(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        entry = evidence["entries"][0]
        self.assertEqual(entry["observer_model_types"]["I/O"], 40)
        self.assertEqual(entry["product_model_types"]["IO"], 40)

    def test_rejects_model_type_admission_false(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["model_type_data_line"] = False
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.ModelDeclError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()