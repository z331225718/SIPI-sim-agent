"""Tests for the P3C-03 profile-compare decision-surface preflight verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3c_03_profile_compare_decision_preflight as GATE


class ProfileComparePreflightTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        result = GATE.verify_document(document)
        self.assertTrue(result["valid"])
        self.assertEqual(result["profile_compare_implementation"], "oracle_reference_bound_compare_executed")

    def test_c4_metric_profile_selected_reference_pending(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        self.assertEqual(document["decision_surface"]["metric_profile"], "selected_c4_com_dB_ICN_mV_ERL_1pct")
        self.assertEqual(document["decision_surface"]["reference_binding"], "bound_p5_06e_matlab_oracle")
        self.assertEqual(document["decision_surface"]["tolerance_policy"], "selected_1pct_relative")
        self.assertIn("(C4:", document["decision_ref"])

    def test_blocker_linkage_is_exact(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        self.assertEqual(document["blocker_linkage"]["blocker"], GATE.BLOCKER)
        self.assertEqual(document["blocker_linkage"]["plan_row"], "P3C-01")

    def test_plan_rows_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P3C-03b", plan_text)
        self.assertIn(GATE.BLOCKER, plan_text)

    def test_rejects_reference_binding_regression_to_unselected(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["decision_surface"]["reference_binding"] = "pending_oracle_reference"
        with self.assertRaises(GATE.ProfileComparePreflightError):
            GATE.verify_document(document)
        document2 = GATE.load_yaml(GATE.DEFAULT)
        document2["decision_surface"]["metric_profile"] = "ibis-org-sample1-input-typ-static-v2"
        with self.assertRaises(GATE.ProfileComparePreflightError):
            GATE.verify_document(document2)

    def test_rejects_implementation_admission_drift(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["admission"]["profile_compare_implementation"] = "pending_oracle_reference"
        with self.assertRaises(GATE.ProfileComparePreflightError):
            GATE.verify_document(document)
        document2 = GATE.load_yaml(GATE.DEFAULT)
        document2["admission"]["profile_compare_implementation"] = "prohibited_without_owner_profile"
        with self.assertRaises(GATE.ProfileComparePreflightError):
            GATE.verify_document(document2)


if __name__ == "__main__":
    unittest.main()