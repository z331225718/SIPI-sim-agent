"""Diagnose finite normal-ERL TDR arrays against the pinned MATLAB source.

This is deliberately separate from the accepted ERL-only runner.  It widens
the diagnostic corpus to the original-13 configurations that produce finite
ERL while preserving the immutable ERL-only checkpoint and its tool hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from tools.run_com_normal_erl_trace_diagnostic import (
        CANDIDATE_B456, CHANNELS, CONFIG_PATHS, MATLAB_TIMEOUT_S, UPSTREAM,
        _read_summary, _run_matlab, _scalar_equal, _special,
        _trace_digests, _warning_semantics, bounded, digest,
        instrument_matlab_source, materialize, prepare_matlab_engine,
        require_archive,
    )
except ImportError:
    from run_com_normal_erl_trace_diagnostic import (
        CANDIDATE_B456, CHANNELS, CONFIG_PATHS, MATLAB_TIMEOUT_S, UPSTREAM,
        _read_summary, _run_matlab, _scalar_equal, _special,
        _trace_digests, _warning_semantics, bounded, digest,
        instrument_matlab_source, materialize, prepare_matlab_engine,
        require_archive,
    )


FINITE_ERL_WORKBOOK_INDICES = (0, 2, 8, 10, 12)
VECTORS = ("time_s", "impedance_ohm", "ptdr", "gated")


def _read_rust_sidecar(root: Path) -> list[dict[str, Any]]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "sipi.com.normal-erl-array-sidecar.v1" or manifest.get("normal_erl_applicable") is not True:
        raise RuntimeError("Rust finite normal ERL sidecar manifest")
    ports = manifest.get("ports")
    if not isinstance(ports, list) or len(ports) != 2:
        raise RuntimeError("Rust finite normal ERL sidecar ports")
    result: list[dict[str, Any]] = []
    for expected_port, entry in enumerate(ports, start=1):
        if not isinstance(entry, dict) or entry.get("port") != expected_port:
            raise RuntimeError("Rust finite normal ERL sidecar port order")
        vectors = entry.get("vectors")
        if not isinstance(vectors, dict) or set(vectors) != set(VECTORS):
            raise RuntimeError("Rust finite normal ERL sidecar vector set")
        projected: dict[str, Any] = {"port": expected_port, "available": True, "vectors": {}}
        for name in VECTORS:
            vector = vectors[name]
            if not isinstance(vector, dict):
                raise RuntimeError("Rust finite normal ERL sidecar vector")
            raw = (root / vector["file"]).read_bytes()
            shape = vector.get("shape")
            if vector.get("dtype") != "f64le" or not isinstance(shape, list) or shape != [len(raw) // 8] or vector.get("bytes") != len(raw) or len(raw) % 8 or vector.get("sha256") != hashlib.sha256(raw).hexdigest():
                raise RuntimeError("Rust finite normal ERL sidecar receipt")
            projected["vectors"][name] = {"count": shape[0], "sha256": hashlib.sha256(raw).hexdigest(), "path": root / vector["file"]}
        result.append(projected)
    return result


def _run_rust_sidecar(binary: Path, config: Path, channels: list[Path], output: Path, sidecar: Path, timeout: int) -> tuple[subprocess.CompletedProcess[bytes], float, dict[str, Any] | None]:
    environment = os.environ.copy()
    environment["RAYON_NUM_THREADS"] = "16"
    environment["SIPI_COM_NORMAL_ERL_DIAGNOSTIC_SIDECAR_DIR"] = str(sidecar)
    started = time.perf_counter()
    completed = bounded([str(binary), "run", "--config", str(config), "--thru", str(channels[0]), "--fext", str(channels[1]), "--next", str(channels[2]), "--output-dir", str(output), "--overwrite"], output.parent, timeout, environment)
    result_path = output / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if completed.returncode == 0 and result_path.is_file() else None
    return completed, time.perf_counter() - started, result


def vector_residuals(matlab_root: Path, rust_root: Path) -> list[dict[str, Any]]:
    """Return bounded numeric observations without promoting an acceptance tolerance."""
    observations: list[dict[str, Any]] = []
    for port in (1, 2):
        for name in VECTORS:
            matlab = (matlab_root / f"port-{port}" / f"{name}.f64le").read_bytes()
            rust = (rust_root / f"port-{port}" / f"{name}.f64le").read_bytes()
            if len(matlab) % 8 or len(rust) % 8:
                raise RuntimeError("finite normal ERL residual input alignment")
            entry: dict[str, Any] = {
                "port": port,
                "vector": name,
                "matlab_count": len(matlab) // 8,
                "rust_count": len(rust) // 8,
                "shape_equal": len(matlab) == len(rust),
            }
            if len(matlab) == len(rust):
                squared_error = 0.0
                maximum = 0.0
                for (left,), (right,) in zip(struct.iter_unpack("<d", matlab), struct.iter_unpack("<d", rust), strict=True):
                    if not math.isfinite(left) or not math.isfinite(right):
                        raise RuntimeError("finite normal ERL residual input finite")
                    difference = abs(left - right)
                    maximum = max(maximum, difference)
                    squared_error += difference * difference
                entry["max_abs"] = maximum
                entry["rms"] = (squared_error / (len(matlab) // 8)) ** 0.5 if matlab else 0.0
            observations.append(entry)
    return observations


def _rust_cases(result: dict[str, Any], expected_count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases = result.get("cases")
    if not isinstance(cases, list) or len(cases) != expected_count:
        raise RuntimeError("Rust finite normal ERL case count")
    scalar_cases: list[dict[str, Any]] = []
    reference_ports: list[dict[str, Any]] | None = None
    for case_index, case in enumerate(cases):
        metrics = case.get("metrics")
        normal = case.get("diagnostics", {}).get("normal_erl")
        if not isinstance(metrics, dict) or not isinstance(normal, dict) or normal.get("s_parameter_model_fit") is not False:
            raise RuntimeError("Rust finite normal ERL diagnostics")
        ports = normal.get("ports")
        if not isinstance(ports, list) or len(ports) != 2:
            raise RuntimeError("Rust finite normal ERL port count")
        projected_ports: list[dict[str, Any]] = []
        for expected_port, port in enumerate(ports, start=1):
            if not isinstance(port, dict) or port.get("port") != expected_port:
                raise RuntimeError("Rust finite normal ERL port order")
            projected_ports.append({
                "port": expected_port,
                "available": True,
                "vectors": {
                    "time_s": {"count": port["sample_count"], "sha256": port["time_sha256"]},
                    "impedance_ohm": {"count": port["sample_count"], "sha256": port["impedance_sha256"]},
                    "ptdr": {"count": port["sample_count"], "sha256": port["ptdr_sha256"]},
                    "gated": {"count": port["sample_count"], "sha256": port["gated_sha256"]},
                },
            })
        if reference_ports is None:
            reference_ports = projected_ports
        elif projected_ports != reference_ports:
            raise RuntimeError(f"Rust finite normal ERL package-case trace drift: {case_index}")
        scalar_cases.append({
            "ERL": _special(metrics.get("ERL")),
            "ERL11": _special(ports[0].get("erl_db")),
            "ERL22": _special(ports[1].get("erl_db")),
            "Z11est": _special(ports[0].get("avg_port_impedance_ohm")),
            "Z22est": _special(ports[1].get("avg_port_impedance_ohm")),
        })
    return scalar_cases, reference_ports or []


def compare_case(
    original_summary: dict[str, Any],
    instrumented_summary: dict[str, Any],
    matlab_ports: list[dict[str, Any]],
    rust_result: dict[str, Any],
) -> dict[str, Any]:
    if original_summary["cases"] != instrumented_summary["cases"]:
        raise RuntimeError("instrumented MATLAB finite normal ERL scalar drift")
    if _warning_semantics(original_summary["last_warning"]) != _warning_semantics(instrumented_summary["last_warning"]):
        raise RuntimeError("instrumented MATLAB finite normal ERL warning semantics drift")
    source_cases = original_summary["cases"]
    if not isinstance(source_cases, list) or not source_cases:
        raise RuntimeError("MATLAB finite normal ERL scalar cases")
    rust_scalars, rust_ports = _rust_cases(rust_result, len(source_cases))
    scalar_cases: list[dict[str, Any]] = []
    for source, rust in zip(source_cases, rust_scalars, strict=True):
        if not isinstance(source, dict):
            raise RuntimeError("MATLAB finite normal ERL scalar case")
        scalar = {
            name: {"matlab": source.get(name), "rust": rust.get(name), "passed": _scalar_equal(source.get(name), rust.get(name))}
            for name in sorted(set(source) | set(rust))
        }
        scalar_cases.append({"scalar": scalar, "passed": all(item["passed"] for item in scalar.values())})
    port_comparisons: list[dict[str, Any]] = []
    for matlab, rust in zip(matlab_ports, rust_ports, strict=True):
        if matlab["port"] != rust["port"] or matlab["available"] is not True or rust["available"] is not True:
            raise RuntimeError("finite normal ERL port availability drift")
        vectors = {
            name: {"matlab": matlab["vectors"][name], "rust": rust["vectors"][name], "passed": matlab["vectors"][name] == rust["vectors"][name]}
            for name in VECTORS
        }
        port_comparisons.append({"port": matlab["port"], "vectors": vectors, "passed": all(item["passed"] for item in vectors.values())})
    return {
        "scalar_cases": scalar_cases,
        "scalar_passed": all(item["passed"] for item in scalar_cases),
        "ports": port_comparisons,
        "array_digest_identity": all(item["passed"] for item in port_comparisons),
        "rust_package_case_trace_repeat_exact": True,
    }


def _parse_indices(value: str | None) -> tuple[int, ...]:
    if value is None:
        return FINITE_ERL_WORKBOOK_INDICES
    try:
        parsed = tuple(sorted({int(item) for item in value.split(",") if item.strip()}))
    except ValueError as error:
        raise argparse.ArgumentTypeError("indices must be comma-separated integers") from error
    if not parsed or any(index not in FINITE_ERL_WORKBOOK_INDICES for index in parsed):
        raise argparse.ArgumentTypeError("indices must select original-13 finite-ERL workbooks")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    candidate_group = parser.add_mutually_exclusive_group(required=True)
    candidate_group.add_argument("--candidate-archive", type=Path)
    candidate_group.add_argument("--candidate-root", type=Path)
    parser.add_argument("--upstream-archive", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--matlab", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--indices", type=_parse_indices)
    parser.add_argument("--timeout", type=int, default=MATLAB_TIMEOUT_S)
    args = parser.parse_args()
    if args.output_root.exists() or args.report.exists():
        raise FileExistsError("output root or report already exists")
    require_archive(args.upstream_archive, UPSTREAM)
    indices = args.indices or FINITE_ERL_WORKBOOK_INDICES
    args.output_root.mkdir(parents=True)
    upstream = args.output_root / "upstream"
    materialize(args.upstream_archive, upstream)
    if args.candidate_archive is not None:
        require_archive(args.candidate_archive, CANDIDATE_B456)
        candidate = args.output_root / "candidate"
        materialize(args.candidate_archive, candidate)
        candidate_receipt: dict[str, Any] = {"commit": CANDIDATE_B456[0], "tree": CANDIDATE_B456[1], "archive_sha256": CANDIDATE_B456[2], "archive_bytes": CANDIDATE_B456[3]}
    else:
        candidate = args.candidate_root.resolve()
        if not (candidate / "crates/sipi-agent-com-direct/Cargo.toml").is_file():
            raise RuntimeError("candidate worktree is missing the direct COM crate")
        candidate_receipt = {"mode": "development_worktree", "path_redacted": True}
    build_environment = os.environ.copy()
    build_environment["CARGO_TARGET_DIR"] = str(args.output_root / "target")
    build_environment["RUSTC"] = str(args.rustc)
    build_environment.pop("RUSTC_WRAPPER", None)
    build_environment.pop("RUSTC_WORKSPACE_WRAPPER", None)
    build = bounded([str(args.cargo), "build", "--release", "--locked", "--manifest-path", str(candidate / "crates/sipi-agent-com-direct/Cargo.toml"), "--features", "normal-erl-diagnostic-sidecar", "--bin", "sipi-com-direct-run"], candidate, 1800, build_environment)
    if build.returncode:
        raise RuntimeError("candidate build failed")
    binary = args.output_root / "target" / "release" / "sipi-com-direct-run.exe"
    if not binary.is_file():
        raise RuntimeError("candidate normal ERL binary missing")
    environment = args.output_root / "python-env"
    sync_environment = os.environ.copy()
    sync_environment["UV_PROJECT_ENVIRONMENT"] = str(environment)
    sync = bounded([str(args.uv), "sync", "--frozen", "--offline", "--no-install-project", "--python", str(args.python)], upstream, 300, sync_environment)
    worker_python = environment / "Scripts" / "python.exe"
    if sync.returncode or not worker_python.is_file():
        raise RuntimeError("pinned Python environment failed")
    engine_site = prepare_matlab_engine(worker_python, args.uv, args.matlab, args.output_root)
    patched_root = args.output_root / "upstream-instrumented"
    patch_receipt = instrument_matlab_source(upstream, patched_root)
    channel_paths = [upstream / item[1] for item in CHANNELS]
    if any(not path.is_file() for path in channel_paths):
        raise RuntimeError("original-13 S4P inputs missing")
    records = []
    for ordinal, index in enumerate(indices):
        case_root = args.output_root / f"case-{ordinal:02d}"
        case_root.mkdir()
        config_rel = Path(CONFIG_PATHS[index])
        original_out = case_root / "matlab-original"
        instrumented_out = case_root / "matlab-instrumented"
        trace_root = case_root / "matlab-trace"
        nonce = os.urandom(32).hex()
        original_run, original_wall = _run_matlab(worker_python, engine_site, upstream, upstream / config_rel, channel_paths, original_out, None, nonce, args.timeout)
        instrumented_run, instrumented_wall = _run_matlab(worker_python, engine_site, patched_root, patched_root / config_rel, channel_paths, instrumented_out, trace_root, nonce, args.timeout)
        rust_sidecar = case_root / "rust-trace"
        rust_run, rust_wall, rust_result = _run_rust_sidecar(binary, upstream / config_rel, channel_paths, case_root / "rust", rust_sidecar, args.timeout)
        if original_run.returncode or instrumented_run.returncode or rust_run.returncode or rust_result is None:
            raise RuntimeError(f"finite normal ERL execution failed for workbook {index}")
        matlab_ports = _trace_digests(trace_root)
        rust_ports = _read_rust_sidecar(rust_sidecar)
        comparison = compare_case(_read_summary(original_out / "summary.json"), _read_summary(instrumented_out / "summary.json"), matlab_ports, rust_result)
        comparison["numeric_residual_observation"] = vector_residuals(trace_root, rust_sidecar)
        comparison["rust_sidecar_receipts_match_public"] = all(
            rust_port["vectors"][name]["sha256"] == public_port["vectors"][name]["rust"]["sha256"] and rust_port["vectors"][name]["count"] == public_port["vectors"][name]["rust"]["count"]
            for rust_port, public_port in zip(rust_ports, comparison["ports"], strict=True)
            for name in VECTORS
        )
        records.append({"workbook_index": index, "workbook": {"path": config_rel.as_posix(), "bytes": (upstream / config_rel).stat().st_size, "sha256": digest(upstream / config_rel)}, "matlab_original_wall_seconds": original_wall, "matlab_instrumented_wall_seconds": instrumented_wall, "rust_wall_seconds": rust_wall, "comparison": comparison})
    report = {
        "schema": "sipi.com.finite-normal-erl-trace-diagnostic.v1", "diagnostic_only": True,
        "candidate": candidate_receipt,
        "upstream": {"commit": UPSTREAM[0], "tree": UPSTREAM[1], "archive_sha256": UPSTREAM[2], "archive_bytes": UPSTREAM[3]},
        "instrumentation": patch_receipt, "matlab_release": "R2024b", "vectors": list(VECTORS), "records": records,
        "claims": {"array_digest_identity": all(item["comparison"]["array_digest_identity"] for item in records), "scalar_parity": all(item["comparison"]["scalar_passed"] for item in records), "rust_package_case_trace_repeat_exact": all(item["comparison"]["rust_package_case_trace_repeat_exact"] for item in records), "performance_acceptance": False},
        "non_claims": ["not_release", "not_full_erl_result_graph", "not_warning_catalog", "not_instrumented_matlab_performance", "not_channel_s_parameter_fit"],
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"report_sha256": hashlib.sha256(args.report.read_bytes()).hexdigest(), "array_digest_identity": report["claims"]["array_digest_identity"], "scalar_parity": report["claims"]["scalar_parity"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
