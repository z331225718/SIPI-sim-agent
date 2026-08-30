"""Aggregate two R2024b and two Rust P5-06s v3 full matrix reports."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

try:
    from .run_p5_06_original13_fresh_matrix import digest
    from .run_p5_06_original13_fresh_matrix_v3 import METRICS, file_identity
    from .verify_p5_06_original13_fresh_matrix_v3 import verify
except ImportError:
    from run_p5_06_original13_fresh_matrix import digest
    from run_p5_06_original13_fresh_matrix_v3 import METRICS, file_identity
    from verify_p5_06_original13_fresh_matrix_v3 import verify


MATLAB_REPEAT_TOLERANCE = 1.0e-12
CROSS_TOLERANCE = 1.0e-9


def scalar_equal(left: object, right: object, tolerance: float) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isfinite(float(left)) and math.isfinite(float(right)) and abs(float(left) - float(right)) <= tolerance
    return left == right and left in ("+Inf", "-Inf")


def exact_scalar_equal(left: object, right: object) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    return left == right and (not isinstance(left, float) or math.isfinite(left))


def pair_slots(left: dict, right: dict, comparator) -> bool:
    for left_record, right_record in zip(left["records"], right["records"]):
        if left_record["workbook_index"] != right_record["workbook_index"] or len(left_record["metrics"]) != len(right_record["metrics"]):
            return False
        for left_case, right_case in zip(left_record["metrics"], right_record["metrics"]):
            if set(left_case) != set(right_case) or any(name not in METRICS or not comparator(left_case[name], right_case[name]) for name in left_case):
                return False
    return True


def comparable(left: dict, right: dict) -> bool:
    left_source = dict(left["source"])
    right_source = dict(right["source"])
    left_source.pop("rust_binary")
    right_source.pop("rust_binary")
    return (
        left_source == right_source
        and left["channels"] == right["channels"]
        and left["host_fingerprint"] == right["host_fingerprint"]
        and left["timing_clock"] == right["timing_clock"]
        and left["timing_scope"] == right["timing_scope"]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matlab-report", type=Path, action="append", required=True)
    parser.add_argument("--rust-report", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.matlab_report) != 2 or len(args.rust_report) != 2 or args.output.exists():
        raise RuntimeError("two reports per engine and a fresh output are required")
    paths = args.matlab_report + args.rust_report
    if len({path.resolve() for path in paths}) != 4:
        raise RuntimeError("report paths must be distinct")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    for report, engine in zip(reports, ("matlab", "matlab", "rust", "rust")):
        verify(report)
        if report["engine"] != engine:
            raise RuntimeError("engine order")
    if len({report["run_id"] for report in reports}) != 4 or len({report["nonce"] for report in reports}) != 4 or len({report["root_id"] for report in reports}) != 4:
        raise RuntimeError("run identity collision")
    report_hashes = [digest(path) for path in paths]
    if len(set(report_hashes)) != 4:
        raise RuntimeError("report hash collision")
    if any(not comparable(reports[0], report) for report in reports[1:]):
        raise RuntimeError("source, host, timing, or toolchain drift")
    matlab_a, matlab_b, rust_a, rust_b = reports
    matlab_repeat = pair_slots(matlab_a, matlab_b, lambda left, right: scalar_equal(left, right, MATLAB_REPEAT_TOLERANCE))
    rust_repeat = pair_slots(rust_a, rust_b, exact_scalar_equal)
    cross = pair_slots(matlab_a, rust_a, lambda left, right: scalar_equal(left, right, CROSS_TOLERANCE)) and pair_slots(matlab_b, rust_b, lambda left, right: scalar_equal(left, right, CROSS_TOLERANCE))
    per_workbook = []
    performance = True
    for index in range(13):
        matlab_best_ns = min(matlab_a["records"][index]["execution_wall_ns"], matlab_b["records"][index]["execution_wall_ns"])
        rust_worst_ns = max(rust_a["records"][index]["execution_wall_ns"], rust_b["records"][index]["execution_wall_ns"])
        passed = rust_worst_ns <= matlab_best_ns
        performance = performance and passed
        per_workbook.append({"workbook_index": index, "matlab_best_wall_ns": matlab_best_ns, "rust_worst_wall_ns": rust_worst_ns, "rust_not_slower": passed})
    total_passed = max(rust_a["total_execution_wall_ns"], rust_b["total_execution_wall_ns"]) <= min(matlab_a["total_execution_wall_ns"], matlab_b["total_execution_wall_ns"])
    performance = performance and total_passed
    accepted = matlab_repeat and rust_repeat and cross and performance
    aggregate = {
        "schema": "sipi.p5-06.original13-fresh-aggregate.v3",
        "status": "accepted_stage1" if accepted else "blocked",
        "runs": [{"engine": report["engine"], "run_id": report["run_id"], "nonce": report["nonce"], "root_id": report["root_id"], "report_sha256": report_hash} for report, report_hash in zip(reports, report_hashes)],
        "source": {key: value for key, value in reports[0]["source"].items() if key != "rust_binary"},
        "host_fingerprint": reports[0]["host_fingerprint"], "timing_clock": reports[0]["timing_clock"], "timing_scope": reports[0]["timing_scope"],
        "matrix": {"workbook_count": 13, "case_count": 28, "scalar_slot_count": 303},
        "gates": {"matlab_repeat_1e_12": matlab_repeat, "rust_repeat_exact": rust_repeat, "rust_vs_matlab_1e_9": cross, "per_workbook_rust_not_slower": performance, "total_rust_not_slower": total_passed},
        "performance": {"per_workbook": per_workbook, "matlab_best_total_wall_ns": min(matlab_a["total_execution_wall_ns"], matlab_b["total_execution_wall_ns"]), "rust_worst_total_wall_ns": max(rust_a["total_execution_wall_ns"], rust_b["total_execution_wall_ns"])},
        "gate_tools": {"aggregate": file_identity(Path(__file__)), "verifier": file_identity(Path(__file__).with_name("verify_p5_06_original13_fresh_matrix_v3.py"))},
        "claims": {"stage1_scalar_acceptance": accepted, "performance_acceptance": accepted, "array_acceptance": False, "release": False, "s_parameter_fit": False, "one_final_fd_to_td_impulse": True},
    }
    args.output.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": aggregate["status"], "aggregate_sha256": digest(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
