"""Aggregate two immutable PB-02 replay reports without storing payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "sipi.pb-02-direct-replay.v1"
AGGREGATE_SCHEMA = "sipi.pb-02-direct-replay-aggregate.v1"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    document = json.loads(payload.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"replay report must be an object: {path}")
    return document, _sha256(payload)


def _get(document: dict[str, Any], *keys: str) -> Any:
    value: Any = document
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def aggregate(first_path: Path, second_path: Path, output: Path) -> dict[str, Any]:
    first, first_hash = _read(first_path)
    second, second_hash = _read(second_path)
    blockers: list[str] = []
    for label, document in (("first", first), ("second", second)):
        if document.get("schema") != SCHEMA:
            blockers.append(f"{label} schema drift")
        if document.get("status") != "passed":
            blockers.append(f"{label} replay is not passed")
        if document.get("source_mode") != "git_archive_at_immutable_commit":
            blockers.append(f"{label} is not archive-bound")
    if first.get("run_id") == second.get("run_id"):
        blockers.append("run IDs must be distinct")
    for name in ("candidate", "upstream", "fixture"):
        if first.get(name) != second.get(name):
            blockers.append(f"{name} identity drift between replays")
    first_parity = first.get("replay", {}).get("parity", {})
    second_parity = second.get("replay", {}).get("parity", {})
    if first_parity.get("candidate_array_members_equal_oracle") is not True:
        blockers.append("first replay does not prove candidate/oracle array equality")
    if second_parity.get("candidate_array_members_equal_oracle") is not True:
        blockers.append("second replay does not prove candidate/oracle array equality")
    first_candidate_arrays = _get(first, "replay", "candidate", "artifacts", "arrays", "member_sha256")
    second_candidate_arrays = _get(second, "replay", "candidate", "artifacts", "arrays", "member_sha256")
    first_oracle_arrays = _get(first, "replay", "oracle", "artifacts", "arrays", "member_sha256")
    second_oracle_arrays = _get(second, "replay", "oracle", "artifacts", "arrays", "member_sha256")
    if first_candidate_arrays != second_candidate_arrays:
        blockers.append("candidate array member hashes drift between replays")
    if first_oracle_arrays != second_oracle_arrays:
        blockers.append("oracle array member hashes drift between replays")
    aggregate_document = {
        "schema": AGGREGATE_SCHEMA,
        "status": "passed" if not blockers else "blocked",
        "reports": [
            {
                "path": first_path.as_posix(),
                "sha256": first_hash,
                "run_id": first.get("run_id"),
                "logical_array_sha256": _get(first, "replay", "candidate", "artifacts", "arrays", "logical_sha256"),
            },
            {
                "path": second_path.as_posix(),
                "sha256": second_hash,
                "run_id": second.get("run_id"),
                "logical_array_sha256": _get(second, "replay", "candidate", "artifacts", "arrays", "logical_sha256"),
            },
        ],
        "candidate": first.get("candidate"),
        "upstream": first.get("upstream"),
        "fixture": first.get("fixture"),
        "logical_array_member_sha256": first_candidate_arrays,
        "blockers": blockers,
        "non_claims": [
            "This aggregate proves only the one explicit PB-02 fixture and does not close uncovered SimulationInputV1 branches.",
            "SIPI wrapper admission and artifact policies remain outside upstream numerical parity.",
            "This aggregate is not a license decision, release approval, or product capability admission.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(aggregate_document, ensure_ascii=False, indent=2, sort_keys=True))
        stream.write("\n")
    return aggregate_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = aggregate(args.first, args.second, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"valid": False, "error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": document["status"], "output": str(args.output)}, sort_keys=True))
    return 0 if document["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
