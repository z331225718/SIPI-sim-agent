"""Compare bounded MATLAB and Rust TDILN package-case diagnostics.

This is a diagnostic gate, not a release oracle.  It compares the scalar and
bounded-vector receipts emitted by ``sipi_com_tdiln_matrix_diagnostic_v1``
and the direct Rust result.  It also makes the user-selected performance rule
explicit: the measured Rust invocation must not be slower than MATLAB's
reported TDILN core time.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


SCALAR_FIELDS = {
    "com_db": ("metrics", "COM_dB"),
    "erl_db": ("metrics", "ERL"),
    "fom_tdiln": ("metrics", "FOM_TDILN"),
}
TDILN_SCALAR_FIELDS = {
    "fom": "fom_v",
    "fom_pdf": "fom_pdf_v",
    "snr_isi_fom": "snr_isi_fom_db",
    "snr_isi_fom_pdf": "snr_isi_fom_pdf_db",
}
VECTOR_FIELDS = ("time", "iln", "reference_pr", "fitted_pr")
VECTOR_SUMMARY_FIELDS = ("length", "first", "last", "minimum", "maximum", "sum", "sum_squares")


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")
    return float(value)


def _scalar(value: Any, label: str) -> float | str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _finite(value, label)
    if isinstance(value, str):
        token = {
            "inf": "+Inf",
            "+inf": "+Inf",
            "infinity": "+Inf",
            "+infinity": "+Inf",
            "-inf": "-Inf",
            "-infinity": "-Inf",
            "nan": "NaN",
        }.get(value.casefold())
        if token is not None:
            return token
    raise ValueError(f"{label} must be finite numeric or a supported special token")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _summary(value: Any, label: str) -> dict[str, float | int]:
    raw = _object(value, label)
    if set(raw) != set(VECTOR_SUMMARY_FIELDS):
        raise ValueError(f"{label} key set drift")
    length = raw["length"]
    if isinstance(length, bool) or not isinstance(length, int) or length <= 0:
        raise ValueError(f"{label}.length must be positive integer")
    return {"length": length, **{field: _finite(raw[field], f"{label}.{field}") for field in VECTOR_SUMMARY_FIELDS[1:]}}


def _close(left: float, right: float, tolerance: float) -> bool:
    return abs(left - right) <= tolerance


def _matlab_cases(document: Any) -> list[dict[str, Any]]:
    root = _object(document, "MATLAB summary")
    if root.get("schema") != "sipi.com.tdiln-matrix-diagnostic.v1" or root.get("diagnostic_only") is not True:
        raise ValueError("MATLAB summary schema/diagnostic flag drift")
    case_count = root.get("case_count")
    cases = _array(root.get("cases"), "MATLAB cases")
    if not isinstance(case_count, int) or case_count != len(cases) or not cases:
        raise ValueError("MATLAB case count drift")
    _finite(root.get("core_duration_seconds"), "MATLAB core duration")
    validated = []
    for index, raw in enumerate(cases):
        case = _object(raw, f"MATLAB case {index}")
        if case.get("case_index") != index:
            raise ValueError("MATLAB case index drift")
        applicable = case.get("tdiln_applicable")
        if not isinstance(applicable, bool):
            raise ValueError("MATLAB TDILN applicability drift")
        if applicable:
            tdiln = _object(case.get("tdiln"), f"MATLAB case {index}.tdiln")
            for field in SCALAR_FIELDS:
                _scalar(case.get(field), f"MATLAB case {index}.{field}")
            for field in TDILN_SCALAR_FIELDS:
                _finite(tdiln.get(field), f"MATLAB case {index}.tdiln.{field}")
            for field in VECTOR_FIELDS:
                _summary(tdiln.get(field), f"MATLAB case {index}.tdiln.{field}")
        elif case.get("tdiln") not in (None, []) or case.get("fom_tdiln") not in (None, []) or case.get("tdiln_inapplicable_reason") != "source_did_not_emit_FOM_TDILN_and_TD_ILN":
            raise ValueError("MATLAB TDILN inapplicable shape drift")
        validated.append(case)
    return validated


def _rust_cases(document: Any) -> list[dict[str, Any]]:
    root = _object(document, "Rust result")
    cases = _array(root.get("cases"), "Rust cases")
    if not cases:
        raise ValueError("Rust cases empty")
    validated = []
    for index, raw in enumerate(cases):
        case = _object(raw, f"Rust case {index}")
        if case.get("case_index") != index:
            raise ValueError("Rust case index drift")
        metrics = _object(case.get("metrics"), f"Rust case {index}.metrics")
        diagnostics = _object(case.get("diagnostics"), f"Rust case {index}.diagnostics")
        tdiln = diagnostics.get("tdiln")
        if tdiln is not None:
            tdiln = _object(tdiln, f"Rust case {index}.tdiln")
            summaries = _object(tdiln.get("vector_summaries"), f"Rust case {index}.tdiln.vector_summaries")
            for _, (_, metric_name) in SCALAR_FIELDS.items():
                _scalar(metrics.get(metric_name), f"Rust case {index}.metrics.{metric_name}")
            for _, field in TDILN_SCALAR_FIELDS.items():
                _finite(tdiln.get(field), f"Rust case {index}.tdiln.{field}")
            for field in VECTOR_FIELDS:
                _summary(summaries.get(field), f"Rust case {index}.tdiln.vector_summaries.{field}")
        elif metrics.get("FOM_TDILN") is not None:
            raise ValueError("Rust TDILN metric exists without diagnostics")
        validated.append(case)
    return validated


def compare(
    matlab_document: Any,
    rust_document: Any,
    *,
    rust_wall_seconds: float,
    tolerance: float,
    rust_timing_scope: str = "Rust measures process invocation plus artifact write; MATLAB reports source COM core after engine startup.",
) -> dict[str, Any]:
    """Return a deterministic diagnostic record; raise on malformed inputs."""
    rust_wall_seconds = _finite(rust_wall_seconds, "Rust wall duration")
    tolerance = _finite(tolerance, "tolerance")
    if tolerance < 0.0:
        raise ValueError("tolerance must be nonnegative")
    if not isinstance(rust_timing_scope, str) or not rust_timing_scope:
        raise ValueError("Rust timing scope must be a non-empty string")
    matlab_cases = _matlab_cases(matlab_document)
    rust_cases = _rust_cases(rust_document)
    if len(matlab_cases) != len(rust_cases):
        raise ValueError("MATLAB/Rust case count drift")
    matlab_core_seconds = _finite(matlab_document["core_duration_seconds"], "MATLAB core duration")
    comparisons = []
    passed = rust_wall_seconds <= matlab_core_seconds
    for index, (matlab_case, rust_case) in enumerate(zip(matlab_cases, rust_cases, strict=True)):
        matlab_tdiln_applicable = matlab_case["tdiln_applicable"]
        rust_tdiln = rust_case["diagnostics"].get("tdiln")
        if not matlab_tdiln_applicable:
            rust_absent = rust_tdiln is None and rust_case["metrics"].get("FOM_TDILN") is None
            passed = passed and rust_absent
            comparisons.append({
                "case_index": index,
                "tdiln_applicable": False,
                "source_inapplicable_reason": matlab_case["tdiln_inapplicable_reason"],
                "rust_tdiln_absent": rust_absent,
                "passed": rust_absent,
            })
            continue
        metrics = rust_case["metrics"]
        if rust_tdiln is None:
            passed = False
            comparisons.append({"case_index": index, "tdiln_applicable": True, "rust_tdiln_absent": True, "passed": False})
            continue
        rust_summaries = rust_tdiln["vector_summaries"]
        scalar_deltas = {}
        scalar_special_tokens = {}
        for matlab_name, (_, rust_name) in SCALAR_FIELDS.items():
            left = _scalar(matlab_case[matlab_name], f"MATLAB case {index}.{matlab_name}")
            right = _scalar(metrics[rust_name], f"Rust case {index}.{rust_name}")
            if isinstance(left, float) and isinstance(right, float):
                scalar_deltas[matlab_name] = abs(left - right)
            else:
                scalar_special_tokens[matlab_name] = {"matlab": left, "rust": right, "equal": left == right}
        for matlab_name, rust_name in TDILN_SCALAR_FIELDS.items():
            left = _finite(matlab_case["tdiln"][matlab_name], f"MATLAB case {index}.tdiln.{matlab_name}")
            right = _finite(rust_tdiln[rust_name], f"Rust case {index}.tdiln.{rust_name}")
            scalar_deltas[f"tdiln.{matlab_name}"] = abs(left - right)
        vectors = {}
        for name in VECTOR_FIELDS:
            left = _summary(matlab_case["tdiln"][name], f"MATLAB case {index}.tdiln.{name}")
            right = _summary(rust_summaries[name], f"Rust case {index}.tdiln.{name}")
            length_equal = left["length"] == right["length"]
            deltas = {field: abs(float(left[field]) - float(right[field])) for field in VECTOR_SUMMARY_FIELDS[1:]}
            vectors[name] = {"length_equal": length_equal, "absolute_deltas": deltas}
            passed = passed and length_equal and all(delta <= tolerance for delta in deltas.values())
        scalar_passed = (
            all(delta <= tolerance for delta in scalar_deltas.values())
            and all(item["equal"] for item in scalar_special_tokens.values())
        )
        passed = passed and scalar_passed
        comparisons.append({"case_index": index, "tdiln_applicable": True, "scalar_absolute_deltas": scalar_deltas, "scalar_special_tokens": scalar_special_tokens, "vector_summaries": vectors, "passed": scalar_passed and all(item["length_equal"] and all(delta <= tolerance for delta in item["absolute_deltas"].values()) for item in vectors.values())})
    return {
        "schema": "sipi.com.tdiln-matrix-diagnostic-comparison.v1",
        "status": "passed_diagnostic" if passed else "blocked",
        "diagnostic_only": True,
        "non_claims": ["not_release_evidence", "not_full_vector_identity", "not_complete_warning_catalog"],
        "timing": {
            "matlab_core_seconds": matlab_core_seconds,
            "rust_wall_seconds": rust_wall_seconds,
            "rust_not_slower": rust_wall_seconds <= matlab_core_seconds,
            "scope_note": rust_timing_scope,
        },
        "tolerance": tolerance,
        "case_count": len(comparisons),
        "tdiln_applicable_case_count": sum(item["tdiln_applicable"] for item in comparisons),
        "cases": comparisons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matlab-summary", type=Path, required=True)
    parser.add_argument("--rust-result", type=Path, required=True)
    parser.add_argument("--rust-wall-seconds", type=float, required=True)
    parser.add_argument("--tolerance", type=float, default=1.0e-9)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    document = compare(
        json.loads(args.matlab_summary.read_text(encoding="utf-8")),
        json.loads(args.rust_result.read_text(encoding="utf-8")),
        rust_wall_seconds=args.rust_wall_seconds,
        tolerance=args.tolerance,
    )
    args.output.write_text(json.dumps(document, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": document["status"], "case_count": document["case_count"]}))
    return 0 if document["status"] == "passed_diagnostic" else 1


if __name__ == "__main__":
    raise SystemExit(main())
