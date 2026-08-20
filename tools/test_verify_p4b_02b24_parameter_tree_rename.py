# -*- coding: utf-8 -*-
"""Tests for the P4B-02b24 AMI parameter tree node rename verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_02b24_parameter_tree_rename as GATE


class ParameterTreeRenameTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_three_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 3)

    def test_evidence_matched_three_cases(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(evidence["status"], "matched_hash_bound")
        self.assertEqual(evidence["case_count"], 3)
        self.assertEqual(evidence["matched_count"], 3)

    def test_implementation_tokens_present(self) -> None:
        source = GATE.SOURCE.read_text(encoding="utf-8")
        self.assertIn("pub fn rename_parameter_tree_node_v1", source)
        self.assertIn(GATE.POLICY, source)

    def test_plan_row_present(self) -> None:
        self.assertIn("**P4B-02b24", GATE.PLAN.read_text(encoding="utf-8"))

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
                with self.assertRaises(GATE.ParameterTreeRenameError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
