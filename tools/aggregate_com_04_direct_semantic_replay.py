"""Aggregate two fresh COM-04 semantic replay reports."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.report]
    if len(reports) != 2 or any(report.get("mode") != "com-04" for report in reports):
        raise SystemExit("exactly two COM-04 reports are required")
    semantic = [report["replays"][0]["semantic"] for report in reports]
    aggregate = {
        "schema": "sipi.com-04.direct-semantic-replay-aggregate.v1",
        "fresh_runs": len(reports),
        "scenario_count": len(semantic[0].get("scenarios", [])),
        "semantic_replays_identical": semantic[0] == semantic[1],
        "semantic_payload_sha256": [
            hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            for value in semantic
        ],
        "source": reports[0]["source"],
        "candidate": reports[0]["candidate"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if aggregate["semantic_replays_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
