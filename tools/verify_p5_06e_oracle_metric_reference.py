# -*- coding: utf-8 -*-
"""Fail closed on the P5-06e COM oracle metric reference binding.

Verifies that the authoritative MATLAB oracle reference values bound in the
P5-06e reference document are exactly those present in the machine-verified
P5-06a first-run evidence summary_content, by independently recomputing the
digest over the sorted 'key=repr(value)' lines and checking the C4 metrics.
Fails closed on any drift between the evidence and the bound reference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs" / "baselines" / "p5-06e-com-oracle-metric-reference.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06-matlab-oracle-first-run-evidence.v1.yaml"
PLAN = ROOT / "PLAN.md"
SCHEMA = "sipi.p5-06e.com-oracle-metric-reference.v1"
C4_METRICS = ("COM_dB", "ICN_mV", "ERL")


class OracleReferenceError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise OracleReferenceError("document_not_mapping")
    return value


def reference_digest(refs: dict[str, float]) -> str:
    lines = sorted(f"{k}={v!r}" for k, v in refs.items())
    joined = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()


def extract_from_evidence(evidence: dict[str, Any]) -> tuple[dict[str, float], list[dict[str, Any]]]:
    summary = json.loads(evidence["summary_content"])
    output = summary["output_metrics"]
    aggregate = {k: output[k]["value"] for k in C4_METRICS if output[k]["kind"] == "finite"}
    if set(aggregate) != set(C4_METRICS):
        raise OracleReferenceError("evidence_missing_c4_metric")
    cases = []
    for case in summary["case_metrics"]:
        m = case["output_metrics"]
        values = {k: m[k]["value"] for k in C4_METRICS if m[k]["kind"] == "finite"}
        if set(values) == set(C4_METRICS):
            cases.append({"case_index": case["case_index"], **values})
    return aggregate, cases


def validate(root: Path = ROOT) -> dict[str, Any]:
    reference = load_yaml(REFERENCE)
    if reference.get("schema") != SCHEMA or reference.get("status") != "oracle_metric_reference_bound_hash_verified":
        raise OracleReferenceError("reference_schema_or_status_invalid")
    evidence = load_yaml(EVIDENCE)
    if evidence.get("status") != "matlab_oracle_first_run_succeeded_hash_bound":
        raise OracleReferenceError("evidence_status_drift")
    if reference.get("summary_json_sha256") != evidence.get("output_file_hashes", {}).get("summary.json", "").lower():
        raise OracleReferenceError("summary_hash_drift")
    aggregate, cases = extract_from_evidence(evidence)
    # Recompute the digest from the evidence values and compare to the bound one.
    recomputed = reference_digest(aggregate)
    if recomputed != reference.get("aggregate_reference_digest"):
        raise OracleReferenceError("digest_drift")
    bound_aggregate = reference.get("aggregate_reference", {})
    if set(bound_aggregate) != set(C4_METRICS):
        raise OracleReferenceError("bound_aggregate_missing_c4")
    for k in C4_METRICS:
        if bound_aggregate[k] != aggregate[k]:
            raise OracleReferenceError(f"aggregate_value_drift:{k}")
    bound_cases = reference.get("case_references", [])
    if len(bound_cases) != len(cases) or bound_cases != cases:
        raise OracleReferenceError("case_reference_drift")
    if reference.get("c4_policy") != "sipi.p3c-03c.c4-profile.v1.com-icn-erl-1pct":
        raise OracleReferenceError("c4_policy_drift")
    plan_text = PLAN.read_text(encoding="utf-8")
    if "**P5-06e" not in plan_text:
        raise OracleReferenceError("plan_row_missing")
    return {"valid": True, "aggregate_reference_digest": recomputed, "case_count": len(cases)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except OracleReferenceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
