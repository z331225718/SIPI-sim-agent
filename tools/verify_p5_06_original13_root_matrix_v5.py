"""Strict verifier for one public-root original-13 v5 replay."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

try:
    from .run_p5_06_original13_fresh_matrix import CHANNELS, CONFIG_PATHS, METRICS, UPSTREAM, digest
    from .run_p5_06_original13_root_matrix_v5 import CANDIDATE, HARNESS, MATLAB_RECEIPT, MATLAB_RELEASE, RAYON_THREADS, ROOT_BINARY, ROOT_MANIFEST, ROOT_RECEIPT_SCHEMA, SCHEMA, TIMING_SCOPE, WORKER, file_identity
    from .verify_p5_06_original13_fresh_matrix import WORKBOOKS
except ImportError:
    from run_p5_06_original13_fresh_matrix import CHANNELS, CONFIG_PATHS, METRICS, UPSTREAM, digest
    from run_p5_06_original13_root_matrix_v5 import CANDIDATE, HARNESS, MATLAB_RECEIPT, MATLAB_RELEASE, RAYON_THREADS, ROOT_BINARY, ROOT_MANIFEST, ROOT_RECEIPT_SCHEMA, SCHEMA, TIMING_SCOPE, WORKER, file_identity
    from verify_p5_06_original13_fresh_matrix import WORKBOOKS


HEX = re.compile(r"^[0-9a-f]{64}$")


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def finite(value: object) -> None:
    if isinstance(value, float):
        require(math.isfinite(value), "nonfinite JSON")
    elif isinstance(value, dict):
        for child in value.values():
            finite(child)
    elif isinstance(value, list):
        for child in value:
            finite(child)


def no_absolute_path(value: object) -> None:
    if isinstance(value, str):
        require(not value.startswith(("/", "\\")) and re.match(r"^[A-Za-z]:[\\/]", value) is None, "absolute path")
    elif isinstance(value, dict):
        for child in value.values():
            no_absolute_path(child)
    elif isinstance(value, list):
        for child in value:
            no_absolute_path(child)


def tool_receipt(receipt: object, role: str) -> None:
    require(isinstance(receipt, dict), "tool receipt")
    expected = {"role", "executable", "file_sha256", "version_sha256", "path_redacted"}
    if role == "matlab":
        expected.update(("release", "launch_mode"))
    require(set(receipt) == expected and receipt.get("role") == role and receipt.get("path_redacted") is True, "tool receipt shape")
    require(isinstance(receipt.get("executable"), str) and "/" not in receipt["executable"] and "\\" not in receipt["executable"], "tool executable")
    require(all(isinstance(receipt.get(key), str) and HEX.fullmatch(receipt[key]) for key in ("file_sha256", "version_sha256")), "tool digest")
    if role == "matlab":
        require(receipt["executable"] == "matlab.exe" and receipt["release"] == MATLAB_RELEASE, "MATLAB release")
        require(receipt["launch_mode"] == "python_engine_per_workbook_noFigureWindows_singleCompThread", "MATLAB mode")


def verify(report: object) -> bool:
    require(isinstance(report, dict), "report")
    finite(report)
    no_absolute_path(report)
    expected = {
        "schema", "engine", "run_id", "nonce", "root_id", "status", "timing_clock", "timing_scope",
        "total_execution_wall_ns", "host_fingerprint", "thread_policy", "selection_count", "source", "channels", "records", "claims",
    }
    require(set(report) == expected and report["schema"] == SCHEMA and report["engine"] in ("matlab", "rust"), "envelope")
    require(report["status"] == "fresh_matrix_run" and report["selection_count"] == 13, "matrix status")
    require(report["timing_clock"] == "perf_counter_ns" and report["timing_scope"] == TIMING_SCOPE, "timing envelope")
    require(report["thread_policy"] == {"rust_rayon_num_threads": RAYON_THREADS, "matlab_launch_mode": MATLAB_RECEIPT["launch_mode"]}, "thread policy")
    require(all(isinstance(report[key], str) and HEX.fullmatch(report[key]) for key in ("nonce", "root_id", "host_fingerprint")), "run identity")
    require(report["run_id"] == f"original13-root-v5-{report['engine']}-{report['nonce']}", "run id")
    require(isinstance(report["total_execution_wall_ns"], int) and report["total_execution_wall_ns"] > 0, "total duration")
    require(report["claims"] == {"acceptance": False, "performance_acceptance": False, "release": False, "s_parameter_fit": False, "one_final_fd_to_td_impulse": True}, "claims")

    source = report["source"]
    require(isinstance(source, dict) and set(source) == {"upstream", "candidate", "root_cli_binary", "root_cli", "config_validator_binary", "toolchain", "gate_tools"}, "source")
    require(source["upstream"] == {"commit": UPSTREAM[0], "tree": UPSTREAM[1], "archive_sha256": UPSTREAM[2], "archive_bytes": UPSTREAM[3]}, "upstream identity")
    require(source["candidate"] == {"commit": CANDIDATE[0], "tree": CANDIDATE[1], "archive_sha256": CANDIDATE[2], "archive_bytes": CANDIDATE[3]}, "candidate identity")
    binary = source["root_cli_binary"]
    require(isinstance(binary, dict) and set(binary) == {"path", "bytes", "sha256"} and binary["path"] == "target/release/" + ROOT_BINARY and isinstance(binary["bytes"], int) and binary["bytes"] > 0 and isinstance(binary["sha256"], str) and HEX.fullmatch(binary["sha256"]), "root binary")
    validator = source["config_validator_binary"]
    require(isinstance(validator, dict) and set(validator) == {"path", "bytes", "sha256"} and validator["path"] == "target/release/sipi-com-direct-config-validate.exe" and isinstance(validator["bytes"], int) and validator["bytes"] > 0 and isinstance(validator["sha256"], str) and HEX.fullmatch(validator["sha256"]), "config validator binary")
    require(source["root_cli"] == {"manifest": ROOT_MANIFEST, "feature": "com-direct-integration", "route": ["com", "run"], "receipt_schema": ROOT_RECEIPT_SCHEMA}, "root CLI contract")
    require(isinstance(source["toolchain"], dict) and set(source["toolchain"]) == {"cargo", "rustc", "uv", "matlab", "python"}, "toolchain")
    for role, receipt in source["toolchain"].items():
        tool_receipt(receipt, role)
    require(source["toolchain"]["matlab"] == MATLAB_RECEIPT, "MATLAB receipt")
    require(source["gate_tools"] == {"runner": file_identity(Path(__file__).with_name("run_p5_06_original13_root_matrix_v5.py")), "worker": file_identity(WORKER), "matlab_harness": file_identity(HARNESS)}, "gate tools")

    expected_channels = [{"role": role, "path": path, "bytes": size, "sha256": sha} for role, path, size, sha in CHANNELS]
    require(report["channels"] == expected_channels, "channels")
    records = report["records"]
    require(isinstance(records, list) and len(records) == 13, "records")
    metric_slots = 0
    durations = 0
    for index, record in enumerate(records):
        expected_record = {"workbook_index", "workbook", "status", "exit_code", "timed_out", "execution_wall_ns", "timing_scope", "detail_sha256", "source_inventory_unchanged", "config_materialization", "case_count", "metrics"}
        if report["engine"] == "rust":
            expected_record.add("root_cli_receipt")
        require(isinstance(record, dict) and set(record) == expected_record and record["workbook_index"] == index, "record shape")
        expected_workbook = {"path": CONFIG_PATHS[index], "bytes": WORKBOOKS[CONFIG_PATHS[index]][0], "sha256": WORKBOOKS[CONFIG_PATHS[index]][1]}
        require(record["workbook"] == expected_workbook, "workbook identity")
        require(record["status"] == "passed" and record["exit_code"] == 0 and record["timed_out"] is False and record["source_inventory_unchanged"] is True, "record execution")
        require(record["timing_scope"] == TIMING_SCOPE and isinstance(record["execution_wall_ns"], int) and record["execution_wall_ns"] > 0, "record timing")
        require(isinstance(record["detail_sha256"], str) and HEX.fullmatch(record["detail_sha256"]), "record digest")
        durations += record["execution_wall_ns"]
        materialization = record["config_materialization"]
        if report["engine"] == "rust":
            require(materialization == {"comparison": "not_run_for_rust_result_replay"}, "Rust materialization")
            receipt = record["root_cli_receipt"]
            require(isinstance(receipt, dict) and set(receipt) == {"schema", "status", "profile", "case_count", "warning_count", "config_sha256", "impulse_sha256", "artifacts"}, "root receipt")
            require(receipt["schema"] == ROOT_RECEIPT_SCHEMA and receipt["status"] == "completed" and receipt["profile"] == "r4.80" and isinstance(receipt["case_count"], int) and receipt["case_count"] == record["case_count"] and isinstance(receipt["warning_count"], int) and receipt["warning_count"] >= 0, "root receipt status")
            require(all(isinstance(receipt[key], str) and HEX.fullmatch(receipt[key]) for key in ("config_sha256", "impulse_sha256")), "root receipt digest")
            artifacts = receipt["artifacts"]
            require(isinstance(artifacts, list) and len(artifacts) == 3, "root receipt artifacts")
            names = set()
            for artifact in artifacts:
                require(isinstance(artifact, dict) and set(artifact) == {"name", "sha256", "byte_length"}, "root artifact shape")
                require(artifact["name"] in {"result.json", "report.html", "diagnostics.json"} and artifact["name"] not in names and isinstance(artifact["sha256"], str) and HEX.fullmatch(artifact["sha256"]) and isinstance(artifact["byte_length"], int) and artifact["byte_length"] > 0, "root artifact")
                names.add(artifact["name"])
            require(names == {"result.json", "report.html", "diagnostics.json"}, "root artifact names")
        else:
            expected_materialization = {"comparison", "first_difference", "pinned_sha256", "rust_sha256", "parameter_shape", "parameter_slot_digest", "parameter_mat_bytes", "parameter_mat_sha256"}
            require(isinstance(materialization, dict) and set(materialization) == expected_materialization and materialization["comparison"] == "equal" and materialization["first_difference"] is None, "MATLAB materialization")
            require(materialization["pinned_sha256"] == materialization["rust_sha256"], "materialized content")
            require(all(isinstance(materialization[key], str) and HEX.fullmatch(materialization[key]) for key in ("pinned_sha256", "rust_sha256", "parameter_slot_digest", "parameter_mat_sha256")), "materialization hash")
            require(isinstance(materialization["parameter_shape"], list) and len(materialization["parameter_shape"]) == 2 and all(isinstance(value, int) and value > 0 for value in materialization["parameter_shape"]), "materialization shape")
            require(isinstance(materialization["parameter_mat_bytes"], int) and materialization["parameter_mat_bytes"] > 0, "materialization bytes")
        require(isinstance(record["metrics"], list) and record["case_count"] == len(record["metrics"]) and record["case_count"] > 0, "case count")
        for case in record["metrics"]:
            require(isinstance(case, dict) and case and set(case).issubset(METRICS), "metric surface")
            for value in case.values():
                require(not isinstance(value, bool) and (isinstance(value, (int, float)) or value in ("+Inf", "-Inf", "NaN")), "metric value")
            metric_slots += len(case)
    require(durations == report["total_execution_wall_ns"], "timing sum")
    require(sum(record["case_count"] for record in records) == 28 and metric_slots == 303, "matrix coverage")
    return True


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    verify(json.loads(args.report.read_text(encoding="utf-8")))
    print(json.dumps({"valid": True, "report_sha256": digest(args.report)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
