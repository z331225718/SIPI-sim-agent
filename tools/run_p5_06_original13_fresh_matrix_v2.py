"""Add failure provenance to original-13 MATLAB replay reports.

This deliberately delegates execution to the frozen v1 runner.  v1 remains
the historical report contract; v2 only classifies its MATLAB failures from
the wrapper's per-case ``failure.json`` artifact.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    from .matlab_oracle_failure_v2 import classify_matlab_failure
except ImportError:
    from matlab_oracle_failure_v2 import classify_matlab_failure


V1 = Path(__file__).with_name("run_p5_06_original13_fresh_matrix.py")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("matlab", "rust"), required=True)
    parser.add_argument("--upstream-archive", type=Path, required=True)
    parser.add_argument("--candidate-archive", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--matlab", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--only")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    if args.report.exists():
        raise FileExistsError(args.report)
    args.output_root.mkdir(parents=True, exist_ok=True)
    v1_report = args.output_root / "original13-v1-raw-report.json"
    if v1_report.exists():
        raise FileExistsError(v1_report)
    command = [
        sys.executable,
        str(V1),
        "--engine", args.engine,
        "--upstream-archive", str(args.upstream_archive),
        "--candidate-archive", str(args.candidate_archive),
        "--output-root", str(args.output_root),
        "--report", str(v1_report),
        "--cargo", str(args.cargo),
        "--rustc", str(args.rustc),
        "--uv", str(args.uv),
        "--matlab", str(args.matlab),
        "--python", str(args.python),
        "--timeout", str(args.timeout),
    ]
    if args.only:
        command.extend(("--only", args.only))
    completed = subprocess.run(command, check=False)
    if not v1_report.is_file():
        return completed.returncode or 1
    payload = json.loads(v1_report.read_text(encoding="utf-8"))
    payload["schema"] = "sipi.p5-06.original13-fresh-run.v2"
    for ordinal, record in enumerate(payload["records"]):
        if args.engine != "matlab" or record["status"] != "matlab_failed":
            record["matlab_failure_classification"] = {"kind": "not_applicable"}
            continue
        classification = classify_matlab_failure(
            record["exit_code"],
            record["exit_code"] == 124,
            args.output_root / "run" / f"case-{ordinal:02d}" / "matlab",
        )
        record["matlab_failure_classification"] = classification
        record["status"] = classification["kind"]
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
