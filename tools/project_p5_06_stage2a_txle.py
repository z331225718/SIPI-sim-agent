"""Strict, tool-only projection for the r4.80 TXLE checkpoint pilot.

The Stage 1 COM matrix deliberately accepted only final scalar metrics.  This
module defines the first additive Stage 2a surface: the existing source
``output_args.TXLE_taps`` vector and the same final scalar values emitted by
that core invocation.  It consumes existing Rust diagnostics only; it does
not add or widen a product API.
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Any


SCALAR_METRICS = (
    "COM_dB",
    "CTLE_DC_gain_dB",
    "ERL",
    "FOM",
    "ICN_mV",
    "IL_dB_channel_only_at_Fnq",
    "Peak_ISI_XTK_and_Noise_interference_at_BER_mV",
    "VEC_dB",
    "VEO_mV",
    "fitted_IL_dB_at_Fnq",
    "g_DC_HP",
    "itick",
)
TAP_KEYS = {
    "class",
    "shape",
    "value_count",
    "storage_order",
    "semantic_axis",
    "unit",
    "encoding",
    "raw_f64_sha256",
    "column_major_values",
}
TAP_METADATA = {
    "class": "double",
    "storage_order": "matlab_column_major",
    "semantic_axis": "tap_order_pre_to_cursor_to_post",
    "unit": "ratio",
    "encoding": "ieee754_f64_little_endian_column_major",
}
FINITE_TOLERANCE = 1.0e-9


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite numeric")
    return float(value)


def _digest_f64(values: list[float]) -> str:
    return hashlib.sha256(b"".join(struct.pack("<d", value) for value in values)).hexdigest()


def _scalar(value: Any, label: str) -> float | str:
    if isinstance(value, bool):
        raise ValueError(f"{label} must not be bool")
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number):
            return number
        return "+Inf" if number > 0 else "-Inf" if number < 0 else "NaN"
    if value in ("+Inf", "-Inf", "NaN"):
        return value
    raise ValueError(f"{label} has an unsupported scalar token")


def _source_scalar(value: Any, label: str) -> float | str:
    if not isinstance(value, dict) or set(value) != ({"kind", "value"} if value.get("kind") == "finite" else {"kind"}):
        raise ValueError(f"{label} source scalar schema drift")
    kind = value["kind"]
    if kind == "finite":
        return _finite(value["value"], label)
    if kind == "inf":
        return "+Inf"
    if kind == "-inf":
        return "-Inf"
    if kind == "nan":
        return "NaN"
    raise ValueError(f"{label} source scalar kind drift")


def _scalar_surface(values: Any, label: str, source: bool) -> dict[str, float | str]:
    if not isinstance(values, dict) or (source and set(values) - set(SCALAR_METRICS)):
        raise ValueError(f"{label} scalar surface schema drift")
    return {
        name: _source_scalar(value, f"{label}.{name}") if source else _scalar(value, f"{label}.{name}")
        for name, value in sorted(values.items())
        if name in SCALAR_METRICS
    }


def _source_txle(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != TAP_KEYS:
        raise ValueError(f"{label} TXLE schema drift")
    for key, expected in TAP_METADATA.items():
        if value.get(key) != expected:
            raise ValueError(f"{label} TXLE {key} drift")
    shape = value["shape"]
    if (
        not isinstance(shape, list)
        or len(shape) != 2
        or any(isinstance(item, bool) or not isinstance(item, (int, float)) or int(item) != item or item < 0 for item in shape)
        or int(shape[0]) != 1
    ):
        raise ValueError(f"{label} TXLE must be a source row vector")
    values = value["column_major_values"]
    if not isinstance(values, list) or len(values) != int(shape[1]) or value["value_count"] != len(values):
        raise ValueError(f"{label} TXLE shape/value count drift")
    projected = [_finite(item, f"{label}.TXLE[{index}]") for index, item in enumerate(values)]
    receipt = value["raw_f64_sha256"]
    if not isinstance(receipt, str) or len(receipt) != 64 or receipt != _digest_f64(projected):
        raise ValueError(f"{label} TXLE raw digest drift")
    return {"shape": [1, len(projected)], "values": projected, "raw_f64_sha256": receipt}


def _rust_txle(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} selected TX taps missing")
    projected = [_finite(item, f"{label}[{index}]") for index, item in enumerate(value)]
    if not projected:
        raise ValueError(f"{label} selected TX taps empty")
    return {"shape": [1, len(projected)], "values": projected, "raw_f64_sha256": _digest_f64(projected)}


def project_matlab_summary(document: Any) -> list[dict[str, Any]]:
    """Project the bounded MATLAB harness output without accepting unknown wire shapes."""
    if not isinstance(document, dict) or document.get("schema_version") != 1 or document.get("diagnostic_only") is not True:
        raise ValueError("MATLAB TXLE checkpoint summary schema drift")
    cases = document.get("case_checkpoints")
    if not isinstance(cases, list) or document.get("case_count") != len(cases):
        raise ValueError("MATLAB TXLE checkpoint case count drift")
    projected = []
    for expected_index, item in enumerate(cases):
        if not isinstance(item, dict) or set(item) != {"case_index", "applicable", "final_scalar_metrics", "txle_taps"}:
            raise ValueError("MATLAB TXLE checkpoint case schema drift")
        if item["case_index"] != expected_index + 1 or item["applicable"] is not True:
            raise ValueError("MATLAB TXLE checkpoint applicability drift")
        projected.append({
            "case_index": expected_index,
            "final_scalar_metrics": _scalar_surface(item["final_scalar_metrics"], f"MATLAB case {expected_index}", True),
            "txle_taps": _source_txle(item["txle_taps"], f"MATLAB case {expected_index}"),
        })
    return projected


def project_rust_result(document: Any) -> list[dict[str, Any]]:
    """Project the existing private COM search diagnostics as a source-shaped row."""
    if not isinstance(document, dict) or not isinstance(document.get("cases"), list):
        raise ValueError("Rust result schema drift")
    projected = []
    for expected_index, item in enumerate(document["cases"]):
        if not isinstance(item, dict) or item.get("case_index") != expected_index:
            raise ValueError("Rust result case order drift")
        diagnostics = item.get("diagnostics")
        if not isinstance(diagnostics, dict):
            raise ValueError("Rust result diagnostics missing")
        branches = diagnostics.get("portable_branches")
        if not isinstance(branches, dict) or not isinstance(branches.get("search"), dict):
            raise ValueError("Rust result source-compatible search checkpoint missing")
        metrics = item.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError("Rust result metrics missing")
        projected.append({
            "case_index": expected_index,
            "final_scalar_metrics": _scalar_surface(metrics, f"Rust case {expected_index}", False),
            "txle_taps": _rust_txle(branches["search"].get("selected_tx_taps"), f"Rust case {expected_index}"),
        })
    return projected


def compare_txle_checkpoint_surface(matlab: Any, rust: Any) -> list[str]:
    """Return exact shape/digest and bounded scalar mismatches for one run pair."""
    source_cases = project_matlab_summary(matlab)
    rust_cases = project_rust_result(rust)
    if len(source_cases) != len(rust_cases):
        return [f"case count: MATLAB={len(source_cases)} Rust={len(rust_cases)}"]
    mismatches: list[str] = []
    for source, candidate in zip(source_cases, rust_cases, strict=True):
        index = source["case_index"]
        if source["txle_taps"] != candidate["txle_taps"]:
            mismatches.append(f"case {index}: TXLE checkpoint differs")
        source_scalars = source["final_scalar_metrics"]
        candidate_scalars = candidate["final_scalar_metrics"]
        if set(source_scalars) != set(candidate_scalars):
            mismatches.append(f"case {index}: scalar field set differs")
            continue
        for name in source_scalars:
            left, right = source_scalars[name], candidate_scalars[name]
            if isinstance(left, str) or isinstance(right, str):
                if left != right:
                    mismatches.append(f"case {index}: {name} special scalar differs")
            elif abs(left - right) > FINITE_TOLERANCE:
                mismatches.append(f"case {index}: {name} differs")
    return mismatches
