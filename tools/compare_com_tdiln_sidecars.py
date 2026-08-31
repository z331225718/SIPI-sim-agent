"""Strict, diagnostic-only same-index comparison for TDILN f64 sidecars."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any

SCHEMA = "sipi.com.tdiln-array-sidecar-comparison.v1"
VECTORS = (
    "time_s",
    "iln_pulse",
    "reference_pulse",
    "fitted_pulse",
    "pdf_axis",
    "pdf_probability",
)
EXACT_VECTORS = frozenset({"time_s"})
ATOL = 5.0e-12
RTOL = 1.0e-9


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _shape(value: Any, name: str) -> int:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], int) and value[0] > 0:
        return value[0]
    raise ValueError(f"{name} must be one positive one-dimensional shape")


def _load_manifest(root: Path, case_index: int, role: str) -> tuple[Path, dict[str, Any]]:
    case_root = root / f"case-{case_index}"
    manifest = _object(json.loads((case_root / "manifest.json").read_text(encoding="utf-8")), f"{role} manifest")
    if manifest.get("schema") != "sipi.com.tdiln-array-sidecar.v1" or manifest.get("diagnostic_only") is not True:
        raise ValueError(f"{role} manifest schema")
    if manifest.get("case_index") != case_index:
        raise ValueError(f"{role} manifest case index")
    if not isinstance(manifest.get("tdiln_applicable"), bool):
        raise ValueError(f"{role} applicability")
    return case_root, manifest


def _read_vector(case_root: Path, entry: Any, name: str, require_hash: bool) -> tuple[bytes, tuple[float, ...]]:
    entry = _object(entry, name)
    if entry.get("dtype") != "f64le":
        raise ValueError(f"{name} dtype")
    shape = _shape(entry.get("shape"), f"{name}.shape")
    filename = entry.get("file")
    if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".f64le"):
        raise ValueError(f"{name} file")
    raw = (case_root / filename).read_bytes()
    if entry.get("bytes") != len(raw) or len(raw) != shape * 8:
        raise ValueError(f"{name} byte count")
    if require_hash:
        actual_hash = hashlib.sha256(raw).hexdigest()
        if entry.get("sha256") != actual_hash:
            raise ValueError(f"{name} hash")
    values = struct.unpack(f"<{shape}d", raw)
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{name} non-finite")
    return raw, values


def _compare_vector(name: str, source_raw: bytes, source: tuple[float, ...], candidate_raw: bytes, candidate: tuple[float, ...], atol: float, rtol: float) -> dict[str, Any]:
    if len(source) != len(candidate):
        return {"name": name, "passed": False, "reason": "shape_mismatch"}
    if name in EXACT_VECTORS:
        return {"name": name, "length": len(source), "exact_f64le": True, "passed": source_raw == candidate_raw}
    max_abs = -1.0
    max_index = 0
    squared_error = 0.0
    squared_source = 0.0
    passed = True
    for index, (reference, observed) in enumerate(zip(source, candidate, strict=True)):
        delta = abs(reference - observed)
        if delta > max_abs:
            max_abs = delta
            max_index = index
        squared_error += delta * delta
        squared_source += reference * reference
        if delta > atol + rtol * abs(reference):
            passed = False
    nrmse = math.sqrt(squared_error) / max(math.sqrt(squared_source), float.fromhex("0x1.0p-1022"))
    return {"name": name, "length": len(source), "max_abs": max_abs, "max_abs_index": max_index, "nrmse": nrmse, "atol": atol, "rtol": rtol, "passed": passed}


def compare_sidecars(matlab_root: Path, rust_root: Path, case_count: int, *, atol: float = ATOL, rtol: float = RTOL) -> dict[str, Any]:
    if case_count <= 0 or not math.isfinite(atol) or not math.isfinite(rtol) or atol < 0.0 or rtol < 0.0:
        raise ValueError("invalid comparison bounds")
    cases: list[dict[str, Any]] = []
    passed = True
    for case_index in range(case_count):
        source_case = matlab_root / f"case-{case_index}"
        source_manifest_path = source_case / "manifest.json"
        rust_case, rust_manifest = _load_manifest(rust_root, case_index, "Rust")
        if not source_manifest_path.is_file():
            inapplicable = rust_manifest["tdiln_applicable"] is False
            cases.append({"case_index": case_index, "tdiln_applicable": False, "rust_tdiln_absent": inapplicable, "passed": inapplicable})
            passed = passed and inapplicable
            continue
        source_case, source_manifest = _load_manifest(matlab_root, case_index, "MATLAB")
        applicable = source_manifest["tdiln_applicable"]
        if applicable is False:
            match = rust_manifest["tdiln_applicable"] is False
            cases.append({"case_index": case_index, "tdiln_applicable": False, "rust_tdiln_absent": match, "passed": match})
            passed = passed and match
            continue
        if rust_manifest["tdiln_applicable"] is not True:
            cases.append({"case_index": case_index, "tdiln_applicable": True, "reason": "rust_missing_tdiln", "passed": False})
            passed = False
            continue
        source_vectors = _object(source_manifest.get("vectors"), "MATLAB vectors")
        rust_vectors = _object(rust_manifest.get("vectors"), "Rust vectors")
        vectors = []
        for name in VECTORS:
            source_raw, source_values = _read_vector(source_case, source_vectors.get(name), f"MATLAB {name}", False)
            rust_raw, rust_values = _read_vector(rust_case, rust_vectors.get(name), f"Rust {name}", True)
            vectors.append(_compare_vector(name, source_raw, source_values, rust_raw, rust_values, atol, rtol))
        case_passed = all(vector["passed"] for vector in vectors)
        cases.append({"case_index": case_index, "tdiln_applicable": True, "vectors": vectors, "passed": case_passed})
        passed = passed and case_passed
    return {"schema": SCHEMA, "diagnostic_only": True, "non_claims": ["not_public_result_wire", "not_full_result_graph", "not_complete_warning_catalog", "not_channel_s_parameter_fit"], "status": "passed_diagnostic" if passed else "blocked", "case_count": case_count, "atol": atol, "rtol": rtol, "cases": cases}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matlab-root", type=Path, required=True)
    parser.add_argument("--rust-root", type=Path, required=True)
    parser.add_argument("--case-count", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare_sidecars(args.matlab_root, args.rust_root, args.case_count)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}))
    if report["status"] != "passed_diagnostic":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
