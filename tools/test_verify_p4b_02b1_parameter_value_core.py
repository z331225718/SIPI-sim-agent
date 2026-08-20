"""Tests for the P4B-02b1 typed .ami parameter value core verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_02b1_parameter_value_core as GATE


class ParameterValueTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        result = GATE.verify_document(document)
        self.assertTrue(result["valid"])
        self.assertEqual(result["status"], "product_owned_parameter_value_core_specified_no_catalog_no_defaults")

    def test_scope_policy_is_exact(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        self.assertEqual(
            document["scope_policy"],
            "sipi.p4b-02b1.parameter-value-v1.syntax-only-no-catalog-no-defaults",
        )

    def test_catalog_and_defaults_not_in_slice(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        self.assertEqual(document["admission"]["reserved_names"], "not_in_this_slice")
        self.assertEqual(document["admission"]["defaults"], "not_in_this_slice")
        self.assertFalse(document["admission"]["document_decoding"])

    def test_implementation_source_exists(self) -> None:
        self.assertTrue(GATE.SOURCE.is_file())
        source = GATE.SOURCE.read_text(encoding="utf-8")
        self.assertIn("pub struct AmiParameterValueV1", source)
        self.assertIn("pub fn try_new", source)

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P4B-02b1", plan_text)

    def test_rejects_value_rule_drift(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["value_rules"]["Boolean"] = "case_insensitive"
        with self.assertRaises(GATE.ParameterValueError):
            GATE.verify_document(document)

    def test_rejects_admission_drift(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["admission"]["defaults"] = "inferred"
        with self.assertRaises(GATE.ParameterValueError):
            GATE.verify_document(document)


if __name__ == "__main__":
    unittest.main()
