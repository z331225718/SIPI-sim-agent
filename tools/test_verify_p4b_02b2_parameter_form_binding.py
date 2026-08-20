"""Tests for the P4B-02b2 parameter form identity binding verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4b_02b2_parameter_form_binding as GATE


class FormBindingTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        result = GATE.verify_document(document)
        self.assertTrue(result["valid"])
        self.assertEqual(result["status"], "product_owned_parameter_form_identity_binding_specified_no_semantics")

    def test_scope_policy_is_exact(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        self.assertEqual(
            document["scope_policy"],
            "sipi.p4b-02b2.parameter-form-binding-v1.identity-only",
        )

    def test_no_semantic_interpretation(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        self.assertEqual(document["admission"]["semantic_interpretation"], "never")
        self.assertEqual(document["admission"]["two_item_forms"], "not_interpreted")

    def test_implementation_source_exists(self) -> None:
        self.assertTrue(GATE.SOURCE.is_file())
        source = GATE.SOURCE.read_text(encoding="utf-8")
        self.assertIn("pub fn bind_parameter_value_v1", source)
        self.assertIn("ParameterFormBindingV1", source)

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P4B-02b2", plan_text)

    def test_rejects_identity_rule_drift(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["identity_rules"]["item_count"] = "at_least_two"
        with self.assertRaises(GATE.FormBindingError):
            GATE.verify_document(document)

    def test_rejects_admission_drift(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["admission"]["semantic_interpretation"] = "allowed_with_call"
        with self.assertRaises(GATE.FormBindingError):
            GATE.verify_document(document)


if __name__ == "__main__":
    unittest.main()
