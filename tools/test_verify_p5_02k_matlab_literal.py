"""Tests for the P5-02k MATLAB numeric-literal stage verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_02k_matlab_literal as GATE


class MatlabLiteralStageTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_five_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 5)

    def test_required_tokens_in_source(self) -> None:
        source = GATE.SOURCE.read_text(encoding="utf-8")
        for token in ("pub fn parse_literal_v1", "pub enum LiteralV1", "fn colon_range"):
            self.assertIn(token, source)

    def test_plan_row_present(self) -> None:
        self.assertIn("**P5-02k", GATE.PLAN.read_text(encoding="utf-8"))

    def test_evidence_matches_all_cases(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(evidence["status"], "matched_hash_bound")
        self.assertEqual(evidence["matched_count"], evidence["case_count"])
        self.assertTrue(all(c["matched"] for c in evidence["cases"]))
        limits = evidence["oracle_limitations"]
        self.assertEqual(len(limits), 1)
        self.assertTrue(limits[0]["oracle_raises"])

    def test_rejects_vector_admission_false(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["vector_literals"] = False
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.MatlabLiteralError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
