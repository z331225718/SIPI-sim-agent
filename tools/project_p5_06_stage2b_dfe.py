"""Strict, tool-only projection for the r4.80 DFE winner checkpoint.

Stage 2b observes the source-visible ``output_args.DFE_taps`` vector and the
same final scalar surface from a single MATLAB invocation.  It consumes the
already-published private Rust search diagnostic and does not widen a product
API or execute another numerical stage.
"""

from __future__ import annotations

import hashlib
import math
import re
import struct
from typing import Any

try:
    from .project_p5_06_stage2a_txle import FINITE_TOLERANCE, SCALAR_METRICS
except ImportError:
    from project_p5_06_stage2a_txle import FINITE_TOLERANCE, SCALAR_METRICS


DFE_LEGACY_KEYS = {
    "class", "shape", "value_count", "storage_order", "semantic_axis",
    "axis_origin_ui", "axis_step_ui", "unit", "encoding",
    "raw_f64_sha256", "column_major_values",
}
DFE_LOSSLESS_KEYS = DFE_LEGACY_KEYS | {"raw_f64_le_hex"}
DFE_METADATA = {
    "class": "double",
    "storage_order": "matlab_column_major",
    "semantic_axis": "postcursor_ui_offsets_from_winner_cursor",
    "axis_origin_ui": 1,
    "axis_step_ui": 1,
    "unit": "ratio",
    "encoding": "ieee754_f64_little_endian_column_major",
}
INAPPLICABLE_REASON = "source_DFE_taps_missing_due_to_ERL_ONLY"


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
    if isinstance(value, str):
        token = {"inf": "+Inf", "+inf": "+Inf", "-inf": "-Inf", "nan": "NaN"}.get(value.casefold())
        if token is not None:
            return token
    raise ValueError(f"{label} has an unsupported scalar token")


def _source_scalar(value: Any, label: str) -> float | str:
    if not isinstance(value, dict) or set(value) != ({"kind", "value"} if value.get("kind") == "finite" else {"kind"}):
        raise ValueError(f"{label} source scalar schema drift")
    if value["kind"] == "finite":
        return _finite(value["value"], label)
    token = {"inf": "+Inf", "-inf": "-Inf", "nan": "NaN"}.get(value["kind"])
    if token is not None:
        return token
    raise ValueError(f"{label} source scalar kind drift")


def _scalar_surface(values: Any, label: str, source: bool) -> dict[str, float | str]:
    if not isinstance(values, dict) or (source and set(values) - set(SCALAR_METRICS)):
        raise ValueError(f"{label} scalar surface schema drift")
    return {
        name: _source_scalar(value, f"{label}.{name}") if source else _scalar(value, f"{label}.{name}")
        for name, value in sorted(values.items()) if name in SCALAR_METRICS
    }


def _source_dfe(value: Any, label: str, require_lossless: bool) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) not in (DFE_LEGACY_KEYS, DFE_LOSSLESS_KEYS):
        raise ValueError(f"{label} DFE schema drift")
    has_lossless = set(value) == DFE_LOSSLESS_KEYS
    if require_lossless and not has_lossless:
        raise ValueError(f"{label} DFE lossless raw bytes missing")
    for key, expected in DFE_METADATA.items():
        if value.get(key) != expected:
            raise ValueError(f"{label} DFE {key} drift")
    shape = value["shape"]
    if (
        not isinstance(shape, list) or len(shape) != 2
        or any(isinstance(item, bool) or not isinstance(item, (int, float)) or int(item) != item or item < 0 for item in shape)
    ):
        raise ValueError(f"{label} DFE shape drift")
    values = value["column_major_values"]
    count = int(shape[0]) * int(shape[1])
    if not isinstance(values, list) or len(values) != count or value["value_count"] != count:
        raise ValueError(f"{label} DFE shape/value count drift")
    receipt = value["raw_f64_sha256"]
    if not isinstance(receipt, str) or re.fullmatch(r"[0-9a-f]{64}", receipt) is None:
        raise ValueError(f"{label} DFE raw digest drift")
    if has_lossless:
        raw_hex = value["raw_f64_le_hex"]
        if not isinstance(raw_hex, str) or re.fullmatch(rf"[0-9a-f]{{{count * 16}}}", raw_hex) is None:
            raise ValueError(f"{label} DFE lossless raw bytes drift")
        raw_bytes = bytes.fromhex(raw_hex)
        projected = list(struct.unpack(f"<{count}d", raw_bytes)) if count else []
        if any(not math.isfinite(item) for item in projected) or hashlib.sha256(raw_bytes).hexdigest() != receipt:
            raise ValueError(f"{label} DFE raw digest drift")
    else:
        projected = [_finite(item, f"{label}.DFE[{index}]") for index, item in enumerate(values)]
        if receipt != _digest_f64(projected):
            raise ValueError(f"{label} DFE raw digest drift")
    return {"shape": [int(shape[0]), int(shape[1])], "values": projected, "raw_f64_sha256": receipt}


