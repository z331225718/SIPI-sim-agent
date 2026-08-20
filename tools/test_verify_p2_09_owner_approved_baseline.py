"""Tests for the P2-09 owner-approved baseline gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p2_09_owner_approved_baseline as GATE


class BaselineTests(unittest.TestCase):
    def test_current_baseline_is_approved(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertTrue(result["approved"])

    def test_policy_is_delegated_approved(self) -> None:
        policy = GATE.load_yaml(GATE.POLICY)
        self.assertEqual(policy["status"], "delegated_approved")
        self.assertEqual(policy["delegated_approval"]["approval_ref"], GATE.APPROVAL_REF)

    def test_thresholds_rule_disposition(self) -> None:
        policy = GATE.load_yaml(GATE.POLICY)
        self.assertEqual(policy["thresholds"], GATE.EXPECTED_THRESHOLDS)
        self.assertEqual(policy["statistical_rule"], GATE.EXPECTED_RULE)
        self.assertEqual(policy["over_limit_disposition"], GATE.EXPECTED_DISPOSITION)

    def test_baseline_binding(self) -> None:
        policy = GATE.load_yaml(GATE.POLICY)
        baseline = policy["baseline"]
        self.assertEqual(baseline["observation_sha256"], GATE.OBSERVATION_SHA256)
        self.assertEqual(baseline["p1_locked_build_report_sha256"], GATE.P1_REPORT_SHA256)
        self.assertGreater(baseline["observed_medians"]["wall_time_ns"], 0)

    def test_audit_records_delegation(self) -> None:
        audit = GATE.read_text(GATE.AUDIT)
        self.assertIn("delegated", audit.lower())
        self.assertIn("30,000,000", audit)


if __name__ == "__main__":
    unittest.main()
