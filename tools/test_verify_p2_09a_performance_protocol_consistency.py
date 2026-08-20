"""Tests for the P2-09a performance-protocol consistency gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p2_09a_performance_protocol_consistency as GATE


class ProtocolConsistencyTests(unittest.TestCase):
    def test_current_protocol_is_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["tools"], 4)

    def test_measure_constants(self) -> None:
        measure = GATE.load_module(GATE.TOOLS["measure"])
        self.assertEqual(measure.WARMUP_COUNT, 3)
        self.assertEqual(measure.MEASURED_COUNT, 10)
        self.assertEqual(measure.PROFILE_ID, "tran-rc-pulse-v1")
        self.assertEqual(measure.REQUEST_SCHEMA, "sipi.tran.rc-pulse-request.v1")

    def test_verify_budget_protocol_tokens(self) -> None:
        text = GATE.read_text(GATE.TOOLS["verify_budget"])
        for token in ("perf_counter_ns", "GetProcessMemoryInfo.PeakWorkingSetSize", "median_min_max_nanoseconds", "median_min_max_bytes", "windows-x86_64"):
            self.assertIn(token, text)

    def test_pending_approval_guard_present(self) -> None:
        text = GATE.read_text(GATE.TOOLS["verify_budget"])
        self.assertIn("pending_budget_must_not_imply_approval", text)

    def test_policy_imports_measure(self) -> None:
        text = GATE.read_text(GATE.TOOLS["policy"])
        self.assertIn("measure_tran_rc_pulse_performance", text)

    def test_candidate_reaches_measure_indirectly(self) -> None:
        text = GATE.read_text(GATE.TOOLS["candidate"])
        self.assertTrue(
            "measure_tran_rc_pulse_performance" in text or "verify_p7_fixed_tran_performance_policy" in text
        )

    def test_all_tools_tracked(self) -> None:
        for relative in GATE.TOOLS.values():
            self.assertTrue(GATE.git_tracked(relative), relative)


if __name__ == "__main__":
    unittest.main()
