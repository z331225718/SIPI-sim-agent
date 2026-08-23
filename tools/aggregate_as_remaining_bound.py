"""Aggregate two immutable AS-02..AS-06 v2 replay reports."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

CANDIDATE_COMMIT = "64b783f66d7e986d0975be5ac3946b453b15c4ed"
CANDIDATE_TREE = "0e11721f2bb5b564002820cc7a5aaab45e30ba3b"
UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate(row: str, first_path: Path, second_path: Path, output: Path) -> dict[str, Any]:
    first = json.loads(first_path.read_text(encoding="utf-8"))
    second = json.loads(second_path.read_text(encoding="utf-8"))
    blockers: list[str] = []
    for label, report in (("first", first), ("second", second)):
        if report.get("schema") != f"sipi.agent-spice-{row.lower()}-bound-replay.v2":
            blockers.append(f"{label}:schema")
        if report.get("source_mode") != "candidate_and_upstream_git_archive_at_immutable_commit":
            blockers.append(f"{label}:source_mode")
        if report.get("candidate", {}).get("commit") != CANDIDATE_COMMIT or report.get("candidate", {}).get("tree") != CANDIDATE_TREE:
            blockers.append(f"{label}:candidate")
        if report.get("upstream", {}).get("commit") != UPSTREAM_COMMIT or report.get("upstream", {}).get("tree") != UPSTREAM_TREE:
            blockers.append(f"{label}:upstream")
        if report.get("parity_claim") is not False or report.get("numeric_parity") is not False or report.get("replay", {}).get("corpus_expected") is not True:
            blockers.append(f"{label}:parity_or_corpus")
        for key in ("runner", "helper"):
            if report.get(key, {}).get("path", "").startswith(("/", "\\")) or ".." in report.get(key, {}).get("path", "").replace("\\", "/").split("/"):
                blockers.append(f"{label}:{key}_path")
        if not isinstance(report.get("fresh_run_nonce"), str) or len(report["fresh_run_nonce"]) != 64:
            blockers.append(f"{label}:nonce")
    if first.get("run_id") == second.get("run_id") or first.get("fresh_run_nonce") == second.get("fresh_run_nonce"):
        blockers.append("runs_not_independent")
    if sha(first_path) == sha(second_path):
        blockers.append("report_sha_equal")
    for key in ("candidate", "upstream", "runner", "toolchain", "corpus", "external_runtime_blocked"):
        if first.get(key) != second.get(key):
            blockers.append(f"drift:{key}")
    if first.get("helper") != second.get("helper"):
        blockers.append("drift:helper")
    document = {
        "schema": f"sipi.agent-spice-{row.lower()}-bound-aggregate.v2",
        "status": "completed_external_blocker_open" if row in {"AS-04", "AS-05", "AS-06"} else "completed_portable_observation_open",
        "custody_valid": not blockers,
        "parity_claim": False,
        "numeric_parity": False,
        "candidate": first.get("candidate"),
        "upstream": first.get("upstream"),
        "runner": first.get("runner"),
        "helper": first.get("helper"),
        "toolchain": first.get("toolchain"),
        "corpus": first.get("corpus"),
        "reports": [{"path": first_path.as_posix(), "sha256": sha(first_path), "run_id": first.get("run_id"), "fresh_run_nonce": first.get("fresh_run_nonce")}, {"path": second_path.as_posix(), "sha256": sha(second_path), "run_id": second.get("run_id"), "fresh_run_nonce": second.get("fresh_run_nonce")}],
        "run_tree_sha256": [first.get("replay", {}).get("tree_sha256"), second.get("replay", {}).get("tree_sha256")],
        "input_tree_sha256": [first.get("replay", {}).get("input_tree_sha256"), second.get("replay", {}).get("input_tree_sha256")],
        "acceptance_tolerance": None,
        "blockers": blockers,
    }
    output.write_bytes(json.dumps(document, indent=2, sort_keys=True).encode() + b"\n")
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("row", choices=["AS-02", "AS-03", "AS-04", "AS-05", "AS-06"])
    parser.add_argument("--report", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.report) != 2:
        raise SystemExit("exactly two reports are required")
    result = aggregate(args.row, args.report[0], args.report[1], args.output)
    print(json.dumps({"status": result["status"], "sha256": sha(args.output), "blockers": result["blockers"]}, sort_keys=True))
    return 0 if result["custody_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
