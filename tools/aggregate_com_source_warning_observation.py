"""Aggregate the five original-13 MATLAB anti-causal warning observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

try:
    from tools.run_com_source_warning_observation import SCHEMA, digest
except ImportError:
    from run_com_source_warning_observation import SCHEMA, digest


AGGREGATE_SCHEMA = "sipi.com.source-warning-observation-aggregate.v1"
EXPECTED_INDICES = (0, 2, 8, 10, 12)
TRACE_SCHEMA = "sipi.com.interp-sparam-input-trace.v1"
STACK_SCHEMA = "sipi.com.source-warning-stack.v1"
ANTI_CAUSAL_STACK = (
    ("warning", 55),
    ("interp_Sparam", 6337),
    ("s21_to_impulse_DC", 10110),
    ("get_TDR", 5427),
    ("process_sxp", 8408),
    ("com_ieee8023_480", 332),
    ("sipi_com_tdiln_matrix_diagnostic_v1", 51),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _finite(value: Any, label: str) -> float:
    _require(not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value)), label)
    return float(value)


def _record(document: Any) -> dict[str, Any]:
    _require(isinstance(document, dict), "report must be an object")
    expected = {
        "schema", "diagnostic_only", "non_claims", "source_commit_unverified",
        "matlab_harness_sha256", "matlab_launch", "records", "status",
    }
    _require(set(document) == expected and document["schema"] == SCHEMA, "report schema")
    _require(document["diagnostic_only"] is True and document["status"] == "passed_observation", "report status")
    _require(document["non_claims"] == ["not_rust_parity", "not_complete_warning_catalog", "not_release_evidence"], "report non-claims")
    _require(document["source_commit_unverified"] is True and document["matlab_launch"] == "python_engine_noFigureWindows_singleCompThread", "report launch")
    _require(isinstance(document["matlab_harness_sha256"], str) and len(document["matlab_harness_sha256"]) == 64, "harness hash")
    records = document["records"]
    _require(isinstance(records, list) and len(records) == 1, "one record per report")
    record = records[0]
    _require(isinstance(record, dict) and set(record) == {"workbook_index", "workbook", "status", "matlab_summary_sha256", "core_duration_seconds", "events"}, "record schema")
    _require(record["status"] == "passed_observation" and isinstance(record["workbook_index"], int) and isinstance(record["workbook"], str), "record status")
    _require(isinstance(record["matlab_summary_sha256"], str) and len(record["matlab_summary_sha256"]) == 64, "summary hash")
    _require(_finite(record["core_duration_seconds"], "core duration") > 0.0, "core duration")
    _require(isinstance(record["events"], list), "events")
    return {"harness_sha256": document["matlab_harness_sha256"], **record}


def _anti_trace(event: dict[str, Any]) -> dict[str, Any]:
    trace = event.get("source_trace")
    expected = {
        "schema", "status", "element_count", "first_real", "first_imaginary",
        "last_real", "last_imaginary", "sum_real", "sum_imaginary",
        "maximum_magnitude", "mean_unwrapped_phase_step", "positive_mean_phase_step",
    }
    _require(isinstance(trace, dict) and set(trace) == expected, "anti-causal trace schema")
    _require(trace["schema"] == TRACE_SCHEMA and trace["status"] == "captured", "anti-causal trace status")
    _require(isinstance(trace["element_count"], (int, float)) and trace["element_count"] >= 2, "anti-causal trace size")
    for key in expected - {"schema", "status", "element_count", "positive_mean_phase_step"}:
        _finite(trace[key], f"anti-causal trace {key}")
    _require(trace["positive_mean_phase_step"] is True and _finite(trace["mean_unwrapped_phase_step"], "anti-causal slope") > 0.0, "anti-causal predicate")
    return trace


def _anti_stack(event: dict[str, Any]) -> list[dict[str, Any]]:
    stack = event.get("source_stack")
    _require(isinstance(stack, dict) and set(stack) == {"schema", "status", "frames"}, "anti-causal stack schema")
    _require(stack["schema"] == STACK_SCHEMA and stack["status"] == "captured", "anti-causal stack status")
    frames = stack["frames"]
    _require(isinstance(frames, list), "anti-causal stack frames")
    observed: list[tuple[str, int]] = []
    for frame in frames:
        _require(isinstance(frame, dict) and set(frame) == {"name", "line"}, "anti-causal stack frame")
        _require(isinstance(frame["name"], str) and isinstance(frame["line"], int), "anti-causal stack frame value")
        observed.append((frame["name"], frame["line"]))
    _require(tuple(observed) == ANTI_CAUSAL_STACK, "anti-causal stack identity")
    return frames


def _maximum_frequency_event(event: dict[str, Any]) -> None:
    _require(
        isinstance(event, dict)
        and set(event) == {"sequence", "identifier", "source_line", "source_stack", "source_trace"}
        and isinstance(event["sequence"], int)
        and event["identifier"] == "COM:read_s4p:MaxFreqTooLow"
        and event["source_line"] == 9715
        and event["source_stack"] == {"schema": STACK_SCHEMA, "status": "not_requested"}
        and event["source_trace"] == {"schema": TRACE_SCHEMA, "status": "not_requested"},
        "maximum-frequency source event",
    )


def aggregate(reports: list[tuple[Path, Any]]) -> dict[str, Any]:
    _require(len(reports) == len(EXPECTED_INDICES), "five reports required")
    parsed = [(path, _record(document)) for path, document in reports]
    _require(len({path.resolve() for path, _ in parsed}) == len(parsed), "report paths must be distinct")
    ordered = sorted(parsed, key=lambda item: item[1]["workbook_index"])
    _require(tuple(record["workbook_index"] for _, record in ordered) == EXPECTED_INDICES, "original-13 anti-causal index set")
    harnesses = {record["harness_sha256"] for _, record in ordered}
    _require(len(harnesses) == 1, "MATLAB harness drift")
    summary: list[dict[str, Any]] = []
    for path, record in ordered:
        events = record["events"]
        expected_lines = (6337,) if record["workbook_index"] in (0, 2) else (9715, 9715, 9715, 6337)
        _require(tuple(event.get("source_line") for event in events) == expected_lines, "source warning order")
        anti = events[-1]
        _require(anti.get("identifier") == "" and anti.get("source_line") == 6337, "identifier-less anti-causal source event")
        trace = _anti_trace(anti)
        stack = _anti_stack(anti)
        for maximum in events[:-1]:
            _maximum_frequency_event(maximum)
        summary.append({
            "workbook_index": record["workbook_index"],
            "matlab_summary_sha256": record["matlab_summary_sha256"],
            "core_duration_seconds": record["core_duration_seconds"],
            "event_lines": list(expected_lines),
            "anti_causal_trace": trace,
            "anti_causal_stack": stack,
            "report_sha256": digest(path),
        })
    return {
        "schema": AGGREGATE_SCHEMA,
        "diagnostic_only": True,
        "non_claims": ["not_rust_parity", "not_complete_warning_catalog", "not_release_evidence"],
        "status": "passed_observation",
        "matlab_harness_sha256": next(iter(harnesses)),
        "source_warning_callsite_set": {
            "anti_causal": {"identifier": "", "source_line": 6337},
            "maximum_frequency": {"identifier": "COM:read_s4p:MaxFreqTooLow", "source_line": 9715},
        },
        "records": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _require(args.output.exists() is False, "output must be fresh")
    result = aggregate([(path, json.loads(path.read_text(encoding="utf-8"))) for path in args.report])
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "aggregate_sha256": digest(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
