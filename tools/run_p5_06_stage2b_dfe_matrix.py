"""Run one bounded, immutable P5-06 Stage 2b DFE checkpoint replay.

The runner is deliberately additive to the accepted scalar matrix.  It uses a
pre-tooling product candidate and emits no full MATLAB result graph or new
Rust product API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import secrets
import time
from pathlib import Path

try:
    from .run_p5_06_original13_fresh_matrix import (
        ADAPTER, CHANNELS, CONFIG_PATHS, METRICS, PROJECTION_SOURCES, UPSTREAM, bounded, canonical, digest,
        first_difference, inventory, materialize, prepare_matlab_engine, runtime_projection,
        tool_receipt, worker_environment,
    )
    from .project_p5_06_stage2b_dfe import project_matlab_summary, project_rust_result_raw
    from .run_p5_06_stage2b_dfe_shape_probe import dfe_engine_worker
except ImportError:
    from run_p5_06_original13_fresh_matrix import (
        ADAPTER, CHANNELS, CONFIG_PATHS, METRICS, PROJECTION_SOURCES, UPSTREAM, bounded, canonical, digest,
        first_difference, inventory, materialize, prepare_matlab_engine, runtime_projection,
        tool_receipt, worker_environment,
    )
    from project_p5_06_stage2b_dfe import project_matlab_summary, project_rust_result_raw
    from run_p5_06_stage2b_dfe_shape_probe import dfe_engine_worker


CANDIDATE = (
    "83e9cb6c264ca728d4147d8e4b19d75ee3c01ec5",
    "49dbc479a42a7cdbe068a624e28e7582b0795269",
    "a3004fb29ef29439684af10f2c4fd58bf742f59d54fc8299a3a5cc02f86645ab",
    57098240,
)
SCHEMA = "sipi.p5-06.stage2b-dfe-checkpoint-run.v1"
TIMING_SCOPE = "model-subprocess-only:engine-start-run-quit-or-rust-run-write"
RAYON_THREADS = 16
MATLAB_RELEASE = "R2024b"
MATLAB_RECEIPT = {
    "role": "matlab", "executable": "matlab.exe",
    "file_sha256": "4b0fcf8112211ad1ae6ef5e51df0801d7afbe89c4daaac45473a46e1de16e633",
    "version_sha256": "905d468be26f24d87d64d17df71a8cb26c7131cb7601192a01365311bc6824ca",
    "path_redacted": True, "release": MATLAB_RELEASE,
    "launch_mode": "python_engine_per_workbook_noFigureWindows_singleCompThread",
}
HARNESS = Path(__file__).with_name("sipi_com_dfe_checkpoint_oracle_v1.m")


def require_archive(path: Path, identity: tuple[str, str, str, int]) -> None:
    if not path.is_file() or path.stat().st_size != identity[3] or digest(path) != identity[2]:
        raise RuntimeError("archive identity drift")


def file_identity(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise RuntimeError(f"gate tool missing: {path.name}")
    return {"path": f"tools/{path.name}", "bytes": path.stat().st_size, "sha256": digest(path)}


def host_fingerprint() -> str:
    # This remains path-free and is deliberately coarse: it only prevents
    # mixing measurements from materially different local execution hosts.
    value = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "logical_cpus": os.cpu_count(),
        "thread_policy": f"rayon-explicit-{RAYON_THREADS}",
        "timing_clock": "perf_counter_ns",
    }
    return hashlib.sha256(canonical(value)).hexdigest()


def require_matlab_r2024b(path: Path) -> dict[str, object]:
    if not path.is_file() or path.name != "matlab.exe" or digest(path) != MATLAB_RECEIPT["file_sha256"]:
        raise RuntimeError("MATLAB R2024b executable identity drift")
    return dict(MATLAB_RECEIPT)


def normalize_metric_value(value: object) -> object:
    if isinstance(value, str):
        return {
            "inf": "+Inf",
            "+inf": "+Inf",
            "-inf": "-Inf",
            "nan": "NaN",
        }.get(value.casefold(), value)
    return value


def metric_values(result: dict) -> list[dict]:
    return [
        {
            name: normalize_metric_value(value)
            for name, value in item.get("metrics", {}).items()
            if name in METRICS
        }
        for item in result.get("cases", [])
    ]


def matlab_metrics(summary: dict) -> list[dict]:
    items = summary.get("case_metrics", [])
    if not isinstance(items, list):
        items = [items]
    values: list[dict] = []
    for item in items:
        output = item.get("output_metrics", {})
        values.append(
            {
                name: (
                    value.get("value")
                    if isinstance(value, dict) and value.get("kind") == "finite"
                    else {"inf": "+Inf", "-inf": "-Inf", "nan": "NaN"}.get(value.get("kind"), value)
                    if isinstance(value, dict)
                    else value
                )
                for name, value in output.items()
                if name in METRICS
            }
        )
    return values


def dfe_scope(document: dict, checkpoints: list[dict], cases_key: str, label: str) -> dict[str, int]:
    """Account for every bounded source result without widening Stage 2b.

    The projector has already fail-closed each inapplicable ERL-only case.
    This helper merely keeps those declared exclusions visible in the replay
    record, instead of treating an empty eligible set as a failed process.
    """
    cases = document.get(cases_key)
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{label} result has no bounded cases")
    if len(checkpoints) > len(cases):
        raise ValueError(f"{label} DFE checkpoint count exceeds result cases")
    return {
        "eligible_case_count": len(checkpoints),
        "inapplicable_erl_only_case_count": len(cases) - len(checkpoints),
    }


def unused_stage2a_worker(spec_path: str) -> None:
    """Retained only to avoid altering the copied Stage 2a implementation."""
    import numpy as np
    from scipy.io import savemat
    import matlab.engine
    from agent_com.config import ComConfig, ComSettings
    from agent_com.config.consumption import _IMPLEMENTED_OPTIONS, _IMPLEMENTED_PARAMETERS

    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    config, mat, output = Path(spec["config"]), Path(spec["mat"]), Path(spec["output"])
    settings = ComSettings.from_xlsx(config)
    rows = settings.rows
    columns = max(len(row) for row in rows)
    parameter = np.empty((len(rows), columns), dtype=object)
    slots = []
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
    logical = {"shape": [len(rows), columns], "slots": slots}
    savemat(mat, {"parameter": parameter}, do_compression=False, oned_as="row")
    materialized = ComConfig.from_xlsx(config).materialize()
    raw = {"parameters": dict(materialized.parameters), "options": dict(materialized.options)}
    pinned = runtime_projection(raw, _IMPLEMENTED_PARAMETERS, _IMPLEMENTED_OPTIONS)
    if not HARNESS.is_file():
        raise RuntimeError("DFE MATLAB harness missing")
    engine = matlab.engine.start_matlab("-noFigureWindows -singleCompThread")
    try:
        engine.cd(str(output.parent), nargout=0)
        engine.addpath(str(HARNESS.parent), nargout=0)
        engine.sipi_com_dfe_checkpoint_oracle_v1(
            spec["upstream"], str(mat), str(output), float(1), float(1), spec["run_nonce"], *spec["channels"], nargout=0
        )
    finally:
        engine.quit()
    result = {
        "parameter_shape": logical["shape"],
        "parameter_slot_digest": hashlib.sha256(canonical(logical)).hexdigest(),
        "parameter_mat_bytes": mat.stat().st_size,
        "parameter_mat_sha256": digest(mat),
        "projection_parameters": sorted(_IMPLEMENTED_PARAMETERS),
        "projection_options": sorted(_IMPLEMENTED_OPTIONS),
        "pinned_materialized": pinned,
        "pinned_materialized_sha256": hashlib.sha256(canonical(pinned)).hexdigest(),
    }
    Path(spec["worker_result"]).write_text(json.dumps(result, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("matlab", "rust"), required=True)
    parser.add_argument("--upstream-archive", type=Path, required=True)
    parser.add_argument("--candidate-archive", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--matlab", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--workbook-index", type=int, action="append", help="diagnostic subset only; repeat for more than one workbook")
    args = parser.parse_args()
    if args.report.exists() or args.output_root.exists():
        raise FileExistsError("report or output root already exists")
    require_archive(args.upstream_archive, UPSTREAM)
    require_archive(args.candidate_archive, CANDIDATE)
    selected_indices = tuple(range(len(CONFIG_PATHS))) if args.workbook_index is None else tuple(sorted(set(args.workbook_index)))
    if not selected_indices or any(index < 0 or index >= len(CONFIG_PATHS) for index in selected_indices):
        raise ValueError("workbook index outside original-13 matrix")
    if os.cpu_count() is None or os.cpu_count() < RAYON_THREADS:
        raise RuntimeError("host cannot honor the fixed Rayon thread policy")

    args.output_root.mkdir(parents=True)
    candidate = args.output_root / "candidate-source"
    source = args.output_root / "upstream-source"
    materialize(args.candidate_archive, candidate)
    materialize(args.upstream_archive, source)
    candidate_before = inventory(candidate)
    source_before = inventory(source)

    target = args.output_root / "candidate-target"
    build_env = os.environ.copy()
    build_env["CARGO_TARGET_DIR"] = str(target)
    build_env["RUSTC"] = str(args.rustc)
    build_env.pop("RUSTC_WRAPPER", None)
    build_env.pop("RUSTC_WORKSPACE_WRAPPER", None)
    build = bounded(
        [
            str(args.cargo),
            "build",
            "--release",
            "--locked",
            "--manifest-path",
            str(candidate / "crates/sipi-agent-com-direct/Cargo.toml"),
            "--bin",
            "sipi-com-direct-run",
            "--bin",
            "sipi-com-direct-config-validate",
        ],
        candidate,
        1800,
        build_env,
    )
    if build.returncode or inventory(candidate) != candidate_before:
        raise RuntimeError("candidate build failed or modified archive")
    rust_binary = target / "release" / "sipi-com-direct-run.exe"
    rust_config = target / "release" / "sipi-com-direct-config-validate.exe"
    if not rust_binary.is_file() or not rust_config.is_file():
        raise RuntimeError("candidate binary missing")

    environment = args.output_root / "python-env"
    sync_env = os.environ.copy()
    sync_env["UV_PROJECT_ENVIRONMENT"] = str(environment)
    sync = bounded(
        [str(args.uv), "sync", "--frozen", "--offline", "--no-install-project", "--python", str(args.python)],
        source,
        300,
        sync_env,
    )
    worker_python = environment / "Scripts" / "python.exe"
    if sync.returncode or not worker_python.is_file():
        raise RuntimeError("pinned Python environment failed")
    engine_site = prepare_matlab_engine(worker_python, args.uv, args.matlab, args.output_root) if args.engine == "matlab" else None

    toolchain = {
        "cargo": tool_receipt(args.cargo, "cargo"),
        "rustc": tool_receipt(args.rustc, "rustc"),
        "uv": tool_receipt(args.uv, "uv"),
        "matlab": require_matlab_r2024b(args.matlab),
        "python": tool_receipt(args.python, "python"),
    }
    nonce = secrets.token_hex(32)
    root_id = secrets.token_hex(32)
    records = []
    started_ns = time.perf_counter_ns()
    for index in selected_indices:
        relative_config = CONFIG_PATHS[index]
        case_root = args.output_root / f"case-{index:02d}"
        case_root.mkdir()
        upstream = case_root / "upstream-source"
        materialize(args.upstream_archive, upstream)
        before = inventory(upstream)
        config = upstream / relative_config
        channels = [(role, upstream / path) for role, path, _, _ in CHANNELS]
        if args.engine == "rust":
            output = case_root / "rust"
            command = [
                str(rust_binary), "run", "--config", str(config), "--thru", str(channels[0][1]),
                "--fext", str(channels[1][1]), "--next", str(channels[2][1]), "--output-dir", str(output),
            ]
            timing_start = time.perf_counter_ns()
            run_env = os.environ.copy()
            run_env["RAYON_NUM_THREADS"] = str(RAYON_THREADS)
            run = bounded(command, upstream, args.timeout, run_env)
            execution_wall_ns = time.perf_counter_ns() - timing_start
            result_path = output / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8")) if run.returncode == 0 and result_path.is_file() else None
            checkpoints = project_rust_result_raw(result) if result is not None else []
            scope = dfe_scope(result, checkpoints, "cases", "Rust") if result is not None else None
            metrics = [item["final_scalar_metrics"] for item in checkpoints]
            materialization = {"comparison": "not_run_for_rust_result_replay"}
        else:
            output = case_root / "matlab"
            output.mkdir()
            spec_path = case_root / "engine-spec.json"
            worker_result = case_root / "engine-result.json"
            spec = {
                "upstream": str(upstream), "config": str(config), "mat": str(case_root / "parameter.mat"),
                "output": str(output), "channels": [str(path) for _, path in channels],
                "worker_result": str(worker_result), "run_nonce": secrets.token_hex(32),
            }
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            timing_start = time.perf_counter_ns()
            run = bounded(
                [str(worker_python), str(Path(__file__).resolve()), "--engine-worker", str(spec_path)],
                case_root,
                args.timeout,
                worker_environment(upstream, engine_site),
            )
            execution_wall_ns = time.perf_counter_ns() - timing_start
            summary_path = output / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8")) if run.returncode == 0 and summary_path.is_file() and worker_result.is_file() else None
            if summary is not None and summary.get("matlab_release") != "2024b":
                raise RuntimeError("MATLAB Engine did not report R2024b")
            checkpoints = project_matlab_summary(summary) if summary is not None else []
            scope = dfe_scope(summary, checkpoints, "case_checkpoints", "MATLAB") if summary is not None else None
            metrics = [item["final_scalar_metrics"] for item in checkpoints]
            materialization = {"comparison": "bound_by_current_stage1_v4_scalar_replay"}
        source_unchanged = inventory(upstream) == before
        status = "passed" if run.returncode == 0 and scope is not None and source_unchanged and materialization.get("comparison") != "drift" else "failed"
        size, sha = before[relative_config]
        records.append({
            "workbook_index": index, "workbook": {"path": relative_config, "bytes": size, "sha256": sha},
            "status": status, "exit_code": run.returncode, "timed_out": bool(getattr(run, "timed_out", False)),
            "execution_wall_ns": execution_wall_ns, "timing_scope": TIMING_SCOPE,
            "detail_sha256": hashlib.sha256(run.stderr).hexdigest(), "source_inventory_unchanged": source_unchanged,
            "config_materialization": materialization, "case_count": len(checkpoints), "metrics": metrics,
            "dfe_checkpoints": checkpoints, "dfe_scope": scope,
        })
    if inventory(source) != source_before:
        raise RuntimeError("upstream preparation archive drift")
    report = {
        "schema": SCHEMA, "engine": args.engine, "run_id": f"original13-stage2b-dfe-{args.engine}-{nonce}", "nonce": nonce,
        "root_id": root_id,
        "status": (
            "fresh_matrix_run" if len(selected_indices) == len(CONFIG_PATHS) and all(record["status"] == "passed" for record in records)
            else "diagnostic_subset" if all(record["status"] == "passed" for record in records)
            else "failed_matrix_run"
        ),
        "timing_clock": "perf_counter_ns", "timing_scope": TIMING_SCOPE, "total_execution_wall_ns": sum(record["execution_wall_ns"] for record in records),
        "host_fingerprint": host_fingerprint(),
        "thread_policy": {"rust_rayon_num_threads": RAYON_THREADS, "matlab_launch_mode": MATLAB_RECEIPT["launch_mode"]},
        "selection_count": len(records),
        "source": {
            "upstream": {"commit": UPSTREAM[0], "tree": UPSTREAM[1], "archive_sha256": UPSTREAM[2], "archive_bytes": UPSTREAM[3]},
            "candidate": {"commit": CANDIDATE[0], "tree": CANDIDATE[1], "archive_sha256": CANDIDATE[2], "archive_bytes": CANDIDATE[3]},
            "rust_binary": {"bytes": rust_binary.stat().st_size, "sha256": digest(rust_binary)},
            "toolchain": toolchain,
            "gate_tools": {
                "runner": file_identity(Path(__file__)),
                "matlab_harness": file_identity(HARNESS),
                "projection": file_identity(Path(__file__).with_name("project_p5_06_stage2b_dfe.py")),
            },
        },
        "channels": [{"role": role, "path": path, "bytes": size, "sha256": sha} for role, path, size, sha in CHANNELS],
        "records": records,
        "claims": {"acceptance": False, "stage2b_dfe_numeric_parity": False, "release": False, "s_parameter_fit": False, "one_final_fd_to_td_impulse": True},
    }
    if time.perf_counter_ns() < started_ns:
        raise RuntimeError("monotonic timing clock drift")
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"report_sha256": digest(args.report), "status": report["status"], "cases": sum(record["case_count"] for record in records)}))
    return 0


if __name__ == "__main__":
    if len(os.sys.argv) == 3 and os.sys.argv[1] == "--engine-worker":
        dfe_engine_worker(os.sys.argv[2])
    else:
        raise SystemExit(main())
