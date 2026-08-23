"""Aggregate two independent AS-02..AS-06 preparation observations.

The v1 aggregate is intentionally unbound: temporary replay trees and source
identity are observations only.  An immutable content-addressed v2 may be
created after the preparation commit; v1 must never claim that binding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
ROWS = {"AS-02", "AS-03", "AS-04", "AS-05", "AS-06"}


def _canonical_sha(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def aggregate(row: str, reports: list[dict[str, Any]]) -> dict[str, Any]:
    if row not in ROWS:
        raise ValueError(f"unsupported row {row}")
    if len(reports) != 2:
        raise ValueError("exactly two independent replay reports are required")
    expected_schema = f"sipi.agent-spice-{row.lower()}-replay.v1"
    for report in reports:
        if report.get("schema") != expected_schema or report.get("workflow") != row:
            raise ValueError("replay schema/workflow mismatch")
        source = report.get("upstream")
        if not isinstance(source, dict) or source.get("commit") != COMMIT or source.get("tree") != TREE:
            raise ValueError("replay source identity mismatch")
        runs = report.get("runs")
        if not isinstance(runs, list) or len(runs) != 2:
            raise ValueError("each replay report must contain its two runs")
        if report.get("corpus_expected") is not True:
            raise ValueError("fixed corpus expectation did not pass")
        corpus = report.get("corpus")
        case_ids = [case.get("case") for run in runs for case in run.get("cases", []) if isinstance(case, dict)]
        if not isinstance(corpus, list) or sorted(case_ids) != sorted(corpus * 2):
            raise ValueError("fixed corpus case inventory mismatch")
    replay_instances = [report.get("replay_instance_sha256") for report in reports]
    if any(not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value) for value in replay_instances):
        raise ValueError("independent replay instance identity missing")
    if replay_instances[0] == replay_instances[1]:
        raise ValueError("independent replay instance identity must differ")
    for report in reports:
        if (
            report.get("binding_status") != "unbound_preparation_observation"
            or report.get("content_addressed_replay") is not False
            or report.get("immutable_source_binding") is not False
        ):
            raise ValueError("v1 replay reports must remain unbound preparation observations")
    run_hashes = [[run.get("tree_sha256") for run in report["runs"]] for report in reports]
    result = {
        "schema": f"sipi.agent-spice-{row.lower()}-replay-aggregate.v1",
        "workflow": row,
        "upstream": {"commit": COMMIT, "tree": TREE, "license": "MIT"},
        "corpus": reports[0].get("corpus"),
        "corpus_expected": True,
        "fresh_reports": 2,
        "runs_per_report": 2,
        "run_tree_sha256": run_hashes,
        "independent_report_sha256": [_canonical_sha(report) for report in reports],
        "replay_instance_sha256": replay_instances,
        "binding_status": "unbound_preparation_observation",
        "content_addressed_replay": False,
        "immutable_source_binding": False,
        "returncodes": [[run.get("returncode") for run in report["runs"]] for report in reports],
        "parity_status": "open",
        "numeric_comparison": "not_claimed",
    }
    if reports[1].get("corpus") != result["corpus"]:
        raise ValueError("replay corpus identity mismatch")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("row", choices=sorted(ROWS))
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    resolved_reports = [path.resolve() for path in args.report]
    if len(resolved_reports) != len(set(resolved_reports)):
        raise SystemExit("independent replay report paths must be distinct")
    if len(args.report) == 2 and args.report[0].read_bytes() == args.report[1].read_bytes():
        raise SystemExit("independent replay reports must have distinct complete payloads")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.report]
    try:
        result = aggregate(args.row, reports)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["corpus_expected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
