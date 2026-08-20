"""Tests for the P4A-04g typed Ramp/Package declaration core verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4a_04g_ramp_package_spec_core as GATE


class RampPackageTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        result = GATE.verify_document(document)
        self.assertTrue(result["valid"])
        self.assertEqual(result["status"], "product_owned_ramp_package_declaration_core_specified_no_profile_acceptance")

    def test_scope_policy_is_exact(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        self.assertEqual(
            document["scope_policy"],
            "sipi.p4a-04g.ramp-package-spec-v1.declaration-only",
        )

    def test_network_solve_not_in_slice(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        self.assertEqual(document["slice"]["network_solve"], "not_in_this_slice")
        self.assertEqual(document["slice"]["decoder"], "not_in_this_slice")

    def test_implementation_source_exists(self) -> None:
        self.assertTrue(GATE.SOURCE.is_file())
        source = GATE.SOURCE.read_text(encoding="utf-8")
        self.assertIn("pub struct RampSpecV1", source)
        self.assertIn("pub struct PackageSpecV1", source)

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P4A-04g", plan_text)

    def test_rejects_validation_rule_drift(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["validation_rules"]["ramp"]["r_load"] = "finite_non_negative"
        with self.assertRaises(GATE.RampPackageError):
            GATE.verify_document(document)

    def test_rejects_admission_drift(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["admission"]["network_solve"] = True
        with self.assertRaises(GATE.RampPackageError):
            GATE.verify_document(document)


if __name__ == "__main__":
    unittest.main()
