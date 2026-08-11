"""Contract tests for the delegated P7-06a fixed TRAN performance policy."""

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
POLICY_SPEC = importlib.util.spec_from_file_location("policy", ROOT / "tools" / "verify_p7_fixed_tran_performance_policy.py")
assert POLICY_SPEC and POLICY_SPEC.loader
POLICY = importlib.util.module_from_spec(POLICY_SPEC)
POLICY_SPEC.loader.exec_module(POLICY)


class FixedTranPerformancePolicyTests(unittest.TestCase):
    def observation(self) -> dict:
        digest = "a" * 64
        samples = [
            {
                "index": index,
                "wall_time_ns": 24_000_000 + index,
                "peak_working_set_bytes": 4_000_000 + index,
                "success_sha256": digest,
                "result_sha256": digest,
                "provenance_sha256": digest,
            }
            for index in range(MEASURE.MEASURED_COUNT)
        ]
        return {
            "schema": MEASURE.REPORT_SCHEMA,
            "status": "observed_pending_owner_budget",
            "workload": {
                "profile_id": MEASURE.PROFILE_ID,
                "request_schema": MEASURE.REQUEST_SCHEMA,
                "request_sha256": MEASURE.sha256(MEASURE.REQUEST),
            },
            "identity": {
                "commit": "b" * 40,
                "cargo_lock_sha256": "c" * 64,
                "toolchain": "1.97.0-x86_64-pc-windows-msvc",
                "executable_sha256": "d" * 64,
                "executable_bytes": 1,
                "platform": "windows-x86_64",
                "os": "Windows-test",
            },
            "protocol": {
                "warmup_count": MEASURE.WARMUP_COUNT,
                "measured_count": MEASURE.MEASURED_COUNT,
                "wall_clock": "perf_counter_ns",
                "peak_working_set": "GetProcessMemoryInfo.PeakWorkingSetSize",
            },
            "samples": samples,
            "summary": {
                "wall_time_ns": MEASURE._summary(samples, "wall_time_ns"),
                "peak_working_set_bytes": MEASURE._summary(samples, "peak_working_set_bytes"),
            },
            "limitations": ["observation only"],
        }

    def locked_build_for(self, observation: dict) -> tuple[dict, str]:
        identity = observation["identity"]
        report = {
            "schema": "sipi.p1-windows-locked-build-report.v1",
            "status": "passed",
            "commit": identity["commit"],
            "lock_sha256": identity["cargo_lock_sha256"],
            "target": "x86_64-pc-windows-msvc",
            "installed_executable_sha256": identity["executable_sha256"],
            "commands": [{"command": ["cargo"], "exit_code": 0, "stdout_sha256": "a" * 64, "stderr_sha256": "a" * 64}],
            "smoke": [{"command": ["sipi.exe", "version"], "exit_code": 0, "stdout_sha256": "a" * 64, "stderr_sha256": "a" * 64}],
            "schema_inventory_sha256": "a" * 64,
            "limitations": ["provisional"],
        }
        return report, hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def policy_for(self, observation: dict) -> tuple[dict, str, dict, str]:
        policy = json.loads(POLICY.POLICY.read_text(encoding="utf-8"))
        observation_sha256 = hashlib.sha256(
            json.dumps(observation, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        locked_build, locked_build_sha256 = self.locked_build_for(observation)
        policy["baseline"] = {
            "observation_sha256": observation_sha256,
            "p1_locked_build_report_sha256": locked_build_sha256,
            "identity": {
                "commit": observation["identity"]["commit"],
                "cargo_lock_sha256": observation["identity"]["cargo_lock_sha256"],
                "executable_sha256": observation["identity"]["executable_sha256"],
            },
            "observed_medians": {
                "wall_time_ns": observation["summary"]["wall_time_ns"]["median"],
                "peak_working_set_bytes": observation["summary"]["peak_working_set_bytes"]["median"],
            },
            "evidence_ref": "docs/baselines/audits/2026-08-11-p7-fixed-tran-performance-policy.md",
        }
        return policy, observation_sha256, locked_build, locked_build_sha256

    def test_valid_policy_is_baseline_bound_but_not_release_ready(self) -> None:
        observation = self.observation()
        policy, observation_sha256, locked_build, locked_build_sha256 = self.policy_for(observation)
        report = POLICY.validate_policy(policy, observation, observation_sha256, locked_build, locked_build_sha256)
        self.assertTrue(report["valid"], report)
        self.assertFalse(report["release_ready"])
        self.assertEqual(report["status"], "delegated_approved_baseline_bound")
        self.assertIn("candidate_archive_observation_required", report["blockers"])

    def test_threshold_and_workload_drift_are_rejected(self) -> None:
        observation = self.observation()
        policy, observation_sha256, locked_build, locked_build_sha256 = self.policy_for(observation)
        policy["thresholds"]["median_wall_time_ns_max"] -= 1
        self.assertFalse(POLICY.validate_policy(policy, observation, observation_sha256, locked_build, locked_build_sha256)["valid"])
        policy, observation_sha256, locked_build, locked_build_sha256 = self.policy_for(observation)
        policy["workload"]["profile_id"] = "other"
        self.assertFalse(POLICY.validate_policy(policy, observation, observation_sha256, locked_build, locked_build_sha256)["valid"])

    def test_baseline_and_approval_tampering_are_rejected(self) -> None:
        observation = self.observation()
        policy, observation_sha256, locked_build, locked_build_sha256 = self.policy_for(observation)
        policy["baseline"]["observation_sha256"] = "0" * 64
        self.assertFalse(POLICY.validate_policy(policy, observation, observation_sha256, locked_build, locked_build_sha256)["valid"])
        policy, observation_sha256, locked_build, locked_build_sha256 = self.policy_for(observation)
        policy["delegated_approval"]["approval_ref"] = "unrecorded"
        self.assertFalse(POLICY.validate_policy(policy, observation, observation_sha256, locked_build, locked_build_sha256)["valid"])

    def test_observation_identity_and_output_drift_are_rejected(self) -> None:
        observation = self.observation()
        policy, observation_sha256, locked_build, locked_build_sha256 = self.policy_for(observation)
        altered = copy.deepcopy(observation)
        altered["identity"]["executable_sha256"] = "f" * 64
        self.assertFalse(POLICY.validate_policy(policy, altered, observation_sha256, locked_build, locked_build_sha256)["valid"])
        altered = copy.deepcopy(observation)
        altered["samples"][0]["result_sha256"] = "f" * 64
        self.assertFalse(POLICY.validate_policy(policy, altered, observation_sha256, locked_build, locked_build_sha256)["valid"])

    def test_locked_build_evidence_must_match_baseline_identity(self) -> None:
        observation = self.observation()
        policy, observation_sha256, locked_build, locked_build_sha256 = self.policy_for(observation)
        locked_build["installed_executable_sha256"] = "f" * 64
        self.assertFalse(POLICY.validate_policy(policy, observation, observation_sha256, locked_build, locked_build_sha256)["valid"])

    def test_baseline_must_fit_the_approved_thresholds(self) -> None:
        observation = self.observation()
        for sample in observation["samples"]:
            sample["wall_time_ns"] = POLICY.THRESHOLDS["median_wall_time_ns_max"] + 1
        observation["summary"]["wall_time_ns"] = MEASURE._summary(observation["samples"], "wall_time_ns")
        policy, observation_sha256, locked_build, locked_build_sha256 = self.policy_for(observation)
        report = POLICY.validate_policy(policy, observation, observation_sha256, locked_build, locked_build_sha256)
        self.assertFalse(report["valid"])
        self.assertEqual(report["blockers"], ["baseline_exceeds_policy_threshold"])


if __name__ == "__main__":
    unittest.main()
