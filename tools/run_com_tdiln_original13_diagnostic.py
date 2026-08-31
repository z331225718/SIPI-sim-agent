"""Run the original 13 COM workbooks through MATLAB and direct Rust TDILN.

This runner is intentionally diagnostic-only.  It is a practical matrix
expander for the checked-in TDILN comparison gate, not immutable replay or
release evidence.  It keeps MATLAB startup outside MATLAB's source-core timer
and measures the complete Rust process invocation, including artifact write.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

try:
    from tools.compare_com_tdiln_matrix_diagnostic import compare
    from tools.compare_com_tdiln_sidecars import compare_sidecars
    from tools.run_p5_06_original13_fresh_matrix import (
        CONFIG_PATHS,
        bounded,
        digest,
        prepare_matlab_engine,
    )
except ImportError:
    from compare_com_tdiln_matrix_diagnostic import compare
    from compare_com_tdiln_sidecars import compare_sidecars
    from run_p5_06_original13_fresh_matrix import (
        CONFIG_PATHS,
        bounded,
        digest,
        prepare_matlab_engine,
    )


def _parse_indices(value: str | None) -> tuple[int, ...]:
    if value is None:
        return tuple(range(len(CONFIG_PATHS)))
    try:
        parsed = tuple(sorted({int(item) for item in value.split(",") if item.strip()}))
    except ValueError as error:
        raise argparse.ArgumentTypeError("indices must be comma-separated integers") from error
    if not parsed or any(index < 0 or index >= len(CONFIG_PATHS) for index in parsed):
        raise argparse.ArgumentTypeError("index is outside the original-13 corpus")
    return parsed


def _engine_worker(spec_path: str) -> None:
    import numpy as np
    from scipy.io import savemat
    import matlab.engine
    from agent_com.config import ComSettings

    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    config = Path(spec["config"])
    mat = Path(spec["parameter_mat"])
    output = Path(spec["output"])
    harness = Path(spec["harness"])
    settings = ComSettings.from_xlsx(config)
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
    savemat(mat, {"parameter": parameter}, do_compression=False, oned_as="row")
    engine = matlab.engine.start_matlab("-noFigureWindows -singleCompThread")
    try:
        engine.cd(str(output.parent), nargout=0)
        engine.addpath(str(harness.parent), nargout=0)
        engine.sipi_com_tdiln_matrix_diagnostic_v1(
            spec["source_root"],
            str(mat),
            str(output),
            float(1),
            float(1),
            spec["nonce"],
            *spec["channels"],
            "OP.COMPUTE_TDILN",
            "1",
            nargout=0,
        )
    finally:
        engine.quit()


def _run_engine_worker(worker_python: Path, specification: dict[str, Any], cwd: Path, environment: dict[str, str], timeout: int) -> subprocess.CompletedProcess[bytes]:
    spec_path = cwd / "engine-spec.json"
    spec_path.write_text(json.dumps(specification, sort_keys=True), encoding="utf-8")
    return bounded([str(worker_python), str(Path(__file__).resolve()), "--engine-worker", str(spec_path)], cwd, timeout, environment)


def _worker_environment(source_root: Path, engine_site: Path, preference_dir: Path) -> dict[str, str]:
    """Isolate every MATLAB Engine invocation, including its preferences.

    The historical original-13 helper uses a source-root-adjacent preference
    directory and intentionally creates it once.  A matrix runner invokes it
    repeatedly, so it needs a fresh case-local directory instead.
    """
    preference_dir.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join((str(engine_site), str(source_root / "src")))
    environment["MATLAB_PREFDIR"] = str(preference_dir)
    environment["MW_DISABLE_CONNECTOR"] = "1"
    return environment


_PACKAGE_CASE_TEMP_ROOT = re.compile(r"sipi-com-package-cases-\d+-[0-9a-f]{64}", re.IGNORECASE)


def _stable_result_value(value: Any) -> Any:
    """Replace only the process-specific package staging root in result receipts."""
    if isinstance(value, str):
        return _PACKAGE_CASE_TEMP_ROOT.sub("sipi-com-package-cases-<process>-<config>", value)
    if isinstance(value, list):
        return [_stable_result_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _stable_result_value(item) for key, item in value.items()}
    return value


def _stable_result_sha256(path: Path) -> str:
    document = json.loads(path.read_text(encoding="utf-8"))
    payload = json.dumps(_stable_result_value(document), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _run_rust(
    binary: Path,
    workbook: Path,
    channels: list[Path],
    output: Path,
    timeout: int,
    rayon_threads: int,
    sidecar_root: Path | None,
    cwd: Path,
) -> tuple[subprocess.CompletedProcess[bytes], float]:
    environment = os.environ.copy()
    environment["RAYON_NUM_THREADS"] = str(rayon_threads)
    if sidecar_root is not None:
        environment["SIPI_COM_TDILN_DIAGNOSTIC_SIDECAR_DIR"] = str(sidecar_root)
    else:
        environment.pop("SIPI_COM_TDILN_DIAGNOSTIC_SIDECAR_DIR", None)
    start = time.perf_counter()
    completed = bounded(
        [
            str(binary), "run", "--config", str(workbook), "--thru", str(channels[0]),
            "--fext", str(channels[1]), "--next", str(channels[2]),
            "--override", "COMPUTE_TDILN=1", "--output-dir", str(output),
        ],
        cwd,
        timeout,
        environment,
    )
    return completed, time.perf_counter() - start


def _record(index: int, source_root: Path, binary: Path, performance_binary: Path | None, worker_python: Path, engine_site: Path, harness: Path, output_root: Path, timeout: int, rayon_threads: int, require_tdiln_sidecars: bool) -> dict[str, Any]:
    workbook = source_root / CONFIG_PATHS[index]
    channels = [
        source_root / "fixtures" / "synthetic" / name
        for name in ("thru_10db_at_26p56ghz.s4p", "fext_m40db_at_26p56ghz.s4p", "next_m40db_at_26p56ghz.s4p")
    ]
    if not workbook.is_file() or any(not path.is_file() for path in channels):
        raise FileNotFoundError(f"original-13 input missing for index {index}")
    case_root = output_root / f"case-{index:02d}"
    case_root.mkdir()
    matlab_output = case_root / "matlab"
    matlab_output.mkdir()
    nonce = secrets.token_hex(32)
    worker_spec = {
        "source_root": str(source_root),
        "config": str(workbook),
        "parameter_mat": str(case_root / "parameter.mat"),
        "output": str(matlab_output),
        "harness": str(harness),
        "nonce": nonce,
        "channels": [str(path) for path in channels],
    }
    matlab_run = _run_engine_worker(
        worker_python,
        worker_spec,
        case_root,
        _worker_environment(source_root, engine_site, case_root / "matlab-pref"),
        timeout,
    )
    matlab_summary_path = matlab_output / "summary.json"
    if matlab_run.returncode != 0 or not matlab_summary_path.is_file():
        return {
            "workbook_index": index,
            "workbook": CONFIG_PATHS[index],
            "status": "matlab_failed",
            "matlab_exit_code": matlab_run.returncode,
            "matlab_detail_sha256": hashlib.sha256(matlab_run.stdout + matlab_run.stderr).hexdigest(),
        }
    rust_output = case_root / "rust-diagnostic"
    rust_run, rust_diagnostic_wall_seconds = _run_rust(
        binary,
        workbook,
        channels,
        rust_output,
        timeout,
        rayon_threads,
        (case_root / "rust-tdiln-sidecar") if require_tdiln_sidecars else None,
        source_root,
    )
    rust_result_path = rust_output / "result.json"
    if rust_run.returncode != 0 or not rust_result_path.is_file():
        return {
            "workbook_index": index,
            "workbook": CONFIG_PATHS[index],
            "status": "rust_failed",
            "matlab_exit_code": matlab_run.returncode,
            "rust_exit_code": rust_run.returncode,
            "rust_diagnostic_wall_seconds": rust_diagnostic_wall_seconds,
            "rust_detail_sha256": hashlib.sha256(rust_run.stdout + rust_run.stderr).hexdigest(),
        }
    rust_diagnostic_result_sha256 = digest(rust_result_path)
    rust_diagnostic_result_semantic_sha256 = _stable_result_sha256(rust_result_path)
    rust_performance_result_sha256 = rust_diagnostic_result_sha256
    rust_performance_result_semantic_sha256 = rust_diagnostic_result_semantic_sha256
    rust_wall_seconds = rust_diagnostic_wall_seconds
    rust_timing_scope = "Rust diagnostic process invocation plus normal artifact write; MATLAB reports source COM core after engine startup."
    if performance_binary is not None:
        performance_output = case_root / "rust-performance"
        performance_run, rust_wall_seconds = _run_rust(
            performance_binary,
            workbook,
            channels,
            performance_output,
            timeout,
            rayon_threads,
            None,
            source_root,
        )
        performance_result = performance_output / "result.json"
        if performance_run.returncode != 0 or not performance_result.is_file():
            return {
                "workbook_index": index,
                "workbook": CONFIG_PATHS[index],
                "status": "rust_performance_failed",
                "matlab_exit_code": matlab_run.returncode,
                "rust_diagnostic_exit_code": rust_run.returncode,
                "rust_performance_exit_code": performance_run.returncode,
                "rust_wall_seconds": rust_wall_seconds,
                "rust_detail_sha256": hashlib.sha256(performance_run.stdout + performance_run.stderr).hexdigest(),
            }
        rust_performance_result_sha256 = digest(performance_result)
        rust_performance_result_semantic_sha256 = _stable_result_sha256(performance_result)
        if rust_performance_result_semantic_sha256 != rust_diagnostic_result_semantic_sha256:
            return {
                "workbook_index": index,
                "workbook": CONFIG_PATHS[index],
                "status": "rust_build_result_drift",
                "rust_diagnostic_result_sha256": rust_diagnostic_result_sha256,
                "rust_performance_result_sha256": rust_performance_result_sha256,
                "rust_diagnostic_result_semantic_sha256": rust_diagnostic_result_semantic_sha256,
                "rust_performance_result_semantic_sha256": rust_performance_result_semantic_sha256,
            }
        rust_timing_scope = "Rust default-production process invocation plus normal artifact write; opt-in TDILN sidecar I/O is excluded. MATLAB reports source COM core after engine startup."
    matlab_document = json.loads(matlab_summary_path.read_text(encoding="utf-8"))
    rust_document = json.loads(rust_result_path.read_text(encoding="utf-8"))
    comparison = compare(
        matlab_document,
        rust_document,
        rust_wall_seconds=rust_wall_seconds,
        tolerance=1.0e-9,
        rust_timing_scope=rust_timing_scope,
    )
    if require_tdiln_sidecars:
        sidecar = compare_sidecars(
            matlab_output / "tdiln-sidecar",
            case_root / "rust-tdiln-sidecar",
            int(comparison["case_count"]),
        )
        comparison["tdiln_array_sidecars"] = sidecar
        if sidecar["status"] != "passed_diagnostic":
            comparison["status"] = "blocked"
    return {
        "workbook_index": index,
        "workbook": CONFIG_PATHS[index],
        "status": comparison["status"],
        "matlab_summary_sha256": digest(matlab_summary_path),
        "rust_result_sha256": rust_diagnostic_result_sha256,
        "rust_result_semantic_sha256": rust_diagnostic_result_semantic_sha256,
        "rust_performance_result_sha256": rust_performance_result_sha256,
        "rust_performance_result_semantic_sha256": rust_performance_result_semantic_sha256,
        "rust_diagnostic_wall_seconds": rust_diagnostic_wall_seconds,
        "comparison": comparison,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="pinned Agent-COM source checkout")
    parser.add_argument("--rust-binary", type=Path, required=True)
    parser.add_argument("--performance-rust-binary", type=Path, help="default-production Rust binary used for the hard speed gate")
    parser.add_argument("--matlab", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True, help="Python used for the frozen Agent-COM environment")
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--harness", type=Path, help="pinned TDILN MATLAB harness; defaults to this checkout's diagnostic harness")
    parser.add_argument("--indices", help="comma-separated original-13 indices; default runs all")
    parser.add_argument("--rayon-threads", type=int, default=1)
    parser.add_argument("--require-tdiln-sidecars", action="store_true", help="require the opt-in full-array diagnostic receipts")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    if args.output.exists() or not args.source_root.is_dir() or not args.rust_binary.is_file() or (args.performance_rust_binary is not None and not args.performance_rust_binary.is_file()) or not args.matlab.is_file() or args.rayon_threads <= 0:
        raise ValueError("invalid output/source/tool/thread request")
    indices = _parse_indices(args.indices)
    harness = args.harness or Path(__file__).with_name("sipi_com_tdiln_matrix_diagnostic_v1.m")
    if not harness.is_file():
        raise FileNotFoundError("TDILN MATLAB harness missing")
    args.output.mkdir(parents=True)
    environment = args.output / "python-env"
    sync_env = os.environ.copy()
    sync_env["UV_PROJECT_ENVIRONMENT"] = str(environment)
    sync = bounded([str(args.uv), "sync", "--frozen", "--offline", "--no-install-project", "--python", str(args.python)], args.source_root, 300, sync_env)
    worker_python = environment / "Scripts" / "python.exe"
    if sync.returncode != 0 or not worker_python.is_file():
        raise RuntimeError("frozen Agent-COM Python environment failed")
    engine_site = prepare_matlab_engine(worker_python, args.uv, args.matlab, args.output)
    records = []
    for index in indices:
        try:
            records.append(_record(index, args.source_root, args.rust_binary, args.performance_rust_binary, worker_python, engine_site, harness, args.output, args.timeout, args.rayon_threads, args.require_tdiln_sidecars))
        except Exception as error:  # keep the rest of the matrix observable
            records.append({"workbook_index": index, "workbook": CONFIG_PATHS[index], "status": "runner_failed", "error_type": type(error).__name__, "error_sha256": hashlib.sha256(str(error).encode()).hexdigest()})
    passed = all(record["status"] == "passed_diagnostic" for record in records)
    report = {
        "schema": "sipi.com.tdiln-original13-diagnostic.v1",
        "diagnostic_only": True,
        "non_claims": ["not_immutable_replay", "not_release_evidence", "not_complete_warning_catalog"],
        "source_commit_unverified": True,
        "rust_binary_sha256": digest(args.rust_binary),
        "performance_rust_binary_sha256": digest(args.performance_rust_binary) if args.performance_rust_binary is not None else None,
        "performance_gate_binary": "default_production" if args.performance_rust_binary is not None else "diagnostic_binary",
        "matlab_harness_sha256": digest(harness),
        "matlab_launch": "python_engine_noFigureWindows_singleCompThread",
        "rayon_threads": args.rayon_threads,
        "tdiln_array_sidecars_required": args.require_tdiln_sidecars,
        "records": records,
        "status": "passed_diagnostic" if passed else "blocked",
    }
    (args.output / "report.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"], "records": len(records)}))
    return 0 if passed else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--engine-worker":
        _engine_worker(sys.argv[2])
    else:
        raise SystemExit(main())
