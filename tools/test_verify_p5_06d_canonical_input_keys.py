# -*- coding: utf-8 -*-
"""Tests for the P5-06d canonical-input-key verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_06d_canonical_input_keys as GATE


class CanonicalInputKeysTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_five_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 5)

    def test_policy_in_source(self) -> None:
        self.assertIn(GATE.POLICY, GATE.SOURCE.read_text(encoding="utf-8"))

    def test_plan_row_present(self) -> None:
        self.assertIn("**P5-06d", GATE.PLAN.read_text(encoding="utf-8"))

    def test_evidence_matched(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(evidence["status"], "matched_hash_bound")
        self.assertEqual(evidence["matched_count"], evidence["case_count"])
        self.assertEqual(evidence["case_count"], 9)

    def test_authoritative_surface_uses_82_keys(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        surface = [e for e in evidence["entries"] if e["label"] == "authoritative_in_config_surface"]
        self.assertEqual(len(surface), 1)
        self.assertEqual(surface[0]["surface_in_config_count"], 82)
        self.assertEqual(surface[0]["product_digest"], surface[0]["reference_digest"])

    def test_evidence_exercises_both_paths(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        happy = [e for e in evidence["entries"] if e.get("product_ok") and e["reference_ok"]]
        failure = [e for e in evidence["entries"] if not e.get("product_ok") and not e["reference_ok"]]
        self.assertTrue(happy)
        self.assertTrue(failure)
        labels = [e["label"] for e in happy]
        self.assertIn("three_keys_sorted", labels)
        self.assertIn("nested_token_list", labels)
        self.assertIn("duplicate_key_fails", [e["label"] for e in failure])

    def test_rejects_compare_matrix_admission(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["compare_matrix"] = True
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.CanonicalInputKeysError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
