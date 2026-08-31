"""Aggregate two fresh MATLAB and Rust P5-06 Stage 2b DFE matrix replays."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

try:
    from .project_p5_06_stage2b_dfe import (
        align_raw_rust_dfe_cases,
        compare_projected_dfe_cases,
        dfe_raw_receipts_equal,
    )
    from .run_p5_06_original13_fresh_matrix import CONFIG_PATHS, digest
    from .run_p5_06_stage2b_dfe_matrix import (
        CANDIDATE, HARNESS, MATLAB_RECEIPT, RAYON_THREADS, SCHEMA, TIMING_SCOPE, file_identity,
    )
except ImportError:
    from project_p5_06_stage2b_dfe import align_raw_rust_dfe_cases, compare_projected_dfe_cases, dfe_raw_receipts_equal
    from run_p5_06_original13_fresh_matrix import CONFIG_PATHS, digest
    from run_p5_06_stage2b_dfe_matrix import CANDIDATE, HARNESS, MATLAB_RECEIPT, RAYON_THREADS, SCHEMA, TIMING_SCOPE, file_identity


MATLAB_REPEAT_TOLERANCE = 1.0e-12
CROSS_TOLERANCE = 1.0e-9
HEX = re.compile(r"^[0-9a-f]{64}$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def finite(value: Any) -> None:
    if isinstance(value, float):
        require(math.isfinite(value), "nonfinite JSON")
    elif isinstance(value, dict):
        for child in value.values():
            finite(child)
    elif isinstance(value, list):
        for child in value:
            finite(child)


def no_absolute_path(value: Any) -> None:
    if isinstance(value, str):
        require(not value.startswith(("/", "\\")) and re.match(r"^[A-Za-z]:[\\/]", value) is None, "absolute path")
    elif isinstance(value, dict):
        for child in value.values():
            no_absolute_path(child)
    elif isinstance(value, list):
        for child in value:
            no_absolute_path(child)


def validate_report(report: Any, engine: str) -> None:
    require(isinstance(report, dict), "report")
    finite(report)
    no_absolute_path(report)
    expected = {
        "channels", "claims", "engine", "host_fingerprint", "nonce", "records", "root_id", "run_id", "schema",
        "selection_count", "source", "status", "thread_policy", "timing_clock", "timing_scope", "total_execution_wall_ns",
    }
    require(set(report) == expected and report["schema"] == SCHEMA and report["engine"] == engine, "report envelope")
    require(report["status"] == "fresh_matrix_run" and report["selection_count"] == len(CONFIG_PATHS), "matrix status")
    require(report["timing_clock"] == "perf_counter_ns" and report["timing_scope"] == TIMING_SCOPE, "timing")
    require(report["thread_policy"] == {"rust_rayon_num_threads": RAYON_THREADS, "matlab_launch_mode": MATLAB_RECEIPT["launch_mode"]}, "thread policy")
    require(all(isinstance(report[key], str) and HEX.fullmatch(report[key]) for key in ("nonce", "root_id", "host_fingerprint")), "run identity")
    require(report["run_id"] == f"original13-stage2b-dfe-{engine}-{report['nonce']}", "run id")
    require(report["claims"] == {"acceptance": False, "stage2b_dfe_numeric_parity": False, "release": False, "s_parameter_fit": False, "one_final_fd_to_td_impulse": True}, "claims")
    source = report["source"]
    require(isinstance(source, dict) and set(source) == {"upstream", "candidate", "rust_binary", "toolchain", "gate_tools"}, "source")
    require(source["candidate"] == {"commit": CANDIDATE[0], "tree": CANDIDATE[1], "archive_sha256": CANDIDATE[2], "archive_bytes": CANDIDATE[3]}, "candidate")
    require(source["toolchain"]["matlab"] == MATLAB_RECEIPT, "MATLAB receipt")
    expected_tools = {
        "runner": file_identity(Path(__file__).with_name("run_p5_06_stage2b_dfe_matrix.py")),
        "matlab_harness": file_identity(HARNESS),
        "projection": file_identity(Path(__file__).with_name("project_p5_06_stage2b_dfe.py")),
    }
    require(source["gate_tools"] == expected_tools, "gate tools")
    records = report["records"]
    require(isinstance(records, list) and len(records) == len(CONFIG_PATHS), "records")
    total = 0
    for index, record in enumerate(records):
        expected_record = {
            "workbook_index", "workbook", "status", "exit_code", "timed_out", "execution_wall_ns", "timing_scope",
            "detail_sha256", "source_inventory_unchanged", "config_materialization", "case_count", "metrics",
            "dfe_checkpoints", "dfe_scope",
        }
        require(isinstance(record, dict) and set(record) == expected_record and record["workbook_index"] == index, "record envelope")
        require(record["status"] == "passed" and record["exit_code"] == 0 and record["timed_out"] is False and record["source_inventory_unchanged"] is True, "record execution")
        require(record["timing_scope"] == TIMING_SCOPE and isinstance(record["execution_wall_ns"], int) and record["execution_wall_ns"] > 0, "record timing")
        require(isinstance(record["detail_sha256"], str) and HEX.fullmatch(record["detail_sha256"]), "detail receipt")
        require(isinstance(record["case_count"], int) and record["case_count"] == len(record["dfe_checkpoints"]), "DFE case count")
        scope = record["dfe_scope"]
        require(
            isinstance(scope, dict)
            and set(scope) == {"eligible_case_count", "inapplicable_erl_only_case_count"}
            and scope["eligible_case_count"] == record["case_count"]
            and isinstance(scope["inapplicable_erl_only_case_count"], int)
            and scope["inapplicable_erl_only_case_count"] >= 0,
            "DFE scope",
        )
        total += record["execution_wall_ns"]
    require(total == report["total_execution_wall_ns"], "total timing")


def comparable(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_source, right_source = dict(left["source"]), dict(right["source"])
    left_source.pop("rust_binary")
    right_source.pop("rust_binary")
    return left_source == right_source and left["channels"] == right["channels"] and left["host_fingerprint"] == right["host_fingerprint"] and left["thread_policy"] == right["thread_policy"]


def check_cross_pair(matlab: dict[str, Any], rust: dict[str, Any], tolerance: float) -> tuple[list[dict[str, Any]], bool]:
    records: list[dict[str, Any]] = []
    passed = True
    for source, candidate in zip(matlab["records"], rust["records"], strict=True):
        require(source["workbook_index"] == candidate["workbook_index"], "workbook alignment")
        joined = align_raw_rust_dfe_cases(candidate["dfe_checkpoints"], source["dfe_checkpoints"])
        differences = compare_projected_dfe_cases(source["dfe_checkpoints"], joined, tolerance)
        item = {
            "workbook_index": source["workbook_index"], "eligible_case_count": source["case_count"],
            "numeric_equal_within_tolerance": not differences,
            "raw_f64_receipts_equal": dfe_raw_receipts_equal(source["dfe_checkpoints"], joined),
        }
        records.append(item)
        passed = passed and item["numeric_equal_within_tolerance"]
    return records, passed


def check_matlab_repeat(left: dict[str, Any], right: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    records: list[dict[str, Any]] = []
    passed = True
    for first, second in zip(left["records"], right["records"], strict=True):
        require(first["workbook_index"] == second["workbook_index"], "workbook alignment")
        differences = compare_projected_dfe_cases(first["dfe_checkpoints"], second["dfe_checkpoints"], MATLAB_REPEAT_TOLERANCE)
        item = {"workbook_index": first["workbook_index"], "eligible_case_count": first["case_count"], "numeric_equal_within_tolerance": not differences}
        records.append(item)
        passed = passed and item["numeric_equal_within_tolerance"]
    return records, passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matlab-report", type=Path, action="append", required=True)
    parser.add_argument("--rust-report", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(len(args.matlab_report) == 2 and len(args.rust_report) == 2 and not args.output.exists(), "two fresh reports per engine and output required")
    paths = args.matlab_report + args.rust_report
    require(len({path.resolve() for path in paths}) == 4, "report paths must differ")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    for report, engine in zip(reports, ("matlab", "matlab", "rust", "rust"), strict=True):
        validate_report(report, engine)
    require(len({report["run_id"] for report in reports}) == 4 and len({report["nonce"] for report in reports}) == 4 and len({report["root_id"] for report in reports}) == 4, "run identity collision")
    hashes = [digest(path) for path in paths]
    require(len(set(hashes)) == 4 and all(comparable(reports[0], report) for report in reports[1:]), "report source drift")
    matlab_a, matlab_b, rust_a, rust_b = reports
    matlab_repeat_records, matlab_repeat = check_matlab_repeat(matlab_a, matlab_b)
    rust_repeat = all(left["dfe_checkpoints"] == right["dfe_checkpoints"] for left, right in zip(rust_a["records"], rust_b["records"], strict=True))
    cross_a, cross_a_ok = check_cross_pair(matlab_a, rust_a, CROSS_TOLERANCE)
    cross_b, cross_b_ok = check_cross_pair(matlab_b, rust_b, CROSS_TOLERANCE)
    performance_records = []
    performance = True
    for index in range(len(CONFIG_PATHS)):
        matlab_best = min(matlab_a["records"][index]["execution_wall_ns"], matlab_b["records"][index]["execution_wall_ns"])
        rust_worst = max(rust_a["records"][index]["execution_wall_ns"], rust_b["records"][index]["execution_wall_ns"])
        passed = rust_worst <= matlab_best
        performance_records.append({"workbook_index": index, "matlab_best_wall_ns": matlab_best, "rust_worst_wall_ns": rust_worst, "rust_not_slower": passed})
        performance = performance and passed
    total_performance = max(rust_a["total_execution_wall_ns"], rust_b["total_execution_wall_ns"]) <= min(matlab_a["total_execution_wall_ns"], matlab_b["total_execution_wall_ns"])
    accepted = matlab_repeat and rust_repeat and cross_a_ok and cross_b_ok and performance and total_performance
    aggregate = {
        "schema": "sipi.p5-06.stage2b-dfe-checkpoint-aggregate.v1",
        "status": "accepted_stage2b_dfe_checkpoint" if accepted else "blocked",
        "runs": [{"engine": report["engine"], "run_id": report["run_id"], "nonce": report["nonce"], "root_id": report["root_id"], "report_sha256": report_hash} for report, report_hash in zip(reports, hashes, strict=True)],
        "source": {key: value for key, value in reports[0]["source"].items() if key != "rust_binary"},
        "host_fingerprint": reports[0]["host_fingerprint"], "thread_policy": reports[0]["thread_policy"], "timing_clock": reports[0]["timing_clock"], "timing_scope": reports[0]["timing_scope"],
        "matrix": {"workbook_count": len(CONFIG_PATHS), "eligible_dfe_case_count": sum(record["case_count"] for record in matlab_a["records"])},
        "gates": {"matlab_repeat_1e_12": matlab_repeat, "rust_repeat_exact": rust_repeat, "rust_vs_matlab_1e_9_run_a": cross_a_ok, "rust_vs_matlab_1e_9_run_b": cross_b_ok, "per_workbook_rust_not_slower": performance, "total_rust_not_slower": total_performance},
        "comparison": {"matlab_repeat": matlab_repeat_records, "cross_run_a": cross_a, "cross_run_b": cross_b},
        "performance": {
            "per_workbook": performance_records,
            "matlab_best_total_wall_ns": min(matlab_a["total_execution_wall_ns"], matlab_b["total_execution_wall_ns"]),
            "rust_worst_total_wall_ns": max(rust_a["total_execution_wall_ns"], rust_b["total_execution_wall_ns"]),
            "fixed_deployment_speedup_min": min(matlab_a["total_execution_wall_ns"], matlab_b["total_execution_wall_ns"]) / max(rust_a["total_execution_wall_ns"], rust_b["total_execution_wall_ns"]),
        },
        "gate_tools": {
            "aggregate": file_identity(Path(__file__)),
            "runner": file_identity(Path(__file__).with_name("run_p5_06_stage2b_dfe_matrix.py")),
            "matlab_harness": file_identity(HARNESS),
            "projection": file_identity(Path(__file__).with_name("project_p5_06_stage2b_dfe.py")),
        },
        "claims": {"stage2b_dfe_checkpoint_acceptance": accepted, "p5_06_main_closed": False, "array_acceptance": False, "release": False, "s_parameter_fit": False, "one_final_fd_to_td_impulse": True},
    }
    args.output.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": aggregate["status"], "aggregate_sha256": digest(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
