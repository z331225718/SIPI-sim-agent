"""Contract tests for the external RC/PULSE performance observation gate."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEASURE_SPEC = importlib.util.spec_from_file_location("measure", ROOT / "tools" / "measure_tran_rc_pulse_performance.py")
assert MEASURE_SPEC and MEASURE_SPEC.loader
MEASURE = importlib.util.module_from_spec(MEASURE_SPEC)
MEASURE_SPEC.loader.exec_module(MEASURE)
BUDGET_SPEC = importlib.util.spec_from_file_location("budget", ROOT / "tools" / "verify_tran_rc_pulse_performance.py")
assert BUDGET_SPEC and BUDGET_SPEC.loader
BUDGET = importlib.util.module_from_spec(BUDGET_SPEC)
BUDGET_SPEC.loader.exec_module(BUDGET)


class TranPerformanceGateTests(unittest.TestCase):
    def observation(self) -> dict:
        digest = "a" * 64
        samples = [
            {
                "index": index,
                "wall_time_ns": 1000 + index,
                "peak_working_set_bytes": 4096 + index,
                "success_sha256": digest,
                "result_sha256": digest,
                "provenance_sha256": digest,
            }
            for index in range(10)
        ]
        return {
            "schema": MEASURE.REPORT_SCHEMA,
            "status": "observed_pending_owner_budget",
            "workload": {"profile_id": "tran-rc-pulse-v1", "request_schema": "sipi.tran.rc-pulse-request.v1", "request_sha256": MEASURE.sha256(MEASURE.REQUEST)},
            "identity": {"commit": "b" * 40, "cargo_lock_sha256": "c" * 64, "toolchain": "1.97.0-x86_64-pc-windows-msvc", "executable_sha256": "d" * 64, "executable_bytes": 1, "platform": "windows-x86_64", "os": "Windows-test"},
            "protocol": {"warmup_count": 3, "measured_count": 10, "wall_clock": "perf_counter_ns", "peak_working_set": "GetProcessMemoryInfo.PeakWorkingSetSize"},
            "samples": samples,
            "summary": {"wall_time_ns": MEASURE._summary(samples, "wall_time_ns"), "peak_working_set_bytes": MEASURE._summary(samples, "peak_working_set_bytes")},
            "limitations": ["observation only"],
        }

    def budget(self) -> dict:
        return BUDGET._load_yaml(ROOT / "docs" / "baselines" / "tran-rc-pulse-performance-budget.v1.yaml")

    def test_observation_requires_complete_identical_samples(self) -> None:
        report = self.observation()
        self.assertTrue(MEASURE.validate_observation(report)["valid"])
        invalid = copy.deepcopy(report)
        invalid["samples"][3]["result_sha256"] = "e" * 64
        self.assertEqual(MEASURE.validate_observation(invalid)["reason"], "output_identity_drift")
        invalid = copy.deepcopy(report)
        invalid["samples"] = invalid["samples"][:-1]
        self.assertEqual(MEASURE.validate_observation(invalid)["reason"], "sample_count")
        invalid = copy.deepcopy(report)
        invalid["summary"]["wall_time_ns"]["max"] = 1
        self.assertEqual(MEASURE.validate_observation(invalid)["reason"], "summary_invalid")

    def test_pending_budget_is_preflight_valid_but_never_release_ready(self) -> None:
        payload = json.dumps(self.observation(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        observation_sha256 = hashlib.sha256(payload).hexdigest()
        preflight = BUDGET.verify_budget(self.budget(), observation_sha256, release=False)
        self.assertTrue(preflight["valid"], preflight["blockers"])
        self.assertFalse(preflight["release_ready"])
        release = BUDGET.verify_budget(self.budget(), observation_sha256, release=True)
        self.assertFalse(release["valid"])
        self.assertIn("owner_budget_pending", release["blockers"])

    def test_approved_budget_binds_observation_and_all_owner_fields(self) -> None:
        payload = json.dumps(self.observation(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        observation_sha256 = hashlib.sha256(payload).hexdigest()
        approved = self.budget()
        approved["status"] = "approved"
        approved["observation_sha256"] = observation_sha256
        approved["approval"] = {
            "owner": "owner",
            "approved_at_utc": "2026-08-10T00:00:00Z",
            "scope": "fixed profile",
            "thresholds": "declared",
            "statistical_rule": "median",
            "over_limit_disposition": "reject",
            "approval_ref": "decision",
        }
        self.assertTrue(BUDGET.verify_budget(approved, observation_sha256, release=True)["valid"])
        approved["observation_sha256"] = "0" * 64
        self.assertFalse(BUDGET.verify_budget(approved, observation_sha256, release=True)["valid"])


if __name__ == "__main__":
    unittest.main()
