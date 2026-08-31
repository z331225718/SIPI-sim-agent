"""Compare the bounded, source-local COM warning surface.

This is deliberately separate from numeric and performance acceptance.  MATLAB
captures only static calls in the pinned ``com_ieee8023_480.m`` source, while
Rust publishes only source predicates that have an exact port.  The comparison
therefore fails closed for every observed, unmapped source callsite and never
mistakes SIPI runtime observations for MATLAB warnings.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any


PINNED_AGENT_COM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
PINNED_COM_SOURCE_SHA256 = "642b28910a6fccca4682aa0a66a6a6c00633a14c17d05d8d6ee73d2808954cad"
MAX_FREQUENCY = {
    "identifier": "COM:read_s4p:MaxFreqTooLow",
    "source_line": 9715,
    "source_callsite_id": "read_s4p.max_frequency_below_fb",
}
ANTI_CAUSAL_SOURCE_LINE = 6337
TRACE_SCHEMA = "sipi.com.interp-sparam-input-trace.v1"
NORMAL_TDR_STAGE = "normal_tdr_reflection_interpolation"
TRACE_NUMERIC_FIELDS = (
    "first_real", "first_imaginary", "last_real", "last_imaginary",
    "sum_real", "sum_imaginary", "maximum_magnitude", "mean_unwrapped_phase_step",
)
ROLES = ("THRU", "FEXT", "NEXT")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")
    return float(value)


def _source_events(matlab: Any) -> list[dict[str, Any]]:
    root = _object(matlab, "MATLAB summary")
    source = _object(root.get("source_warning_calls"), "MATLAB source_warning_calls")
    if source.get("schema") != "sipi.com.pinned-source-warning-call-observation.v1" or source.get("capture_incomplete") is not False:
        raise ValueError("MATLAB warning capture schema/status drift")
    events = source.get("events")
    if not isinstance(events, list):
        raise ValueError("MATLAB source_warning_calls.events must be an array")
    for index, raw in enumerate(events, start=1):
        event = _object(raw, f"MATLAB source warning {index}")
        if event.get("sequence") != index or not isinstance(event.get("identifier"), str) or not isinstance(event.get("message"), str) or not isinstance(event.get("source_line"), (int, float)):
            raise ValueError("MATLAB source warning event shape drift")
        _validate_source_trace(event)
    return events


def _validate_source_trace(event: dict[str, Any]) -> None:
    trace = _object(event.get("source_trace"), "MATLAB source warning trace")
    stack = _object(event.get("source_stack"), "MATLAB source warning stack")
    line = event["source_line"]
    if line == ANTI_CAUSAL_SOURCE_LINE:
        if set(stack) != {"schema", "status", "frames"} or stack.get("schema") != "sipi.com.source-warning-stack.v1" or stack.get("status") != "captured":
            raise ValueError("MATLAB anti-causal source stack drift")
        frames = stack.get("frames")
        if not isinstance(frames, list) or not 2 <= len(frames) <= 15:
            raise ValueError("MATLAB anti-causal source stack size drift")
        for frame in frames:
            if not isinstance(frame, dict) or set(frame) != {"name", "line"} or not isinstance(frame["name"], str) or not isinstance(frame["line"], (int, float)):
                raise ValueError("MATLAB anti-causal source stack frame drift")
        expected = {
            "schema", "status", "element_count", "first_real", "first_imaginary",
            "last_real", "last_imaginary", "sum_real", "sum_imaginary",
            "maximum_magnitude", "mean_unwrapped_phase_step", "positive_mean_phase_step",
        }
        if set(trace) != expected or trace.get("schema") != TRACE_SCHEMA or trace.get("status") != "captured":
            raise ValueError("MATLAB anti-causal source trace drift")
        if not isinstance(trace.get("element_count"), (int, float)) or trace["element_count"] < 2:
            raise ValueError("MATLAB anti-causal source trace size drift")
        for key in expected - {"schema", "status", "element_count", "positive_mean_phase_step"}:
            _finite(trace.get(key), f"MATLAB anti-causal trace {key}")
        if not isinstance(trace.get("positive_mean_phase_step"), bool) or trace["positive_mean_phase_step"] is not True:
            raise ValueError("MATLAB anti-causal source trace predicate drift")
    elif stack != {"schema": "sipi.com.source-warning-stack.v1", "status": "not_requested"}:
        raise ValueError("MATLAB non-anti-causal source stack drift")
    elif trace != {"schema": TRACE_SCHEMA, "status": "not_requested"}:
        raise ValueError("MATLAB non-anti-causal source trace drift")


def _rust_warnings(rust: Any) -> list[dict[str, Any]]:
    root = _object(rust, "Rust result")
    coverage = _object(root.get("provenance", {}).get("warning_coverage"), "Rust warning coverage")
    if coverage != {
        "source_commit": PINNED_AGENT_COM_COMMIT,
        "source_file_sha256": PINNED_COM_SOURCE_SHA256,
        "complete_catalog": False,
        "scope": "implemented_source_mapped_calls_only",
    }:
        raise ValueError("Rust warning coverage provenance drift")
    warnings = root.get("warnings")
    if not isinstance(warnings, list):
        raise ValueError("Rust warnings must be an array")
    for index, raw in enumerate(warnings):
        warning = _object(raw, f"Rust warning {index}")
        if set(warning) != {
            "namespace", "code", "source_callsite_id", "source_line", "channel_role",
            "source_sha256", "maximum_frequency_hz", "signaling_rate_hz",
        } or warning.get("namespace") != "agent_com_r480":
            raise ValueError("Rust source warning shape drift")
        if warning.get("code") != MAX_FREQUENCY["identifier"] or warning.get("source_callsite_id") != MAX_FREQUENCY["source_callsite_id"] or warning.get("source_line") != MAX_FREQUENCY["source_line"]:
            raise ValueError("Rust root warnings may contain only exact source-mapped calls")
        if warning.get("channel_role") not in ROLES:
            raise ValueError("Rust source warning channel role drift")
        if not isinstance(warning.get("source_sha256"), str) or not HEX64.fullmatch(warning["source_sha256"]):
            raise ValueError("Rust source warning source hash drift")
        maximum = _finite(warning.get("maximum_frequency_hz"), "Rust maximum frequency")
        signaling = _finite(warning.get("signaling_rate_hz"), "Rust signaling rate")
        if maximum >= signaling:
            raise ValueError("Rust MaxFreqTooLow predicate drift")
    return warnings


def _normal_tdr_candidate(source_events: list[dict[str, Any]], rust: Any) -> dict[str, Any]:
    """Diagnose, but never promote, the normal-TDR anti-causal stage.

    The source stack establishes that line 6337 is reached through
    ``process_sxp -> get_TDR -> s21_to_impulse_DC``. Rust exposes a bounded
    trace from its corresponding normal-TDR FD-to-TD input only when DEBUG
    bypasses the same predicate. This evidence stays diagnostic until the
    vectors and occurrence semantics agree.
    """
    source_anti = [event for event in source_events if event["source_line"] == ANTI_CAUSAL_SOURCE_LINE]
    root = _object(rust, "Rust result")
    cases = root.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Rust result cases must be a non-empty array")
    candidates = []
    for case_index, case in enumerate(cases):
        diagnostics = _object(_object(case, f"Rust case {case_index}").get("diagnostics"), f"Rust case {case_index} diagnostics")
        observations = diagnostics.get("sipi_runtime_observations")
        if not isinstance(observations, list):
            raise ValueError("Rust SIPI observations must be an array")
        candidates.extend(
            (case_index, event)
            for event in observations
            if isinstance(event, dict)
            and event.get("code") == "SIPI-COM-ANTI-CAUSAL-PHASE-SLOPE-BYPASSED"
            and event.get("stage") == NORMAL_TDR_STAGE
        )
    result: dict[str, Any] = {
        "source_event_count": len(source_anti),
        "rust_observation_count": len(candidates),
        "source_stack_proves_normal_tdr_route": bool(source_anti),
        "source_warning_equivalent": False,
    }
    if len(source_anti) != 1 or len(candidates) != 1:
        result["trace_matched"] = False
        result["state"] = "incomplete_occurrence_evidence"
        return result
    case_index, candidate = candidates[0]
    expected = {
        "code", "severity", "stage", "ports", "interpolation_input_traces",
        "occurrence_count", "source_warning_equivalent",
    }
    if set(candidate) != expected or candidate["severity"] != "DEGRADED" or candidate["occurrence_count"] != len(candidate["ports"]) or candidate["source_warning_equivalent"] is not False:
        raise ValueError("Rust normal-TDR observation shape drift")
    traces = candidate["interpolation_input_traces"]
    if not isinstance(candidate["ports"], list) or not isinstance(traces, list) or len(traces) != len(candidate["ports"]):
        raise ValueError("Rust normal-TDR observation trace count drift")
    source_trace = source_anti[0]["source_trace"]
    trace_deltas: list[dict[str, Any]] = []
    observed_ports: list[int] = []
    source_maximum_magnitude = _finite(source_trace["maximum_magnitude"], "source trace maximum magnitude")
    rust_maximum_magnitudes: list[float] = []
    for port, trace in zip(candidate["ports"], traces, strict=True):
        if not isinstance(port, int) or port not in (1, 2) or not isinstance(trace, dict):
            raise ValueError("Rust normal-TDR port drift")
        expected_trace = {"port", "schema", "element_count", *TRACE_NUMERIC_FIELDS, "positive_mean_phase_step"}
        if set(trace) != expected_trace or trace["port"] != port or trace["schema"] != TRACE_SCHEMA:
            raise ValueError("Rust normal-TDR trace schema drift")
        if trace["element_count"] != source_trace["element_count"] or trace["positive_mean_phase_step"] is not True:
            trace_deltas.append({"port": port, "field": "shape_or_predicate"})
        for field in TRACE_NUMERIC_FIELDS:
            source_value = _finite(source_trace[field], f"source trace {field}")
            rust_value = _finite(trace[field], f"Rust normal-TDR trace {field}")
            if field == "maximum_magnitude":
                rust_maximum_magnitudes.append(rust_value)
            delta = abs(source_value - rust_value)
            if delta > 1.0e-12:
                trace_deltas.append({"port": port, "field": field, "absolute_delta": delta})
        observed_ports.append(port)
    result.update({
        "state": (
            "trace_matched_diagnostic_only"
            if not trace_deltas
            else "roundoff_sensitive_trace_mismatch"
            if source_maximum_magnitude <= 1.0e-12 and all(value == 0.0 for value in rust_maximum_magnitudes)
            else "trace_mismatch"
        ),
        "rust_ports": observed_ports,
        "rust_case_index": case_index,
        "trace_matched": not trace_deltas,
        "trace_mismatches": trace_deltas,
        "source_maximum_magnitude": source_maximum_magnitude,
        "rust_maximum_magnitudes": rust_maximum_magnitudes,
    })
    return result


def compare(matlab: Any, rust: Any) -> dict[str, Any]:
    """Return an auditable partial-coverage result without broad catalog claims."""
    source_events = _source_events(matlab)
    rust_warnings = _rust_warnings(rust)
    mapped = [event for event in source_events if event["identifier"] == MAX_FREQUENCY["identifier"] and event["source_line"] == MAX_FREQUENCY["source_line"]]
    unmapped = [
        {"sequence": event["sequence"], "identifier": event["identifier"], "source_line": event["source_line"]}
        for event in source_events
        if event not in mapped
    ]
    expected_roles = [ROLES[index % len(ROLES)] for index in range(len(mapped))]
    actual_roles = [warning["channel_role"] for warning in rust_warnings]
    max_frequency_matched = len(mapped) == len(rust_warnings) and expected_roles == actual_roles
    accepted = max_frequency_matched and not unmapped
    return {
        "schema": "sipi.com.source-warning-observation-comparison.v1",
        "diagnostic_only": True,
        "non_claims": ["not_complete_warning_catalog", "not_release_evidence"],
        "status": "passed_diagnostic" if accepted else "blocked",
        "implemented_callsite": MAX_FREQUENCY,
        "mapped_max_frequency": {
            "matlab_event_count": len(mapped),
            "rust_event_count": len(rust_warnings),
            "expected_roles": expected_roles,
            "actual_roles": actual_roles,
            "matched": max_frequency_matched,
        },
        "normal_tdr_interpolation_candidate": _normal_tdr_candidate(source_events, rust),
        "unimplemented_source_events": unmapped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matlab-summary", type=Path, required=True)
    parser.add_argument("--rust-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    report = compare(
        json.loads(args.matlab_summary.read_text(encoding="utf-8")),
        json.loads(args.rust_result.read_text(encoding="utf-8")),
    )
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"]}))
    return 0 if report["status"] == "passed_diagnostic" else 1


if __name__ == "__main__":
    raise SystemExit(main())
