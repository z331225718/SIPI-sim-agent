"""Aggregate two immutable PB-01 scoped legacy-leaf replay reports."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import aggregate_pb_02_direct_replay as custody

SCHEMA = "sipi.pb-01-legacy-leaf-replay.v1"
AGGREGATE_SCHEMA = "sipi.pb-01-legacy-leaf-replay-aggregate.v1"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ARRAY_NAMES = (
    "chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h", "chnl_s", "tx_out_s",
    "ctle_out_s", "dfe_out_s", "chnl_p", "tx_out_p", "ctle_out_p", "dfe_out_p",
)
CANONICAL_ITEM_NAMES = (
    "chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h", "chnl_s", "tx_s",
    "ctle_s", "dfe_s", "tx_out_s", "ctle_out_s", "dfe_out_s", "chnl_p",
    "tx_out_p", "ctle_out_p", "dfe_out_p", "chnl_H", "tx_H", "ctle_H",
    "dfe_H", "tx_out_H", "ctle_out_H", "dfe_out_H", "tx_out",
)
COMPARISON_POLICY = {"absolute_tolerance": 1.0e-7, "relative_scale": 1.0e-6, "formula": "absolute_tolerance + relative_scale * scale"}


def _get(document: dict[str, Any], *keys: str) -> Any:
    value: Any = document
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def aggregate(first_path: Path, second_path: Path, output: Path) -> dict[str, Any]:
    first, first_hash = custody._read(first_path)
    second, second_hash = custody._read(second_path)
    blockers: list[str] = []
    if first_path.resolve() == second_path.resolve():
        blockers.append("report paths must be distinct")
    if first_hash == second_hash:
        blockers.append("complete report digests must be distinct")
    for label, document in (("first", first), ("second", second)):
        if document.get("schema") != SCHEMA:
            blockers.append(f"{label} schema drift")
        if document.get("status") != "passed":
            blockers.append(f"{label} replay is not passed")
        if document.get("source_mode") != "git_archive_at_immutable_commit":
            blockers.append(f"{label} is not archive-bound")
        if _get(document, "replay", "comparison", "status") != "passed":
            blockers.append(f"{label} scoped numeric comparison is not passed")
        if _get(document, "replay", "comparison", "policy") != COMPARISON_POLICY:
            blockers.append(f"{label} comparison policy drift")
        if document.get("reproducibility") != {"binary_bit_reproducible": False}:
            blockers.append(f"{label} binary reproducibility claim drift")
        harness = document.get("harness")
        if not isinstance(harness, dict) or harness.get("source_mode") != "content_addressed_working_tree_files":
            blockers.append(f"{label} content-addressed harness is missing")
        else:
            for key in ("runner", "custody_runner_helper"):
                binding = harness.get(key)
                if not isinstance(binding, dict) or set(binding) != {"path", "sha256"} or not isinstance(binding.get("sha256"), str) or HEX64.fullmatch(binding["sha256"]) is None:
                    blockers.append(f"{label} {key} harness binding malformed")
        schema = _get(document, "replay", "candidate_artifact_schema")
        expected = {
            "kind": "python_pickle_dict",
            "schema": "sipi.pybert_data.v1",
            "item_names": list(CANONICAL_ITEM_NAMES),
            "array_keys": sorted(CANONICAL_ITEM_NAMES),
        }
        if schema != expected:
            blockers.append(f"{label} candidate artifact schema is not exact")
        contract = document.get("artifact_contract")
        if not isinstance(contract, dict) or contract.get("selected_arrays") != list(ARRAY_NAMES) or contract.get("canonical_item_names") != list(CANONICAL_ITEM_NAMES):
            blockers.append(f"{label} artifact contract drift")
    first_toolchain = custody._toolchain_identity(first, "first", blockers)
    second_toolchain = custody._toolchain_identity(second, "second", blockers)
    if first_toolchain is not None and second_toolchain is not None and first_toolchain != second_toolchain:
        blockers.append("toolchain identity drift between replays")
    if first.get("run_id") == second.get("run_id"):
        blockers.append("run IDs must be distinct")
    first_nonce, second_nonce = first.get("fresh_run_nonce"), second.get("fresh_run_nonce")
    if not isinstance(first_nonce, str) or HEX64.fullmatch(first_nonce) is None:
        blockers.append("first fresh run nonce is missing or malformed")
    if not isinstance(second_nonce, str) or HEX64.fullmatch(second_nonce) is None:
        blockers.append("second fresh run nonce is missing or malformed")
    if first_nonce == second_nonce:
        blockers.append("fresh run nonces must be distinct")
    for name in ("candidate", "upstream", "fixture", "artifact_contract", "harness", "reproducibility"):
        if first.get(name) != second.get(name):
            blockers.append(f"{name} identity drift between replays")
    first_comparison = _get(first, "replay", "comparison")
    second_comparison = _get(second, "replay", "comparison")
    if first_comparison != second_comparison:
        blockers.append("comparison policy/facts drift between replays")
    first_id, second_id = custody._stable_report_id(first_path), custody._stable_report_id(second_path)
    if first_id == second_id:
        blockers.append("stable report ids must be distinct")
    result = {
        "schema": AGGREGATE_SCHEMA,
        "status": "passed" if not blockers else "blocked",
        "reports": [
            {"path": first_id, "sha256": first_hash, "run_id": first.get("run_id"), "fresh_run_nonce": first_nonce},
            {"path": second_id, "sha256": second_hash, "run_id": second.get("run_id"), "fresh_run_nonce": second_nonce},
        ],
        "candidate": first.get("candidate"),
        "upstream": first.get("upstream"),
        "fixture": first.get("fixture"),
        "toolchain": first_toolchain,
        "harness": first.get("harness"),
        "reproducibility": first.get("reproducibility"),
        "artifact_contract": first.get("artifact_contract"),
        "candidate_artifact_schema": _get(first, "replay", "candidate_artifact_schema"),
        "comparison": first_comparison,
        "blockers": blockers,
        "non_claims": first.get("non_claims"),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return result


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
