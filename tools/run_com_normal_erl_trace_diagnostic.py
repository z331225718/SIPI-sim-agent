"""Compare original MATLAB normal-TDR traces with b456 Rust receipts.

This is a diagnostic preparation runner, not an acceptance gate.  It creates
an archive-local MATLAB source copy with four exact, read-only trace hooks:
the completed TDR time axis, impedance, pre-gate PTDR, and gated PTDR for both
ports.  The original source copy is run first and must retain the same scalar
surface and last-warning observation as the instrumented copy.  Rust itself is
not changed: its normal-ERL result already publishes SHA-256 receipts for these
four vectors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from tools.run_p5_06_original13_fresh_matrix import (
        CANDIDATE,
        CHANNELS,
        CONFIG_PATHS,
        UPSTREAM,
        bounded,
        digest,
        materialize,
        prepare_matlab_engine,
    )
except ImportError:
    from run_p5_06_original13_fresh_matrix import (
        CANDIDATE,
        CHANNELS,
        CONFIG_PATHS,
        UPSTREAM,
        bounded,
        digest,
        materialize,
        prepare_matlab_engine,
    )


CANDIDATE_B456 = (
    "b456e9d57b2449787e22cdefdad6c0edc70d69dc",
    "9cd25bd57387e571917cf5274952d8c4fffe44f5",
    "dfbf605916dccb0912a7dbc565eb49e58055efb869113ee0fc3704c598c0f0a8",
    58337280,
)
SOURCE_FILE = Path("matlab_src/com_ieee8023_480.m")
SOURCE_SHA256 = "88db14d7d82dab980d223a5be02a28013c11e0d0239e0e97e36c9d36fef55596"
ERL_WORKBOOK_INDICES = (3, 4, 5)
VECTORS = ("time_s", "impedance_ohm", "ptdr", "gated")
MATLAB_TIMEOUT_S = 600


def require_archive(path: Path, identity: tuple[str, str, str, int]) -> None:
    if not path.is_file() or path.stat().st_size != identity[3] or digest(path) != identity[2]:
        raise RuntimeError("archive identity drift")


def _replace_once(content: str, needle: str, replacement: str, label: str) -> str:
    if content.count(needle) != 1:
        raise RuntimeError(f"instrumentation source context drift: {label}")
    return content.replace(needle, replacement, 1)


def instrument_matlab_source(source_root: Path, instrumented_root: Path) -> dict[str, str]:
    """Copy and add trace-only fields without touching numerical statements."""
    shutil.copytree(source_root, instrumented_root)
    path = instrumented_root / SOURCE_FILE
    original = path.read_text(encoding="utf-8")
    if hashlib.sha256(original.encode("utf-8")).hexdigest() != SOURCE_SHA256:
        raise RuntimeError("pinned MATLAB source hash drift")
    patched = _replace_once(
        original,
        "        [output_args,ERL,min_ERL]=TDR_ERL_Processing(output_args,OP,package_testcase_i,chdata,param);",
        "        [output_args,ERL,min_ERL]=TDR_ERL_Processing(output_args,OP,package_testcase_i,chdata,param);\n"
        "        if ~isempty(getenv('SIPI_COM_NORMAL_ERL_TRACE_DIR'))\n"
        "            sipi_com_normal_erl_trace_sink_v1(chdata, OP, package_testcase_i);\n"
        "        end",
        "post_tdr_hook",
    )
    patched = _replace_once(
        patched,
        "    PTDR.pulse_orig=PTDR.pulse;",
        "    PTDR.pulse_orig=PTDR.pulse;\n    TDR_results.ptdr_raw=PTDR.pulse_orig;",
        "raw_ptdr_field",
    )
    patched = _replace_once(
        patched,
        "                        if OP.PTDR, chdata(i).PDTR11(izt).ptdr=TDR_results(izt,1).ptdr_RL;end",
        "                        if OP.PTDR, chdata(i).PDTR11(izt).ptdr=TDR_results(izt,1).ptdr_RL; chdata(i).PDTR11(izt).ptdr_raw=TDR_results(izt,1).ptdr_raw;end",
        "port1_raw_ptdr_copy",
    )
    patched = _replace_once(
        patched,
        "                        if OP.PTDR, chdata(i).PDTR22(izt).ptdr=TDR_results(izt,2).ptdr_RL;end",
        "                        if OP.PTDR, chdata(i).PDTR22(izt).ptdr=TDR_results(izt,2).ptdr_RL; chdata(i).PDTR22(izt).ptdr_raw=TDR_results(izt,2).ptdr_raw;end",
        "port2_raw_ptdr_copy",
    )
    path.write_text(patched, encoding="utf-8", newline="\n")
    return {
        "source_path": SOURCE_FILE.as_posix(),
        "original_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        "instrumented_sha256": hashlib.sha256(patched.encode("utf-8")).hexdigest(),
    }


def _special(value: Any) -> Any:
    if isinstance(value, str):
        return {
            "inf": "+Inf", "+inf": "+Inf", "-inf": "-Inf", "nan": "NaN",
        }.get(value.casefold(), value)
    if isinstance(value, float):
        if value != value:
            return "NaN"
        if value == float("inf"):
            return "+Inf"
        if value == float("-inf"):
            return "-Inf"
    return value


def _engine_worker(spec_path: str) -> None:
    import numpy as np
    import matlab.engine
    from scipy.io import savemat
    from agent_com.config import ComSettings

    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    settings = ComSettings.from_xlsx(Path(spec["config"]))
    rows = settings.rows
    column_count = max(len(row) for row in rows)
    parameter = np.empty((len(rows), column_count), dtype=object)
    for row_index, row in enumerate(rows):
        for column_index in range(column_count):
            raw = row[column_index].value if column_index < len(row) else None
            if raw is None:
                value = ""
            elif isinstance(raw, (bool, int, float, np.integer, np.floating)):
                value = float(raw)
            elif isinstance(raw, str):
                value = raw
            else:
                raise TypeError(f"unsupported workbook cell type: {type(raw).__name__}")
            parameter[row_index, column_index] = value
    parameter_mat = Path(spec["output_parent"]) / "parameter.mat"
    savemat(parameter_mat, {"parameter": parameter}, do_compression=False, oned_as="row")
    engine = matlab.engine.start_matlab("-noFigureWindows -singleCompThread")
    try:
        engine.addpath(spec["tools_dir"], nargout=0)
        engine.cd(spec["output_parent"], nargout=0)
        engine.sipi_com_normal_erl_trace_run_v1(
            spec["source_root"],
            str(parameter_mat),
            spec["output"],
            float(1),
            float(1),
            spec["nonce"],
            *spec["channels"],
            nargout=0,
        )
    finally:
        engine.quit()


def _run_matlab(
    worker_python: Path,
    engine_site: Path,
    source_root: Path,
    config: Path,
    channels: list[Path],
    output: Path,
    trace_root: Path | None,
    nonce: str,
    timeout: int,
) -> tuple[subprocess.CompletedProcess[bytes], float]:
    output.parent.mkdir(parents=True, exist_ok=True)
    spec = {
        "tools_dir": str(Path(__file__).resolve().parent),
        "output_parent": str(output.parent),
        "source_root": str(source_root),
        "config": str(config),
        "output": str(output),
        "channels": [str(value) for value in channels],
        "nonce": nonce,
    }
    spec_path = output.parent / "engine-spec.json"
    spec_path.write_text(json.dumps(spec, sort_keys=True), encoding="utf-8", newline="\n")
    preference = output.parent / f"{output.name}-matlab-pref"
    preference.mkdir()
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join((str(engine_site), str(source_root / "src")))
    environment["MATLAB_PREFDIR"] = str(preference)
    environment["MW_DISABLE_CONNECTOR"] = "1"
    if trace_root is None:
        environment.pop("SIPI_COM_NORMAL_ERL_TRACE_DIR", None)
    else:
        trace_root.mkdir(parents=True, exist_ok=False)
        environment["SIPI_COM_NORMAL_ERL_TRACE_DIR"] = str(trace_root)
    started = time.perf_counter()
    completed = bounded(
        [str(worker_python), str(Path(__file__).resolve()), "--engine-worker", str(spec_path)],
        output.parent,
        timeout,
        environment,
    )
    return completed, time.perf_counter() - started


def _read_summary(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "schema", "nonce", "matlab_release", "matlab_version", "duration_seconds",
        "case_count", "cases", "last_warning",
    }
    if set(value) != expected or value["schema"] != "sipi.com.normal-erl-trace-run.v1":
        raise RuntimeError("MATLAB normal ERL summary schema")
    return value


def _trace_digests(root: Path) -> list[dict[str, Any]]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "sipi.com.normal-erl-array-trace.v1" or manifest.get("diagnostic_only") is not True:
        raise RuntimeError("MATLAB normal ERL trace manifest")
    ports = manifest.get("ports")
    if not isinstance(ports, list) or len(ports) != 2:
        raise RuntimeError("MATLAB normal ERL trace ports")
    result: list[dict[str, Any]] = []
    for expected_port, entry in enumerate(ports, start=1):
        if not isinstance(entry, dict) or entry.get("port") != expected_port:
            raise RuntimeError("MATLAB normal ERL trace port identity")
        if entry.get("available") is False:
            result.append({"port": expected_port, "available": False})
            continue
        vectors = entry.get("vectors")
        if entry.get("available") is not True or not isinstance(vectors, dict) or set(vectors) != set(VECTORS):
            raise RuntimeError("MATLAB normal ERL trace vector set")
        projected: dict[str, Any] = {"port": expected_port, "available": True, "vectors": {}}
        for name in VECTORS:
            vector = vectors[name]
            path = root / vector["file"]
            raw = path.read_bytes()
            if vector.get("dtype") != "f64le" or vector.get("bytes") != len(raw) or len(raw) != int(vector.get("shape", 0)) * 8:
                raise RuntimeError("MATLAB normal ERL trace vector receipt")
            projected["vectors"][name] = {
                "count": int(vector["shape"]),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        result.append(projected)
    return result


def _run_rust(binary: Path, config: Path, channels: list[Path], output: Path, timeout: int) -> tuple[subprocess.CompletedProcess[bytes], float, dict[str, Any] | None]:
    environment = os.environ.copy()
    environment["RAYON_NUM_THREADS"] = "16"
    started = time.perf_counter()
    completed = bounded(
        [
            str(binary), "run", "--config", str(config), "--thru", str(channels[0]),
            "--fext", str(channels[1]), "--next", str(channels[2]),
            "--output-dir", str(output), "--overwrite",
        ],
        output.parent,
        timeout,
        environment,
    )
    result_path = output / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if completed.returncode == 0 and result_path.is_file() else None
    return completed, time.perf_counter() - started, result


def _rust_receipts(result: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cases = result.get("cases")
    if not isinstance(cases, list) or len(cases) != 1:
        raise RuntimeError("Rust normal ERL result cases")
    case = cases[0]
    normal = case.get("diagnostics", {}).get("normal_erl")
    if not isinstance(normal, dict) or normal.get("s_parameter_model_fit") is not False:
        raise RuntimeError("Rust normal ERL diagnostic missing")
    ports = normal.get("ports")
    if not isinstance(ports, list) or len(ports) != 2:
        raise RuntimeError("Rust normal ERL diagnostic ports")
    source_keys = {
        "ERL": _special(case.get("metrics", {}).get("ERL")),
        "ERL11": _special(ports[0].get("erl_db")),
        "ERL22": _special(ports[1].get("erl_db")),
        "Z11est": _special(ports[0].get("avg_port_impedance_ohm")),
        "Z22est": _special(ports[1].get("avg_port_impedance_ohm")),
    }
    projected: list[dict[str, Any]] = []
    for index, port in enumerate(ports, start=1):
        if port.get("port") != index:
            raise RuntimeError("Rust normal ERL port order")
        values = {
            "time_s": ("sample_count", "time_sha256"),
            "impedance_ohm": ("sample_count", "impedance_sha256"),
            "ptdr": ("sample_count", "ptdr_sha256"),
            "gated": ("sample_count", "gated_sha256"),
        }
        projected.append({
            "port": index,
            "available": True,
            "vectors": {
                name: {"count": port[count], "sha256": port[digest_key]}
                for name, (count, digest_key) in values.items()
            },
        })
    return source_keys, projected


def _scalar_equal(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 1.0e-9
    return left == right


def _warning_semantics(value: Any) -> tuple[Any, Any]:
    """Ignore instrumentation-copy path/line noise, never claim catalog parity."""
    if not isinstance(value, dict):
        raise RuntimeError("MATLAB last-warning schema")
    message = value.get("message")
    if not isinstance(message, str):
        raise RuntimeError("MATLAB last-warning message")
    return value.get("identifier"), message.rsplit("\n", 1)[-1]


def _compare_case(
    original_summary: dict[str, Any],
    instrumented_summary: dict[str, Any],
    matlab_ports: list[dict[str, Any]],
    rust_result: dict[str, Any],
) -> dict[str, Any]:
    if original_summary["cases"] != instrumented_summary["cases"]:
        raise RuntimeError("instrumented MATLAB scalar drift")
    if _warning_semantics(original_summary["last_warning"]) != _warning_semantics(instrumented_summary["last_warning"]):
        raise RuntimeError("instrumented MATLAB warning semantics drift")
    source_scalars = original_summary["cases"][0]
    rust_scalars, rust_ports = _rust_receipts(rust_result)
    scalar = {
        name: {
            "matlab": source_scalars.get(name),
            "rust": rust_scalars.get(name),
            "passed": _scalar_equal(source_scalars.get(name), rust_scalars.get(name)),
        }
        for name in sorted(set(source_scalars) | set(rust_scalars))
    }
    port_comparisons: list[dict[str, Any]] = []
    for matlab, rust in zip(matlab_ports, rust_ports, strict=True):
        if matlab["port"] != rust["port"] or matlab["available"] != rust["available"]:
            raise RuntimeError("normal ERL port availability drift")
        vectors = {
            name: {
                "matlab": matlab["vectors"][name],
                "rust": rust["vectors"][name],
                "passed": matlab["vectors"][name] == rust["vectors"][name],
            }
            for name in VECTORS
        }
        port_comparisons.append({"port": matlab["port"], "vectors": vectors, "passed": all(item["passed"] for item in vectors.values())})
    return {
        "scalar": scalar,
        "scalar_passed": all(item["passed"] for item in scalar.values()),
        "ports": port_comparisons,
        "array_digest_identity": all(item["passed"] for item in port_comparisons),
    }


def _parse_indices(value: str | None) -> tuple[int, ...]:
    if value is None:
        return ERL_WORKBOOK_INDICES
    try:
        parsed = tuple(sorted({int(item) for item in value.split(",") if item.strip()}))
    except ValueError as error:
        raise argparse.ArgumentTypeError("indices must be comma-separated integers") from error
    if not parsed or any(index not in ERL_WORKBOOK_INDICES for index in parsed):
        raise argparse.ArgumentTypeError("indices must select original-13 ERL-only workbooks")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-archive", type=Path, required=True)
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
    require_archive(args.candidate_archive, CANDIDATE_B456)
    require_archive(args.upstream_archive, UPSTREAM)
    indices = args.indices or ERL_WORKBOOK_INDICES
    args.output_root.mkdir(parents=True)
    candidate = args.output_root / "candidate"
    upstream = args.output_root / "upstream"
    materialize(args.candidate_archive, candidate)
    materialize(args.upstream_archive, upstream)
    build_environment = os.environ.copy()
    build_environment["CARGO_TARGET_DIR"] = str(args.output_root / "target")
    build_environment["RUSTC"] = str(args.rustc)
    build_environment.pop("RUSTC_WRAPPER", None)
    build_environment.pop("RUSTC_WORKSPACE_WRAPPER", None)
    build = bounded(
        [str(args.cargo), "build", "--release", "--locked", "--manifest-path", str(candidate / "crates/sipi-agent-com-direct/Cargo.toml"), "--bin", "sipi-com-direct-run"],
        candidate,
        1800,
        build_environment,
    )
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
        rust_run, rust_wall, rust_result = _run_rust(binary, upstream / config_rel, channel_paths, case_root / "rust", args.timeout)
        if original_run.returncode or instrumented_run.returncode or rust_run.returncode or rust_result is None:
            raise RuntimeError(f"normal ERL execution failed for workbook {index}")
        comparison = _compare_case(
            _read_summary(original_out / "summary.json"),
            _read_summary(instrumented_out / "summary.json"),
            _trace_digests(trace_root),
            rust_result,
        )
        records.append({
            "workbook_index": index,
            "workbook": {"path": config_rel.as_posix(), "bytes": (upstream / config_rel).stat().st_size, "sha256": digest(upstream / config_rel)},
            "matlab_original_wall_seconds": original_wall,
            "matlab_instrumented_wall_seconds": instrumented_wall,
            "rust_wall_seconds": rust_wall,
            "comparison": comparison,
        })
    report = {
        "schema": "sipi.com.normal-erl-trace-diagnostic.v1",
        "diagnostic_only": True,
        "candidate": {"commit": CANDIDATE_B456[0], "tree": CANDIDATE_B456[1], "archive_sha256": CANDIDATE_B456[2], "archive_bytes": CANDIDATE_B456[3]},
        "upstream": {"commit": UPSTREAM[0], "tree": UPSTREAM[1], "archive_sha256": UPSTREAM[2], "archive_bytes": UPSTREAM[3]},
        "instrumentation": patch_receipt,
        "matlab_release": "R2024b",
        "vectors": list(VECTORS),
        "records": records,
        "claims": {"array_digest_identity": all(item["comparison"]["array_digest_identity"] for item in records), "scalar_parity": all(item["comparison"]["scalar_passed"] for item in records), "performance_acceptance": False},
        "non_claims": ["not_release", "not_full_erl_result_graph", "not_warning_catalog", "not_instrumented_matlab_performance", "not_channel_s_parameter_fit"],
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"report_sha256": digest(args.report), "array_digest_identity": report["claims"]["array_digest_identity"], "scalar_parity": report["claims"]["scalar_parity"]}))
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--engine-worker":
        _engine_worker(sys.argv[2])
    else:
        raise SystemExit(main())
