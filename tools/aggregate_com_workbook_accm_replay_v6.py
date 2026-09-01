"""Aggregate two independent current-candidate COM workbook replay reports."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from tools import run_com_workbook_accm_replay_v6 as replay
except ModuleNotFoundError as error:
    if error.name != "tools":
        raise
    import run_com_workbook_accm_replay_v6 as replay


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != "sipi.com.workbook-accm-replay.v6.diagnostic":
        raise ValueError("invalid v6 replay report")
    if value.get("status") != replay.STATUS or value.get("matched") is not True or value.get("acceptance") is not False or value.get("blockers") != []:
        raise ValueError("report is not a scoped numeric-parity observation")
    replay.legacy.assert_report_path_free(value)
    return value


def stable_controls(value: dict[str, Any]) -> list[dict[str, Any]]:
    controls = value.get("controls")
    if not isinstance(controls, list) or len(controls) != len(replay.legacy.CONTROL_VECTORS):
        raise ValueError("control matrix drift")
    result = []
    for control in controls:
        if not isinstance(control, dict) or not isinstance(control.get("comparison"), list):
            raise ValueError("control comparison drift")
        comparisons = control["comparison"]
        if len(comparisons) != 2 or not all(item.get("numeric_within_tolerance") is True for item in comparisons if isinstance(item, dict)):
            raise ValueError("numeric comparison drift")
        result.append({"vector": control.get("vector"), "comparison": comparisons})
    return result


def aggregate(first_path: Path, second_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError("aggregate output must be new")
    first = load(first_path)
    second = load(second_path)
    if first.get("run_id") == second.get("run_id") or first.get("nonce") == second.get("nonce"):
        raise ValueError("fresh run identities must differ")
    for key in ("candidate", "upstream", "fixtures", "fixture_post", "upstream_source_pre", "upstream_source_post", "archive_post", "port_order", "toolchain", "toolchain_post", "toolchain_stable"):
        if first.get(key) != second.get(key):
            raise ValueError(f"cross-run {key} drift")
    controls = stable_controls(first)
    if controls != stable_controls(second):
        raise ValueError("cross-run numeric projection drift")
    first_bytes = first_path.read_bytes()
    second_bytes = second_path.read_bytes()
    result = {
        "schema": "sipi.com.workbook-accm-replay.v6.aggregate",
        "status": replay.STATUS,
        "matched": True,
        "acceptance": False,
        "blockers": [],
        "candidate": first["candidate"],
        "upstream": first["upstream"],
        "controls": controls,
        "runs": [
            {"slot": "run1", "basename": first_path.name, "bytes": len(first_bytes), "sha256": hashlib.sha256(first_bytes).hexdigest(), "run_id": first["run_id"], "nonce": first["nonce"]},
            {"slot": "run2", "basename": second_path.name, "bytes": len(second_bytes), "sha256": hashlib.sha256(second_bytes).hexdigest(), "run_id": second["run_id"], "nonce": second["nonce"]},
        ],
        "non_claims": first["non_claims"],
    }
    replay.legacy.assert_report_path_free(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(args.first, args.second, args.output)
    print(json.dumps({"status": result["status"], "output": args.output.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
