"""Verify the delegated P7-06a fixed TRAN performance policy and baseline."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs" / "baselines" / "fixed-tran-performance-policy.v1.yaml"
SCHEMA = "sipi.fixed-tran-performance-policy.v1"
POLICY_VERSION = "p7-06a-delegated-1"
APPROVAL_REF = "user-delegated-numeric-policy-2026-08-11"
THRESHOLDS = {"median_wall_time_ns_max": 30_000_000, "median_peak_working_set_bytes_max": 5_000_000}
SAFE_EVIDENCE_REF = re.compile(r"docs/baselines/audits/[A-Za-z0-9][A-Za-z0-9._-]*\.md")

MEASURE_SPEC = importlib.util.spec_from_file_location("tran_performance", ROOT / "tools" / "measure_tran_rc_pulse_performance.py")
assert MEASURE_SPEC and MEASURE_SPEC.loader
MEASURE = importlib.util.module_from_spec(MEASURE_SPEC)
MEASURE_SPEC.loader.exec_module(MEASURE)


class PolicyError(RuntimeError):
    pass


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hex(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PolicyError("invalid_json") from error
    if not isinstance(value, dict):
        raise PolicyError("invalid_json")
    return value, payload


def _external(path: Path) -> bool:
    resolved = path.resolve()
    return resolved != ROOT and ROOT not in resolved.parents


def _validate_locked_build_report(report: object) -> dict[str, Any] | None:
    expected = {
        "schema", "status", "commit", "lock_sha256", "target", "installed_executable_sha256",
        "commands", "smoke", "schema_inventory_sha256", "limitations",
    }
    if (
        not isinstance(report, dict)
        or set(report) != expected
        or report.get("schema") != "sipi.p1-windows-locked-build-report.v1"
        or report.get("status") != "passed"
        or not isinstance(report.get("commit"), str)
        or not re.fullmatch(r"[0-9a-f]{40}", report["commit"])
        or not _hex(report.get("lock_sha256"))
        or report.get("target") != "x86_64-pc-windows-msvc"
        or not _hex(report.get("installed_executable_sha256"))
        or not isinstance(report.get("commands"), list)
        or not report["commands"]
        or not isinstance(report.get("smoke"), list)
        or not report["smoke"]
        or not _hex(report.get("schema_inventory_sha256"))
        or not isinstance(report.get("limitations"), list)
        or not report["limitations"]
    ):
        return None
    return report


def validate_policy(
    policy: object,
    baseline: object,
    baseline_sha256: str,
    locked_build: object,
    locked_build_sha256: str,
) -> dict[str, Any]:
    expected_top = {
        "schema", "status", "policy_version", "delegated_approval", "baseline", "workload",
        "measurement_protocol", "thresholds", "statistical_rule", "over_limit_disposition", "non_claims",
    }
    if not isinstance(policy, dict) or set(policy) != expected_top or policy.get("schema") != SCHEMA:
        return {"valid": False, "release_ready": False, "blockers": ["policy_schema_invalid"]}
    if policy.get("status") != "delegated_approved" or policy.get("policy_version") != POLICY_VERSION:
        return {"valid": False, "release_ready": False, "blockers": ["policy_status_invalid"]}
    approval = policy.get("delegated_approval")
    expected_approval = {"owner", "approved_at_utc", "approval_ref", "scope"}
    if (
        not isinstance(approval, dict)
        or set(approval) != expected_approval
        or approval.get("owner") != "project_owner_delegated_policy"
        or approval.get("approval_ref") != APPROVAL_REF
        or not isinstance(approval.get("scope"), str)
        or not approval["scope"]
        or not isinstance(approval.get("approved_at_utc"), str)
    ):
        return {"valid": False, "release_ready": False, "blockers": ["delegated_approval_invalid"]}
    try:
        datetime.fromisoformat(approval["approved_at_utc"].replace("Z", "+00:00"))
    except ValueError:
        return {"valid": False, "release_ready": False, "blockers": ["delegated_approval_invalid"]}

    measure = MEASURE.validate_observation(baseline)
    if not measure["valid"]:
        return {"valid": False, "release_ready": False, "blockers": [f"baseline_{measure['reason']}"]}
    locked_build_report = _validate_locked_build_report(locked_build)
    if locked_build_report is None or not _hex(locked_build_sha256):
        return {"valid": False, "release_ready": False, "blockers": ["locked_build_report_invalid"]}
    expected_workload = {
        "profile_id": MEASURE.PROFILE_ID,
        "request_schema": MEASURE.REQUEST_SCHEMA,
        "request_sha256": MEASURE.sha256(MEASURE.REQUEST),
        "platform": "windows-x86_64",
        "executable_kind": "p7-admitted-archive-direct-installed-sipi-exe",
    }
    expected_protocol = {
        "warmup_count": MEASURE.WARMUP_COUNT,
        "measured_count": MEASURE.MEASURED_COUNT,
        "wall_clock": "perf_counter_ns",
        "peak_working_set": "GetProcessMemoryInfo.PeakWorkingSetSize",
    }
    if policy.get("workload") != expected_workload or policy.get("measurement_protocol") != expected_protocol:
        return {"valid": False, "release_ready": False, "blockers": ["policy_workload_or_protocol_invalid"]}
    if policy.get("thresholds") != THRESHOLDS or policy.get("statistical_rule") != "median_of_exactly_ten_measured_runs_only" or policy.get("over_limit_disposition") != "block_release_candidate":
        return {"valid": False, "release_ready": False, "blockers": ["policy_threshold_or_disposition_invalid"]}
    baseline_binding = policy.get("baseline")
    expected_baseline_fields = {"observation_sha256", "p1_locked_build_report_sha256", "identity", "observed_medians", "evidence_ref"}
    if not isinstance(baseline_binding, dict) or set(baseline_binding) != expected_baseline_fields:
        return {"valid": False, "release_ready": False, "blockers": ["baseline_binding_invalid"]}
    if (
        not _hex(baseline_sha256)
        or baseline_binding.get("observation_sha256") != baseline_sha256
        or not _hex(baseline_binding.get("observation_sha256"))
        or baseline_binding.get("p1_locked_build_report_sha256") != locked_build_sha256
        or not _hex(baseline_binding.get("p1_locked_build_report_sha256"))
    ):
        return {"valid": False, "release_ready": False, "blockers": ["baseline_hash_mismatch"]}
    if not isinstance(baseline_binding.get("evidence_ref"), str) or not SAFE_EVIDENCE_REF.fullmatch(baseline_binding["evidence_ref"]) or not (ROOT / baseline_binding["evidence_ref"]).is_file():
        return {"valid": False, "release_ready": False, "blockers": ["baseline_evidence_ref_invalid"]}
    identity = baseline_binding.get("identity")
    expected_identity_keys = {"commit", "cargo_lock_sha256", "executable_sha256"}
    if (
        not isinstance(identity, dict)
        or set(identity) != expected_identity_keys
        or not isinstance(identity.get("commit"), str)
        or not re.fullmatch(r"[0-9a-f]{40}", identity["commit"])
        or not _hex(identity.get("cargo_lock_sha256"))
        or not _hex(identity.get("executable_sha256"))
    ):
        return {"valid": False, "release_ready": False, "blockers": ["baseline_identity_invalid"]}
    observed_identity = baseline["identity"]
    if any(identity[key] != observed_identity[key] for key in expected_identity_keys):
        return {"valid": False, "release_ready": False, "blockers": ["baseline_identity_mismatch"]}
    if (
        locked_build_report["commit"] != identity["commit"]
        or locked_build_report["lock_sha256"] != identity["cargo_lock_sha256"]
        or locked_build_report["installed_executable_sha256"] != identity["executable_sha256"]
    ):
        return {"valid": False, "release_ready": False, "blockers": ["locked_build_identity_mismatch"]}
    medians = {"wall_time_ns": baseline["summary"]["wall_time_ns"]["median"], "peak_working_set_bytes": baseline["summary"]["peak_working_set_bytes"]["median"]}
    if baseline_binding.get("observed_medians") != medians:
        return {"valid": False, "release_ready": False, "blockers": ["baseline_median_mismatch"]}
    if (
        medians["wall_time_ns"] > THRESHOLDS["median_wall_time_ns_max"]
        or medians["peak_working_set_bytes"] > THRESHOLDS["median_peak_working_set_bytes_max"]
    ):
        return {"valid": False, "release_ready": False, "blockers": ["baseline_exceeds_policy_threshold"]}
    non_claims = policy.get("non_claims")
    if not isinstance(non_claims, list) or not non_claims or any(not isinstance(item, str) or not item for item in non_claims):
        return {"valid": False, "release_ready": False, "blockers": ["policy_non_claims_invalid"]}
    return {
        "valid": True,
        "release_ready": False,
        "status": "delegated_approved_baseline_bound",
        "baseline_observation_sha256": baseline_sha256,
        "blockers": ["candidate_archive_observation_required", "global_release_gates_pending"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-observation", type=Path, required=True)
    parser.add_argument("--p1-locked-build-report", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=POLICY)
    arguments = parser.parse_args()
    try:
        if not _external(arguments.baseline_observation) or not _external(arguments.p1_locked_build_report):
            raise PolicyError("external_evidence_required")
        policy, _ = _load_json(arguments.policy)
        baseline, payload = _load_json(arguments.baseline_observation)
        locked_build, locked_build_payload = _load_json(arguments.p1_locked_build_report)
        report = validate_policy(policy, baseline, sha256(payload), locked_build, sha256(locked_build_payload))
    except PolicyError as error:
        report = {"valid": False, "release_ready": False, "blockers": [str(error)]}
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
