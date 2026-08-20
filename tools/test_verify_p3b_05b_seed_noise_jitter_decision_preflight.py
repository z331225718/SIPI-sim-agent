"""Tests for the P3B-05 seed/noise/jitter decision-surface preflight verifier."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3b_05b_seed_noise_jitter_decision_preflight as GATE


class SeedNoiseJitterPreflightTests(unittest.TestCase):
    def test_current_charter_is_valid(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        result = GATE.verify_document(document)
        self.assertTrue(result["valid"])
        self.assertEqual(result["seed_noise_jitter_implementation"], "prohibited")

    def test_decision_surface_all_unselected(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        for key in ("required_profile", "injection_position", "units_model", "seed_replay", "observables", "tolerance"):
            self.assertEqual(document["decision_surface"][key], "unselected_pending_owner_decision")

    def test_blocker_linkage_is_exact(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        self.assertEqual(document["blocker_linkage"]["request_schema_id"], "sipi.link.causal-fir-request.v1")
        self.assertEqual(document["blocker_linkage"]["plan_row"], "P3B-05")

    def test_plan_rows_present(self) -> None:
        plan_text = GATE.PLAN.read_text(encoding="utf-8")
        self.assertIn("**P3B-05b", plan_text)
        self.assertIn("**P3B-05a 已完成", plan_text)

    def test_rejection_gate_and_schema_present(self) -> None:
        self.assertTrue(GATE.REJECTION_GATE.is_file())
        self.assertIn(GATE.REQUEST_SCHEMA_ID, GATE.CONTRACTS.read_text(encoding="utf-8"))

    def test_rejects_profile_selection(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["decision_surface"]["required_profile"] = "selected"
        with self.assertRaises(GATE.SeedNoiseJitterPreflightError):
            GATE.verify_document(document)

    def test_rejects_implementation_admission(self) -> None:
        document = GATE.load_yaml(GATE.DEFAULT)
        document["admission"]["noise_jitter_profile_implementation"] = "admitted"
        with self.assertRaises(GATE.SeedNoiseJitterPreflightError):
            GATE.verify_document(document)


if __name__ == "__main__":
    unittest.main()
