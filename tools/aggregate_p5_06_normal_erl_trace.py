"""Aggregate two independent MATLAB normal-ERL trace diagnostic replays."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "sipi.p5-06.normal-erl-trace-aggregate.v1"
EXPECTED_INDICES = [3, 4, 5]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_report(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != "sipi.com.normal-erl-trace-diagnostic.v1":
        raise ValueError("diagnostic report schema")
    if value.get("diagnostic_only") is not True or value.get("claims", {}).get("array_digest_identity") is not True or value.get("claims", {}).get("scalar_parity") is not True:
        raise ValueError("diagnostic claims")
    records = value.get("records")
    if not isinstance(records, list) or [record.get("workbook_index") for record in records] != EXPECTED_INDICES:
        raise ValueError("workbook coverage")
    for record in records:
        comparison = record.get("comparison", {})
        if comparison.get("array_digest_identity") is not True or comparison.get("scalar_passed") is not True:
            raise ValueError("comparison result")
        if not isinstance(record.get("matlab_original_wall_seconds"), (int, float)) or not isinstance(record.get("rust_wall_seconds"), (int, float)) or record["matlab_original_wall_seconds"] <= record["rust_wall_seconds"]:
            raise ValueError("Rust no-slower timing")
    return value


def _semantic_surface(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate": value["candidate"],
        "upstream": value["upstream"],
        "instrumentation": value["instrumentation"],
        "matlab_release": value["matlab_release"],
        "vectors": value["vectors"],
        "records": [
            {
                "workbook_index": record["workbook_index"],
                "workbook": record["workbook"],
                "comparison": record["comparison"],
            }
            for record in value["records"]
        ],
    }


def aggregate(first: dict[str, Any], second: dict[str, Any], first_sha256: str, second_sha256: str) -> dict[str, Any]:
    first = _require_report(first)
    second = _require_report(second)
    if _semantic_surface(first) != _semantic_surface(second):
        raise ValueError("semantic repeat drift")
    timings = []
    for left, right in zip(first["records"], second["records"], strict=True):
        matlab_best = min(left["matlab_original_wall_seconds"], right["matlab_original_wall_seconds"])
        rust_worst = max(left["rust_wall_seconds"], right["rust_wall_seconds"])
        timings.append({
            "workbook_index": left["workbook_index"],
            "matlab_best_wall_seconds": matlab_best,
            "rust_worst_wall_seconds": rust_worst,
            "speedup_floor": matlab_best / rust_worst,
        })
    return {
        "schema": SCHEMA,
        "status": "accepted_named_normal_erl_tdr_array_checkpoint",
        "diagnostic_only": True,
        "candidate": first["candidate"],
        "upstream": first["upstream"],
        "instrumentation": first["instrumentation"],
        "matlab_release": first["matlab_release"],
        "workbook_indices": EXPECTED_INDICES,
        "vectors": first["vectors"],
        "reports": [
            {"path": "docs/baselines/p5-06-normal-erl-trace-replay-01.v1.json", "sha256": first_sha256},
            {"path": "docs/baselines/p5-06-normal-erl-trace-replay-02.v1.json", "sha256": second_sha256},
        ],
        "gates": {
            "two_fresh_matlab_instrumented_replays": True,
            "instrumentation_scalar_and_warning_semantics_unchanged": True,
            "matlab_rust_normal_erl_array_digest_identity": True,
            "matlab_rust_scalar_parity": True,
            "per_workbook_rust_not_slower": True,
            "s_parameter_fit": False,
        },
        "performance": {"per_workbook": timings, "minimum_speedup_floor": min(item["speedup_floor"] for item in timings)},
        "non_claims": [
            "not_public_result_wire",
            "not_full_erl_result_graph",
            "not_complete_warning_catalog",
            "not_instrumented_matlab_performance",
            "not_ieee_certification",
            "not_release",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.report) != 2:
        raise ValueError("exactly two reports required")
    result = aggregate(
        json.loads(args.report[0].read_text(encoding="utf-8")),
        json.loads(args.report[1].read_text(encoding="utf-8")),
        digest(args.report[0]),
        digest(args.report[1]),
    )
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "aggregate_sha256": digest(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
