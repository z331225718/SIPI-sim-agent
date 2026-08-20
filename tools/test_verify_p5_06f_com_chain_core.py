# -*- coding: utf-8 -*-
"""Tests for the P5-06f fixed-tap COM chain core verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_06f_com_chain_core as GATE


class ChainTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_charter_admission_boundaries(self) -> None:
        charter = GATE.load_yaml(GATE.CHARTER)
        self.assertFalse(charter["admission"]["product_vs_oracle_compare"])
        self.assertFalse(charter["admission"]["external_assets_materialized"])

    def test_source_map_has_five_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 5)
        self.assertEqual(len(source_map["not_ported"]), 5)

    def test_implementation_tokens_present(self) -> None:
        source = GATE.SOURCE.read_text(encoding="utf-8")
        for token in ("pub fn run_com_chain_v1", GATE.POLICY):
            self.assertIn(token, source)

    def test_evidence_matched_two_cases(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(evidence["status"], "matched_hash_bound")
        self.assertEqual(evidence["case_count"], 2)
        self.assertEqual(evidence["matched_count"], 2)

    def test_plan_row_present(self) -> None:
        self.assertIn("**P5-06f", GATE.PLAN.read_text(encoding="utf-8"))

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
                with self.assertRaises(GATE.ChainError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
