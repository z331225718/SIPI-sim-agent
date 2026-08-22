"""Aggregate two immutable COM-01 replay reports without storing values."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.com-01-direct-replay.v1"
AGGREGATE_SCHEMA = "sipi.com-01-direct-replay-aggregate.v1"
OPEN_STATUS = "open_differential_mismatch_fingerprint_only"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
EXPECTED_OUTCOMES = {
    "error_code_match": 7,
    "passed": 6,
    "values_equal_fingerprint_drift": 1,
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _read(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    document = json.loads(payload.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("replay report must be a JSON object")
    return document, _sha256(payload)


def _stable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def aggregate(first_path: Path, second_path: Path, output: Path) -> dict[str, Any]:
    first, first_hash = _read(first_path)
    second, second_hash = _read(second_path)
    blockers: list[str] = []
    if first_path.resolve() == second_path.resolve():
        blockers.append("report paths must be distinct")
    if first_hash == second_hash:
        blockers.append("complete report SHA-256 values must be distinct")
    for label, document in (("first", first), ("second", second)):
        if document.get("schema") != SCHEMA:
            blockers.append(f"{label} report schema drift")
        if document.get("status") != OPEN_STATUS:
            blockers.append(f"{label} report does not preserve fingerprint-only open status")
        if document.get("source_mode") != "git_archive_at_immutable_commit":
            blockers.append(f"{label} report is not archive-bound")
        if document.get("outcomes") != EXPECTED_OUTCOMES:
            blockers.append(f"{label} report outcome inventory drift")
        if document.get("values_aligned") is not True:
            blockers.append(f"{label} report value projection is not aligned")
        if document.get("fingerprint_drift_count") != 1:
            blockers.append(f"{label} report fingerprint drift count changed")
    if first.get("run_id") == second.get("run_id"):
        blockers.append("run IDs must be distinct")
    first_nonce = first.get("fresh_run_nonce")
    second_nonce = second.get("fresh_run_nonce")
    for label, nonce in (("first", first_nonce), ("second", second_nonce)):
        if not isinstance(nonce, str) or HEX64.fullmatch(nonce) is None:
            blockers.append(f"{label} fresh run nonce is missing or malformed")
    if isinstance(first_nonce, str) and first_nonce == second_nonce:
        blockers.append("fresh run nonces must be distinct")
    first_candidate = first.get("candidate")
    second_candidate = second.get("candidate")
    if not isinstance(first_candidate, dict) or not isinstance(second_candidate, dict):
        blockers.append("candidate identity is missing")
        first_candidate = {}
        second_candidate = {}
    first_candidate_static = {
        key: value for key, value in first_candidate.items() if key != "binary_sha256"
    }
    second_candidate_static = {
        key: value for key, value in second_candidate.items() if key != "binary_sha256"
    }
    if first_candidate_static != second_candidate_static:
        blockers.append("candidate static identity drift between replays")
    for key in ("upstream", "harness", "toolchain", "fixtures", "outcomes"):
        if first.get(key) != second.get(key):
            blockers.append(f"{key} identity drift between replays")
    first_scenarios = first.get("scenarios")
    second_scenarios = second.get("scenarios")
    if first_scenarios != second_scenarios:
        blockers.append("scenario summaries drift between replays")
    first_id = _stable_path(first_path)
    second_id = _stable_path(second_path)
    if first_id == second_id:
        blockers.append("stable report identifiers must be distinct")
    document = {
        "schema": AGGREGATE_SCHEMA,
        "status": OPEN_STATUS if not blockers else "blocked",
        "reports": [
            {
                "path": first_id,
                "sha256": first_hash,
                "run_id": first.get("run_id"),
                "fresh_run_nonce": first_nonce,
                "candidate_binary_sha256": first_candidate.get("binary_sha256"),
            },
            {
                "path": second_id,
                "sha256": second_hash,
                "run_id": second.get("run_id"),
                "fresh_run_nonce": second_nonce,
                "candidate_binary_sha256": second_candidate.get("binary_sha256"),
            },
        ],
        "candidate_static_identity": first_candidate_static,
        "binary_bit_reproducible": (
            first_candidate.get("binary_sha256") == second_candidate.get("binary_sha256")
        ),
        "upstream": first.get("upstream"),
        "harness": first.get("harness"),
        "toolchain": first.get("toolchain"),
        "fixtures": first.get("fixtures"),
        "outcomes": first.get("outcomes"),
        "values_aligned": first.get("values_aligned"),
        "fingerprint_drift_count": first.get("fingerprint_drift_count"),
        "scenario_summaries_sha256": _sha256(_canonical(first_scenarios)),
        "blockers": blockers,
        "artifact_policy": "hashes_counts_error_categories_and_bounded_difference_keys_only",
        "non_claims": [
            "no_complete_com_parity",
            "no_global_migration_row_close",
            "no_product_capability_promotion",
            "no_release_readiness",
            "no_configuration_value_payloads_committed",
            "no_bit_reproducible_binary_claim",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = aggregate(args.first, args.second, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": document["status"], "output": args.output.name}, sort_keys=True))
    return 0 if document["status"] == OPEN_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
