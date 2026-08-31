"""Aggregate two immutable full-array TDILN replays with a hard speed gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

try:
    from tools.run_p5_06_original13_fresh_matrix import CONFIG_PATHS, digest
    from tools.run_p5_06_tdiln_array_replay import RAYON_THREADS, SCHEMA
except ImportError:
    from run_p5_06_original13_fresh_matrix import CONFIG_PATHS, digest
    from run_p5_06_tdiln_array_replay import RAYON_THREADS, SCHEMA


AGGREGATE_SCHEMA = "sipi.p5-06.tdiln-array-replay-aggregate.v1"
HEX = re.compile(r"^[0-9a-f]{64}$")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _hex(value: Any, label: str) -> str:
    _require(isinstance(value, str) and HEX.fullmatch(value) is not None, f"{label} must be sha256")
    return value


def _positive_number(value: Any, label: str) -> float:
    _require(not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value)) and value > 0.0, f"{label} must be finite positive")
    return float(value)


def _validate(report: Any) -> dict[str, Any]:
    _require(isinstance(report, dict), "report object")
    expected = {"schema", "diagnostic_only", "status", "run_id", "nonce", "source", "host", "matrix", "performance_policy", "claims"}
    _require(set(report) == expected and report["schema"] == SCHEMA, "report schema")
    _require(report["diagnostic_only"] is True and report["status"] == "passed_replay", "replay status")
    _hex(report["nonce"], "nonce")
    _require(isinstance(report["run_id"], str) and report["run_id"].startswith("tdiln-array-"), "run id")
    source = report["source"]
    _require(isinstance(source, dict) and set(source) == {"candidate", "upstream", "rust_binary", "rust_production_binary", "gate_tools", "toolchain"}, "source envelope")
    for role in ("candidate", "upstream"):
        identity = source[role]
        _require(isinstance(identity, dict) and set(identity) == {"commit", "tree", "archive_sha256", "archive_bytes"}, f"{role} identity")
        _require(all(isinstance(identity[key], str) and identity[key] for key in ("commit", "tree")), f"{role} git identity")
        _hex(identity["archive_sha256"], f"{role} archive")
        _require(isinstance(identity["archive_bytes"], int) and identity["archive_bytes"] > 0, f"{role} archive bytes")
    for role in ("rust_binary", "rust_production_binary"):
        binary = source[role]
        _require(isinstance(binary, dict) and set(binary) == {"name", "bytes", "sha256"}, f"{role} identity")
        _require(binary["name"] == "sipi-com-direct-run.exe" and isinstance(binary["bytes"], int) and binary["bytes"] > 0, f"{role} binary")
        _hex(binary["sha256"], role)
    for group, roles in (("gate_tools", {"runner", "diagnostic_runner", "matlab_harness", "array_comparator"}), ("toolchain", {"cargo", "rustc", "uv", "matlab", "python"})):
        entries = source[group]
        _require(isinstance(entries, dict) and set(entries) == roles, f"{group} roles")
        for role, entry in entries.items():
            _require(isinstance(entry, dict), f"{group}.{role}")
            if group == "gate_tools":
                _require(set(entry) == {"name", "bytes", "sha256"} and isinstance(entry["name"], str) and isinstance(entry["bytes"], int) and entry["bytes"] > 0, f"{group}.{role} identity")
                _hex(entry["sha256"], f"{group}.{role}")
            else:
                _require(entry.get("role") == role and entry.get("path_redacted") is True, f"{group}.{role} receipt")
                _hex(entry.get("file_sha256"), f"{group}.{role} file")
                _hex(entry.get("version_sha256"), f"{group}.{role} version")
    host = report["host"]
    _require(isinstance(host, dict) and set(host) == {"system", "machine", "logical_cpus", "rayon_threads"}, "host")
    _require(isinstance(host["logical_cpus"], int) and host["logical_cpus"] >= RAYON_THREADS and host["rayon_threads"] == RAYON_THREADS, "host parallelism")
    policy = report["performance_policy"]
    _require(policy == {"rust_not_slower_required": True, "scope": "default-production Rust process plus normal artifacts; TDILN diagnostic sidecar I/O excluded; MATLAB source core after engine start"}, "performance policy")
    _require(report["claims"] == {"tdiln_named_intermediate_checkpoint_parity": True, "performance_acceptance_checkpoint": True, "full_result_graph": False, "complete_warning_catalog": False, "channel_s_parameter_fit": False, "release": False}, "claims")
    matrix = report["matrix"]
    _require(isinstance(matrix, dict) and set(matrix) == {"workbook_count", "records", "diagnostic_report_sha256"}, "matrix")
    _require(matrix["workbook_count"] == len(CONFIG_PATHS) and isinstance(matrix["records"], list) and len(matrix["records"]) == len(CONFIG_PATHS), "matrix coverage")
    _hex(matrix["diagnostic_report_sha256"], "diagnostic report")
    for index, record in enumerate(matrix["records"]):
        expected_record = {"workbook_index", "status", "matlab_summary_sha256", "rust_result_sha256", "rust_result_semantic_sha256", "rust_production_result_sha256", "rust_production_result_semantic_sha256", "matlab_core_seconds", "rust_wall_seconds", "rust_not_slower", "speedup", "array_status", "array_case_count"}
        _require(isinstance(record, dict) and set(record) == expected_record and record["workbook_index"] == index, "record shape")
        _require(record["status"] == "passed_diagnostic" and record["array_status"] == "passed_diagnostic" and record["rust_not_slower"] is True, "record gates")
        for key in ("matlab_summary_sha256", "rust_result_sha256", "rust_result_semantic_sha256", "rust_production_result_sha256", "rust_production_result_semantic_sha256"):
            _hex(record[key], key)
        matlab_seconds = _positive_number(record["matlab_core_seconds"], "matlab duration")
        rust_seconds = _positive_number(record["rust_wall_seconds"], "Rust duration")
        speedup = _positive_number(record["speedup"], "speedup")
        _require(rust_seconds <= matlab_seconds and math.isclose(speedup, matlab_seconds / rust_seconds, rel_tol=1.0e-12, abs_tol=0.0), "record performance")
        _require(isinstance(record["array_case_count"], int) and record["array_case_count"] > 0, "array coverage")
    return report


def _common_source(source: dict[str, Any]) -> dict[str, Any]:
    """Build artifacts are replay-local; source, tools, and harnesses are not."""
    return {key: value for key, value in source.items() if key not in {"rust_binary", "rust_production_binary"}}


def aggregate(first: Any, second: Any, first_sha256: str, second_sha256: str) -> dict[str, Any]:
    first = _validate(first)
    second = _validate(second)
    _require(first_sha256 != second_sha256, "duplicate report content")
    _require(first["run_id"] != second["run_id"] and first["nonce"] != second["nonce"], "run identity collision")
    _require(_common_source(first["source"]) == _common_source(second["source"]) and first["host"] == second["host"] and first["performance_policy"] == second["performance_policy"], "source, host, or policy drift")
    per_workbook = []
    semantic_repeat = True
    hard_speed_gate = True
    for left, right in zip(first["matrix"]["records"], second["matrix"]["records"], strict=True):
        _require(left["workbook_index"] == right["workbook_index"], "workbook order drift")
        semantic_equal = left["rust_result_semantic_sha256"] == right["rust_result_semantic_sha256"] and left["rust_production_result_semantic_sha256"] == right["rust_production_result_semantic_sha256"]
        matlab_best = min(left["matlab_core_seconds"], right["matlab_core_seconds"])
        rust_worst = max(left["rust_wall_seconds"], right["rust_wall_seconds"])
        rust_not_slower = rust_worst <= matlab_best
        semantic_repeat = semantic_repeat and semantic_equal
        hard_speed_gate = hard_speed_gate and rust_not_slower
        per_workbook.append({"workbook_index": left["workbook_index"], "matlab_best_core_seconds": matlab_best, "rust_worst_wall_seconds": rust_worst, "speedup_floor": matlab_best / rust_worst, "rust_not_slower": rust_not_slower, "rust_semantic_repeat_exact": semantic_equal})
    matlab_best_total = min(sum(record["matlab_core_seconds"] for record in report["matrix"]["records"]) for report in (first, second))
    rust_worst_total = max(sum(record["rust_wall_seconds"] for record in report["matrix"]["records"]) for report in (first, second))
    total_speed_gate = rust_worst_total <= matlab_best_total
    accepted = semantic_repeat and hard_speed_gate and total_speed_gate
    return {
        "schema": AGGREGATE_SCHEMA,
        "status": "accepted_diagnostic_checkpoint" if accepted else "blocked",
        "diagnostic_only": True,
        "runs": [{"run_id": report["run_id"], "nonce": report["nonce"], "report_sha256": sha256} for report, sha256 in ((first, first_sha256), (second, second_sha256))],
        "source": _common_source(first["source"]),
        "builds": [
            {"diagnostic_binary": report["source"]["rust_binary"], "production_binary": report["source"]["rust_production_binary"]}
            for report in (first, second)
        ],
        "host": first["host"],
        "performance_policy": first["performance_policy"],
        "gates": {"two_fresh_replays": True, "rust_semantic_repeat_exact": semantic_repeat, "per_workbook_rust_not_slower": hard_speed_gate, "total_rust_not_slower": total_speed_gate},
        "performance": {"per_workbook": per_workbook, "matlab_best_total_core_seconds": matlab_best_total, "rust_worst_total_wall_seconds": rust_worst_total, "speedup_floor": matlab_best_total / rust_worst_total},
        "claims": {"tdiln_named_intermediate_checkpoint_parity": accepted, "performance_acceptance_checkpoint": accepted, "full_result_graph": False, "complete_warning_catalog": False, "channel_s_parameter_fit": False, "release": False},
        "aggregate_input_sha256": _digest({"first": first_sha256, "second": second_sha256}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _require(len(args.report) == 2 and args.output.exists() is False, "two reports and fresh output required")
    _require(args.report[0].resolve() != args.report[1].resolve(), "report paths must differ")
    report_a = json.loads(args.report[0].read_text(encoding="utf-8"))
    report_b = json.loads(args.report[1].read_text(encoding="utf-8"))
    result = aggregate(report_a, report_b, digest(args.report[0]), digest(args.report[1]))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "aggregate_sha256": digest(args.output)}))
    return 0 if result["status"].startswith("accepted_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
