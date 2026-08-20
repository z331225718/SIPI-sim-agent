# -*- coding: utf-8 -*-
"""Tests for the P3B-05d PRBS9 inject verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3b_05d_prbs9_inject as GATE


class InjectTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_three_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 3)

    def test_policy_in_source(self) -> None:
        self.assertIn(GATE.POLICY, GATE.SOURCE.read_text(encoding="utf-8"))

    def test_plan_row_present(self) -> None:
        self.assertIn("**P3B-05d", GATE.PLAN.read_text(encoding="utf-8"))

    def test_evidence_matched(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(evidence["status"], "matched_hash_bound")
        self.assertEqual(evidence["matched_count"], evidence["case_count"])
        self.assertEqual(evidence["case_count"], 3)

    def test_waveform_length(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        # seed1_bits4_spu2 => length 8
        self.assertEqual(evidence["entries"][0]["product_length"], 8)
        # seed511_bits16_spu8 => length 128
        self.assertEqual(evidence["entries"][2]["product_length"], 128)

    def test_rejects_jitter_admission(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["time_warp_jitter_model"] = True
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.InjectError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()