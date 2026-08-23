"""Aggregate two clean-archive COM v2 semantic replay reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_absolute_path(value: object) -> bool:
    if isinstance(value, dict):
        return any(has_absolute_path(key) or has_absolute_path(item) for key, item in value.items())
    if isinstance(value, list):
        return any(has_absolute_path(item) for item in value)
    if isinstance(value, str):
        return bool(re.search(r"(?:^[A-Za-z]:[\\/])|(?:^/)|(?:\\\\)", value))
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("com-02", "com-04"), required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--upstream-commit", required=True)
    parser.add_argument("--upstream-tree", required=True)
    parser.add_argument("--report", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.report) != 2:
        raise SystemExit("exactly two fresh reports are required")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.report]
    if any(report.get("schema") != f"sipi.{args.mode}.direct-semantic-replay.v2" for report in reports):
        raise SystemExit("report schema mismatch")
    if any(report.get("candidate", {}).get("commit") != args.candidate_commit for report in reports):
        raise SystemExit("candidate commit mismatch")
    if any(report.get("candidate", {}).get("tree") != args.candidate_tree for report in reports):
        raise SystemExit("candidate tree mismatch")
    if any(has_absolute_path(report) for report in reports):
        raise SystemExit("absolute path leaked into report")
    if reports[0]["replays"][0]["semantic"] != reports[1]["replays"][0]["semantic"]:
        raise SystemExit("fresh semantic payload mismatch")
    if reports[0]["execution_binding"]["nonce"] == reports[1]["execution_binding"]["nonce"]:
        raise SystemExit("fresh nonces must be distinct")
    if len(reports[0]["execution_binding"]["nonce"]) != 64 or len(reports[1]["execution_binding"]["nonce"]) != 64:
        raise SystemExit("nonce must be 64 hex characters")
    if reports[0]["execution_binding"]["toolchain"] != reports[1]["execution_binding"]["toolchain"]:
        raise SystemExit("toolchain identity drift")
    build_keys = ("command", "returncode", "timeout_seconds", "timed_out", "rustc_wrapper_cleared", "source_mode", "source_commit", "source_tree", "archive_sha256")
    if any(reports[0]["execution_binding"]["build"].get(key) != reports[1]["execution_binding"]["build"].get(key) for key in build_keys):
        raise SystemExit("build source identity drift")
    report_hashes = [sha256(path) for path in args.report]
    if report_hashes[0] == report_hashes[1]:
        raise SystemExit("fresh report hashes must be distinct")
    aggregate = {
        "schema": f"sipi.{args.mode}.direct-semantic-replay-aggregate.v2",
        "status": "bound_clean_archive_observation",
        "fresh_runs": 2,
        "report_paths": [path.as_posix() for path in args.report],
        "report_sha256": report_hashes,
        "run_ids": [report["run_id"] for report in reports],
        "nonces": [report["execution_binding"]["nonce"] for report in reports],
        "toolchain_exact_equal": True,
        "build_source_exact_equal": True,
        "binary_sha256_by_run": [report["candidate"]["binary_sha256"] for report in reports],
        "semantic_payload_sha256": [report["replays"][0]["semantic_sha256"] for report in reports],
        "semantic_replays_identical": True,
        "candidate": reports[0]["candidate"],
        "execution_binding": {
            "runner": reports[0]["execution_binding"]["runner"],
            "helper": reports[0]["execution_binding"]["helper"],
            "v2_wrapper": reports[0]["execution_binding"]["v2_wrapper"],
            "fixture": reports[0]["execution_binding"]["fixture"],
            "toolchain": reports[0]["execution_binding"]["toolchain"],
            "source_probe": reports[0]["execution_binding"]["source_probe"],
            "build_source": {key: reports[0]["execution_binding"]["build"][key] for key in build_keys},
        },
        "upstream": reports[0]["upstream"],
        "parity": reports[0]["parity"],
        "non_claims": [
            "no_numeric_upstream_parity_claim",
            "no_release_or_promotion",
            "no_product_capability_promotion",
            "no_global_migration_row_close",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": aggregate["schema"], "aggregate_sha256": sha256(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
