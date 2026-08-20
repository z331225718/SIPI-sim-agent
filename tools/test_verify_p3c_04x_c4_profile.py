# -*- coding: utf-8 -*-
"""Tests for the P3C-03 C4 owner metric-profile verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3c_04x_c4_profile as GATE


class C4ProfileTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_four_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 4)

    def test_policy_in_source(self) -> None:
        self.assertIn(GATE.POLICY, GATE.SOURCE.read_text(encoding="utf-8"))

    def test_evidence_matched(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(evidence["status"], "matched_hash_bound")
        self.assertEqual(evidence["matched_count"], evidence["case_count"])
        self.assertEqual(evidence["case_count"], 6)

    def test_c4_metrics_and_tolerance(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        full = [e for e in evidence["entries"] if e["label"] == "full_references"][0]
        self.assertEqual([s["name"] for s in full["product_specs"]], ["COM_dB", "ICN_mV", "ERL"])
        self.assertEqual(set(s["relative_tolerance"] for s in full["product_specs"]), {0.01})

    def test_evidence_exercises_both_paths(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        happy = [e for e in evidence["entries"] if e.get("product_ok")]
        failure = [e for e in evidence["entries"] if not e.get("product_ok")]
        self.assertTrue(happy)
        self.assertTrue(failure)
        reasons = {e.get("product_error") for e in failure}
        self.assertTrue(reasons.issuperset({"missing_reference:ERL", "missing_reference:ICN_mV", "missing_reference:COM_dB"}))

    def test_rejects_hardcoded_reference_admission(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["reference_from_oracle"] = True
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.C4ProfileError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
