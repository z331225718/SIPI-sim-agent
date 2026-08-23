"""Aggregate two v3 reports only after their schema gates pass."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from pb_03_replay_common import compare_windows_pe_custody, validate_windows_pe_replay_custody
from verify_com_erl_exact_profile_replay_v3 import verify_aggregate

SCHEMA = "sipi.com.erl-only.exact-profile-replay.v3"
AGG_SCHEMA = "sipi.com.erl-only.exact-profile-replay.v3.aggregate"
ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|/|\\\\)")

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def path_free(value: Any) -> bool:
    if isinstance(value, dict):
        return all(path_free(k) and path_free(v) for k, v in value.items())
    if isinstance(value, list):
        return all(path_free(v) for v in value)
    return not isinstance(value, str) or not ABSOLUTE.search(value)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema") != "sipi.com.erl-only.exact-profile-replay.v3.manifest":
        raise SystemExit("manifest schema mismatch")
    if len(args.report) != 2:
        raise SystemExit("exactly two reports required")
    if any(path.is_absolute() for path in args.report) or [path.as_posix() for path in args.report] != manifest["reports"]["paths"]:
        raise SystemExit("report path/order mismatch")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.report]
    if any(report.get("schema") != SCHEMA for report in reports):
        raise SystemExit("report schema mismatch")
    if any(not path_free(report) for report in reports):
        raise SystemExit("absolute path leaked")
    if any(report.get("input", {}).get("fixture_sha256") != manifest["fixture"]["sha256"] for report in reports):
        raise SystemExit("fixture identity mismatch")
    for report in reports:
        if report.get("candidate", {}).get("commit") != manifest["candidate"]["commit"] or report.get("candidate", {}).get("tree") != manifest["candidate"]["tree"] or report.get("candidate", {}).get("archive_sha256") != manifest["candidate"]["archive_sha256"]:
            raise SystemExit("candidate identity mismatch")
        if report.get("upstream", {}).get("commit") != manifest["upstream"]["commit"] or report.get("upstream", {}).get("tree") != manifest["upstream"]["tree"] or report.get("upstream", {}).get("archive_sha256") != manifest["upstream"]["archive_sha256"]:
            raise SystemExit("upstream identity mismatch")
    if any(report.get("input", {}).get("fixture_bytes") != manifest["fixture"]["bytes"] or report.get("input", {}).get("fixture_rows") != manifest["fixture"]["rows"] for report in reports):
        raise SystemExit("fixture shape mismatch")
    if reports[0].get("fresh_run_nonce") == reports[1].get("fresh_run_nonce"):
        raise SystemExit("fresh nonce collision")
    if len(reports[0].get("fresh_run_nonce", "")) != 64 or len(reports[1].get("fresh_run_nonce", "")) != 64:
        raise SystemExit("nonce must be 64 hex characters")
    if any(not re.fullmatch(r"[0-9a-f]{64}", report.get("fresh_run_nonce", "")) for report in reports):
        raise SystemExit("nonce must be lowercase hex")
    report_hashes = [sha256(path) for path in args.report]
    if report_hashes[0] == report_hashes[1]:
        raise SystemExit("report hashes must differ")
    if [report.get("run_id") for report in reports] != manifest["reports"]["run_ids"]:
        raise SystemExit("run id binding mismatch")
    for report in reports:
        candidate = report.get("candidate", {})
        custody = candidate.get("binary_custody", {})
        if validate_windows_pe_replay_custody(custody):
            raise SystemExit("binary custody schema mismatch")
        if custody.get("raw_sha256") != candidate.get("binary_sha256"):
            raise SystemExit("binary raw custody mismatch")
        if report.get("execution", {}).get("timeout_s") != manifest["runtime"]["timeout_s"]:
            raise SystemExit("runtime gate mismatch")
        if report.get("input", {}).get("controls") != manifest["controls"]:
            raise SystemExit("control payload mismatch")
        if report.get("stage_payload", {}).get("mapping") != manifest["stage_mapping"]:
            raise SystemExit("stage mapping mismatch")
        if report.get("execution", {}).get("runner", {}).get("path") != manifest["runner"]["path"] or report.get("execution", {}).get("helper", {}).get("path") != manifest["runner"]["helper_path"]:
            raise SystemExit("runner/helper path mismatch")
        if report.get("status") == "external_blocked" or report.get("parity", {}).get("status") not in {"matched", "numeric_mismatch_open"}:
            raise SystemExit("blocked report cannot aggregate")
    if reports[0].get("candidate") != reports[1].get("candidate"):
        for key in ("commit", "tree", "archive_sha256"):
            if reports[0].get("candidate", {}).get(key) != reports[1].get("candidate", {}).get(key):
                raise SystemExit("candidate identity drift")
    if reports[0].get("toolchain") != reports[1].get("toolchain"):
        raise SystemExit("toolchain identity drift")
    custody_errors = compare_windows_pe_custody(reports[0]["candidate"]["binary_custody"], reports[1]["candidate"]["binary_custody"])
    if custody_errors:
        raise SystemExit("binary custody drift")
    aggregate = {
        "schema": AGG_SCHEMA,
        "status": "bound_clean_archive_observation",
        "fresh_runs": 2,
        "reports": [{"path": path.as_posix(), "sha256": digest, "run_id": report["run_id"], "nonce": report["fresh_run_nonce"]} for path, digest, report in zip(args.report, report_hashes, reports, strict=True)],
        "candidate": {key: reports[0].get("candidate", {}).get(key) for key in ("commit", "tree", "archive_sha256", "materialization", "runtime_executed", "cargo_lock_sha256")},
        "upstream": reports[0].get("upstream"),
        "fixture": manifest["fixture"],
        "controls": manifest["controls"],
        "stage_mapping": reports[0].get("stage_payload", {}).get("mapping"),
        "toolchain_exact_equal": reports[0].get("toolchain") == reports[1].get("toolchain"),
        "binary_custody": [report.get("candidate", {}).get("binary_custody") for report in reports],
        "parity": {"status": "open_until_numeric_and_stage_match", "run_statuses": [report.get("parity", {}).get("status", report.get("status")) for report in reports]},
        "non_claims": ["no_release_or_promotion", "no_global_migration_row_close"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    verify_aggregate(aggregate, manifest, args.report)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
