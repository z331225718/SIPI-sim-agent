"""Fail-closed verifier for shared-Engine MATLAB fresh reports."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from run_p5_06_original13_fresh_matrix import CHANNELS, CONFIG_PATHS, METRICS
from verify_p5_06_original13_fresh_matrix import ADAPTER, CANDIDATE, PROJECTION_SOURCES, UPSTREAM, WORKBOOKS

HEX = re.compile(r"^[0-9a-f]{64}$")


class Error(RuntimeError):
    pass


def _walk(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise Error("non-finite JSON")
    if isinstance(value, str) and (value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", value)):
        raise Error("absolute path")
    if isinstance(value, dict):
        for item in value.values():
            _walk(item)
    elif isinstance(value, list):
        for item in value:
            _walk(item)


def verify(report: dict[str, object]) -> bool:
    _walk(report)
    expected = {"schema", "engine", "run_id", "nonce", "status", "selection_count", "source", "channels", "runtime_session", "records", "claims"}
    if set(report) != expected or report["schema"] != "sipi.p5-06.original13-shared-matlab-fresh-run.v1" or report["engine"] != "matlab" or report["status"] != "fresh_matrix_run":
        raise Error("envelope")
    if not isinstance(report["nonce"], str) or not HEX.fullmatch(report["nonce"]) or not isinstance(report["run_id"], str) or not report["run_id"].endswith(report["nonce"]):
        raise Error("run identity")
    if report["selection_count"] != 13 or report["channels"] != [{"role": role, "path": path, "bytes": size, "sha256": sha} for role, path, size, sha in CHANNELS]:
        raise Error("corpus")
    source = report["source"]
    expected_source_keys = {"upstream", "candidate", "adapter", "projection_sources", "shared_runner", "diagnostic_runner", "harness", "verifier", "toolchain"}
    if not isinstance(source, dict) or set(source) != expected_source_keys or source.get("upstream") != {"commit": UPSTREAM[0], "tree": UPSTREAM[1], "archive_sha256": UPSTREAM[2], "archive_bytes": UPSTREAM[3]} or source.get("candidate") != {"commit": CANDIDATE[0], "tree": CANDIDATE[1], "archive_sha256": CANDIDATE[2], "archive_bytes": CANDIDATE[3]}:
        raise Error("source")
    if source.get("adapter") != {"path": ADAPTER[0], "bytes": ADAPTER[1], "sha256": ADAPTER[2], "git_blob": ADAPTER[3]} or source.get("projection_sources") != [{"path": p, "bytes": b, "sha256": s, "git_blob": g} for p, b, s, g in PROJECTION_SOURCES]:
        raise Error("source mapping")
    expected_tools = {
        "shared_runner": "tools/run_p5_06_original13_shared_matlab_fresh_v1.py",
        "diagnostic_runner": "tools/run_p5_06_original13_shared_matlab_diagnostic_v4.py",
        "harness": "tools/sipi_com_final_surface_oracle_v3.m",
        "verifier": "tools/verify_p5_06_original13_shared_matlab_fresh_v1.py",
    }
    for name, expected_path in expected_tools.items():
        item = source[name]
        if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"} or item["path"] != expected_path:
            raise Error("formal tool")
        if not isinstance(item["bytes"], int) or item["bytes"] <= 0 or not isinstance(item["sha256"], str) or not HEX.fullmatch(item["sha256"]):
            raise Error("formal tool hash")
    toolchain = source.get("toolchain")
    if not isinstance(toolchain, dict) or set(toolchain) != {"cargo", "rustc", "uv", "matlab", "python"} or toolchain["matlab"].get("launch_mode") != "python_engine_shared_13_sequential":
        raise Error("toolchain")
    for receipt in toolchain.values():
        if not isinstance(receipt, dict) or receipt.get("path_redacted") is not True or not isinstance(receipt.get("file_sha256"), str) or not HEX.fullmatch(receipt["file_sha256"]):
            raise Error("tool receipt")
    runtime = report["runtime_session"]
    if runtime != {"engine_start_count": 1, "engine_call_count": 13, "execution_order": runtime.get("execution_order") if isinstance(runtime, dict) else None, "worker_exit_code": 0, "timed_out": False, "source_resolution_verified": True, "shutdown_complete": True}:
        raise Error("session")
    if not isinstance(runtime["execution_order"], list) or sorted(runtime["execution_order"]) != list(range(13)):
        raise Error("execution order")
    records = report["records"]
    if not isinstance(records, list) or len(records) != 13 or [record.get("workbook_index") for record in records] != list(range(13)):
        raise Error("records")
    nonces: set[str] = set()
    summaries: set[str] = set()
    slots: set[tuple[int, int, str]] = set()
    cases = 0
    for index, record in enumerate(records):
        if record.get("workbook") != {"path": CONFIG_PATHS[index], "bytes": WORKBOOKS[CONFIG_PATHS[index]][0], "sha256": WORKBOOKS[CONFIG_PATHS[index]][1]} or record.get("status") != "passed" or record.get("source_inventory_unchanged") is not True:
            raise Error("record identity")
        nonce = record.get("case_nonce")
        if not isinstance(nonce, str) or not HEX.fullmatch(nonce) or nonce in nonces:
            raise Error("case nonce")
        nonces.add(nonce)
        if not isinstance(record.get("summary_sha256"), str) or not HEX.fullmatch(record["summary_sha256"]) or record["summary_sha256"] in summaries:
            raise Error("summary")
        summaries.add(record["summary_sha256"])
        materialization = record.get("config_materialization")
        if not isinstance(materialization, dict) or materialization.get("comparison") != "equal" or materialization.get("first_difference") is not None or materialization.get("pinned_sha256") != materialization.get("rust_sha256"):
            raise Error("materialization")
        metrics = record.get("metrics")
        if not isinstance(metrics, list) or record.get("case_count") != len(metrics) or not metrics:
            raise Error("metrics")
        cases += len(metrics)
        for case_index, case in enumerate(metrics):
            if not isinstance(case, dict) or any(name not in METRICS for name in case):
                raise Error("metric name")
            for name, value in case.items():
                if isinstance(value, bool) or not (isinstance(value, (int, float)) or value in ("+Inf", "-Inf")):
                    raise Error("metric value")
                slots.add((index, case_index, name))
    if len(nonces) != 13 or len(summaries) != 13 or cases != 28 or len(slots) != 303:
        raise Error("scalar surface")
    return True


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    verify(json.loads(args.report.read_text(encoding="utf-8")))
    print(json.dumps({"valid": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
