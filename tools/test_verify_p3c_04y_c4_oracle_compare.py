# -*- coding: utf-8 -*-
"""Tests for the P3C-04y C4-vs-oracle compare verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3c_04y_c4_oracle_compare as GATE


class C4OracleCompareTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_four_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 4)

    def test_evidence_matched_two_cases(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(evidence["status"], "matched_hash_bound")
        self.assertEqual(evidence["case_count"], 2)

    def test_case1_passes_case2_passes(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        by_label = {e["label"]: e for e in evidence["entries"]}
        self.assertTrue(by_label["case_1"]["product_passed"])
        self.assertTrue(by_label["case_2"]["product_passed"])
        c2 = {x["name"]: x for x in by_label["case_2"]["product_results"]}
        self.assertTrue(c2["COM_dB"]["passed"])
        self.assertTrue(c2["ICN_mV"]["passed"])
        self.assertTrue(c2["ERL"]["passed"])

    def test_oracle_reference_has_c4_metrics(self) -> None:
        oracle = GATE.load_yaml(GATE.ORACLE_REF)
        agg = oracle["aggregate_reference"]
        for k in ("COM_dB", "ICN_mV", "ERL"):
            self.assertGreater(agg[k], 0.0)

    def test_plan_row_present(self) -> None:
        self.assertIn("**P3C-04y", GATE.PLAN.read_text(encoding="utf-8"))

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
                with self.assertRaises(GATE.C4OracleCompareError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()