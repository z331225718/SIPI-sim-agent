"""Verify the fixed-MATLAB/current-Rust original-13 performance rebind."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_bound(entry: dict) -> dict:
    path = ROOT / entry["path"]
    require(path.is_file() and path.stat().st_size == entry["bytes"], "bound report bytes")
    require(digest(path) == entry["sha256"], "bound report digest")
    report = json.loads(path.read_text(encoding="utf-8"))
    require(report["status"] == "fresh_matrix_run" and len(report["records"]) == 13, "matrix status")
    return report


def slot_values(report: dict) -> list[object]:
    values: list[object] = []
    for record in report["records"]:
        require(record["status"] == "passed", "record status")
        for case in record["metrics"]:
            values.extend(case[name] for name in sorted(case))
    return values


def equal(left: object, right: object, tolerance: float) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isfinite(float(left)) and math.isfinite(float(right)) and abs(float(left) - float(right)) <= tolerance
    return left == right and left in ("+Inf", "-Inf")


def verify(manifest: dict) -> dict:
    require(manifest["status"] == "accepted_current_rust_rebind_against_fixed_r2024b_baseline", "manifest status")
    matrix = manifest["matrix"]
    matlab = [load_bound(entry) for entry in manifest["fixed_matlab_baseline"]["reports"]]
    rust = [load_bound(entry) for entry in manifest["current_rust_reports"]]
    reference = load_bound(manifest["reference_rust_report"])
    require(all(report["engine"] == "matlab" for report in matlab), "MATLAB engine")
    require(all(report["engine"] == "rust" for report in rust) and reference["engine"] == "rust", "Rust engine")
    candidate = {"commit": manifest["candidate"]["commit"], "tree": manifest["candidate"]["tree"], "archive_sha256": manifest["candidate"]["archive_sha256"], "archive_bytes": manifest["candidate"]["archive_bytes"]}
    require(all(report["source"]["candidate"] == candidate for report in rust), "current candidate binding")
    slots = [slot_values(report) for report in [*matlab, *rust, reference]]
    require(all(len(values) == matrix["scalar_slots"] for values in slots), "scalar slot count")
    require(slots[2] == slots[3] == slots[4], "current Rust exact scalar drift")
    tolerance = matrix["cross_tolerance"]
    require(all(equal(left, right, tolerance) for left, right in zip(slots[0], slots[2])), "MATLAB one drift")
    require(all(equal(left, right, tolerance) for left, right in zip(slots[1], slots[2])), "MATLAB two drift")
    per_workbook = []
    for index in range(matrix["workbooks"]):
        rust_worst = max(report["records"][index]["execution_wall_ns"] for report in rust)
        matlab_best = min(report["records"][index]["execution_wall_ns"] for report in matlab)
        require(rust_worst <= matlab_best, f"performance workbook {index}")
        per_workbook.append({"workbook_index": index, "rust_worst_wall_ns": rust_worst, "matlab_best_wall_ns": matlab_best})
    rust_total = max(report["total_execution_wall_ns"] for report in rust)
    matlab_total = min(report["total_execution_wall_ns"] for report in matlab)
    require(rust_total <= matlab_total, "total performance")
    receipt = manifest["performance"]
    require(
        receipt["matlab_best_total_wall_ns"] == matlab_total
        and receipt["rust_worst_total_wall_ns"] == rust_total
        and math.isclose(receipt["speedup_floor"], matlab_total / rust_total, rel_tol=0.0, abs_tol=1e-12),
        "performance receipt",
    )
    return {"valid": True, "scalar_slots": matrix["scalar_slots"], "rust_worst_total_wall_ns": rust_total, "matlab_best_total_wall_ns": matlab_total, "per_workbook": per_workbook}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    result = verify(json.loads(args.manifest.read_text(encoding="utf-8")))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
