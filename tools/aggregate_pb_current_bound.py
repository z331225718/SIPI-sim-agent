"""Aggregate two immutable PB-01..PB-05 current-bound replay reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
CANDIDATE_COMMIT = "64b783f66d7e986d0975be5ac3946b453b15c4ed"
CANDIDATE_TREE = "0e11721f2bb5b564002820cc7a5aaab45e30ba3b"
NONCE = re.compile(r"[0-9a-f]{32,64}\Z")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def has_overlay_claim(value: Any) -> bool:
    """Keep aggregates archive-only; never preserve a worktree overlay claim."""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if "overlay" in normalized_key or "working_tree" in normalized_key:
                return True
            if has_overlay_claim(item):
                return True
        return False
    if isinstance(value, list):
        return any(has_overlay_claim(item) for item in value)
    if isinstance(value, str):
        normalized = value.lower()
        return "overlay" in normalized or "working_tree" in normalized
    return False


def stable(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def load(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("report must be an object")
    return value, sha256(payload)


def identity(report: dict[str, Any]) -> dict[str, Any]:
    candidate = report.get("candidate") or report.get("stage_1_source_preparation", {}).get("candidate")
    upstream = report.get("upstream") or report.get("stage_1_source_preparation", {}).get("upstream")
    fixture = report.get("fixture") or report.get("stage_1_source_preparation", {}).get("config")
    return {"candidate": candidate, "upstream": upstream, "fixture": fixture, "toolchain": report.get("toolchain")}


def semantic(report: dict[str, Any], row: str) -> dict[str, Any]:
    replay = report.get("replay") or report.get("stage_2_oracle_replay") or {}
    if row == "PB-01":
        comparison = replay.get("comparison") or {}
        return {"status": comparison.get("status"), "blockers": comparison.get("blockers", [])}
    if row == "PB-02":
        parity = replay.get("parity") or {}
        return {"candidate_array_members_equal_oracle": parity.get("candidate_array_members_equal_oracle"), "candidate_exit_zero": parity.get("candidate_exit_zero"), "oracle_exit_zero": parity.get("oracle_exit_zero")}
    return {"semantic_gate": replay.get("semantic_gate"), "payload": replay.get("payload"), "selection": replay.get("selection"), "comparison": replay.get("comparison")}


def aggregate(first_path: Path, second_path: Path, output: Path, row: str) -> dict[str, Any]:
    first, first_hash = load(first_path)
    second, second_hash = load(second_path)
    blockers: list[str] = []
    expected_schema = {
        "PB-01": "sipi.pb-01-legacy-leaf-replay.v1",
        "PB-02": "sipi.pb-02-direct-replay.v1",
        "PB-03": "sipi.pb-03-direct-replay.v1",
        "PB-04": "sipi.pb-04-direct-replay.v1",
        "PB-05": "sipi.pb-05-direct-replay.v1",
    }[row]
    for label, report in (("first", first), ("second", second)):
        if has_overlay_claim(report):
            blockers.append(f"{label} contains a worktree overlay claim")
        if report.get("schema") != expected_schema:
            blockers.append(f"{label} schema drift")
        if report.get("source_mode") != "git_archive_at_immutable_commit":
            blockers.append(f"{label} source mode is not immutable archive")
        if report.get("candidate", {}).get("commit") != CANDIDATE_COMMIT:
            blockers.append(f"{label} candidate commit drift")
        if report.get("candidate", {}).get("tree") != CANDIDATE_TREE:
            blockers.append(f"{label} candidate tree drift")
        if report.get("upstream", {}).get("commit") != UPSTREAM_COMMIT:
            blockers.append(f"{label} upstream commit drift")
        if report.get("upstream", {}).get("tree") != UPSTREAM_TREE:
            blockers.append(f"{label} upstream tree drift")
        if report.get("fixture", {}).get("archive_present") is not True:
            blockers.append(f"{label} fixture is not present in candidate archive")
        if not isinstance(report.get("fresh_run_nonce"), str) or NONCE.fullmatch(report.get("fresh_run_nonce", "")) is None:
            blockers.append(f"{label} nonce malformed")
    if first.get("run_id") == second.get("run_id"):
        blockers.append("run IDs must be distinct")
    if first.get("fresh_run_nonce") == second.get("fresh_run_nonce"):
        blockers.append("fresh nonces must be distinct")
    if first_hash == second_hash:
        blockers.append("report digests must be distinct")
    if identity(first) != identity(second):
        blockers.append("immutable identity drift")
    first_semantic = semantic(first, row)
    second_semantic = semantic(second, row)
    if first_semantic != second_semantic:
        blockers.append("replay semantic drift")
    if row == "PB-04":
        candidate = (first_semantic.get("selection") or {}).get("candidate") or {}
        if not (candidate.get("selected") == "python" and candidate.get("implementation") == "external_python_reference_required" and candidate.get("rust_only") is False):
            blockers.append("PB-04 Python selection/fail-closed semantic missing")
    if row == "PB-05":
        candidate = (first_semantic.get("comparison") or {}).get("candidate") or {}
        if not (candidate.get("reason") == "not_evaluated" and candidate.get("reference_required") == "external_python_reference_required" and candidate.get("status_only_comparison") is False):
            blockers.append("PB-05 independent-reference-required semantic missing")
    # Replay status is intentionally open for every row except a payload-passing
    # PB-03.  A blocked result is evidence, not a promotion.
    if row in {"PB-01", "PB-02", "PB-04", "PB-05"}:
        blockers.append(f"{row} remains open by contract: {first.get('status')}")
    elif first.get("status") != "passed" or second.get("status") != "passed":
        blockers.append("PB-03 payload replay did not pass")
    result = {
        "schema": "sipi.pb-current-bound-replay-aggregate.v1",
        "status": "passed" if not blockers else "blocked",
        "row": row,
        "reports": [
            {"path": stable(first_path), "sha256": first_hash, "run_id": first.get("run_id"), "fresh_run_nonce": first.get("fresh_run_nonce"), "status": first.get("status")},
            {"path": stable(second_path), "sha256": second_hash, "run_id": second.get("run_id"), "fresh_run_nonce": second.get("fresh_run_nonce"), "status": second.get("status")},
        ],
        **identity(first),
        "semantic": {"first": first_semantic, "second": second_semantic},
        "blockers": blockers,
        "claims": {"payload_parity": row == "PB-03" and not blockers, "global_row_closed": False, "release_approval": False},
        "non_claims": ["This aggregate is immutable replay evidence, not a license decision, release approval, or promotion."],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--row", required=True, choices=["PB-01", "PB-02", "PB-03", "PB-04", "PB-05"])
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(args.first, args.second, args.output, args.row)
    print(json.dumps({"status": result["status"], "output": stable(args.output)}, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
