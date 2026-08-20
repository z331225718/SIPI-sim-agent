# -*- coding: utf-8 -*-
"""Tests for the P5-08a COM run-request admission verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p5_08a_com_run_admission as GATE


class ComRunAdmissionTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_four_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 4)

    def test_policy_in_source(self) -> None:
        self.assertIn(GATE.POLICY, GATE.SOURCE.read_text(encoding="utf-8"))

    def test_request_schema_in_source(self) -> None:
        self.assertIn(GATE.REQUEST_SCHEMA, GATE.SOURCE.read_text(encoding="utf-8"))

    def test_evidence_matched(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(evidence["status"], "matched_hash_bound")
        self.assertEqual(evidence["matched_count"], evidence["case_count"])
        self.assertEqual(evidence["case_count"], 8)

    def test_evidence_exercises_all_paths(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        admitted = [e for e in evidence["entries"] if e.get("admitting")]
        rejected = [e for e in evidence["entries"] if not e.get("admitting", False) and e.get("product_ok")]
        hard = [e for e in evidence["entries"] if not e.get("product_ok")]
        self.assertTrue(admitted)
        self.assertTrue(rejected)
        self.assertTrue(hard)
        reasons = {e.get("product_reason") for e in rejected}
        self.assertTrue({"unbound_artifacts", "empty_params", "missing_params"}.issubset(reasons))

    def test_rejects_conformance_admission(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["no_com_execution"] = False
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.ComRunAdmissionError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()
