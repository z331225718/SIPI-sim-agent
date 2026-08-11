"""Contract tests for the P7 fixed TRAN candidate-performance wrapper."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("candidate", ROOT / "tools" / "verify_p7_fixed_tran_candidate_performance.py")
assert SPEC and SPEC.loader
CANDIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANDIDATE)
MEASURE = CANDIDATE.POLICY.MEASURE


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class CandidatePerformanceTests(unittest.TestCase):
    def observation(self, *, commit: str, lock: str, executable: str, wall_time_ns: int = 24_000_000) -> dict:
        samples = [
            {
                "index": index,
                "wall_time_ns": wall_time_ns + index,
                "peak_working_set_bytes": 4_000_000 + index,
                "success_sha256": "a" * 64,
                "result_sha256": "a" * 64,
                "provenance_sha256": "a" * 64,
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
                "commit": commit,
                "cargo_lock_sha256": lock,
                "toolchain": "1.97.0-x86_64-pc-windows-msvc",
                "executable_sha256": executable,
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

    def policy_inputs(self, observation: dict) -> tuple[dict, dict]:
        policy = json.loads(CANDIDATE.POLICY.POLICY.read_text(encoding="utf-8"))
        policy["baseline"] = {
            "observation_sha256": digest(observation),
            "p1_locked_build_report_sha256": "0" * 64,
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
        locked = {
            "schema": "sipi.p1-windows-locked-build-report.v1",
            "status": "passed",
            "commit": observation["identity"]["commit"],
            "lock_sha256": observation["identity"]["cargo_lock_sha256"],
            "target": "x86_64-pc-windows-msvc",
            "installed_executable_sha256": observation["identity"]["executable_sha256"],
            "commands": [{"command": ["cargo"], "exit_code": 0, "stdout_sha256": "a" * 64, "stderr_sha256": "a" * 64}],
            "smoke": [{"command": ["sipi.exe"], "exit_code": 0, "stdout_sha256": "a" * 64, "stderr_sha256": "a" * 64}],
            "schema_inventory_sha256": "a" * 64,
            "limitations": ["provisional"],
        }
        policy["baseline"]["p1_locked_build_report_sha256"] = digest(locked)
        return policy, locked

    def evidence(self) -> dict:
        commit, tree, lock, executable = "b" * 40, "c" * 40, "d" * 64, "e" * 64
        baseline = self.observation(commit=commit, lock=lock, executable=executable)
        policy, locked = self.policy_inputs(baseline)
        candidate = self.observation(commit=commit, lock=lock, executable=executable)
        twin = {
            "schema": "sipi.p7-windows-twin-build-report.v1",
            "status": "identical",
            "commit": commit,
            "tree": tree,
            "lock_sha256": lock,
            "toolchain_sha256": "f" * 64,
            "rustflags_sha256": "a" * 64,
            "target": "x86_64-pc-windows-msvc",
            "build_a": {"binary_bytes": 1, "binary_sha256": executable, "cargo_version_sha256": "a" * 64, "rustc_version_sha256": "a" * 64},
            "build_b": {"binary_bytes": 1, "binary_sha256": executable, "cargo_version_sha256": "a" * 64, "rustc_version_sha256": "a" * 64},
            "comparison": {"size_match": True, "digest_match": True},
            "limitations": ["provisional"],
        }
        composition = {
            "schema": "sipi.release-composition-preflight.v1",
            "evidence_status": "incomplete",
            "promotion_status": "blocked",
            "source_build": {
                "commit": commit,
                "tree": tree,
                "target": "x86_64-pc-windows-msvc",
                "cargo_lock_sha256": lock,
                "toolchain_sha256": twin["toolchain_sha256"],
                "twin_report_sha256": digest(twin),
                "staged_binary_sha256": executable,
                "staged_binary_bytes": 1,
            },
            "dependency_inventory": [],
            "notice_license_gaps": ["pending"],
            "static_pe": {
                "layout_report_sha256": "a" * 64,
                "machine": "amd64",
                "normal_imports": ["kernel32.dll"],
                "delay_imports": "not_present_in_layout_observation",
                "dynamic_load_closure": "not_assessed",
                "runtime_dependency_closure": "not_assessed",
            },
            "limitations": ["provisional"],
        }
        archive = {
            "schema": "sipi.release-archive-report.v1",
            "structural_admission": "conformant",
            "composition_evidence_status": "incomplete",
            "promotion_status": "blocked",
            "archive_sha256": "f" * 64,
            "archive_bytes": 2,
            "policy_sha256": "a" * 64,
            "composition_report_sha256": digest(composition),
            "source_commit": commit,
            "entries": [
                {"role": "main_executable", "bytes": 1, "content_sha256": executable},
                {"role": "mit_license", "bytes": 1, "content_sha256": "a" * 64},
            ],
            "static_pe_binding": "same_executable_bytes_as_composition_stage",
            "limitations": ["provisional"],
        }
        install = {
            "schema": "sipi.isolated-install-admission.v1",
            "status": "isolated_install_smoke_passed",
            "environment_class": "same_host_isolated_prefix",
            "fresh_machine": False,
            "fresh_user": "not_assessed",
            "host_loader_closure": "not_assessed",
            "promotion_status": "blocked",
            "archive_sha256": archive["archive_sha256"],
            "archive_report_sha256": digest(archive),
            "installed_executable_sha256": executable,
            "sanitization_policy_sha256": "a" * 64,
            "probes": [{"id": "version"}],
            "limitations": ["provisional"],
        }
        return {
            "policy": policy,
            "baseline": baseline,
            "locked": locked,
            "candidate": candidate,
            "twin": twin,
            "composition": composition,
            "archive": archive,
            "install": install,
            "head": commit,
            "tree": tree,
        }

    def evaluate(self, evidence: dict) -> dict:
        return CANDIDATE.evaluate_candidate(
            policy=evidence["policy"],
            policy_sha256=digest(evidence["policy"]),
            policy_baseline=evidence["baseline"],
            policy_baseline_sha256=digest(evidence["baseline"]),
            policy_locked_build=evidence["locked"],
            policy_locked_build_sha256=digest(evidence["locked"]),
            candidate_observation=evidence["candidate"],
            candidate_observation_sha256=digest(evidence["candidate"]),
            twin=evidence["twin"],
            twin_sha256=digest(evidence["twin"]),
            composition=evidence["composition"],
            composition_sha256=digest(evidence["composition"]),
            archive=evidence["archive"],
            archive_sha256=digest(evidence["archive"]),
            install=evidence["install"],
            install_sha256=digest(evidence["install"]),
            head=evidence["head"],
            tree=evidence["tree"],
        )

    def test_valid_chain_is_within_policy_but_promotion_remains_blocked(self) -> None:
        report = self.evaluate(self.evidence())
        self.assertEqual(report["status"], "within_policy")
        self.assertEqual(report["promotion_status"], "blocked")
        self.assertEqual(report["threshold_verdict"], "pass")
        self.assertNotIn("C:\\", json.dumps(report))

    def test_over_limit_is_a_reported_nonzero_condition(self) -> None:
        evidence = self.evidence()
        for sample in evidence["candidate"]["samples"]:
            sample["wall_time_ns"] = 30_000_001
        evidence["candidate"]["summary"]["wall_time_ns"] = MEASURE._summary(evidence["candidate"]["samples"], "wall_time_ns")
        report = self.evaluate(evidence)
        self.assertEqual(report["status"], "over_limit")
        self.assertEqual(report["threshold_verdict"], "block_release_candidate")

    def test_chain_and_observation_mismatches_are_rejected(self) -> None:
        evidence = self.evidence()
        evidence["composition"]["source_build"]["twin_report_sha256"] = "0" * 64
        with self.assertRaisesRegex(CANDIDATE.CandidateError, "twin_composition_identity_mismatch"):
            self.evaluate(evidence)
        evidence = self.evidence()
        evidence["candidate"]["identity"]["executable_sha256"] = "0" * 64
        with self.assertRaisesRegex(CANDIDATE.CandidateError, "candidate_observation_chain_mismatch"):
            self.evaluate(evidence)

    def test_policy_baseline_must_remain_valid(self) -> None:
        evidence = self.evidence()
        evidence["policy"]["baseline"]["observation_sha256"] = "0" * 64
        with self.assertRaisesRegex(CANDIDATE.CandidateError, "policy_baseline_not_bound"):
            self.evaluate(evidence)


if __name__ == "__main__":
    unittest.main()
