"""Aggregate two independent COM-03 pinned-oracle reports."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "sipi.com-03-direct-port-oracle-aggregate.v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scenario_projection(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "atol": item.get("atol"),
        "golden_sha256": item.get("golden_sha256"),
        "result_sha256": item.get("result_sha256"),
        "oracle_function": item.get("oracle_function"),
        "python_cli_contract": {
            "exit_code": item.get("python_cli", {}).get("exit_code"),
            "stdout": item.get("python_cli", {}).get("stdout"),
        },
        "rust_cli_contract": {
            "exit_code": item.get("rust_cli", {}).get("exit_code"),
            "stdout": item.get("rust_cli", {}).get("stdout"),
        },
        "cli_contract_match": item.get("cli_contract_match"),
        "stderr_exact_match": item.get("stderr_exact_match"),
    }


def aggregate(first: Path, second: Path) -> dict[str, Any]:
    left = json.loads(first.read_text(encoding="utf-8"))
    right = json.loads(second.read_text(encoding="utf-8"))
    if left.get("schema") != "sipi.com-03-direct-port-oracle.v1" or right.get("schema") != left.get("schema"):
        raise ValueError("oracle report schema drift")
    if left.get("source") != right.get("source"):
        raise ValueError("oracle source identity drift between fresh runs")
    if left.get("candidate") != right.get("candidate"):
        raise ValueError("candidate binding drift between fresh runs")
    if left.get("scenario_set_sha256") != right.get("scenario_set_sha256"):
        raise ValueError("scenario-set fixture digest drift between fresh runs")
    if not left.get("all_cli_contracts_match") or not right.get("all_cli_contracts_match"):
        raise ValueError("one fresh oracle run did not satisfy the CLI contract")
    left_scenarios = [scenario_projection(item) for item in left.get("scenarios", [])]
    right_scenarios = [scenario_projection(item) for item in right.get("scenarios", [])]
    if left_scenarios != right_scenarios:
        raise ValueError("fresh oracle scenario outcomes are not identical")
    return {
        "schema": SCHEMA,
        "source": left["source"],
        "candidate": left["candidate"],
        "scenario_set_sha256": left["scenario_set_sha256"],
        "invocations": [
            {"report": first.name, "run_id": left["run_id"], "sha256": sha256(first)},
            {"report": second.name, "run_id": right["run_id"], "sha256": sha256(second)},
        ],
        "scenario_count": len(left_scenarios),
        "fresh_runs": 2,
        "scenario_outcomes_identical": True,
        "all_cli_contracts_match": True,
        "stderr_is_not_a_frozen_contract": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = aggregate(args.first, args.second)
    with args.output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"scenario_count": document["scenario_count"], "fresh_runs": 2}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
