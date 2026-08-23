"""Aggregate two positive runs and one upstream-only N=1 guard."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_com_erl_exact_profile_replay_v4 import MANIFEST, VerificationError, verify_aggregate, verify_manifest, verify_report
from pb_03_replay_common import compare_windows_pe_custody


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    verify_manifest(manifest)
    expected_paths = [Path(path) for path in manifest["reports"]["positive"] + [manifest["reports"]["negative"]]]
    if args.report != expected_paths:
        raise SystemExit("aggregate requires ordered run1/run2/n1 report paths")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.report]
    for report in reports:
        verify_report(report, manifest)
    if [report["run_id"] for report in reports] != manifest["reports"]["run_ids"] or len({report["fresh_run_nonce"] for report in reports}) != 3:
        raise SystemExit("run_id/nonce binding")
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in args.report]
    custody_errors = compare_windows_pe_custody(reports[0]["candidate"]["binary_custody"], reports[1]["candidate"]["binary_custody"])
    aggregate = {
        "schema": "sipi.com.erl-only.exact-profile-replay.v4.aggregate",
        "status": "bound_clean_archive_observation",
        "run_ids": list(manifest["reports"]["run_ids"]),
        "reports": [{"path": path.as_posix(), "sha256": digest, "run_id": report["run_id"], "nonce": report["fresh_run_nonce"]} for path, digest, report in zip(args.report, hashes, reports, strict=True)],
        "candidate": {key: reports[0]["candidate"].get(key) for key in ("commit", "tree", "archive_sha256", "materialization", "runtime_executed", "cargo_lock_sha256")},
        "upstream": reports[0]["upstream"],
        "fixture": manifest["fixture"],
        "controls": manifest["controls"],
        "stage_mapping": manifest["stage_mapping"],
        "toolchain_exact_equal": reports[0]["toolchain"] == reports[1]["toolchain"],
        "pe_custody_compare": {"status": "ok" if not custody_errors else "mismatch", "errors": custody_errors},
        "parity": {"status": "numeric_mismatch_open", "run_statuses": [report["parity"]["status"] for report in reports]},
        "non_claims": ["no_release_or_promotion", "no_global_migration_row_close", "no_numeric_parity_close", "no_s_parameter_fit"],
    }
    try:
        verify_aggregate(aggregate, manifest, args.report)
    except VerificationError as error:
        raise SystemExit(str(error)) from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": aggregate["schema"], "status": aggregate["status"], "parity": aggregate["parity"]["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
