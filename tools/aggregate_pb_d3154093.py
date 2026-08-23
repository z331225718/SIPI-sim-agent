"""Build the additive PB-01/PB-02 replay aggregate for candidate d3154093."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


CANDIDATE_COMMIT = "d3154093fd58aeaa596444825dc17be6cb7e35c0"
CANDIDATE_TREE = "2d51e84554558bb4947c0152259af9bf7f927efe"
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
ROWS = {
    "PB-01": {
        "schema": "sipi.pb-01-legacy-leaf-replay.v1",
        "fixture": "crates/sipi-pybert-direct/fixtures/pb-01-legacy-nrz.yaml",
        "arrays": [
            "chnl_h",
            "tx_out_h",
            "ctle_out_h",
            "dfe_out_h",
            "chnl_s",
            "tx_out_s",
            "ctle_out_s",
            "dfe_out_s",
            "chnl_p",
            "tx_out_p",
            "ctle_out_p",
            "dfe_out_p",
        ],
    },
    "PB-02": {
        "schema": "sipi.pb-02-direct-replay.v1",
        "fixture": "crates/sipi-pybert-direct/fixtures/pb-02-nrz.json",
        "arrays": [
            "channel_impulse_v_per_v.npy",
            "channel_output_v.npy",
            "ctle_output_v.npy",
            "rx_ffe_impulse_v_per_v.npy",
            "rx_filter_impulse_v_per_v.npy",
            "rx_input_v.npy",
            "rx_output_v.npy",
            "symbols_v.npy",
            "time_s.npy",
            "tx_channel_impulse_v_per_v.npy",
            "tx_waveform_v.npy",
        ],
    },
}


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def relative_path(path: Path, root: Path) -> str:
    resolved = path.resolve()
    relative = resolved.relative_to(root.resolve())
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"path is outside repository: {path}")
    return relative.as_posix()


def load_report(path: Path, root: Path, row: str) -> tuple[dict[str, Any], str, str]:
    relative = relative_path(path, root)
    payload = path.read_bytes()
    report = json.loads(payload.decode("utf-8"))
    if not isinstance(report, dict):
        raise ValueError(f"report is not an object: {relative}")
    spec = ROWS[row]
    if report.get("schema") != spec["schema"]:
        raise ValueError(f"{relative}: schema mismatch")
    if report.get("source_mode") != "git_archive_at_immutable_commit":
        raise ValueError(f"{relative}: non-archive source mode")
    if report.get("status") != "passed":
        raise ValueError(f"{relative}: replay is not passed")
    if report.get("candidate", {}).get("commit") != CANDIDATE_COMMIT or report.get("candidate", {}).get("tree") != CANDIDATE_TREE:
        raise ValueError(f"{relative}: candidate identity mismatch")
    if report.get("upstream", {}).get("commit") != UPSTREAM_COMMIT or report.get("upstream", {}).get("tree") != UPSTREAM_TREE:
        raise ValueError(f"{relative}: upstream identity mismatch")
    fixture = report.get("fixture", {})
    if fixture.get("path") != spec["fixture"] or fixture.get("archive_present") is not True:
        raise ValueError(f"{relative}: fixture binding mismatch")
    if row == "PB-01":
        comparison = report.get("replay", {}).get("comparison", {})
        arrays = comparison.get("arrays", [])
        if comparison.get("status") != "passed" or [item.get("name") for item in arrays] != spec["arrays"]:
            raise ValueError(f"{relative}: PB-01 payload gate mismatch")
        if not all(item.get("passed") is True for item in arrays):
            raise ValueError(f"{relative}: PB-01 array gate mismatch")
    else:
        parity = report.get("replay", {}).get("parity", {})
        if any(parity.get(key) is not True for key in ("candidate_exit_zero", "oracle_exit_zero", "candidate_array_members_equal_oracle")):
            raise ValueError(f"{relative}: PB-02 payload gate mismatch")
        if parity.get("array_member_names") != spec["arrays"]:
            raise ValueError(f"{relative}: PB-02 array member inventory mismatch")
    return report, relative, digest(payload)


def aggregate(first_path: Path, second_path: Path, output: Path, row: str, root: Path) -> dict[str, Any]:
    if row not in ROWS:
        raise ValueError(f"unsupported row: {row}")
    first, first_rel, first_hash = load_report(first_path, root, row)
    second, second_rel, second_hash = load_report(second_path, root, row)
    for label, left, right in (
        ("candidate", first.get("candidate"), second.get("candidate")),
        ("upstream", first.get("upstream"), second.get("upstream")),
        ("fixture", first.get("fixture"), second.get("fixture")),
        ("toolchain", first.get("toolchain"), second.get("toolchain")),
    ):
        if left != right:
            raise ValueError(f"immutable identity drift: {label}")
    if first.get("run_id") == second.get("run_id") or first.get("fresh_run_nonce") == second.get("fresh_run_nonce"):
        raise ValueError("fresh replay identities are not independent")
    if row == "PB-01":
        arrays = first["replay"]["comparison"]["arrays"]
        payload = {
            "array_names": ROWS[row]["arrays"],
            "lengths": {item["name"]: item["length"] for item in arrays},
            "max_abs": {item["name"]: item["max_abs"] for item in arrays},
            "all_passed": True,
        }
        blockers = [
            "The 12-array legacy payload is numerically equal within the pinned replay tolerances.",
            "Exact PyBertData class pickle restoration remains outside this data-only leaf.",
            "External AMI/IBIS/ts4/getwave model branches remain quarantined.",
        ]
    else:
        parity = first["replay"]["parity"]
        payload = {
            "array_member_names": parity["array_member_names"],
            "candidate_array_members_equal_oracle": True,
            "candidate_exit_zero": True,
            "oracle_exit_zero": True,
            "logical_payload_contract": "11-member f64 NPZ inventory and logical member hashes",
        }
        blockers = [
            "The 11-member sim-native payload is equal for this pinned fixture and replay pair only.",
            "Uncovered SimulationInputV1 branches remain outside this fixture-bound payload claim.",
            "External AMI/IBIS models remain quarantined and non-distributed.",
        ]

    result = {
        "schema": "sipi.pb-current-d3154093-replay-aggregate.v1",
        "version": 1,
        "row": row,
        "status": "passed_replay_open",
        "source_mode": "git_archive_at_immutable_commit",
        "candidate": first["candidate"],
        "upstream": first["upstream"],
        "fixture": first["fixture"],
        "toolchain": first["toolchain"],
        "reports": [
            {"path": first_rel, "sha256": first_hash, "run_id": first["run_id"], "fresh_run_nonce": first["fresh_run_nonce"]},
            {"path": second_rel, "sha256": second_hash, "run_id": second["run_id"], "fresh_run_nonce": second["fresh_run_nonce"]},
        ],
        "payload": payload,
        "claims": {
            "fixture_payload_parity": True,
            "global_row_closed": False,
            "promotion": False,
            "independent_branch_oracle_complete": False,
        },
        "blockers": blockers,
        "non_claims": [
            "This additive aggregate does not rewrite or supersede historical PB evidence.",
            "A fixture-bound replay pass is not global PyBERT branch parity.",
            "No Python class, AMI, IBIS, or host-owned service is distributed by this evidence.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--row", choices=sorted(ROWS), required=True)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = aggregate(args.first.resolve(), args.second.resolve(), args.output.resolve(), args.row, args.root.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "blockers": [str(error)]}, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps({"status": result["status"], "row": result["row"], "output": relative_path(args.output, args.root)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
