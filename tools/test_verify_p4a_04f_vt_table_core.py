"""Tests for the P4A-04f typed V-T table core verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p4a_04f_vt_table_core as GATE


class VtCoreTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        result = GATE.verify_document(document)
        self.assertEqual(result["status"], "product_owned_vt_table_core_specified_no_profile_acceptance")

    def test_policy_string_is_exact(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        self.assertEqual(
            document["evaluation_policy"]["policy"],
            "sipi.p4a-04f.vt-table-v1.linear-within-domain.reject-out-of-domain",
        )

    def test_ramp_package_not_in_slice(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        self.assertEqual(document["slice"]["ramp"], "not_in_this_slice")
        self.assertEqual(document["slice"]["package"], "not_in_this_slice")

    def test_implementation_source_exists(self) -> None:
        self.assertTrue(GATE.SOURCE.is_file())
        source = GATE.SOURCE.read_text(encoding="utf-8")
        self.assertIn("pub fn evaluate_vt_v1", source)
        self.assertIn("VtTableV1", source)

    def test_plan_row_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P4A-04f", plan_text)

    def test_rejects_scope_drift(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["slice"]["ramp"] = "this_slice"
        with self.assertRaises(GATE.VtCoreError):
            GATE.verify_document(document)

    def test_rejects_policy_drift(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["evaluation_policy"]["extrapolation"] = "linear_extrapolation"
        with self.assertRaises(GATE.VtCoreError):
            GATE.verify_document(document)

    def test_rejects_admission_drift(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["admission"]["profile_accepted"] = True
        with self.assertRaises(GATE.VtCoreError):
            GATE.verify_document(document)


if __name__ == "__main__":
    unittest.main()
