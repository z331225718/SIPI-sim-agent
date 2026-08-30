"""Aggregate two shared MATLAB reports and two existing Rust fresh reports."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from run_p5_06_original13_fresh_matrix import METRICS
from run_p5_06_original13_rust_matlab_prep import scalar_equal
from verify_p5_06_original13_fresh_matrix import verify as verify_rust
from verify_p5_06_original13_shared_matlab_fresh_v1 import verify as verify_shared


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def slots(report: dict[str, object]) -> dict[tuple[int, int, str], object]:
    return {(record["workbook_index"], case_index, name): value for record in report["records"] for case_index, case in enumerate(record["metrics"]) for name, value in case.items() if name in METRICS}


def equal(left: object, right: object, tolerance: float) -> bool:
    if isinstance(left, str) or isinstance(right, str):
        return left == right and left in ("+Inf", "-Inf")
    if isinstance(left, bool) or isinstance(right, bool) or not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return False
    if not math.isfinite(float(left)) or not math.isfinite(float(right)):
        return scalar_equal(left, right)
    return abs(float(left) - float(right)) <= tolerance


def source_core(report: dict[str, object]) -> dict[str, object]:
    source = report["source"]
    return {key: source[key] for key in ("upstream", "candidate", "adapter", "projection_sources")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matlab", action="append", type=Path, required=True)
    parser.add_argument("--rust", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.matlab) != 2 or len(args.rust) != 2 or args.output.exists():
        parser.error("two MATLAB reports, two Rust reports, and create-new output required")
    matlab = [load(path) for path in args.matlab]
    rust = [load(path) for path in args.rust]
    for report in matlab:
        verify_shared(report)
    for report in rust:
        verify_rust(report)
        if report["engine"] != "rust" or report["status"] != "fresh_matrix_run" or any(record["status"] != "passed" for record in report["records"]):
            raise RuntimeError("non-passed Rust report")
    if matlab[0]["runtime_session"]["execution_order"] == matlab[1]["runtime_session"]["execution_order"]:
        raise RuntimeError("MATLAB order not inverted")
    all_reports = matlab + rust
    if len({report["run_id"] for report in all_reports}) != 4 or len({report["nonce"] for report in all_reports}) != 4:
        raise RuntimeError("fresh run identity")
    if any(source_core(report) != source_core(all_reports[0]) for report in all_reports[1:]) or any(report["channels"] != all_reports[0]["channels"] for report in all_reports[1:]):
        raise RuntimeError("source drift")
    maps = [slots(report) for report in all_reports]
    if any(len(mapping) != 303 or set(mapping) != set(maps[0]) for mapping in maps[1:]):
        raise RuntimeError("scalar surface drift")
    matlab_repeat = all(equal(maps[0][key], maps[1][key], 1e-12) for key in maps[0])
    rust_repeat = all(equal(maps[2][key], maps[3][key], 0.0) for key in maps[2])
    cross = all(equal(maps[0][key], maps[2][key], 1e-9) and equal(maps[1][key], maps[3][key], 1e-9) for key in maps[0])
    output = {
        "schema": "sipi.p5-06.original13-shared-fresh-aggregate.v2",
        "status": "accepted_stage1" if matlab_repeat and rust_repeat and cross else "blocked",
        "slot_count": 303,
        "matlab_repeat_1e_12": matlab_repeat,
        "rust_repeat_exact": rust_repeat,
        "rust_vs_matlab_1e_9": cross,
        "formal_runs": [{"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "engine": report["engine"], "run_id": report["run_id"], "nonce": report["nonce"]} for path, report in zip(args.matlab + args.rust, all_reports)],
        "source": source_core(all_reports[0]),
        "channels": all_reports[0]["channels"],
        "stage2": {"status": "diagnostic_only", "array_tolerances": "unset", "instrumentation_equivalence": "unproven"},
        "claims": {"release": False, "s_parameter_fit": False, "one_final_fd_to_td_impulse": True},
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
