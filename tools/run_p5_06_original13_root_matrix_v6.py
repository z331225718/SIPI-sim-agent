"""Run the immutable original-13 matrix through the public root COM CLI.

This is the current R2024b acceptance runner.  It deliberately supersedes
neither the historical v1/v2 report schemas nor their evidence.  Its candidate
is an earlier immutable product commit.  Rust timing starts immediately before
the root `sipi com run` process and ends after its receipt is validated and the
owned result artifact is read.  That deliberately measures the deployable
surface, not a private direct-port binary.
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
except ImportError:
    from run_p5_06_original13_fresh_matrix import (
        ADAPTER, CHANNELS, CONFIG_PATHS, METRICS, PROJECTION_SOURCES, UPSTREAM, bounded, canonical, digest,
        first_difference, inventory, materialize, prepare_matlab_engine, runtime_projection,
        tool_receipt, worker_environment,
    )


CANDIDATE = (
    "b9b195a19d3d209a37a52ba29c730759361dba03",
    "becca5842b55eeb1d1a310b2c3174458936ec901",
    "4e40155745d439a721e0f9923a36a60c9daf2404ff24f574b12a4fd7d425a8a2",
    58705920,
)
SCHEMA = "sipi.p5-06.original13-root-matrix.v6"
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
WORKER = Path(__file__).with_name("run_p5_06_original13_fresh_matrix.py")
HARNESS = Path(__file__).with_name("sipi_com_final_surface_oracle_v3.m")
ROOT_MANIFEST = "crates/sipi-cli/Cargo.toml"
ROOT_BINARY = "sipi.exe"
ROOT_RECEIPT_SCHEMA = "sipi.com.r480-cli-receipt.v1"


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


def read_root_receipt(stdout: bytes, output: Path) -> dict:
    """Check the public response and its three content-addressed artifacts."""
    response = json.loads(stdout)
    if set(response) != {"schema", "protocol", "command", "request_id", "status", "result", "diagnostic_count"}:
        raise RuntimeError("root response envelope")
    receipt = response["result"]
    if (
        response["schema"] != "sipi.cli.response.v1"
        or response["protocol"] != 1
        or response["command"] != "com"
        or response["request_id"] is not None
        or response["status"] != "ok"
        or response["diagnostic_count"] != 0
        or not isinstance(receipt, dict)
    ):
        raise RuntimeError("root response status")
    expected = {"schema", "status", "profile", "case_count", "warning_count", "config_sha256", "impulse_sha256", "artifacts"}
    if set(receipt) != expected or receipt["schema"] != ROOT_RECEIPT_SCHEMA or receipt["status"] != "completed" or receipt["profile"] != "r4.80":
        raise RuntimeError("root receipt")
    artifacts = receipt["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        raise RuntimeError("root receipt artifacts")
    expected_names = {"result.json", "report.html", "diagnostics.json"}
    seen = set()
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"name", "sha256", "byte_length"}:
            raise RuntimeError("root artifact receipt shape")
        name = item["name"]
        if name not in expected_names or name in seen or not isinstance(item["byte_length"], int) or item["byte_length"] <= 0:
            raise RuntimeError("root artifact receipt name")
        path = output / name
        if not path.is_file() or path.stat().st_size != item["byte_length"] or digest(path) != item["sha256"]:
            raise RuntimeError("root artifact receipt content")
        seen.add(name)
    if seen != expected_names:
        raise RuntimeError("root artifact receipt set")
    return receipt


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
    if os.cpu_count() is None or os.cpu_count() < RAYON_THREADS:
        raise RuntimeError("host cannot honor the fixed Rayon thread policy")
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
    root_build = bounded(
        [
            str(args.cargo),
            "build",
            "--release",
            "--locked",
            "--manifest-path",
            str(candidate / ROOT_MANIFEST),
            "--features",
            "com-direct-integration",
            "--bin",
            "sipi",
        ],
        candidate,
        1800,
        build_env,
    )
    config_build = bounded(
        [
            str(args.cargo),
            "build",
            "--release",
            "--locked",
            "--manifest-path",
            str(candidate / "crates/sipi-agent-com-direct/Cargo.toml"),
            "--bin",
            "sipi-com-direct-config-validate",
        ],
        candidate,
        1800,
        build_env,
    )
    if root_build.returncode or config_build.returncode or inventory(candidate) != candidate_before:
        raise RuntimeError("candidate build failed or modified archive")
    rust_binary = target / "release" / ROOT_BINARY
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
                str(rust_binary), "com", "run", "--config", str(config), "--thru", str(channels[0][1]),
                "--fext", str(channels[1][1]), "--next", str(channels[2][1]), "--output-dir", str(output),
            ]
            timing_start = time.perf_counter_ns()
            run_env = os.environ.copy()
            run_env["RAYON_NUM_THREADS"] = str(RAYON_THREADS)
            run = bounded(command, upstream, args.timeout, run_env)
            result_path = output / "result.json"
            receipt = read_root_receipt(run.stdout, output) if run.returncode == 0 else None
            metrics = metric_values(json.loads(result_path.read_text(encoding="utf-8"))) if receipt is not None and result_path.is_file() else []
            execution_wall_ns = time.perf_counter_ns() - timing_start
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
            summary_path = output / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8")) if run.returncode == 0 and summary_path.is_file() and worker_result.is_file() else None
            if summary is not None and summary.get("matlab_release") != "2024b":
                raise RuntimeError("MATLAB Engine did not report R2024b")
            metrics = matlab_metrics(summary) if summary is not None else []
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
        record = {
            "workbook_index": index, "workbook": {"path": relative_config, "bytes": size, "sha256": sha},
            "status": status, "exit_code": run.returncode, "timed_out": bool(getattr(run, "timed_out", False)),
            "execution_wall_ns": execution_wall_ns, "timing_scope": TIMING_SCOPE,
            "detail_sha256": hashlib.sha256(run.stderr).hexdigest(), "source_inventory_unchanged": source_unchanged,
            "config_materialization": materialization, "case_count": len(metrics), "metrics": metrics,
        }
        if args.engine == "rust":
            record["root_cli_receipt"] = receipt
        records.append(record)
    if inventory(source) != source_before:
        raise RuntimeError("upstream preparation archive drift")
    report = {
        "schema": SCHEMA, "engine": args.engine, "run_id": f"original13-root-v6-{args.engine}-{nonce}", "nonce": nonce,
        "root_id": root_id, "status": "fresh_matrix_run" if all(record["status"] == "passed" for record in records) else "failed_matrix_run",
        "timing_clock": "perf_counter_ns", "timing_scope": TIMING_SCOPE, "total_execution_wall_ns": sum(record["execution_wall_ns"] for record in records),
        "host_fingerprint": host_fingerprint(),
        "thread_policy": {"rust_rayon_num_threads": RAYON_THREADS, "matlab_launch_mode": MATLAB_RECEIPT["launch_mode"]},
        "selection_count": len(records),
        "source": {
            "upstream": {"commit": UPSTREAM[0], "tree": UPSTREAM[1], "archive_sha256": UPSTREAM[2], "archive_bytes": UPSTREAM[3]},
            "candidate": {"commit": CANDIDATE[0], "tree": CANDIDATE[1], "archive_sha256": CANDIDATE[2], "archive_bytes": CANDIDATE[3]},
            "root_cli_binary": {"path": "target/release/sipi.exe", "bytes": rust_binary.stat().st_size, "sha256": digest(rust_binary)},
            "root_cli": {"manifest": ROOT_MANIFEST, "feature": "com-direct-integration", "route": ["com", "run"], "receipt_schema": ROOT_RECEIPT_SCHEMA},
            "config_validator_binary": {"path": "target/release/sipi-com-direct-config-validate.exe", "bytes": rust_config.stat().st_size, "sha256": digest(rust_config)},
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
