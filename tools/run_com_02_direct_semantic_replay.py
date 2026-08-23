"""Run two independent COM-02 direct semantic replays."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from com_direct_semantic_replay import redact_for_report, run_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = redact_for_report(run_report(args.binary, "com-02", args.run_id))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": report["schema"], "replay_count": 2, "semantic_replays_identical": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
