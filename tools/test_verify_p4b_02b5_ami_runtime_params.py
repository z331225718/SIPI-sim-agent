# -*- coding: utf-8 -*-
"""Tests for the P4B-02b5 AMI runtime-parameter-table verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_02b5_ami_runtime_params as GATE


class RuntimeParamsTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_six_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 6)

    def test_policy_in_source(self) -> None:
        self.assertIn(GATE.POLICY, GATE.SOURCE.read_text(encoding="utf-8"))

    def test_plan_row_present(self) -> None:
        self.assertIn("**P4B-02b5", GATE.PLAN.read_text(encoding="utf-8"))

    def test_evidence_matched(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(evidence["status"], "matched_hash_bound")
        self.assertEqual(evidence["matched_count"], evidence["case_count"])
        self.assertEqual(evidence["case_count"], 8)

    def test_in_missing_both_present_in_evidence(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        matched = [e for e in evidence["entries"] if e["label"] == "missing_in_without_default"]
        self.assertEqual(len(matched), 1)
        self.assertFalse(matched[0]["product_ok"])
        self.assertFalse(matched[0]["reference_ok"])

    def test_rejects_ami_runtime_execution_admission(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["ami_runtime_execution"] = True
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.RuntimeParamsError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
