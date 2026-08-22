"""Aggregate two PB-01 preparation/observation reports without claiming parity."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = "sipi.pb-01-direct-replay.v1"
AGGREGATE_SCHEMA = "sipi.pb-01-direct-replay-aggregate.v1"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("PB-01 replay report must be an object")
    return value, _sha256(payload)


def _report_id(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def aggregate(first_path: Path, second_path: Path, output: Path) -> dict[str, Any]:
    first, first_hash = _read(first_path)
    second, second_hash = _read(second_path)
    blockers: list[str] = []
    if first_path.resolve() == second_path.resolve():
        blockers.append("report paths must be distinct")
    if first_hash == second_hash:
        blockers.append("complete report hashes must be distinct")
    for label, report in (("first", first), ("second", second)):
        if report.get("schema") != REPORT_SCHEMA:
            blockers.append(f"{label} schema drift")
        if report.get("source_mode") != "git_archive_at_immutable_commit":
            blockers.append(f"{label} source mode drift")
        if report.get("status") not in {"prepared_open", "observed_open"}:
            blockers.append(f"{label} status is not an open preparation/observation")
        nonce = report.get("fresh_run_nonce")
        if not isinstance(nonce, str) or HEX64.fullmatch(nonce) is None:
            blockers.append(f"{label} nonce malformed")
    if first.get("run_id") == second.get("run_id"):
        blockers.append("run IDs must be distinct")
    if first.get("fresh_run_nonce") == second.get("fresh_run_nonce"):
        blockers.append("fresh nonces must be distinct")
    for key in ("stage_1_source_preparation", "runtime"):
        if first.get(key) != second.get(key):
            blockers.append(f"{key} drift between reports")
    first_id = _report_id(first_path)
    second_id = _report_id(second_path)
    if first_id == second_id:
        blockers.append("stable report IDs must be distinct")
    # The comparator and legacy-config projection are intentionally open.  A
    # future aggregate may become a parity gate only after those are bound.
    blockers.append("PB-01 numeric comparator and Rust legacy-config projection remain open")
    result = {
        "schema": AGGREGATE_SCHEMA,
        "status": "blocked",
        "reports": [
            {"path": first_id, "sha256": first_hash, "run_id": first.get("run_id"), "fresh_run_nonce": first.get("fresh_run_nonce")},
            {"path": second_id, "sha256": second_hash, "run_id": second.get("run_id"), "fresh_run_nonce": second.get("fresh_run_nonce")},
        ],
        "candidate": first.get("stage_1_source_preparation", {}).get("candidate"),
        "upstream": first.get("stage_1_source_preparation", {}).get("upstream"),
        "config": first.get("stage_1_source_preparation", {}).get("config"),
        "blockers": blockers,
        "non_claims": [
            "This aggregate is preparation/opaque-artifact evidence only and never closes PB-01 parity.",
            "The legacy PyBertData pickle payload is not decoded or compared.",
            "This aggregate is not a license decision, product admission, release approval, or redistribution authorization.",
        ],
        "canonical_input_sha256": _sha256(_canonical(first.get("stage_1_source_preparation", {}).get("config"))),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        stream.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(args.first, args.second, args.output)
    print(json.dumps({"status": result["status"], "output": str(args.output)}, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
