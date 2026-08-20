"""Tests for the P7-08 same-batch drift-gate retirement strategy verifier (owner-approved)."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p7_08_drift_gate_retirement_strategy as GATE


def current_strategy() -> dict:
    return GATE.load_json(GATE.STRATEGY)


class DriftGateStrategyTests(unittest.TestCase):
    def test_current_strategy_is_valid_and_deterministic(self) -> None:
        document = current_strategy()
        GATE.validate(document, ROOT)
        self.assertEqual(GATE.render(document), GATE.render(document))

    def test_current_strategy_registers_all_required_gate_paths(self) -> None:
        document = current_strategy()
        covered = {entry["gate_path"] for entry in document["entries"]}
        self.assertEqual(covered, GATE.REQUIRED_GATE_PATHS)

    def test_strategy_is_owner_approved(self) -> None:
        document = current_strategy()
        self.assertEqual(document["approval_state"], "owner_approved")

    def test_strategy_cross_binds_signed_approval_record(self) -> None:
        GATE.check_approval_record(ROOT)
        record = GATE.load_json(GATE.RECORD)
        self.assertEqual(record["approval_state"], "owner_approved")
        self.assertTrue(isinstance(record["approved_by"], str) and record["approved_by"])
        self.assertTrue(isinstance(record["approved_at_utc"], str) and record["approved_at_utc"])

    def test_strategy_rejects_reverted_approval_state(self) -> None:
        document = current_strategy()
        document["approval_state"] = "awaiting_owner_approval"
        with self.assertRaises(GATE.StrategyError):
            GATE.validate(document, ROOT)

    def test_strategy_rejects_blocker_removal(self) -> None:
        document = current_strategy()
        document["blocker"] = "release_ready"
        with self.assertRaises(GATE.StrategyError):
            GATE.validate(document, ROOT)

    def test_strategy_rejects_removal_disposition_after_approval(self) -> None:
        # Owner approval does NOT grant gate removal; removal dispositions stay
        # forbidden even after approval.
        document = current_strategy()
        document["entries"][0]["disposition"] = "removal_approved"
        with self.assertRaises(GATE.StrategyError):
            GATE.validate(document, ROOT)

    def test_strategy_rejects_gate_dropping(self) -> None:
        document = current_strategy()
        document["entries"][0]["required_gates"] = ["per_path_replacement_mapping"]
        with self.assertRaises(GATE.StrategyError):
            GATE.validate(document, ROOT)

    def test_strategy_rejects_glob_gate_path(self) -> None:
        document = current_strategy()
        document["entries"][0]["gate_path"] = "tools/verify_m0_*.py"
        with self.assertRaises(GATE.StrategyError):
            GATE.validate(document, ROOT)

    def test_strategy_rejects_approval_claim_in_notes(self) -> None:
        document = current_strategy()
        document["entries"][0]["notes"] = "owner approved removal"
        with self.assertRaises(GATE.StrategyError):
            GATE.validate(document, ROOT)

    def test_strategy_rejects_tracked_count_drift(self) -> None:
        document = current_strategy()
        document["entries"][0]["tracked_file_count"] += 1
        with self.assertRaises(GATE.StrategyError):
            GATE.validate(document, ROOT)

    def test_strategy_rejects_coverage_gap(self) -> None:
        document = current_strategy()
        del document["entries"][0]
        with self.assertRaises(GATE.StrategyError):
            GATE.validate(document, ROOT)

    def test_strategy_rejects_retirement_procedure_drift(self) -> None:
        document = current_strategy()
        document["retirement_procedure"].append("remove_all_gates_now")
        with self.assertRaises(GATE.StrategyError):
            GATE.validate(document, ROOT)

    def test_strategy_rejects_purpose_claim(self) -> None:
        document = current_strategy()
        document["purpose"] = "This strategy is approved and removes the gates."
        with self.assertRaises(GATE.StrategyError):
            GATE.validate(document, ROOT)

    def test_render_is_stable_and_machine_readable(self) -> None:
        document = current_strategy()
        rendered = GATE.render(document)
        self.assertTrue(rendered.startswith("# SIPI P7-08 Same-Batch Drift-Gate Retirement Strategy"))
        self.assertIn(GATE.BLOCKER, rendered)

    def test_real_strategy_binds_live_git_tracked_counts(self) -> None:
        document = current_strategy()
        for entry in document["entries"]:
            completed = subprocess.run(
                ["git", "-C", str(ROOT), "ls-files", "--", entry["gate_path"]],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=60,
            )
            count = len([line for line in completed.stdout.splitlines() if line.strip()])
            self.assertEqual(count, entry["tracked_file_count"], f"count drift for {entry['gate_path']}")


if __name__ == "__main__":
    unittest.main()
