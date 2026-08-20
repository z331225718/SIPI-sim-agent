# -*- coding: utf-8 -*-
"""P3C-02i statistical eye contour cross-check (product vs independent ref).

Drives the product eye contour runner (p3c_02i_eye_contour_runner) over a statistical eye grid
plus a target Q. An independent Python reference replicates the per-column Q-threshold crossings
with the same interpolation formula. Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-02i-statistical-eye-contour-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p3c-02i-statistical-eye-contour-crosscheck-evidence.v1"
POLICY = "sipi.p3c-02i.statistical-eye-contour.v1.q-threshold-contour"


def interpolate_crossing(v_low: float, q_low: float, v_high: float, q_high: float,
                         target_q: float) -> float:
    return v_low + (target_q - q_low) * (v_high - v_low) / (q_high - q_low)


def ref_contour(time_offsets: list[float], voltage_levels: list[float],
                q_grid: list[list[float]], target_q: float) -> dict[str, Any]:
    if not time_offsets or not voltage_levels:
        return {"valid": False, "contour_error": "EmptyGrid"}
    if len(q_grid) != len(time_offsets):
        return {"valid": False,
                "contour_error": f'ColumnCountMismatch {{ columns: {len(q_grid)}, time: {len(time_offsets)} }}'}
    for column_index, column in enumerate(q_grid):
        if len(column) != len(voltage_levels):
            return {"valid": False,
                    "contour_error": f'RowCountMismatch {{ column: {column_index}, rows: {len(column)}, voltage: {len(voltage_levels)} }}'}
    if not target_q > 0.0:
        return {"valid": False, "contour_error": "InvalidTargetQ"}
    for i in range(len(time_offsets) - 1):
        if time_offsets[i] >= time_offsets[i + 1]:
            return {"valid": False, "contour_error": "TimeNotAscending"}
    for i in range(len(voltage_levels) - 1):
        if voltage_levels[i] >= voltage_levels[i + 1]:
            return {"valid": False, "contour_error": "VoltageNotAscending"}
    for column in q_grid:
        for q in column:
            if not math.isfinite(q) or q <= 0.0:
                return {"valid": False, "contour_error": "InvalidQ"}

    columns: list[dict[str, float]] = []
    for column_index, column in enumerate(q_grid):
        above = [q >= target_q for q in column]
        try:
            first = above.index(True)
        except ValueError:
            return {"valid": False,
                    "contour_error": f'NoContourAtColumn {{ column: {column_index} }}'}
        last = len(column) - 1 - above[::-1].index(True)

        if first == 0:
            lower = voltage_levels[0]
        else:
            lower = interpolate_crossing(voltage_levels[first - 1], column[first - 1],
                                         voltage_levels[first], column[first], target_q)
        if last == len(voltage_levels) - 1:
            upper = voltage_levels[last]
        else:
            upper = interpolate_crossing(voltage_levels[last], column[last],
                                         voltage_levels[last + 1], column[last + 1], target_q)
        columns.append({
            "time_offset_ui": time_offsets[column_index],
            "lower_voltage": lower,
            "upper_voltage": upper,
        })
    return {"valid": True, "target_q": target_q, "columns": columns}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-com", "--test", "p3c_02i_eye_contour_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3c_02i_eye_contour_runner-*.exe"))[-1]

    cases = [
        {
            "label": "parabola_grid",
            "time_offsets": [0.0, 0.5, 1.0],
            "voltage_levels": [0.0, 0.25, 0.5, 0.75, 1.0],
            "q_grid": [
                [1.0, 5.0, 10.0, 5.0, 1.0],
                [1.0, 5.0, 10.0, 5.0, 1.0],
                [1.0, 5.0, 10.0, 5.0, 1.0],
            ],
            "target_q": 5.0,
        },
        {
            "label": "clamped_edges",
            "time_offsets": [0.0],
            "voltage_levels": [0.0, 0.5, 1.0],
            "q_grid": [[8.0, 10.0, 8.0]],
            "target_q": 5.0,
        },
        {
            "label": "no_contour_column",
            "time_offsets": [0.0, 1.0],
            "voltage_levels": [0.0, 0.5, 1.0],
            "q_grid": [[8.0, 10.0, 8.0], [1.0, 2.0, 1.0]],
            "target_q": 5.0,
        },
        {
            "label": "invalid_q",
            "time_offsets": [0.0],
            "voltage_levels": [0.0, 1.0],
            "q_grid": [[0.0, 10.0]],
            "target_q": 5.0,
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p3c-02i-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_path = work / f"{case['label']}_in.json"
            input_path.write_text(json.dumps(case), encoding="utf-8")
            report_path = work / f"{case['label']}_rep.json"
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0:
                raise SystemExit(f"runner failed for {case['label']}: " + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = ref_contour(case["time_offsets"], case["voltage_levels"],
                                    case["q_grid"], case["target_q"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("target_q") != reference.get("target_q") or
                    product.get("columns") != reference.get("columns")):
                    matched = False
            else:
                prod_err = product.get("contour_error")
                ref_err = reference.get("contour_error")
                if str(prod_err) != str(ref_err):
                    matched = False

            if not matched:
                ok_all = False

            entries.append({
                "label": case["label"],
                "matched": matched,
                "product": product,
                "reference": reference,
            })

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if ok_all else "mis_match",
        "policy": POLICY,
        "matched_count": sum(1 for e in entries if e["matched"]),
        "case_count": len(entries),
        "entries": entries,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"],
                      "matched_count": evidence["matched_count"], "case_count": evidence["case_count"]}, indent=2))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
