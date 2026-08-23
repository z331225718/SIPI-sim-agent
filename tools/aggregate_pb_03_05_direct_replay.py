"""Aggregate two PB-03..PB-05 replay reports with fail-closed gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


HEX_NONCE = re.compile(r"[0-9a-f]{32,64}\Z")
ROOT = Path(__file__).resolve().parents[1]


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def stable(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def load(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("replay report must be an object")
    return value, sha256(payload)


def aggregate(first_path: Path, second_path: Path, output: Path, row: str | None = None) -> dict[str, Any]:
    first, first_hash = load(first_path)
    second, second_hash = load(second_path)
    blockers: list[str] = []
    if first_path.resolve() == second_path.resolve():
        blockers.append("report paths must be distinct")
    if first_hash == second_hash:
        blockers.append("report digests must be distinct")
    no_reference_reports: list[bool] = []
    for label, report in (("first", first), ("second", second)):
        if report.get("source_mode") not in {
            "git_archive_at_immutable_commit",
            "git_archive_plus_lane_working_tree_content_addressed",
        }:
            blockers.append(f"{label} source is not archive/content-address bound")
        replay = report.get("replay") if isinstance(report.get("replay"), dict) else {}
        comparison = replay.get("comparison") if isinstance(replay, dict) else {}
        candidate_comparison = comparison.get("candidate") if isinstance(comparison, dict) else {}
        no_reference = (
            row == "PB-05"
            and isinstance(candidate_comparison, dict)
            and candidate_comparison.get("reason") == "not_evaluated"
            and candidate_comparison.get("reference_required") == "external_python_reference_required"
            and candidate_comparison.get("status_only_comparison") is False
        )
        no_reference_reports.append(no_reference)
        if report.get("status") != "passed":
            if no_reference:
                blockers.append(f"{label} compare is intentionally not_evaluated without an independent reference")
            else:
                blockers.append(f"{label} replay is not passed")
        if row is not None and report.get("row") != row:
            blockers.append(f"{label} row drift")
        nonce = report.get("fresh_run_nonce")
        if not isinstance(nonce, str) or HEX_NONCE.fullmatch(nonce) is None:
            blockers.append(f"{label} fresh nonce malformed")
        replay = report.get("replay")
        if not isinstance(replay, dict) or replay.get("semantic_gate") is not True:
            blockers.append(f"{label} workflow semantic gate is not proven")
    if first.get("run_id") == second.get("run_id"):
        blockers.append("run IDs must be distinct")
    if first.get("fresh_run_nonce") == second.get("fresh_run_nonce"):
        blockers.append("fresh nonces must be distinct")
    for identity in ("candidate", "upstream", "fixture", "toolchain"):
        if first.get(identity) != second.get(identity):
            blockers.append(f"{identity} identity drift")
    first_replay = first.get("replay") if isinstance(first.get("replay"), dict) else {}
    second_replay = second.get("replay") if isinstance(second.get("replay"), dict) else {}
    first_payload = first_replay.get("payload", {})
    second_payload = second_replay.get("payload", {})
    if first_payload != second_payload:
        blockers.append("payload digest drift")
    if first_payload.get("equal") is not True or second_payload.get("equal") is not True:
        if row == "PB-05" and all(no_reference_reports):
            blockers.append("candidate/oracle payload parity is intentionally not_evaluated without an independent reference")
        else:
            blockers.append("candidate/oracle payload parity is not proven")
    aggregate_document = {
        "schema": "sipi.pb-direct-replay-aggregate.v1",
        "status": "passed" if not blockers else "blocked",
        "row": row or first.get("row"),
        "reports": [
            {"path": stable(first_path), "sha256": first_hash, "run_id": first.get("run_id"), "fresh_run_nonce": first.get("fresh_run_nonce"), "payload": first_payload},
            {"path": stable(second_path), "sha256": second_hash, "run_id": second.get("run_id"), "fresh_run_nonce": second.get("fresh_run_nonce"), "payload": second_payload},
        ],
        "candidate": first.get("candidate"),
        "upstream": first.get("upstream"),
        "fixture": first.get("fixture"),
        "toolchain": first.get("toolchain"),
        "distinct_gate": {
            "unique_report_paths": first_path.resolve() != second_path.resolve(),
            "unique_report_sha256": first_hash != second_hash,
            "unique_run_ids": first.get("run_id") != second.get("run_id"),
            "unique_fresh_run_nonces": first.get("fresh_run_nonce") != second.get("fresh_run_nonce"),
            "exact_toolchain_identity": first.get("toolchain") == second.get("toolchain"),
        },
        "payload": first_payload,
        "workflow_semantics": {
            "first": first_replay.get("selection"),
            "second": second_replay.get("selection"),
            "compare_first": first_replay.get("comparison"),
            "compare_second": second_replay.get("comparison"),
            "payload_is_not_status_only": row != "PB-05" or all(
                isinstance(report.get("replay"), dict)
                and isinstance(report["replay"].get("comparison"), dict)
                and report["replay"]["comparison"].get("payload_gate", {}).get("status_only_comparison") is False
                for report in (first, second)
            ),
        },
        "blockers": blockers,
        "claims": {"payload_parity": not blockers, "global_row_closed": False, "release_approval": False},
        "non_claims": ["A frozen fixture does not cover all branches.", "This aggregate is not a license decision or release approval."],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(aggregate_document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return aggregate_document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--row")
    args = parser.parse_args()
    try:
        value = aggregate(args.first, args.second, args.output, args.row)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": value["status"], "output": stable(args.output)}, sort_keys=True))
    return 0 if value["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
