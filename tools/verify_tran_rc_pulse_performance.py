"""Fail closed on an unapproved RC/PULSE performance budget."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.tran.performance-budget.v1"
MEASURE_SPEC = importlib.util.spec_from_file_location("tran_performance", ROOT / "tools" / "measure_tran_rc_pulse_performance.py")
assert MEASURE_SPEC and MEASURE_SPEC.loader
MEASURE = importlib.util.module_from_spec(MEASURE_SPEC)
MEASURE_SPEC.loader.exec_module(MEASURE)


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("pyyaml_unavailable")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("budget_not_object")
    return document


def _load_observation(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as error:
        raise RuntimeError("observation_invalid_json") from error
    report = MEASURE.validate_observation(document)
    if not report["valid"]:
        raise RuntimeError(f"observation_{report['reason']}")
    return document, hashlib.sha256(payload).hexdigest()


def verify_budget(document: object, observation_sha256: str, *, release: bool) -> dict[str, Any]:
    blockers: list[str] = []
    expected_top = {"schema", "status", "workload", "measurement_protocol", "observation_sha256", "metric_definitions", "approval", "non_claims"}
    if not _exact(document, expected_top) or document.get("schema") != SCHEMA:
        return {"valid": False, "release_ready": False, "blockers": ["budget_schema_invalid"]}
    expected_workload = {"profile_id": "tran-rc-pulse-v1", "request_schema": "sipi.tran.rc-pulse-request.v1", "platform": "windows-x86_64", "executable_kind": "p1-11-installed-rust-cli"}
    expected_protocol = {"warmup_count": 3, "measured_count": 10, "wall_clock": "perf_counter_ns", "peak_working_set": "GetProcessMemoryInfo.PeakWorkingSetSize"}
    expected_metrics = {"wall_time": "median_min_max_nanoseconds", "peak_working_set": "median_min_max_bytes"}
    if document.get("workload") != expected_workload:
        blockers.append("budget_workload_invalid")
    if document.get("measurement_protocol") != expected_protocol:
        blockers.append("budget_protocol_invalid")
    if document.get("metric_definitions") != expected_metrics:
        blockers.append("budget_metrics_invalid")
    if not isinstance(document.get("non_claims"), list) or not document["non_claims"] or not all(isinstance(item, str) and item for item in document["non_claims"]):
        blockers.append("budget_non_claims_invalid")
    approval = document.get("approval")
    approval_keys = {"owner", "approved_at_utc", "scope", "thresholds", "statistical_rule", "over_limit_disposition", "approval_ref"}
    if not _exact(approval, approval_keys):
        blockers.append("budget_approval_shape_invalid")
    status = document.get("status")
    if status == "pending":
        if document.get("observation_sha256") is not None or approval != {key: None for key in approval_keys}:
            blockers.append("pending_budget_must_not_imply_approval")
        if release:
            blockers.append("owner_budget_pending")
        return {"valid": not blockers, "release_ready": False, "status": "pending", "observation_sha256": observation_sha256, "blockers": blockers}
    if status != "approved":
        blockers.append("budget_status_invalid")
    if document.get("observation_sha256") != observation_sha256:
        blockers.append("approved_budget_observation_mismatch")
    if not isinstance(approval, dict) or not all(isinstance(approval.get(key), str) and approval[key] for key in approval_keys):
        blockers.append("approved_budget_fields_missing")
    return {"valid": not blockers, "release_ready": not blockers, "status": status, "observation_sha256": observation_sha256, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--budget", type=Path, default=ROOT / "docs" / "baselines" / "tran-rc-pulse-performance-budget.v1.yaml")
    parser.add_argument("--release", action="store_true")
    arguments = parser.parse_args()
    try:
        _, observation_sha256 = _load_observation(arguments.observation)
        report = verify_budget(_load_yaml(arguments.budget), observation_sha256, release=arguments.release)
    except (OSError, RuntimeError) as error:
        report = {"valid": False, "release_ready": False, "blockers": [str(error)]}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["valid"] and (not arguments.release or report["release_ready"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
