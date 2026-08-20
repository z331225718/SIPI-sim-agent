# -*- coding: utf-8 -*-
"""Tests for the P3C-02g horizontal-margin verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3c_02g_horizontal_margin as GATE


class MarginTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_three_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 3)

    def test_policy_in_source(self) -> None:
        self.assertIn(GATE.POLICY, GATE.SOURCE.read_text(encoding="utf-8"))

    def test_plan_row_present(self) -> None:
        self.assertIn("**P3C-02g", GATE.PLAN.read_text(encoding="utf-8"))

    def test_evidence_matched(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(evidence["status"], "matched_hash_bound")
        self.assertEqual(evidence["matched_count"], evidence["case_count"]);
        self.assertEqual(evidence["case_count"], 3)

    def test_margin_values(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        prod0 = evidence["entries"][0]["product"]
        self.assertTrue(prod0["ok"])
        # sym_center: eye width ~0.833, sample at 0.5 => left 0.5, right ~0.333
        self.assertAlmostEqual(prod0["left"], 0.5, places=9)
        self.assertAlmostEqual(prod0["eye_width"], 0.8333333333333334, places=9)

    def test_rejects_curve_admission(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["bathtub_curve_fit"] = True
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.MarginError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()