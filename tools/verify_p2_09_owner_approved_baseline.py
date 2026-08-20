"""Verify P2-09 owner-approved performance baseline completeness.

P2-09 requires an owner-approved workload performance/RSS baseline with
thresholds, statistical rule, and over-limit disposition. P7-06a recorded
the delegated owner approval (user-delegated-numeric-policy-2026-08-11)
with the 3+10 observation baseline, median-only rule, and
block_release_candidate disposition. This gate fails closed if the policy
loses its delegated_approved status, its four required elements, or its
baseline binding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p2-09.owner-approved-baseline.v1"

POLICY = "docs/baselines/fixed-tran-performance-policy.v1.yaml"
AUDIT = "docs/baselines/audits/2026-08-11-p7-fixed-tran-performance-policy.md"
APPROVAL_REF = "user-delegated-numeric-policy-2026-08-11"
OBSERVATION_SHA256 = "f6bcef3ee820919062018a6c3d37128260ca4cc28e8bb8c8867e3e98d060ae4f"
P1_REPORT_SHA256 = "a17d68e504d5112b401aac970431e31460db67faecc975a19fe0d1bb6a9de1f7"
EXPECTED_THRESHOLDS = {"median_wall_time_ns_max": 30000000, "median_peak_working_set_bytes_max": 5000000}
EXPECTED_RULE = "median_of_exactly_ten_measured_runs_only"
EXPECTED_DISPOSITION = "block_release_candidate"


class BaselineError(RuntimeError):
    pass


def load_yaml(relative: str) -> dict[str, Any]:
    if yaml is None:
        raise BaselineError("pyyaml_unavailable")
    value = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BaselineError("document_not_mapping")
    return value


def read_text(relative: str) -> str:
    try:
        return (ROOT / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise BaselineError("source_read_failed") from error


def validate(root: Path = ROOT) -> dict[str, Any]:
    for relative in (POLICY, AUDIT):
        if not (root / relative).is_file():
            raise BaselineError(f"file_missing:{relative}")
    policy = load_yaml(POLICY)
    if policy.get("schema") != "sipi.fixed-tran-performance-policy.v1":
        raise BaselineError("policy_schema_invalid")
    if policy.get("status") != "delegated_approved":
        raise BaselineError("policy_not_approved")

    delegated = policy.get("delegated_approval", {})
    if delegated.get("approval_ref") != APPROVAL_REF:
        raise BaselineError("approval_ref_drift")
    baseline = policy.get("baseline", {})
    if baseline.get("observation_sha256") != OBSERVATION_SHA256:
        raise BaselineError("observation_binding_drift")
    if baseline.get("p1_locked_build_report_sha256") != P1_REPORT_SHA256:
        raise BaselineError("p1_report_binding_drift")
    observed = baseline.get("observed_medians", {})
    if not isinstance(observed.get("wall_time_ns"), (int, float)) or not isinstance(observed.get("peak_working_set_bytes"), (int, float)):
        raise BaselineError("observed_medians_invalid")
    if policy.get("thresholds") != EXPECTED_THRESHOLDS:
        raise BaselineError("thresholds_drift")
    if policy.get("statistical_rule") != EXPECTED_RULE:
        raise BaselineError("statistical_rule_drift")
    if policy.get("over_limit_disposition") != EXPECTED_DISPOSITION:
        raise BaselineError("disposition_drift")

    audit = read_text(AUDIT)
    # The audit records the delegation narrative; the exact approval_ref token
    # lives in the policy document (checked above).
    if "delegated" not in audit.lower() or "30,000,000" not in audit:
        raise BaselineError("audit_delegation_missing")
    return {"valid": True, "approved": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except BaselineError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
