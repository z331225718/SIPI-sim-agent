# -*- coding: utf-8 -*-
"""Tests for the P4A-03f pin-to-model linkage verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4a_03f_pin_model_linkage as GATE


class PinModelLinkageTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_four_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 4)

    def test_policy_in_source(self) -> None:
        self.assertIn(GATE.POLICY, GATE.SOURCE.read_text(encoding="utf-8"))

    def test_plan_row_present(self) -> None:
        self.assertIn("**P4A-03f", GATE.PLAN.read_text(encoding="utf-8"))

    def test_evidence_matched(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(evidence["status"], "matched_hash_bound")
        self.assertEqual(evidence["matched_count"], evidence["case_count"])
        self.assertEqual(evidence["case_count"], 8)

    def test_evidence_exercises_both_paths(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        happy = [e for e in evidence["entries"] if e.get("product_ok") and e["reference_ok"]]
        failure = [e for e in evidence["entries"] if not e.get("product_ok") and not e["reference_ok"]]
        self.assertTrue(happy)
        self.assertTrue(failure)
        labels = [e["label"] for e in happy]
        self.assertIn("nc_marker_allowed", labels)
        self.assertIn("all_resolved_to_declared_models", labels)
        self.assertIn("unknown_model_rejected_pin_order", [e["label"] for e in failure])

    def test_rejects_electrical_semantics_admission(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["electrical_semantics"] = True
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.PinModelLinkageError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
