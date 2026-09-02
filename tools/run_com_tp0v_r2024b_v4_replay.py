"""Run one immutable TP0V v4 replay for either Rust or MATLAB.

This is an acceptance-preparation runner, not a formal-record writer.  It
materializes the caller supplied archives, uses the public ``sipi com run``
route for Rust, and starts the explicit R2024b MATLAB Engine for the oracle.
Reports are intentionally written outside the repository.  No vector is
aligned, interpolated, resampled, truncated, or delay-corrected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import struct
import sys
import time
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
V3_TOOL = Path(__file__).with_name("run_com_tp0v_r2024b_v3_diagnostic.py")
if str(V3_TOOL.parent) not in sys.path:
    sys.path.insert(0, str(V3_TOOL.parent))

from run_com_tp0v_r2024b_v3_diagnostic import (  # noqa: E402
    _channel_inputs,
    _engine_source,
    bridge_comparison,
    explicit_file,
    inventory,
    matlab_cases,
    matlab_receipt,
    prepare_engine,
    root_command,
    rust_cases,
    run_command,
    safe_materialize,
    sha256_bytes,
    sha256_file,
    tool_receipt,
)
TRACE_TOOL = Path(__file__).with_name("run_com_normal_erl_trace_diagnostic.py")
from run_com_normal_erl_trace_diagnostic import (  # noqa: E402
    SOURCE_FILE as TRACE_SOURCE_FILE,
    SOURCE_SHA256 as TRACE_SOURCE_SHA256,
    instrument_matlab_source,
)


SCHEMA = "sipi.com.tp0v-r2024b-v4-replay.v1"
MATLAB_RELEASE = "R2024b"
RUN_IDS = {"matlab-01", "matlab-02", "rust-01", "rust-02"}
NONCE_RE = re.compile(r"^[0-9a-f]{64}$")
CASE_INDICES = (0,)
SELECTED_CASE_INDEX = 0
PACKAGE_TESTCASE_INDEX = 0
SCALAR_NAMES = (
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
VECTOR_NAMES = ("time_s", "impedance_ohm", "ptdr", "gated")
VECTOR_TOLERANCE = {
    "time_s": {"absolute": 5.0e-24, "relative": 0.0, "unit": "s"},
    "impedance_ohm": {"absolute": 2.0e-12, "relative": 2.0e-14, "unit": "ohm"},
    "ptdr": {"absolute": 5.0e-17, "relative": 2.0e-14, "unit": "linear"},
    "gated": {"absolute": 5.0e-17, "relative": 2.0e-14, "unit": "linear"},
}
PROHIBITED_TRANSFORMS = (
    "alignment",
    "resampling",
    "interpolation",
    "truncation",
    "delay_correction",
)
UPSTREAM_RECEIPT = {
    "commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
    "tree": "7094ab6e84989b218730c52432c70da10261f8ea",
    "archive_sha256": "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf",
    "archive_bytes": 43_694_080,
    "workbook": {
        "path": "matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA _TP0V_08_17_2022.xlsx",
        "bytes": 67_151,
        "sha256": "54562fa2bbe856f1fb6e96b7c1c873d2b399555b1fb38e50cd6f4ad3ddc69f0a",
    },
    "assets": (
        {"role": "THRU", "path": "fixtures/synthetic/thru_10db_at_26p56ghz.s4p", "bytes": 6_393_177, "sha256": "fcbcce086dbae6bbb9a1f8ca5df775073ebb6303f80a9f062caf1f2ab5607361"},
        {"role": "FEXT", "path": "fixtures/synthetic/fext_m40db_at_26p56ghz.s4p", "bytes": 6_393_140, "sha256": "cc5968bacd5bd40d6ccd7db4927dbb1dd3f20d82f4d3ad5a3193ad86e0e9ca04"},
        {"role": "NEXT", "path": "fixtures/synthetic/next_m40db_at_26p56ghz.s4p", "bytes": 6_392_860, "sha256": "882819542f43b8fb5f174c7e984b418ceb0f56e068654c9be362a84547b93e65"},
    ),
}
CANDIDATE_RECEIPT = {
    "commit": "b255967c91898f720a16e5029af09521f94fa7df",
    "tree": "849fc6c1ba682f3302bb4eb1c9c701e8aec6e53e",
    "archive_sha256": "f5a096653d89b79989834fb253438b0a0d63e722638e14ad1e3cd528e61d1930",
    "archive_bytes": 62_033_920,
}
CANDIDATE_GATE_PARENT = {
    "commit": "90bf1a92f699a61511a0bf9b34f3f7038f30df8b",
    "tree": "849fc6c1ba682f3302bb4eb1c9c701e8aec6e53e",
}
SELECTED_PORT = 1
CASE_TO_PORT = {SELECTED_CASE_INDEX: SELECTED_PORT}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _manifest_projection() -> dict[str, Any]:
    return {"candidate": CANDIDATE_RECEIPT, "upstream": UPSTREAM_RECEIPT}


def _derived_nonce(nonce: str, repeat_index: int) -> str:
    return hashlib.sha256(f"{nonce}:repeat:{repeat_index}".encode("ascii")).hexdigest()


def _decode_metric(value: Any) -> Any:
    if isinstance(value, dict) and value.get("kind") == "finite" and set(value) == {"kind", "value"}:
        return value["value"]
    if isinstance(value, dict) and value.get("kind") in {"inf", "-inf", "nan"}:
        return {"inf": "+Inf", "-inf": "-Inf", "nan": "NaN"}[value["kind"]]
    return value


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _vector_records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        result = []
        for name, samples in value.items():
            result.append({"name": str(name), "values": samples})
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                raise RuntimeError("vector item must contain a name")
            if "values" not in item:
                raise RuntimeError("vector item must contain values")
            result.append({"name": item["name"], "values": item["values"]})
        return result
    raise RuntimeError("vectors must be an object or array")


def _extract_case_vectors(item: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("vectors", "waveforms", "vector_payload"):
        if key in item:
            return _vector_records(item[key])
    return []


def _payload_cases(payload: dict[str, Any], engine: str) -> list[dict[str, Any]]:
    values = payload.get("cases") if engine == "rust" else payload.get("case_metrics")
    if not isinstance(values, list):
        raise RuntimeError("engine payload cases is not an array")
    metrics = rust_cases(payload) if engine == "rust" else matlab_cases(payload)
    result = []
    top_vectors = payload.get("vectors")
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise RuntimeError("engine case is not an object")
        source_case_index = item.get("case_index")
        expected_source_case_index = index + 1 if engine == "matlab" else index
        require(source_case_index == expected_source_case_index, "engine case order/index drift")
        vectors = _extract_case_vectors(item)
        if not vectors and isinstance(top_vectors, list) and index < len(top_vectors):
            vectors = _vector_records(top_vectors[index])
        result.append({"case_index": index, "metrics": metrics[index], "vectors": vectors})
    return result


def _json_digest(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def _exact_value(value: Any) -> Any:
    if isinstance(value, float):
        return ("float", value.hex())
    if isinstance(value, int) and not isinstance(value, bool):
        return ("int", value)
    if isinstance(value, list):
        return tuple(_exact_value(item) for item in value)
    if isinstance(value, dict):
        return tuple((key, _exact_value(value[key])) for key in sorted(value))
    return (type(value).__name__, value)


def exact_repeat(first: list[dict[str, Any]], second: list[dict[str, Any]]) -> bool:
    return _exact_value(first) == _exact_value(second)


def repeat_payload_exact(repeats: list[dict[str, Any]], engine: str) -> bool:
    if len(repeats) != 2 or not exact_repeat(repeats[0].get("cases", []), repeats[1].get("cases", [])):
        return False
    if engine == "matlab":
        return _exact_value(repeats[0].get("parameter_bridge")) == _exact_value(repeats[1].get("parameter_bridge"))
    return True


def _validate_vector(values: Any, name: str) -> tuple[bool, str | None]:
    if not isinstance(values, list) or not values:
        return False, "vector_not_nonempty_1d_array"
    if not all(_finite(value) for value in values):
        return False, "vector_nonfinite_sample"
    if name == "time_s" and any(values[index] >= values[index + 1] for index in range(len(values) - 1)):
        return False, "time_not_strictly_monotonic"
    return True, None


def compare_vectors(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare ordered one-dimensional vectors without changing their samples."""
    left_by_name = [item.get("name") for item in left]
    right_by_name = [item.get("name") for item in right]
    result: dict[str, Any] = {"passed": True, "vectors": [], "policy": "ordered_elementwise_no_transform"}
    if left_by_name != list(VECTOR_NAMES) or right_by_name != list(VECTOR_NAMES):
        result["passed"] = False
        result["reason"] = "vector_name_order_drift"
        result["matlab_names"] = left_by_name
        result["rust_names"] = right_by_name
        return result
    for expected, matlab_vector, rust_vector in zip(VECTOR_NAMES, left, right):
        matlab_values = matlab_vector.get("values")
        rust_values = rust_vector.get("values")
        valid_matlab, matlab_reason = _validate_vector(matlab_values, expected)
        valid_rust, rust_reason = _validate_vector(rust_values, expected)
        entry: dict[str, Any] = {"name": expected, "passed": valid_matlab and valid_rust}
        if not valid_matlab or not valid_rust:
            entry["reason"] = matlab_reason or rust_reason
            result["passed"] = False
            result["vectors"].append(entry)
            continue
        if len(matlab_values) != len(rust_values):
            entry.update({"passed": False, "reason": "vector_shape_or_count_drift", "matlab_count": len(matlab_values), "rust_count": len(rust_values)})
            result["passed"] = False
            result["vectors"].append(entry)
            continue
        tolerance = VECTOR_TOLERANCE[expected]
        differences = [abs(float(a) - float(b)) for a, b in zip(matlab_values, rust_values)]
        limits = [tolerance["absolute"] + tolerance["relative"] * abs(float(a)) for a in matlab_values]
        sample_pass = all(difference <= limit for difference, limit in zip(differences, limits))
        entry.update({
            "passed": sample_pass,
            "count": len(matlab_values),
            "shape": [len(matlab_values)],
            "first_sample_equal": differences[0] <= limits[0],
            "max_absolute_difference": max(differences),
            "max_allowed_difference": max(limits),
            "absolute_tolerance": tolerance["absolute"],
            "relative_tolerance": tolerance["relative"],
            "unit": tolerance["unit"],
        })
        result["passed"] = result["passed"] and sample_pass
        result["vectors"].append(entry)
    return result


