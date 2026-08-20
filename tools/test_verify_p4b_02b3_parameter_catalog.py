# -*- coding: utf-8 -*-
"""Tests for the P4B-02b3 parameter-catalog core verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_02b3_parameter_catalog as GATE


class ParameterCatalogTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])

    def test_source_map_has_four_mappings(self) -> None:
        source_map = GATE.load_yaml(GATE.SOURCE_MAP)
        self.assertEqual(len(source_map["mapping"]), 4)

    def test_policy_in_source(self) -> None:
        self.assertIn(GATE.POLICY, GATE.SOURCE.read_text(encoding="utf-8"))

    def test_plan_row_present(self) -> None:
        self.assertIn("**P4B-02b3", GATE.PLAN.read_text(encoding="utf-8"))

    def test_evidence_matched(self) -> None:
        evidence = GATE.load_yaml(GATE.EVIDENCE)
        self.assertEqual(evidence["status"], "product_owned_self_crosscheck_unbound")
        self.assertEqual(evidence["matched_count"], evidence["case_count"])
        self.assertEqual(evidence["case_count"], 4)

    def test_profile_agnostic(self) -> None:
        charter = GATE.load_yaml(GATE.CHARTER)
        self.assertTrue(charter["admission"]["profile_agnostic"]);
        self.assertFalse(charter["admission"]["reserved_name_catalog"])

    def test_rejects_ami_runtime_admission(self) -> None:
        import copy
        import tempfile
        import unittest.mock as mock
        charter = copy.deepcopy(GATE.load_yaml(GATE.CHARTER))
        charter["admission"]["ami_runtime"] = True
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "charter.yaml"
            tmp_path.write_text(GATE.yaml.safe_dump(charter, sort_keys=False), encoding="utf-8")
            with mock.patch.object(GATE, "CHARTER", tmp_path):
                with self.assertRaises(GATE.CatalogError):
                    GATE.validate(ROOT)


if __name__ == "__main__":
    unittest.main()