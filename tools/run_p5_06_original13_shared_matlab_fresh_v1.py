"""Create one immutable, shared-Engine MATLAB original-13 fresh report.

This is intentionally a new formal schema.  The older v1/v2 runners retain
their per-workbook Engine lifecycle and historical evidence meaning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path

from run_p5_06_original13_fresh_matrix import (
    ADAPTER,
    CANDIDATE,
    CHANNELS,
    CONFIG_PATHS,
    PROJECTION_SOURCES,
    UPSTREAM,
    bounded,
    canonical,
    digest,
    first_difference,
    inventory,
    materialize,
    runtime_projection,
    tool_receipt,
    matlab_receipt,
    worker_environment,
)
from run_p5_06_original13_shared_matlab_diagnostic_v4 import write_json


def require_archive(path: Path, identity: tuple[str, str, str, int]) -> None:
    if not path.is_file() or path.stat().st_size != identity[3] or digest(path) != identity[2]:
        raise RuntimeError("archive identity drift")


def local_tool(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise RuntimeError("formal tool missing")
    return {"path": f"tools/{path.name}", "bytes": path.stat().st_size, "sha256": digest(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-archive", type=Path, required=True)
    parser.add_argument("--candidate-archive", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--matlab", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--order", choices=("forward", "reverse"), required=True)
    parser.add_argument("--timeout", type=int, default=7200)
    args = parser.parse_args()
    if args.report.exists() or args.output_root.exists():
        raise FileExistsError("report or output root already exists")
    require_archive(args.upstream_archive, UPSTREAM)
    require_archive(args.candidate_archive, CANDIDATE)

    args.output_root.mkdir(parents=True)
    source = args.output_root / "upstream-source"
    candidate = args.output_root / "candidate-source"
    materialize(args.upstream_archive, source)
    materialize(args.candidate_archive, candidate)
    source_before = inventory(source)
    candidate_before = inventory(candidate)
    target = args.output_root / "candidate-target"
    build_env = os.environ.copy()
    build_env["CARGO_TARGET_DIR"] = str(target)
    build_env["RUSTC"] = str(args.rustc)
    build_env.pop("RUSTC_WRAPPER", None)
    build_env.pop("RUSTC_WORKSPACE_WRAPPER", None)
    build = bounded(
        [str(args.cargo), "build", "--release", "--locked", "--manifest-path", str(candidate / "crates/sipi-agent-com-direct/Cargo.toml"), "--bin", "sipi-com-direct-config-validate"],
        candidate,
        1800,
        build_env,
    )
    if build.returncode or inventory(candidate) != candidate_before:
        raise RuntimeError("candidate build failed or modified archive")
    validator = target / "release" / "sipi-com-direct-config-validate.exe"
    if not validator.is_file():
        raise RuntimeError("candidate config validator missing")

    environment = args.output_root / "python-env"
    sync_env = os.environ.copy()
    sync_env["UV_PROJECT_ENVIRONMENT"] = str(environment)
    sync = bounded([str(args.uv), "sync", "--frozen", "--offline", "--no-install-project", "--python", str(args.python)], source, 300, sync_env)
    worker_python = environment / "Scripts" / "python.exe"
    if sync.returncode or not worker_python.is_file():
        raise RuntimeError("pinned Python environment failed")

    session_nonce = secrets.token_hex(32)
    case_nonces = [secrets.token_hex(32) for _ in CONFIG_PATHS]
    if len(set(case_nonces)) != len(case_nonces):
        raise RuntimeError("case nonce collision")
    execution_order = list(range(len(CONFIG_PATHS)))
    if args.order == "reverse":
        execution_order.reverse()
    # The worker consumes its configured sequence.  Records remain canonical by workbook index.
    manifest = {
        "root": str(args.output_root / "cases"),
        "source": str(source),
        "nonce": session_nonce,
        "case_nonces": case_nonces,
        "harness": str(Path(__file__).with_name("sipi_com_final_surface_oracle_v3.m")),
        "result": str(args.output_root / "shared-result.json"),
        "execution_order": execution_order,
    }
    manifest_path = args.output_root / "shared-manifest.json"
    write_json(manifest_path, manifest)
    worker = bounded(
        [str(worker_python), str(Path(__file__).with_name("run_p5_06_original13_shared_matlab_diagnostic_v4.py")), "--worker", str(manifest_path)],
        args.output_root,
        args.timeout,
        worker_environment(source, args.matlab),
    )
    raw_path = Path(manifest["result"])
    if worker.returncode or not raw_path.is_file() or inventory(source) != source_before:
        raise RuntimeError("shared MATLAB worker failed or modified source archive")
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    session = raw.get("session", {})
    if raw.get("nonce") != session_nonce or session != {
        "engine_started": True,
        "all_cases_returned": True,
        "shutdown_complete": True,
        "source_inventory_unchanged": True,
        "source_resolved": True,
    }:
        raise RuntimeError("shared MATLAB session gate failed")
    raw_cases = raw.get("cases")
    if not isinstance(raw_cases, list) or [case.get("workbook_index") for case in raw_cases] != list(range(13)):
        raise RuntimeError("shared MATLAB case order")

    records = []
    for index, case in enumerate(raw_cases):
        if case.get("case_nonce") != case_nonces[index] or case.get("status") != "engine_call_returned" or case.get("stage") != "summary_written":
            raise RuntimeError("shared MATLAB case gate")
        config = source / CONFIG_PATHS[index]
        rust = bounded([str(validator), "config", "validate", str(config), "--materialized-json"], source, 120)
        if rust.returncode:
            raise RuntimeError("Rust config materialization failed")
        rust_doc = json.loads(rust.stdout)
        rust_projection = runtime_projection(rust_doc["materialized"], case["projection_parameters"], case["projection_options"])
        rust_sha = hashlib.sha256(canonical(rust_projection)).hexdigest()
        equal = rust_sha == case["pinned_materialized_sha256"]
        if not equal:
            raise RuntimeError("config materialization drift")
        size, sha = source_before[CONFIG_PATHS[index]]
        records.append({
            "workbook_index": index,
            "workbook": {"path": CONFIG_PATHS[index], "bytes": size, "sha256": sha},
            "case_nonce": case_nonces[index],
            "summary_sha256": case["summary_sha256"],
            "status": "passed",
            "source_inventory_unchanged": True,
            "config_materialization": {"comparison": "equal", "first_difference": first_difference(case["pinned_materialized"], rust_projection), "pinned_sha256": case["pinned_materialized_sha256"], "rust_sha256": rust_sha},
            "case_count": case["case_count"],
            "metrics": case["metrics"],
        })
    toolchain = {
        "cargo": tool_receipt(args.cargo, "cargo"),
        "rustc": tool_receipt(args.rustc, "rustc"),
        "uv": tool_receipt(args.uv, "uv"),
        "matlab": matlab_receipt(args.matlab, args.python),
        "python": tool_receipt(args.python, "python"),
    }
    toolchain["matlab"]["launch_mode"] = "python_engine_shared_13_sequential"
    shared_runner = Path(__file__)
    diagnostic_runner = Path(__file__).with_name("run_p5_06_original13_shared_matlab_diagnostic_v4.py")
    harness = Path(__file__).with_name("sipi_com_final_surface_oracle_v3.m")
    verifier = Path(__file__).with_name("verify_p5_06_original13_shared_matlab_fresh_v1.py")
    payload = {
        "schema": "sipi.p5-06.original13-shared-matlab-fresh-run.v1",
        "engine": "matlab",
        "run_id": f"original13-shared-{args.order}-{session_nonce}",
        "nonce": session_nonce,
        "status": "fresh_matrix_run",
        "selection_count": 13,
        "source": {"upstream": {"commit": UPSTREAM[0], "tree": UPSTREAM[1], "archive_sha256": UPSTREAM[2], "archive_bytes": UPSTREAM[3]}, "candidate": {"commit": CANDIDATE[0], "tree": CANDIDATE[1], "archive_sha256": CANDIDATE[2], "archive_bytes": CANDIDATE[3]}, "adapter": {"path": ADAPTER[0], "bytes": ADAPTER[1], "sha256": ADAPTER[2], "git_blob": ADAPTER[3]}, "projection_sources": [{"path": p, "bytes": b, "sha256": s, "git_blob": g} for p, b, s, g in PROJECTION_SOURCES], "shared_runner": local_tool(shared_runner), "diagnostic_runner": local_tool(diagnostic_runner), "harness": local_tool(harness), "verifier": local_tool(verifier), "toolchain": toolchain},
        "channels": [{"role": role, "path": path, "bytes": size, "sha256": sha} for role, path, size, sha in CHANNELS],
        "runtime_session": {"engine_start_count": 1, "engine_call_count": 13, "execution_order": execution_order, "worker_exit_code": 0, "timed_out": False, "source_resolution_verified": True, "shutdown_complete": True},
        "records": records,
        "claims": {"acceptance": False, "historical_python_used": False, "s_parameter_fit": False, "one_final_fd_to_td_impulse": True, "release": False},
    }
    write_json(args.report, payload)
    print(json.dumps({"report_sha256": digest(args.report), "slot_cases": sum(record["case_count"] for record in records)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
