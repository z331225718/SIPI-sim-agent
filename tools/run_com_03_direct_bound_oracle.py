"""Run the additive COM-03 immutable-candidate oracle evidence lane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_com_03_direct_oracle import BOUND_SCHEMA, run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-com-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--toolchain", required=True)
    parser.add_argument("--cargo-executable", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = run(
        upstream_root=args.agent_com_root,
        run_id=args.run_id,
        candidate_root=args.candidate_root,
        candidate_commit=args.candidate_commit,
        toolchain=args.toolchain,
        cargo_executable=args.cargo_executable,
        evidence_schema=BOUND_SCHEMA,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "schema": report["schema"],
                "scenario_count": report["scenario_count"],
                "all_cli_contracts_match": report["all_cli_contracts_match"],
                "candidate_status": report["candidate"]["status"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["all_cli_contracts_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
