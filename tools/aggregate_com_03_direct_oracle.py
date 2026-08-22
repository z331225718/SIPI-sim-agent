"""Aggregate two independent COM-03 pinned-oracle reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA = "sipi.com-03-direct-port-oracle-aggregate.v1"
BOUND_INPUT_SCHEMA = "sipi.com-03-direct-port-oracle.v2"
BOUND_SCHEMA = "sipi.com-03-direct-port-oracle-aggregate.v2"


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


def aggregate(
    first: Path,
    second: Path,
    *,
    input_schema: str = "sipi.com-03-direct-port-oracle.v1",
    aggregate_schema: str = SCHEMA,
) -> dict[str, Any]:
    if first.resolve() == second.resolve():
        raise ValueError("fresh oracle reports must have distinct paths")
    first_sha256 = sha256(first)
    second_sha256 = sha256(second)
    if first_sha256 == second_sha256:
        raise ValueError("fresh oracle reports must have distinct complete report digests")
    left = json.loads(first.read_text(encoding="utf-8"))
    right = json.loads(second.read_text(encoding="utf-8"))
    if left.get("schema") != input_schema or right.get("schema") != left.get("schema"):
        raise ValueError("oracle report schema drift")
    if left.get("run_id") == right.get("run_id"):
        raise ValueError("fresh oracle reports must have distinct run ids")
    if input_schema == BOUND_INPUT_SCHEMA:
        left_nonce = left.get("fresh_run_nonce")
        right_nonce = right.get("fresh_run_nonce")
        nonce_pattern = re.compile(r"[0-9a-f]{64}")
        if not isinstance(left_nonce, str) or not nonce_pattern.fullmatch(left_nonce):
            raise ValueError("bound oracle report nonce is missing or malformed")
        if not isinstance(right_nonce, str) or not nonce_pattern.fullmatch(right_nonce):
            raise ValueError("bound oracle report nonce is missing or malformed")
        if left_nonce == right_nonce:
            raise ValueError("fresh oracle reports must have distinct nonces")
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
    left_invocation = {"report": first.name, "run_id": left["run_id"], "sha256": first_sha256}
    right_invocation = {"report": second.name, "run_id": right["run_id"], "sha256": second_sha256}
    if input_schema == BOUND_INPUT_SCHEMA:
        left_invocation["fresh_run_nonce"] = left["fresh_run_nonce"]
        right_invocation["fresh_run_nonce"] = right["fresh_run_nonce"]
    return {
        "schema": aggregate_schema,
        "source": left["source"],
        "candidate": left["candidate"],
        "scenario_set_sha256": left["scenario_set_sha256"],
        "invocations": [
            left_invocation,
            right_invocation,
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
