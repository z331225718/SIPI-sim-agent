"""Aggregate two fresh pinned Agent-COM runtime probe reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


HEX64 = re.compile(r"^[0-9a-f]{64}$")
UPSTREAM = {
    "commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
    "tree": "7094ab6e84989b218730c52432c70da10261f8ea",
    "archive_sha256": "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf",
    "declared_license": "MIT",
    "materialization": "git archive at immutable commit",
    "observation_scope": "upstream_only",
    "runtime_executed": True,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def absolute_path(value: object) -> bool:
    if isinstance(value, dict):
        return any(absolute_path(k) or absolute_path(v) for k, v in value.items())
    if isinstance(value, list):
        return any(absolute_path(v) for v in value)
    return isinstance(value, str) and bool(re.search(r"(?:^[A-Za-z]:[\\/])|(?:^/)|(?:\\\\)", value))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("com-02", "com-04"), required=True)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = [args.first, args.second]
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    blockers: list[str] = []
    for report in reports:
        if report.get("schema") != "sipi.com-upstream-runtime-oracle.v2":
            blockers.append("schema")
        if report.get("mode") != args.mode:
            blockers.append("mode")
        if report.get("upstream") != UPSTREAM:
            blockers.append("upstream")
        if absolute_path(report):
            blockers.append("absolute_path")
        nonce = report.get("fresh_run_nonce", "")
        if not isinstance(nonce, str) or HEX64.fullmatch(nonce) is None:
            blockers.append("nonce")
        if report.get("portable_leaf", {}).get("status") != "numeric_payload_observed":
            blockers.append("portable_leaf")
        if report.get("entrypoint", {}).get("status") != "blocked":
            blockers.append("entrypoint_not_blocked")
        binding = report.get("execution_binding", {})
        if binding.get("entrypoint_timeout_seconds") != 15:
            blockers.append("timeout_gate")
        if binding.get("toolchain", {}).get("path_redacted") is not True:
            blockers.append("toolchain_redaction")
        if binding.get("fixtures", {}).get("paths_relative_to_archive") is not True:
            blockers.append("fixture_paths")
        if binding.get("scripts", {}).get("path_redacted") is not True:
            blockers.append("script_paths")
        if report.get("parity", {}).get("candidate_rust_parity_claim") is not False:
            blockers.append("candidate_parity_overclaim")
    if reports[0].get("run_id") == reports[1].get("run_id"):
        blockers.append("run_id")
    if reports[0].get("fresh_run_nonce") == reports[1].get("fresh_run_nonce"):
        blockers.append("nonce_duplicate")
    if reports[0].get("portable_leaf", {}).get("payload") != reports[1].get("portable_leaf", {}).get("payload"):
        blockers.append("portable_payload_drift")
    if reports[0].get("execution_binding") != reports[1].get("execution_binding"):
        blockers.append("execution_binding_drift")
    hashes = [sha256(path) for path in paths]
    if hashes[0] == hashes[1]:
        blockers.append("report_hash_duplicate")
    document = {
        "schema": "sipi.com-upstream-runtime-oracle-aggregate.v2",
        "mode": args.mode,
        "status": "portable_numeric_observed_full_entrypoint_blocked" if not blockers else "blocked",
        "fresh_runs": 2,
        "reports": [
            {"path": path.as_posix(), "sha256": digest, "run_id": report.get("run_id"), "fresh_run_nonce": report.get("fresh_run_nonce")}
            for path, digest, report in zip(paths, hashes, reports)
        ],
        "upstream": UPSTREAM,
        "portable_leaf_numeric_payload": reports[0].get("portable_leaf", {}).get("payload"),
        "portable_payload_identical": not any(item == "portable_payload_drift" for item in blockers),
        "entrypoint": {
            "name": "agent_com.api.run_com",
            "status": "blocked",
            "reason": "bounded timeout during r480 nonmmse search/evaluation",
            "dependency": "numpy+scipy available; no MATLAB engine requested",
        },
        "execution_binding": reports[0].get("execution_binding"),
        "blockers": blockers,
        "non_claims": ["no_full_run_numeric_parity", "no_release_or_promotion", "no_global_migration_row_close"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": document["schema"], "status": document["status"], "blockers": blockers}, sort_keys=True))
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
