"""Focused tests for the current-candidate v6 normalization layer."""

from __future__ import annotations

import copy
import unittest

from tools import run_com_workbook_accm_replay_v5 as legacy
from tools import run_com_workbook_accm_replay_v6 as replay


def comparison(*, delta: float = 0.0, dfe: bool = True) -> dict[str, object]:
    metrics = {key: delta for key in replay.COMMON_METRIC_KEYS}
    metrics.update({key: None for key in set(legacy.METRIC_KEYS) - set(replay.COMMON_METRIC_KEYS)})
    return {
        "port_order_match": False,
        "port_order_observed": False,
        "port_order_status": "not_observed",
        "cursor_index_match": True,
        "sigma_n_v_abs_delta": delta,
        "fom_db_abs_delta": delta,
        "metric_abs_delta": metrics,
        "dfe": {"upstream_published": True, "candidate_published": dfe, "status": "observed"},
        "array_receipts": {"upstream": {}, "candidate": {}},
    }


def report() -> dict[str, object]:
    return {
        "schema": "sipi.com.workbook-accm-replay.v5.diagnostic",
        "blockers": ["candidate_dfe_taps_not_published"],
        "controls": [
            {"comparison": [comparison(), comparison()]}
            for _ in legacy.CONTROL_VECTORS
        ],
    }


class CurrentCandidateReplayTests(unittest.TestCase):
    def test_current_projection_accepts_observed_numeric_parity(self) -> None:
        result = replay.normalize(report())
        self.assertEqual(result["status"], replay.STATUS)
        self.assertTrue(result["matched"])
        self.assertFalse(result["acceptance"])
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["port_order"]["public_result_comparison"], "not_exposed_by_upstream")
        self.assertEqual(replay.normalize(result)["status"], replay.STATUS)

    def test_numeric_drift_blocks_without_downgrading_to_port_order(self) -> None:
        value = report()
        value["controls"][0]["comparison"][0]["metric_abs_delta"]["COM_dB"] = replay.NUMERIC_TOLERANCE * 2
        result = replay.normalize(value)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["matched"])
        self.assertEqual(result["blockers"], [])

    def test_missing_dfe_is_not_erased(self) -> None:
        value = report()
        value["controls"][0]["comparison"][0] = comparison(dfe=False)
        result = replay.normalize(value)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blockers"], ["candidate_dfe_taps_not_published"])

    def test_legacy_schema_or_matrix_drift_is_rejected(self) -> None:
        value = report()
        value["schema"] = "wrong"
        with self.assertRaises(ValueError):
            replay.normalize(value)
        value = report()
        value["controls"] = value["controls"][:-1]
        with self.assertRaises(ValueError):
            replay.normalize(value)


if __name__ == "__main__":
    unittest.main()
