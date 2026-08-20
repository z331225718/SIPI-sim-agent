"""Verify P2-09a performance-budget tool-chain protocol consistency.

P2-09a fixed the observation protocol (3 warmup / 10 measured, perf_counter
wall clock, PeakWorkingSetSize) and the pending-budget verifier. This gate
fails closed if the protocol constants or the pending/approved semantics
drift across the four tools: measure, verify budget, P7 fixed-tran
performance policy, and P7 candidate performance.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p2-09a.performance-protocol-consistency.v1"

TOOLS = {
    "measure": "tools/measure_tran_rc_pulse_performance.py",
    "verify_budget": "tools/verify_tran_rc_pulse_performance.py",
    "policy": "tools/verify_p7_fixed_tran_performance_policy.py",
    "candidate": "tools/verify_p7_fixed_tran_candidate_performance.py",
}

EXPECTED_PROTOCOL = {
    "warmup_count": 3,
    "measured_count": 10,
    "wall_clock": "perf_counter_ns",
    "peak_working_set": "GetProcessMemoryInfo.PeakWorkingSetSize",
}
EXPECTED_WORKLOAD = {
    "profile_id": "tran-rc-pulse-v1",
    "request_schema": "sipi.tran.rc-pulse-request.v1",
    "platform": "windows-x86_64",
}
EXPECTED_METRICS = {
    "wall_time": "median_min_max_nanoseconds",
    "peak_working_set": "median_min_max_bytes",
}


class ProtocolError(RuntimeError):
    pass


def git_tracked(relative: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", "--", relative],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
    )
    return completed.returncode == 0


def read_text(relative: str) -> str:
    try:
        return (ROOT / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ProtocolError("source_read_failed") from error


def load_module(relative: str) -> Any:
    spec = importlib.util.spec_from_file_location("module_" + relative.replace("/", "_"), ROOT / relative)
    if spec is None or spec.loader is None:
        raise ProtocolError(f"module_load_failed:{relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(root: Path = ROOT) -> dict[str, Any]:
    for relative in TOOLS.values():
        if not git_tracked(relative) or not (root / relative).is_file():
            raise ProtocolError(f"tool_missing:{relative}")

    measure = load_module(TOOLS["measure"])
    if getattr(measure, "WARMUP_COUNT", None) != EXPECTED_PROTOCOL["warmup_count"]:
        raise ProtocolError("warmup_count_drift")
    if getattr(measure, "MEASURED_COUNT", None) != EXPECTED_PROTOCOL["measured_count"]:
        raise ProtocolError("measured_count_drift")
    if getattr(measure, "PROFILE_ID", None) != EXPECTED_WORKLOAD["profile_id"]:
        raise ProtocolError("profile_id_drift")
    if getattr(measure, "REQUEST_SCHEMA", None) != EXPECTED_WORKLOAD["request_schema"]:
        raise ProtocolError("request_schema_drift")

    verify_text = read_text(TOOLS["verify_budget"])
    for token, expected in [
        ("perf_counter_ns", EXPECTED_PROTOCOL["wall_clock"]),
        ("GetProcessMemoryInfo.PeakWorkingSetSize", EXPECTED_PROTOCOL["peak_working_set"]),
        ("median_min_max_nanoseconds", EXPECTED_METRICS["wall_time"]),
        ("median_min_max_bytes", EXPECTED_METRICS["peak_working_set"]),
        ("windows-x86_64", EXPECTED_WORKLOAD["platform"]),
    ]:
        if token not in verify_text:
            raise ProtocolError(f"verify_token_missing:{token}")

    # The pending budget must never imply approval.
    if "pending_budget_must_not_imply_approval" not in verify_text:
        raise ProtocolError("pending_approval_guard_missing")

    # The P7 policy verifier must load the same measure module directly; the
    # candidate verifier consumes it through the policy module (indirect).
    policy_text = read_text(TOOLS["policy"])
    if "measure_tran_rc_pulse_performance" not in policy_text:
        raise ProtocolError("policy_does_not_import_measure")
    candidate_text = read_text(TOOLS["candidate"])
    if (
        "measure_tran_rc_pulse_performance" not in candidate_text
        and "verify_p7_fixed_tran_performance_policy" not in candidate_text
    ):
        raise ProtocolError("candidate_does_not_reach_measure")

    return {"valid": True, "tools": len(TOOLS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except ProtocolError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
