"""Run one immutable, full-array TDILN replay against pinned Agent-COM."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import secrets
import subprocess
import sys
from pathlib import Path

try:
    from tools.run_p5_06_original13_fresh_matrix import CONFIG_PATHS, UPSTREAM, bounded, digest, inventory, materialize, tool_receipt, matlab_receipt
except ImportError:
    from run_p5_06_original13_fresh_matrix import CONFIG_PATHS, UPSTREAM, bounded, digest, inventory, materialize, tool_receipt, matlab_receipt


SCHEMA = "sipi.p5-06.tdiln-array-replay.v1"
RAYON_THREADS = 16


def archive_identity(path: Path, sha256: str, byte_count: int, role: str) -> None:
    if not path.is_file() or path.stat().st_size != byte_count or digest(path) != sha256:
        raise RuntimeError(f"{role} archive identity drift")


def tool_identity(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": digest(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-archive", type=Path, required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--candidate-archive-sha256", required=True)
    parser.add_argument("--candidate-archive-bytes", type=int, required=True)
    parser.add_argument("--upstream-archive", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--matlab", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    if args.output_root.exists() or args.report.exists() or args.candidate_archive_bytes <= 0:
        raise ValueError("output/report must be fresh and candidate archive bytes positive")
    if os.cpu_count() is None or os.cpu_count() < RAYON_THREADS:
        raise RuntimeError("host cannot honor 16 Rayon workers")
    archive_identity(args.candidate_archive, args.candidate_archive_sha256, args.candidate_archive_bytes, "candidate")
    archive_identity(args.upstream_archive, UPSTREAM[2], UPSTREAM[3], "upstream")

    args.output_root.mkdir(parents=True)
    candidate = args.output_root / "candidate"
    source = args.output_root / "upstream"
    materialize(args.candidate_archive, candidate)
    materialize(args.upstream_archive, source)
    candidate_inventory = inventory(candidate)
    source_inventory = inventory(source)
    diagnostic_target = args.output_root / "target-diagnostic"
    performance_target = args.output_root / "target-production"
    build_env = os.environ.copy()
    build_env["CARGO_TARGET_DIR"] = str(diagnostic_target)
    build_env["RUSTC"] = str(args.rustc)
    build_env.pop("RUSTC_WRAPPER", None)
    build_env.pop("RUSTC_WORKSPACE_WRAPPER", None)
    build = bounded([
        str(args.cargo), "build", "--release", "--locked", "--features", "tdiln-diagnostic-sidecar",
        "--manifest-path", str(candidate / "crates/sipi-agent-com-direct/Cargo.toml"), "--bin", "sipi-com-direct-run",
    ], candidate, args.timeout, build_env)
    rust_binary = diagnostic_target / "release" / "sipi-com-direct-run.exe"
    if build.returncode != 0 or not rust_binary.is_file() or inventory(candidate) != candidate_inventory:
        raise RuntimeError("candidate feature build failed or changed its archive")
    performance_env = build_env.copy()
    performance_env["CARGO_TARGET_DIR"] = str(performance_target)
    performance_build = bounded([
        str(args.cargo), "build", "--release", "--locked",
        "--manifest-path", str(candidate / "crates/sipi-agent-com-direct/Cargo.toml"), "--bin", "sipi-com-direct-run",
    ], candidate, args.timeout, performance_env)
    performance_binary = performance_target / "release" / "sipi-com-direct-run.exe"
    if performance_build.returncode != 0 or not performance_binary.is_file() or inventory(candidate) != candidate_inventory:
        raise RuntimeError("candidate production build failed or changed its archive")

    diagnostic_root = args.output_root / "diagnostic"
    diagnostic_runner = Path(__file__).with_name("run_com_tdiln_original13_diagnostic.py")
    harness = candidate / "tools" / "sipi_com_tdiln_matrix_diagnostic_v1.m"
    comparison = Path(__file__).with_name("compare_com_tdiln_sidecars.py")
    command = [
        str(sys.executable), str(diagnostic_runner), "--source-root", str(source), "--rust-binary", str(rust_binary),
        "--performance-rust-binary", str(performance_binary),
        "--matlab", str(args.matlab), "--python", str(args.python), "--uv", str(args.uv), "--output", str(diagnostic_root),
        "--harness", str(harness), "--rayon-threads", str(RAYON_THREADS), "--require-tdiln-sidecars", "--timeout", str(args.timeout),
    ]
    run = bounded(command, args.output_root, args.timeout * len(CONFIG_PATHS) * 2 + 600)
    diagnostic_report = diagnostic_root / "report.json"
    if run.returncode != 0 or not diagnostic_report.is_file() or inventory(source) != source_inventory:
        raise RuntimeError("diagnostic replay failed or modified upstream archive")
    diagnostic = json.loads(diagnostic_report.read_text(encoding="utf-8"))
    if (
        diagnostic.get("status") != "passed_diagnostic"
        or diagnostic.get("tdiln_array_sidecars_required") is not True
        or diagnostic.get("performance_gate_binary") != "default_production"
        or diagnostic.get("rust_binary_sha256") != digest(rust_binary)
        or diagnostic.get("performance_rust_binary_sha256") != digest(performance_binary)
        or diagnostic.get("matlab_harness_sha256") != digest(harness)
    ):
        raise RuntimeError("diagnostic envelope does not bind the required production performance and TDILN array gates")
    records = []
    for record in diagnostic.get("records", []):
        comparison_record = record.get("comparison", {})
        arrays = comparison_record.get("tdiln_array_sidecars", {})
        timing = comparison_record.get("timing", {})
        matlab_seconds = timing.get("matlab_core_seconds")
        rust_seconds = timing.get("rust_wall_seconds")
        if not isinstance(matlab_seconds, (int, float)) or not isinstance(rust_seconds, (int, float)) or matlab_seconds <= 0.0 or rust_seconds <= 0.0:
            raise RuntimeError("diagnostic record omitted finite timing")
        records.append({
            "workbook_index": record.get("workbook_index"), "status": record.get("status"),
            "matlab_summary_sha256": record.get("matlab_summary_sha256"),
            "rust_result_sha256": record.get("rust_result_sha256"),
            "rust_result_semantic_sha256": record.get("rust_result_semantic_sha256"),
            "rust_production_result_sha256": record.get("rust_performance_result_sha256"),
            "rust_production_result_semantic_sha256": record.get("rust_performance_result_semantic_sha256"),
            "matlab_core_seconds": matlab_seconds,
            "rust_wall_seconds": rust_seconds,
            "rust_not_slower": timing.get("rust_not_slower") is True,
            "speedup": matlab_seconds / rust_seconds,
            "array_status": arrays.get("status"), "array_case_count": arrays.get("case_count"),
        })
    passed = diagnostic.get("status") == "passed_diagnostic" and len(records) == len(CONFIG_PATHS) and all(record["status"] == "passed_diagnostic" and record["array_status"] == "passed_diagnostic" and record["rust_not_slower"] for record in records)
    report = {
        "schema": SCHEMA, "diagnostic_only": True, "status": "passed_replay" if passed else "blocked",
        "run_id": f"tdiln-array-{secrets.token_hex(32)}", "nonce": secrets.token_hex(32),
        "source": {
            "candidate": {"commit": args.candidate_commit, "tree": args.candidate_tree, "archive_sha256": args.candidate_archive_sha256, "archive_bytes": args.candidate_archive_bytes},
            "upstream": {"commit": UPSTREAM[0], "tree": UPSTREAM[1], "archive_sha256": UPSTREAM[2], "archive_bytes": UPSTREAM[3]},
            "rust_binary": tool_identity(rust_binary),
            "rust_production_binary": tool_identity(performance_binary),
            "gate_tools": {"runner": tool_identity(Path(__file__)), "diagnostic_runner": tool_identity(diagnostic_runner), "matlab_harness": tool_identity(harness), "array_comparator": tool_identity(comparison)},
            "toolchain": {"cargo": tool_receipt(args.cargo, "cargo"), "rustc": tool_receipt(args.rustc, "rustc"), "uv": tool_receipt(args.uv, "uv"), "matlab": matlab_receipt(args.matlab, args.python), "python": tool_receipt(args.python, "python")},
        },
        "host": {"system": platform.system(), "machine": platform.machine(), "logical_cpus": os.cpu_count(), "rayon_threads": RAYON_THREADS},
        "matrix": {"workbook_count": len(CONFIG_PATHS), "records": records, "diagnostic_report_sha256": digest(diagnostic_report)},
        "performance_policy": {"rust_not_slower_required": True, "scope": "default-production Rust process plus normal artifacts; TDILN diagnostic sidecar I/O excluded; MATLAB source core after engine start"},
        "claims": {"tdiln_named_intermediate_checkpoint_parity": passed, "performance_acceptance_checkpoint": passed, "full_result_graph": False, "complete_warning_catalog": False, "channel_s_parameter_fit": False, "release": False},
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"], "report_sha256": digest(args.report)}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