def _rust_dfe(value: Any, source_shape: list[int], label: str) -> dict[str, Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} selected DFE taps missing")
    projected = [_finite(item, f"{label}[{index}]") for index, item in enumerate(value)]
    if source_shape[0] * source_shape[1] != len(projected):
        raise ValueError(f"{label} DFE source shape/count drift")
    return {"shape": source_shape, "values": projected, "raw_f64_sha256": _digest_f64(projected)}


def project_matlab_summary(document: Any, *, require_lossless: bool = False) -> list[dict[str, Any]]:
    if not isinstance(document, dict) or document.get("schema_version") != 1 or document.get("diagnostic_only") is not True:
        raise ValueError("MATLAB DFE checkpoint summary schema drift")
    cases = document.get("case_checkpoints")
    if not isinstance(cases, list) or document.get("case_count") != len(cases):
        raise ValueError("MATLAB DFE checkpoint case count drift")
    projected = []
    for expected_index, item in enumerate(cases):
        if not isinstance(item, dict) or set(item) != {"case_index", "applicable", "final_scalar_metrics", "dfe_taps"}:
            raise ValueError("MATLAB DFE checkpoint case schema drift")
        if item["case_index"] != expected_index + 1 or not isinstance(item["applicable"], bool):
            raise ValueError("MATLAB DFE checkpoint applicability drift")
        if item["applicable"] is False:
            if item["dfe_taps"] != {"reason": INAPPLICABLE_REASON}:
                raise ValueError("MATLAB inapplicable DFE reason drift")
            continue
        projected.append({
            "case_index": len(projected),
            "final_scalar_metrics": _scalar_surface(item["final_scalar_metrics"], f"MATLAB case {expected_index}", True),
            "dfe_taps": _source_dfe(item["dfe_taps"], f"MATLAB case {expected_index}", require_lossless),
        })
    return projected


def project_rust_result(document: Any, source_cases: Any) -> list[dict[str, Any]]:
    """Project Rust diagnostics against source-native DFE shapes only."""
    source_cases = validate_projected_dfe_cases(source_cases, "MATLAB")
    raw_cases = project_rust_result_raw(document)
    return align_raw_rust_dfe_cases(raw_cases, source_cases)


def align_raw_rust_dfe_cases(raw_cases: Any, source_cases: Any) -> list[dict[str, Any]]:
    """Apply source-native shapes to an already validated raw Rust record."""
    source_cases = validate_projected_dfe_cases(source_cases, "MATLAB")
    if not isinstance(raw_cases, list) or len(raw_cases) != len(source_cases):
        raise ValueError("Rust DFE eligible case count drift")
    validated_raw = []
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, dict) or set(raw) != {"case_index", "final_scalar_metrics", "values", "raw_f64_sha256"} or raw["case_index"] != index:
            raise ValueError("Rust raw DFE case schema drift")
        values = [_finite(value, f"Rust raw case {index}.DFE[{tap_index}]") for tap_index, value in enumerate(raw["values"])] if isinstance(raw["values"], list) else None
        if values is None or raw["raw_f64_sha256"] != _digest_f64(values):
            raise ValueError("Rust raw DFE receipt drift")
        validated_raw.append({
            "case_index": index,
            "final_scalar_metrics": _scalar_surface(raw["final_scalar_metrics"], f"Rust raw case {index}", False),
            "values": values,
        })
    return [
        {
            "case_index": index,
            "final_scalar_metrics": raw["final_scalar_metrics"],
            "dfe_taps": _rust_dfe(raw["values"], source["dfe_taps"]["shape"], f"Rust case {index}"),
        }
        for index, (raw, source) in enumerate(zip(validated_raw, source_cases, strict=True))
    ]


def project_rust_result_raw(document: Any) -> list[dict[str, Any]]:
    """Project the source-independent Rust DFE payload for a replay record.

    Rust diagnostics are a one-dimensional typed sequence; only the MATLAB
    source invocation can establish its native matrix shape.  Keeping this
    raw projection separate lets independently produced reports be joined by
    the aggregate without assigning an oracle shape during the Rust run.
    """
    if not isinstance(document, dict) or not isinstance(document.get("cases"), list):
        raise ValueError("Rust result schema drift")
    projected: list[dict[str, Any]] = []
    for expected_index, item in enumerate(document["cases"]):
        if not isinstance(item, dict) or item.get("case_index") != expected_index:
            raise ValueError("Rust result case order drift")
        diagnostics = item.get("diagnostics")
        metrics = item.get("metrics")
        if not isinstance(diagnostics, dict) or not isinstance(metrics, dict):
            raise ValueError("Rust result diagnostics or metrics missing")
        branches = diagnostics.get("portable_branches")
        if not isinstance(branches, dict) or not isinstance(branches.get("search"), dict):
            if set(metrics) != {"ERL"} or not isinstance(diagnostics.get("normal_erl"), dict):
                raise ValueError("Rust result source-compatible DFE checkpoint missing")
            continue
        search = branches["search"]
        values = search.get("dfe_taps")
        if not isinstance(values, list):
            raise ValueError(f"Rust case {expected_index} selected DFE taps missing")
        values = [_finite(value, f"Rust case {expected_index}.DFE[{index}]") for index, value in enumerate(values)]
        projected.append({
            "case_index": len(projected),
            "final_scalar_metrics": _scalar_surface(metrics, f"Rust case {expected_index}", False),
            "values": values,
            "raw_f64_sha256": _digest_f64(values),
        })
    return projected