def compare_scalar(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> dict[str, Any]:
    records = []
    passed = len(left) == len(right)
    for index, (matlab, rust) in enumerate(zip(left, right)):
        values = []
        case_passed = True
        for name in SCALAR_NAMES:
            if name not in matlab or name not in rust:
                values.append({"name": name, "passed": False, "reason": "missing_key"})
                case_passed = False
                continue
            first, second = _decode_metric(matlab[name]), _decode_metric(rust[name])
            if _finite(first) and _finite(second):
                difference = abs(float(first) - float(second))
                equal = difference <= 1.0e-9
            else:
                difference = None
                equal = type(first) is type(second) and first == second and first != "NaN"
            record: dict[str, Any] = {"name": name, "passed": equal, "matlab": first, "rust": second}
            if difference is not None:
                record["absolute_difference"] = difference
            values.append(record)
            case_passed = case_passed and equal
        records.append({"case_index": index, "passed": case_passed, "values": values})
        passed = passed and case_passed
    if len(left) != len(right):
        passed = False
    return {"passed": passed, "cases": records, "metrics": list(SCALAR_NAMES), "finite_absolute_tolerance": 1.0e-9, "policy": "scalar_elementwise_no_transform"}


def _report_case_payload(payload: dict[str, Any], engine: str) -> list[dict[str, Any]]:
    cases = _payload_cases(payload, engine)
    for case in cases:
        names = [vector.get("name") for vector in case["vectors"]]
        case["vector_payload_present"] = names == list(VECTOR_NAMES)
    return cases


def _select_case(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the traced package case; port 2 is a physical port, not case 1."""
    selected = [case for case in cases if case.get("case_index") == SELECTED_CASE_INDEX]
    require(len(selected) == 1, "selected package case is missing or duplicated")
    return selected


def _selected_sidecar_vectors(sidecar_ports: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Bind the one traced package case to its physical port without copying."""
    selected_port = CASE_TO_PORT[SELECTED_CASE_INDEX]
    selected_vectors = sidecar_ports.get(selected_port)
    require(selected_vectors is not None, "selected package-case port is unavailable")
    return selected_vectors


def _safe_sidecar_file(root: Path, relative: Any) -> Path:
    require(isinstance(relative, str) and relative, "sidecar path syntax")
    normalized = relative.replace("\\", "/")
    path = PurePosixPath(normalized)
    require(not PureWindowsPath(normalized).is_absolute() and not path.is_absolute() and PureWindowsPath(normalized).drive == "" and ".." not in path.parts, "sidecar path escape")
    resolved = (root / path).resolve()
    base = root.resolve()
    require(base == resolved or base in resolved.parents, "sidecar path escapes root")
    require(resolved.is_file() and not resolved.is_symlink(), "sidecar vector file missing or linked")
    return resolved


def _read_f64le_sidecar(root: Path, *, schema: str, ports_required: bool = True) -> dict[int, list[dict[str, Any]]]:
    """Read the private normal-ERL sidecar and verify every raw f64 receipt."""
    manifest_path = root / "manifest.json"
    require(manifest_path.is_file(), "normal ERL sidecar manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == schema and manifest.get("diagnostic_only") is True, "normal ERL sidecar schema")
    if schema == "sipi.com.normal-erl-array-trace.v1":
        require(manifest.get("package_testcase_index") == PACKAGE_TESTCASE_INDEX, "normal ERL sidecar package testcase")
    ports = manifest.get("ports")
    require(isinstance(ports, list) and len(ports) == 2, "normal ERL sidecar port count")
    result: dict[int, list[dict[str, Any]]] = {}
    for expected_port, entry in enumerate(ports, start=1):
        require(isinstance(entry, dict) and entry.get("port") == expected_port, "normal ERL sidecar port order")
        if entry.get("available") is False:
            require(not ports_required, "normal ERL sidecar unavailable port")
            continue
        vectors = entry.get("vectors")
        require(isinstance(vectors, dict) and list(vectors) == list(VECTOR_NAMES), "normal ERL sidecar vector order")
        projected = []
        for name in VECTOR_NAMES:
            receipt = vectors[name]
            require(isinstance(receipt, dict) and receipt.get("dtype") == "f64le", "normal ERL sidecar dtype")
            shape = receipt.get("shape")
            count = int(shape[0]) if isinstance(shape, list) and len(shape) == 1 and isinstance(shape[0], int) and not isinstance(shape[0], bool) else int(shape) if isinstance(shape, int) and not isinstance(shape, bool) else -1
            require(count > 0 and receipt.get("bytes") == count * 8, "normal ERL sidecar shape/bytes")
            raw_path = _safe_sidecar_file(root, receipt.get("file"))
            raw = raw_path.read_bytes()
            require(len(raw) == count * 8 and hashlib.sha256(raw).hexdigest() == receipt.get("sha256"), "normal ERL sidecar hash/length")
            values = [item[0] for item in struct.iter_unpack("<d", raw)]
            require(len(values) == count and all(_finite(value) for value in values), "normal ERL sidecar finite f64")
            if name == "time_s":
                require(all(values[index] < values[index + 1] for index in range(len(values) - 1)), "normal ERL sidecar time order")
            projected.append({"name": name, "values": values, "dtype": "f64le", "shape": [count], "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        result[expected_port] = projected
    return result


def _enrich_trace_hash_receipts(root: Path) -> None:
    """Add hashes to the legacy MATLAB sink receipt without changing samples."""
    manifest_path = root / "manifest.json"
    require(manifest_path.is_file(), "MATLAB trace manifest missing before receipt enrichment")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == "sipi.com.normal-erl-array-trace.v1" and manifest.get("diagnostic_only") is True, "MATLAB trace manifest schema before enrichment")
    ports = manifest.get("ports")
    require(isinstance(ports, list) and len(ports) == 2, "MATLAB trace port count before enrichment")
    for expected_port, entry in enumerate(ports, start=1):
        require(isinstance(entry, dict) and entry.get("port") == expected_port, "MATLAB trace port order before enrichment")
        if entry.get("available") is False:
            continue
        vectors = entry.get("vectors")
        require(isinstance(vectors, dict) and list(vectors) == list(VECTOR_NAMES), "MATLAB trace vector order before enrichment")
        for name in VECTOR_NAMES:
            receipt = vectors[name]
            require(isinstance(receipt, dict), "MATLAB trace vector receipt before enrichment")
            raw_path = _safe_sidecar_file(root, receipt.get("file"))
            raw = raw_path.read_bytes()
            shape = receipt.get("shape")
            count = int(shape[0]) if isinstance(shape, list) and len(shape) == 1 and isinstance(shape[0], int) and not isinstance(shape[0], bool) else int(shape) if isinstance(shape, int) and not isinstance(shape, bool) else -1
            require(count > 0 and len(raw) == count * 8 and receipt.get("bytes") == len(raw), "MATLAB trace vector length before enrichment")
            receipt["sha256"] = hashlib.sha256(raw).hexdigest()
    manifest["receipt_enrichment"] = "v4_runner_sha256_over_unchanged_raw_f64le"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")


def _trace_summary(summary_path: Path) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    require(summary.get("schema") == "sipi.com.normal-erl-trace-run.v1", "normal ERL trace summary schema")
    require(summary.get("matlab_release") == "2024b" and "R2024b" in str(summary.get("matlab_version", "")), "normal ERL trace MATLAB release")
    require(isinstance(summary.get("cases"), list) and summary["cases"], "normal ERL trace cases")
    return summary


def _trace_semantics_equal(original: dict[str, Any], instrumented: dict[str, Any]) -> bool:
    return original.get("cases") == instrumented.get("cases") and original.get("last_warning") == instrumented.get("last_warning")


def _error_record(completed: Any, elapsed: float, label: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "label": label,
        "exit_code": completed.returncode,
        "wall_clock_s": elapsed,
        "stdout_sha256": sha256_bytes(completed.stdout or b""),
        "stderr_sha256": sha256_bytes(completed.stderr or b""),
    }


def _run_rust_once(binary: Path, source: Path, root: Path, timeout: int) -> dict[str, Any]:
    config = source / UPSTREAM_RECEIPT["workbook"]["path"]
    thru, fext, next_channel, _ = _channel_inputs(source, _manifest_projection())
    semantic_output = root / "rust-semantic-output"
    diagnostic_output = root / "rust-diagnostic-output"
    sidecar = root / "rust-normal-erl-trace"
    semantic_environment = os.environ.copy()
    semantic_environment.pop("SIPI_COM_NORMAL_ERL_DIAGNOSTIC_SIDECAR_DIR", None)
    semantic_completed, semantic_elapsed = run_command(root_command(binary, config, thru, fext, next_channel, semantic_output), source, timeout, semantic_environment)
    diagnostic_environment = os.environ.copy()
    diagnostic_environment["SIPI_COM_NORMAL_ERL_DIAGNOSTIC_SIDECAR_DIR"] = str(sidecar)
    diagnostic_completed, diagnostic_elapsed = run_command(root_command(binary, config, thru, fext, next_channel, diagnostic_output), source, timeout, diagnostic_environment)
    result: dict[str, Any] = {
        "engine": "rust",
        "semantic_wall_clock_s": semantic_elapsed,
        "diagnostic_wall_clock_s": diagnostic_elapsed,
        "wall_clock_s": semantic_elapsed,
        "route": "public_root_sipi_com_run",
    }
    semantic_path = semantic_output / "result.json"
    diagnostic_path = diagnostic_output / "result.json"
    if semantic_completed.returncode != 0 or not semantic_path.is_file():
        result.update(_error_record(semantic_completed, semantic_elapsed, "rust_root_route_failed"))
        return result
    if diagnostic_completed.returncode != 0 or not diagnostic_path.is_file():
        result.update(_error_record(diagnostic_completed, diagnostic_elapsed, "rust_diagnostic_route_failed"))
        return result
    try:
        payload = json.loads(semantic_path.read_text(encoding="utf-8"))
        diagnostic_payload = json.loads(diagnostic_path.read_text(encoding="utf-8"))
        cases = _select_case(_report_case_payload(payload, "rust"))
        diagnostic_cases = _select_case(_report_case_payload(diagnostic_payload, "rust"))
        require(exact_repeat(cases, diagnostic_cases), "Rust diagnostic run changed semantic case payload")
        sidecar_ports = _read_f64le_sidecar(sidecar, schema="sipi.com.normal-erl-array-sidecar.v1")
        selected_vectors = _selected_sidecar_vectors(sidecar_ports)
        for case in cases:
            case["vectors"] = json.loads(json.dumps(selected_vectors))
            case["vector_payload_present"] = True
            case["vector_binding"] = {"case_index": SELECTED_CASE_INDEX, "port": SELECTED_PORT, "package_testcase_index": PACKAGE_TESTCASE_INDEX}
    except (OSError, json.JSONDecodeError, RuntimeError, IndexError) as error:
        result.update({"status": "failed", "label": "rust_result_schema_failed", "error": type(error).__name__})
        return result
    result.update({
        "status": "passed",
        "payload": {"path": "rust-semantic-output/result.json", "bytes": semantic_path.stat().st_size, "sha256": sha256_file(semantic_path)},
        "diagnostic_payload": {"path": "rust-diagnostic-output/result.json", "bytes": diagnostic_path.stat().st_size, "sha256": sha256_file(diagnostic_path)},
        "cases": cases,
        "sidecar": {"schema": "sipi.com.normal-erl-array-sidecar.v1", "selected_case_index": SELECTED_CASE_INDEX, "package_testcase_index": PACKAGE_TESTCASE_INDEX, "selected_port": SELECTED_PORT, "ports": sorted(sidecar_ports), "raw_f64": True, "case_to_port": [{"case_index": SELECTED_CASE_INDEX, "port": SELECTED_PORT, "package_testcase_index": PACKAGE_TESTCASE_INDEX}]},
        "stdout_sha256": sha256_bytes((semantic_completed.stdout or b"") + (diagnostic_completed.stdout or b"")),
        "stderr_sha256": sha256_bytes((semantic_completed.stderr or b"") + (diagnostic_completed.stderr or b"")),
        "case_wall_clock_s": [semantic_elapsed],
    })
    return result


def _run_matlab_once(worker_python: Path, engine_site: Path, harness: Path, source: Path, root: Path, nonce: str, timeout: int) -> dict[str, Any]:
    """Run scalar MATLAB semantics plus archive-local normal-ERL trace."""
    config = source / UPSTREAM_RECEIPT["workbook"]["path"]
    thru, fext, next_channel, _ = _channel_inputs(source, _manifest_projection())
    instrumented = root / "instrumented-source"
    instrumentation = instrument_matlab_source(source, instrumented)
    trace_root = root / "matlab-normal-erl-trace"
    scalar_output = root / "matlab-scalar-output"
    trace_original_output = root / "matlab-trace-original-output"
    trace_instrumented_output = root / "matlab-trace-instrumented-output"
    preference = root / "matlab-prefdir"
    spec = {
        "source_root": str(source),
        "instrumented_source": str(instrumented),
        "config": str(config),
        "parameter_mat": str(root / "parameter.mat"),
        "bridge_expected": str(root / "parameter-bridge-expected.json"),
        "bridge_observed": str(scalar_output / "parameter-bridge.json"),
        "scalar_output": str(scalar_output),
        "trace_original_output": str(trace_original_output),
        "trace_instrumented_output": str(trace_instrumented_output),
        "semantic_timing": str(root / "matlab-semantic-timing.json"),
        "trace_root": str(trace_root),
        "harness": str(harness),
        "trace_tools": str(TRACE_TOOL.parent),
        "nonce": nonce,
        "channels": [str(thru), str(fext), str(next_channel)],
    }
    spec_path = root / "engine-spec.json"
    spec_path.write_text(json.dumps(spec, sort_keys=True), encoding="utf-8", newline="\n")
    environment = _worker_environment(source, engine_site, preference, trace_root)
    completed, elapsed = run_command([str(worker_python), str(Path(__file__).resolve()), "--matlab-trace-worker", str(spec_path)], root, timeout, environment)
    result: dict[str, Any] = {"engine": "matlab", "wall_clock_s": elapsed, "route": "pinned_agent_com_matlab_core_uninstrumented", "instrumentation": instrumentation}
    scalar_summary_path = scalar_output / "summary.json"
    bridge_path = scalar_output / "parameter-bridge.json"
    original_summary_path = trace_original_output / "summary.json"
    instrumented_summary_path = trace_instrumented_output / "summary.json"
    if completed.returncode != 0 or not scalar_summary_path.is_file() or not bridge_path.is_file() or not original_summary_path.is_file() or not instrumented_summary_path.is_file():
        result.update(_error_record(completed, elapsed, "matlab_engine_or_trace_failed"))
        return result
    try:
        scalar_summary = json.loads(scalar_summary_path.read_text(encoding="utf-8"))
        cases = _select_case(_report_case_payload(scalar_summary, "matlab"))
        original_trace = _trace_summary(original_summary_path)
        instrumented_trace = _trace_summary(instrumented_summary_path)
        _enrich_trace_hash_receipts(trace_root)
        sidecar_ports = _read_f64le_sidecar(trace_root, schema="sipi.com.normal-erl-array-trace.v1")
        selected_vectors = _selected_sidecar_vectors(sidecar_ports)
        for case in cases:
            case["vectors"] = json.loads(json.dumps(selected_vectors))
            case["vector_payload_present"] = True
            case["vector_binding"] = {"case_index": SELECTED_CASE_INDEX, "port": SELECTED_PORT, "package_testcase_index": PACKAGE_TESTCASE_INDEX}
        timing = json.loads((root / "matlab-semantic-timing.json").read_text(encoding="utf-8"))
        semantic_elapsed = timing.get("wall_clock_s")
        require(isinstance(semantic_elapsed, (int, float)) and not isinstance(semantic_elapsed, bool) and math.isfinite(float(semantic_elapsed)) and semantic_elapsed > 0.0, "MATLAB semantic timing is invalid")
    except (OSError, json.JSONDecodeError, RuntimeError, IndexError, TypeError) as error:
        result.update({"status": "failed", "label": "matlab_result_schema_failed", "error": type(error).__name__})
        return result
    require(scalar_summary.get("matlab_release") == "2024b" and "R2024b" in str(scalar_summary.get("matlab_version", "")), "MATLAB release drift")
    bridge = bridge_comparison(Path(spec["bridge_expected"]), bridge_path)
    trace_equal = _trace_semantics_equal(original_trace, instrumented_trace)
    result.update({
        "status": "passed",
        "payload": {"path": "matlab-scalar-output/summary.json", "bytes": scalar_summary_path.stat().st_size, "sha256": sha256_file(scalar_summary_path)},
        "cases": cases,
        "sidecar": {"schema": "sipi.com.normal-erl-array-trace.v1", "selected_case_index": SELECTED_CASE_INDEX, "package_testcase_index": PACKAGE_TESTCASE_INDEX, "selected_port": SELECTED_PORT, "ports": sorted(sidecar_ports), "raw_f64": True, "case_to_port": [{"case_index": SELECTED_CASE_INDEX, "port": SELECTED_PORT, "package_testcase_index": PACKAGE_TESTCASE_INDEX}]},
        "stdout_sha256": sha256_bytes(completed.stdout or b""),
        "stderr_sha256": sha256_bytes(completed.stderr or b""),
        "parameter_bridge": bridge,
        "trace_semantics_equal": trace_equal,
        "trace_original_summary_sha256": sha256_file(original_summary_path),
        "trace_instrumented_summary_sha256": sha256_file(instrumented_summary_path),
        "semantic_wall_clock_s": semantic_elapsed,
        "diagnostic_wall_clock_s": elapsed,
        "wall_clock_s": semantic_elapsed,
        "case_wall_clock_s": [semantic_elapsed],
    })
    if not trace_equal:
        result["status"] = "failed"
        result["label"] = "matlab_trace_changed_semantics"
    return result


def _worker_environment(source: Path, engine_site: Path, preference: Path, trace_root: Path | None = None) -> dict[str, str]:
    preference.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join((str(engine_site), str(source / "src")))
    environment["MATLAB_PREFDIR"] = str(preference)
    environment["MW_DISABLE_CONNECTOR"] = "1"
    environment["MATLABPATH"] = ""
    if trace_root is not None:
        environment["SIPI_COM_NORMAL_ERL_TRACE_DIR"] = str(trace_root)
    return environment


def _matlab_worker(spec_path: Path) -> None:
    import matlab.engine
    import numpy as np
    from scipy.io import savemat
    from agent_com.config import ComSettings

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    settings = ComSettings.from_xlsx(Path(spec["config"]))
    rows = settings.rows
    columns = max((len(row) for row in rows), default=0)
    require(columns > 0, "workbook has no cells")
    parameter = np.empty((len(rows), columns), dtype=object)
    slots: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        for column_index in range(columns):
            raw = row[column_index].value if column_index < len(row) else None
            if raw is None:
                value, kind = "", "blank"
            elif isinstance(raw, (bool, int, float, np.integer, np.floating)):
                value, kind = float(raw), "number"
            elif isinstance(raw, str):
                value, kind = raw, "string"
            else:
                raise TypeError(f"unsupported workbook cell type: {type(raw).__name__}")
            parameter[row_index, column_index] = value
            slots.append({"row": row_index, "column": column_index, "kind": kind, "value": value})
    parameter_mat = Path(spec["parameter_mat"])
    savemat(parameter_mat, {"parameter": parameter}, do_compression=False, oned_as="row")
    engine = matlab.engine.start_matlab("-noFigureWindows -singleCompThread")
    try:
        engine.cd(str(Path(spec["output"]).parent), nargout=0)
        engine.addpath(str(Path(spec["harness"]).parent), nargout=0)
        engine.sipi_com_final_surface_oracle_v3(spec["source_root"], str(parameter_mat), spec["output"], float(1), float(1), spec["nonce"], *spec["channels"], nargout=0)
    finally:
        engine.quit()
    Path(spec["bridge_expected"]).write_text(
        json.dumps({"shape": [len(rows), columns], "slots": slots}, sort_keys=True, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
        newline="\n",
    )


def _matlab_trace_worker(spec_path: Path) -> None:
    """Materialize the MAT bridge and run the existing trace wrapper twice."""
    import matlab.engine
    import numpy as np
    from scipy.io import savemat
    from agent_com.config import ComSettings

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    settings = ComSettings.from_xlsx(Path(spec["config"]))
    rows = settings.rows
    columns = max((len(row) for row in rows), default=0)
    require(columns > 0, "workbook has no cells")
    parameter = np.empty((len(rows), columns), dtype=object)
    slots: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        for column_index in range(columns):
            raw = row[column_index].value if column_index < len(row) else None
            if raw is None:
                value, kind = "", "blank"
            elif isinstance(raw, (bool, int, float, np.integer, np.floating)):
                value, kind = float(raw), "number"
            elif isinstance(raw, str):
                value, kind = raw, "string"
            else:
                raise TypeError(f"unsupported workbook cell type: {type(raw).__name__}")
            parameter[row_index, column_index] = value
            slots.append({"row": row_index, "column": column_index, "kind": kind, "value": value})
    parameter_mat = Path(spec["parameter_mat"])
    savemat(parameter_mat, {"parameter": parameter}, do_compression=False, oned_as="row")
    engine = matlab.engine.start_matlab("-noFigureWindows -singleCompThread")
    try:
        engine.cd(str(Path(spec["scalar_output"]).parent), nargout=0)
        engine.addpath(str(Path(spec["harness"]).parent), nargout=0)
        engine.addpath(spec["trace_tools"], nargout=0)
        channels = spec["channels"]
        semantic_started = time.perf_counter()
        engine.sipi_com_final_surface_oracle_v3(spec["source_root"], str(parameter_mat), spec["scalar_output"], float(1), float(1), spec["nonce"], *channels, nargout=0)
        semantic_elapsed = time.perf_counter() - semantic_started
        Path(spec["semantic_timing"]).write_text(
            json.dumps({"schema": "sipi.com.tp0v-r2024b-v4-semantic-timing.v1", "wall_clock_s": semantic_elapsed}, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        engine.sipi_com_normal_erl_trace_run_v1(spec["source_root"], str(parameter_mat), spec["trace_original_output"], float(1), float(1), spec["nonce"], *channels, nargout=0)
        engine.sipi_com_normal_erl_trace_run_v1(spec["instrumented_source"], str(parameter_mat), spec["trace_instrumented_output"], float(1), float(1), spec["nonce"], *channels, nargout=0)
    finally:
        engine.quit()
    Path(spec["bridge_expected"]).write_text(
        json.dumps({"shape": [len(rows), columns], "slots": slots}, sort_keys=True, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
        newline="\n",
    )


def _build_candidate(args: argparse.Namespace, root: Path) -> tuple[Path, dict[str, Any], float]:
    candidate = root / "candidate-source"
    materialized = safe_materialize(args.candidate_archive, candidate)
    require(materialized["sha256"] == CANDIDATE_RECEIPT["archive_sha256"] and materialized["bytes"] == CANDIDATE_RECEIPT["archive_bytes"], "candidate archive drift")
    before = inventory(candidate)
    target = root / "candidate-target"
    target.mkdir()
    if args.engine == "matlab":
        return candidate, {"status": "not_built", "target": "candidate archive"}, 0.0
    environment = os.environ.copy()
    environment["CARGO_TARGET_DIR"] = str(target)
    environment["RUSTC"] = str(args.rustc)
    environment.pop("RUSTC_WRAPPER", None)
    environment.pop("RUSTC_WORKSPACE_WRAPPER", None)
    completed, elapsed = run_command([str(args.cargo), "build", "--release", "--locked", "-p", "sipi-cli", "--features", "com-direct-integration,normal-erl-diagnostic-sidecar", "--bin", "sipi"], candidate, args.timeout, environment)
    require(completed.returncode == 0, "candidate root CLI build failed")
    require(inventory(candidate) == before, "candidate archive changed during build")
    binary = target / "release" / ("sipi.exe" if os.name == "nt" else "sipi")
    require(binary.is_file(), "candidate root CLI binary is missing")
    return candidate, {"status": "passed", "target": "candidate-target/release/sipi", "stdout_sha256": sha256_bytes(completed.stdout or b""), "stderr_sha256": sha256_bytes(completed.stderr or b"")}, elapsed


def run_replay(args: argparse.Namespace) -> dict[str, Any]:
    require(args.run_id in RUN_IDS, "unknown fixed run id")
    require(NONCE_RE.fullmatch(args.nonce) is not None, "nonce must be 64 lowercase hex characters")
    require((args.engine == "matlab") == args.run_id.startswith("matlab"), "run id/engine mismatch")
    require(not args.output_root.exists(), "output root already exists")
    args.output_root.mkdir(parents=True)
    candidate_archive = explicit_file(args.candidate_archive, "candidate archive")
    upstream_archive = explicit_file(args.upstream_archive, "upstream archive")
    candidate_receipt = _v3_archive_receipt(candidate_archive, CANDIDATE_RECEIPT, "candidate")
    upstream_receipt = _v3_archive_receipt(upstream_archive, UPSTREAM_RECEIPT, "upstream")
    cargo = explicit_file(args.cargo, "cargo")
    rustc = explicit_file(args.rustc, "rustc")
    uv = explicit_file(args.uv, "uv")
    worker_python = explicit_file(args.python, "Python")
    matlab = explicit_file(args.matlab, "MATLAB R2024b")
    toolchain = {"cargo": tool_receipt(cargo, "cargo"), "rustc": tool_receipt(rustc, "rustc"), "uv": tool_receipt(uv, "uv"), "python": tool_receipt(worker_python, "python"), "matlab": matlab_receipt(matlab, args.output_root)}
    candidate, build, build_elapsed = _build_candidate(args, args.output_root)
    harness = candidate / "tools" / "sipi_com_final_surface_oracle_v3.m"
    require(harness.is_file(), "candidate MATLAB harness is missing")
    harness_receipt = {"path": "tools/sipi_com_final_surface_oracle_v3.m", "bytes": harness.stat().st_size, "sha256": sha256_file(harness)}
    upstream_base = args.output_root / "upstream-base"
    safe_materialize(upstream_archive, upstream_base)
    environment = os.environ.copy()
    environment["UV_PROJECT_ENVIRONMENT"] = str(args.output_root / "python-env")
    sync, sync_elapsed = run_command([str(uv), "sync", "--frozen", "--offline", "--no-install-project", "--python", str(worker_python)], upstream_base, args.timeout, environment)
    require(sync.returncode == 0, "pinned Agent-COM environment failed")
    worker = args.output_root / "python-env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    require(worker.is_file(), "worker Python is missing")
    engine_site = prepare_engine(worker, uv, matlab, args.output_root) if args.engine == "matlab" else None
    repeats = []
    for repeat_index in (1, 2):
        repeat_root = args.output_root / f"repeat-{repeat_index:02d}"
        repeat_root.mkdir()
        source = repeat_root / "upstream-source"
        safe_materialize(upstream_archive, source)
        source_before = inventory(source)
        repeat_nonce = _derived_nonce(args.nonce, repeat_index)
        if args.engine == "rust":
            binary = args.output_root / "candidate-target" / "release" / ("sipi.exe" if os.name == "nt" else "sipi")
            once = _run_rust_once(binary, source, repeat_root, args.timeout)
        else:
            assert engine_site is not None
            once = _run_matlab_once(worker, engine_site, harness, source, repeat_root, repeat_nonce, args.timeout)
        once["repeat_index"] = repeat_index
        once["nonce"] = repeat_nonce
        once["source_inventory_unchanged"] = inventory(source) == source_before
        require(once["source_inventory_unchanged"], "upstream archive changed during replay")
        repeats.append(once)
    runtime_ok = all(item.get("status") == "passed" for item in repeats)
    repeat_exact = runtime_ok and repeat_payload_exact(repeats, args.engine)
    vector_payload = runtime_ok and all(all(case.get("vector_payload_present") for case in repeat["cases"]) for repeat in repeats)
    bridge_ok = args.engine == "rust" or all(repeat.get("parameter_bridge", {}).get("passed") is True for repeat in repeats)
    status = "passed" if runtime_ok and repeat_exact and vector_payload and bridge_ok else "blocked"
    blockers = []
    if not runtime_ok:
        blockers.append("runtime_failure")
    if runtime_ok and not repeat_exact:
        blockers.append("internal_exact_repeat_drift")
    if not vector_payload:
        blockers.append("vector_payload_missing_or_invalid")
    if not bridge_ok:
        blockers.append("mat_bridge_drift")
    return {
        "schema": SCHEMA,
        "diagnostic_only": True,
        "formal_record": False,
        "status": status,
        "blockers": blockers,
        "engine": args.engine,
        "run_id": args.run_id,
        "nonce": args.nonce,
        "candidate": candidate_receipt,
        "candidate_gate_parent": CANDIDATE_GATE_PARENT,
        "upstream": upstream_receipt,
        "toolchain": toolchain,
        "harness": harness_receipt,
        "build": {**build, "wall_clock_s": build_elapsed},
        "dependency_sync": {"status": "passed", "wall_clock_s": sync_elapsed, "stdout_sha256": sha256_bytes(sync.stdout or b""), "stderr_sha256": sha256_bytes(sync.stderr or b"")},
        "roots": {"candidate": f"{args.run_id}:candidate", "build": f"{args.run_id}:build", "repeats": [f"{args.run_id}:repeat-01", f"{args.run_id}:repeat-02"], "path_redacted": True},
        "repeats": repeats,
        "gates": {"internal_exact_repeat": repeat_exact, "vector_payload_present": vector_payload, "mat_bridge": bridge_ok, "public_root_route": args.engine == "rust"},
        "comparison_contract": {"scalar_names": list(SCALAR_NAMES), "scalar_absolute_tolerance": 1.0e-9, "scalar_case_scope": {"selected_case_index": SELECTED_CASE_INDEX, "package_testcase_index": PACKAGE_TESTCASE_INDEX, "case_count": len(CASE_INDICES)}, "vectors": list(VECTOR_NAMES), "vector_tolerance": VECTOR_TOLERANCE, "prohibited_transforms": list(PROHIBITED_TRANSFORMS), "selected_case_index": SELECTED_CASE_INDEX, "package_testcase_index": PACKAGE_TESTCASE_INDEX, "selected_port": SELECTED_PORT, "case_to_port": [{"case_index": SELECTED_CASE_INDEX, "port": SELECTED_PORT, "package_testcase_index": PACKAGE_TESTCASE_INDEX}]},
        "d3": {"status": "not_evaluated_configuration_disables_tdiln", "selected_configs": [{"name": "package-case-0", "COMPUTE_TDILN": 0}, {"name": "package-case-1", "COMPUTE_TDILN": 0}], "global_d3_enabled": True},
        "performance": {"required": True, "instrumented_trace_included": False, "semantic_timing_source": "un-instrumented_semantic_invocation_only", "diagnostic_trace_timing_recorded": True, "case_wall_clock_s": [repeat.get("case_wall_clock_s") for repeat in repeats]},
        "claims": {"acceptance": False, "release": False, "data_transform": False, "s_parameter_fit": False, "public_root_route": args.engine == "rust"},
        "non_claims": ["not_formal_evidence", "not_complete_original13", "not_a_vector_parity_claim_until_four_replays_pass"],
    }


def _v3_archive_receipt(path: Path, expected: dict[str, Any], label: str) -> dict[str, Any]:
    explicit_file(path, f"{label} archive")
    size = path.stat().st_size
    digest = sha256_file(path)
    require(size == expected["archive_bytes"] and digest == expected["archive_sha256"], f"{label} archive receipt drift")
    return {key: expected[key] for key in ("commit", "tree", "archive_sha256", "archive_bytes")}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("matlab", "rust"), required=True)
    parser.add_argument("--run-id", choices=sorted(RUN_IDS), required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--candidate-archive", type=Path, required=True)
    parser.add_argument("--upstream-archive", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--matlab", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is not None and len(argv) == 2 and argv[0] == "--matlab-trace-worker":
        _matlab_trace_worker(Path(argv[1]))
        return 0
    if argv is not None and len(argv) == 2 and argv[0] == "--engine-worker":
        _matlab_worker(Path(argv[1]))
        return 0
    parser = build_parser()
    args = parser.parse_args(argv)
    require(args.timeout > 0, "timeout must be positive")
    require(not args.report.exists(), "report path already exists")
    report = args.report.resolve()
    root = ROOT.resolve()
    require(report != root and root not in report.parents, "report must stay outside repository")
    payload = run_replay(args)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "run_id": payload["run_id"], "blockers": payload["blockers"], "report_sha256": sha256_file(args.report)}, sort_keys=True))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
