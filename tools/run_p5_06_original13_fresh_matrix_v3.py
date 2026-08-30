"""Run one full, immutable P5-06s original-13 matrix replay.

This is the current R2024b acceptance runner.  It deliberately supersedes
neither the historical v1/v2 report schemas nor their evidence.  Its candidate
is an earlier immutable product commit, so the later gate commit cannot become
self-referential.
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
        first_difference, inventory, materialize, matlab_receipt, prepare_matlab_engine, runtime_projection,
        tool_receipt, worker_environment,
    )
except ImportError:
    from run_p5_06_original13_fresh_matrix import (
        ADAPTER, CHANNELS, CONFIG_PATHS, METRICS, PROJECTION_SOURCES, UPSTREAM, bounded, canonical, digest,
        first_difference, inventory, materialize, matlab_receipt, prepare_matlab_engine, runtime_projection,
        tool_receipt, worker_environment,
    )


CANDIDATE = (
    "20e1f132a7b3840860270f34f9825bc07d174e63",
    "e1e7291dd3a985610f4198137c4ecde02a6d6466",
    "403050f1a56cb37669cc91c5a6f7d0bb279905c48f2c0f3b77f7c43729bbb3e1",
    56791040,
)
SCHEMA = "sipi.p5-06.original13-fresh-run.v3"
TIMING_SCOPE = "model-subprocess-only:engine-start-run-quit-or-rust-run-write"
MATLAB_RELEASE = "R2024b"
WORKER = Path(__file__).with_name("run_p5_06_original13_fresh_matrix.py")
HARNESS = Path(__file__).with_name("sipi_com_final_surface_oracle_v3.m")


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
        "thread_policy": "default-process-policy",
        "timing_clock": "perf_counter_ns",
    }
    return hashlib.sha256(canonical(value)).hexdigest()


def metric_values(result: dict) -> list[dict]:
    return [
        {name: value for name, value in item.get("metrics", {}).items() if name in METRICS}
        for item in result.get("cases", [])
    ]


def matlab_metrics(case_dir: Path) -> list[dict]:
    summary = json.loads((case_dir / "summary.json").read_text(encoding="utf-8"))
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
    args = parser.parse_args()
    if args.report.exists() or args.output_root.exists():
        raise FileExistsError("report or output root already exists")
    require_archive(args.upstream_archive, UPSTREAM)
    require_archive(args.candidate_archive, CANDIDATE)

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
        "matlab": matlab_receipt(args.matlab, args.python),
        "python": tool_receipt(args.python, "python"),
    }
    if toolchain["matlab"].get("release") != MATLAB_RELEASE:
        raise RuntimeError("R2024b is required for this acceptance runner")
    toolchain["matlab"]["launch_mode"] = "python_engine_per_workbook_noFigureWindows_singleCompThread"
    nonce = secrets.token_hex(32)
    root_id = secrets.token_hex(32)
    records = []
    started_ns = time.perf_counter_ns()
    for index, relative_config in enumerate(CONFIG_PATHS):
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
            run = bounded(command, upstream, args.timeout)
            execution_wall_ns = time.perf_counter_ns() - timing_start
            result_path = output / "result.json"
            metrics = metric_values(json.loads(result_path.read_text(encoding="utf-8"))) if run.returncode == 0 and result_path.is_file() else []
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
                [str(worker_python), str(WORKER), "--engine-worker", str(spec_path)],
                case_root,
                args.timeout,
                worker_environment(upstream, engine_site),
            )
            execution_wall_ns = time.perf_counter_ns() - timing_start
            metrics = matlab_metrics(output) if run.returncode == 0 and (output / "summary.json").is_file() and worker_result.is_file() else []
            materialization = {"comparison": "worker_failed"}
            if worker_result.is_file():
                worker = json.loads(worker_result.read_text(encoding="utf-8"))
                checked = bounded([str(rust_config), "config", "validate", str(config), "--materialized-json"], upstream, 120)
                if checked.returncode:
                    raise RuntimeError("Rust config materialization failed")
                document = json.loads(checked.stdout)
                rust_projection = runtime_projection(document["materialized"], worker["projection_parameters"], worker["projection_options"])
                rust_sha = hashlib.sha256(canonical(rust_projection)).hexdigest()
                equal = rust_sha == worker["pinned_materialized_sha256"]
                materialization = {
                    "comparison": "equal" if equal else "drift",
                    "first_difference": first_difference(worker["pinned_materialized"], rust_projection),
                    "pinned_sha256": worker["pinned_materialized_sha256"], "rust_sha256": rust_sha,
                    "parameter_shape": worker["parameter_shape"], "parameter_slot_digest": worker["parameter_slot_digest"],
                    "parameter_mat_bytes": worker["parameter_mat_bytes"], "parameter_mat_sha256": worker["parameter_mat_sha256"],
                }
            if materialization.get("comparison") == "drift":
                run = type("Run", (), {"returncode": 1, "stderr": b"config materialization drift", "timed_out": False})()
        source_unchanged = inventory(upstream) == before
        status = "passed" if run.returncode == 0 and metrics and source_unchanged and materialization.get("comparison") != "drift" else "failed"
        size, sha = before[relative_config]
        records.append({
            "workbook_index": index, "workbook": {"path": relative_config, "bytes": size, "sha256": sha},
            "status": status, "exit_code": run.returncode, "timed_out": bool(getattr(run, "timed_out", False)),
            "execution_wall_ns": execution_wall_ns, "timing_scope": TIMING_SCOPE,
            "detail_sha256": hashlib.sha256(run.stderr).hexdigest(), "source_inventory_unchanged": source_unchanged,
            "config_materialization": materialization, "case_count": len(metrics), "metrics": metrics,
        })
    if inventory(source) != source_before:
        raise RuntimeError("upstream preparation archive drift")
    report = {
        "schema": SCHEMA, "engine": args.engine, "run_id": f"original13-v3-{args.engine}-{nonce}", "nonce": nonce,
        "root_id": root_id, "status": "fresh_matrix_run" if all(record["status"] == "passed" for record in records) else "failed_matrix_run",
        "timing_clock": "perf_counter_ns", "timing_scope": TIMING_SCOPE, "total_execution_wall_ns": sum(record["execution_wall_ns"] for record in records),
        "host_fingerprint": host_fingerprint(), "selection_count": len(records),
        "source": {
            "upstream": {"commit": UPSTREAM[0], "tree": UPSTREAM[1], "archive_sha256": UPSTREAM[2], "archive_bytes": UPSTREAM[3]},
            "candidate": {"commit": CANDIDATE[0], "tree": CANDIDATE[1], "archive_sha256": CANDIDATE[2], "archive_bytes": CANDIDATE[3]},
            "rust_binary": {"bytes": rust_binary.stat().st_size, "sha256": digest(rust_binary)},
            "toolchain": toolchain,
            "gate_tools": {"runner": file_identity(Path(__file__)), "worker": file_identity(WORKER), "matlab_harness": file_identity(HARNESS)},
        },
        "channels": [{"role": role, "path": path, "bytes": size, "sha256": sha} for role, path, size, sha in CHANNELS],
        "records": records,
        "claims": {"acceptance": False, "performance_acceptance": False, "release": False, "s_parameter_fit": False, "one_final_fd_to_td_impulse": True},
    }
    if time.perf_counter_ns() < started_ns:
        raise RuntimeError("monotonic timing clock drift")
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"report_sha256": digest(args.report), "status": report["status"], "slots": sum(len(case) for record in records for case in record["metrics"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
