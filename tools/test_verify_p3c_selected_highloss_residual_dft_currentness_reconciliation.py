"""Mutation tests for the selected residual-DFT currentness reconciliation."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p3c_selected_highloss_residual_dft_currentness_reconciliation as GATE


class ResidualDftCurrentnessTests(unittest.TestCase):
    def test_current_reconciliation_and_exact_drift_are_valid(self) -> None:
        self.assertTrue(GATE.validate()["historical"])

    def test_rejects_historical_hash_mutation(self) -> None:
        document = copy.deepcopy(GATE._load(GATE.DOCUMENT))
        document["historical_record"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.ReconciliationError, "historical_record_binding_invalid"):
            GATE.validate(document, execute=False)

    def test_rejects_current_or_acceptance_promotion(self) -> None:
        for key in (
            "current_product_inventory_matches",
            "current_external_replay_available",
            "current_candidate_baseline_reproduced",
            "current_residual_spectral_distribution_observed",
            "selected_highloss_waveform_only_profile_accepted",
            "acceptance_ready",
            "release_ledger_promoted",
        ):
            with self.subTest(key=key):
                document = copy.deepcopy(GATE._load(GATE.DOCUMENT))
                document["state"][key] = True
                with self.assertRaisesRegex(GATE.ReconciliationError, "state_promotion_or_drift"):
                    GATE.validate(document, execute=False)

    def test_rejects_unexpected_historical_verifier_result(self) -> None:
        completed = GATE.subprocess.CompletedProcess([], 0, "{'valid': True}\n", "")
        with mock.patch.object(GATE.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(GATE.ReconciliationError, "historical_source_drift_result_invalid"):
                GATE.validate()


if __name__ == "__main__":
    unittest.main()
