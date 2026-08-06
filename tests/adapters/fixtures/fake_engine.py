"""Minimal fake engine used by the process adapter tests.

Writes a JSON report describing its argv, environment, cwd and optional
materialized input; honors --fail and --sleep for failure/timeout scenarios.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-json", required=True)
    parser.add_argument("--read")
    parser.add_argument("--fail", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.0)
    args = parser.parse_args()
    if args.sleep:
        time.sleep(args.sleep)
    if args.fail:
        print("fixture engine failed", file=sys.stderr)
        return 7
    report = {
        "argv": sys.argv[1:],
        "env_pythonpath": os.environ.get("PYTHONPATH"),
        "py_no_user_site": os.environ.get("PYTHONNOUSERSITE"),
        "cwd": os.getcwd(),
    }
    if args.read:
        report["read_content"] = Path(args.read).read_text(encoding="utf-8")
    Path(args.result_json).write_text(json.dumps(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
