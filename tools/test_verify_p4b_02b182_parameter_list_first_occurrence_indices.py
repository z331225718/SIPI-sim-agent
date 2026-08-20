# -*- coding: utf-8 -*-
"""Tests for the P4B-02b182 parameter list first-occurrence indices verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_02b182_parameter_list_first_occurrence_indices as GATE


class ParameterListFirstOccurrenceIndicesTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_two_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 2)

    def test_evidence_matched_four_cases(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(evidence["status"], "product_owned_self_crosscheck_unbound")
        self.assertEqual(evidence["case_count"], 4)
        self.assertEqual(evidence["matched_count"], 4)

    def test_implementation_tokens_present(self) -> None:
        source = GATE.SOURCE.read_text(encoding="utf-8")
        self.assertIn("pub fn parameter_list_first_occurrence_indices_v1", source)
        self.assertIn(GATE.POLICY, source)

    def test_plan_row_present(self) -> None:
        self.assertIn("**P4B-02b182", GATE.PLAN.read_text(encoding="utf-8"))

    def test_rejects_evidence_mismatch(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        evidence = copy.deepcopy(GATE.load_yaml(GATE.EVIDENCE))
        evidence["status"] = "mis_match"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "evidence.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "EVIDENCE", tmp_path):
                with self.assertRaises(GATE.ParameterListFirstOccurrenceIndicesError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
