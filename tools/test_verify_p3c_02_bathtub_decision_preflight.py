"""Tests for the P3C-02 bathtub decision-surface preflight verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3c_02_bathtub_decision_preflight as GATE


class BathtubPreflightTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        result = GATE.verify_document(document)
        self.assertTrue(result["valid"])
        self.assertEqual(result["bathtub_implementation"], "prohibited")

    def test_decision_surface_all_unselected(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        for key in ("estimator", "tolerance", "reference_binding", "eye_folding_bins"):
            self.assertEqual(document["decision_surface"][key], "unselected_pending_owner_decision")

    def test_blocker_linkage_is_exact(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        self.assertEqual(
            document["blocker_linkage"]["blocker"],
            "blocked_missing_metric_profile_semantics_and_accepted_receiver_stage",
        )
        self.assertEqual(document["blocker_linkage"]["plan_row"], "P3C-01")

    def test_plan_rows_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P3C-02d", plan_text)
        self.assertIn(GATE.BLOCKER, plan_text)

    def test_rejects_estimator_selection(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["decision_surface"]["estimator"] = "gaussian_q_function"
        with self.assertRaises(GATE.BathtubPreflightError):
            GATE.verify_document(document)

    def test_rejects_implementation_admission(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["admission"]["bathtub_implementation"] = "admitted"
        with self.assertRaises(GATE.BathtubPreflightError):
            GATE.verify_document(document)


if __name__ == "__main__":
    unittest.main()