def validate_projected_dfe_cases(cases: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(cases, list):
        raise ValueError(f"{label} projected DFE cases must be a list")
    validated = []
    for expected_index, case in enumerate(cases):
        if not isinstance(case, dict) or set(case) != {"case_index", "final_scalar_metrics", "dfe_taps"} or case["case_index"] != expected_index:
            raise ValueError(f"{label} projected DFE case schema drift")
        taps = case["dfe_taps"]
        if not isinstance(taps, dict) or set(taps) != {"shape", "values", "raw_f64_sha256"}:
            raise ValueError(f"{label} projected DFE schema drift")
        shape, values = taps["shape"], taps["values"]
        if not isinstance(shape, list) or len(shape) != 2 or not isinstance(values, list) or any(not isinstance(item, int) or item < 0 for item in shape):
            raise ValueError(f"{label} projected DFE shape drift")
        values = [_finite(value, f"{label}.DFE[{index}]") for index, value in enumerate(values)]
        if shape[0] * shape[1] != len(values) or taps.get("raw_f64_sha256") != _digest_f64(values):
            raise ValueError(f"{label} projected DFE digest drift")
        validated.append({"case_index": expected_index, "final_scalar_metrics": _scalar_surface(case["final_scalar_metrics"], f"{label} projected scalars", False), "dfe_taps": {"shape": shape, "values": values, "raw_f64_sha256": _digest_f64(values)}})
    return validated


def dfe_raw_receipts_equal(source_cases: Any, rust_cases: Any) -> bool:
    """Report raw receipt identity without mistaking it for numeric parity."""
    source_cases = validate_projected_dfe_cases(source_cases, "MATLAB")
    rust_cases = validate_projected_dfe_cases(rust_cases, "Rust")
    return len(source_cases) == len(rust_cases) and all(
        source["dfe_taps"]["raw_f64_sha256"] == candidate["dfe_taps"]["raw_f64_sha256"]
        for source, candidate in zip(source_cases, rust_cases, strict=True)
    )


def _same_signed_zero(left: float, right: float) -> bool:
    return struct.pack("<d", left) == struct.pack("<d", right)


def compare_projected_dfe_cases(source_cases: Any, rust_cases: Any, finite_tolerance: float = FINITE_TOLERANCE) -> list[str]:
    if not math.isfinite(finite_tolerance) or finite_tolerance < 0:
        raise ValueError("finite tolerance must be nonnegative and finite")
    source_cases = validate_projected_dfe_cases(source_cases, "MATLAB")
    rust_cases = validate_projected_dfe_cases(rust_cases, "Rust")
    if len(source_cases) != len(rust_cases):
        return [f"case count: MATLAB={len(source_cases)} Rust={len(rust_cases)}"]
    mismatches = []
    for source, candidate in zip(source_cases, rust_cases, strict=True):
        index = source["case_index"]
        source_taps = source["dfe_taps"]
        candidate_taps = candidate["dfe_taps"]
        if source_taps["shape"] != candidate_taps["shape"]:
            mismatches.append(f"case {index}: DFE shape differs")
        else:
            for tap_index, (left, right) in enumerate(zip(source_taps["values"], candidate_taps["values"], strict=True)):
                if left == 0.0 and right == 0.0 and not _same_signed_zero(left, right):
                    mismatches.append(f"case {index}: DFE[{tap_index}] signed zero differs")
                elif abs(left - right) > finite_tolerance:
                    mismatches.append(f"case {index}: DFE[{tap_index}] differs")
        if set(source["final_scalar_metrics"]) != set(candidate["final_scalar_metrics"]):
            mismatches.append(f"case {index}: scalar field set differs")
            continue
        for name, left in source["final_scalar_metrics"].items():
            right = candidate["final_scalar_metrics"][name]
            if isinstance(left, str) or isinstance(right, str):
                if left != right:
                    mismatches.append(f"case {index}: {name} special scalar differs")
            elif abs(left - right) > finite_tolerance:
                mismatches.append(f"case {index}: {name} differs")
    return mismatches
