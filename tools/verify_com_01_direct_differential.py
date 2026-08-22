"""Verify a COM-01 differential report without trusting raw local paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from run_com_01_direct_oracle import SCHEMA, UPSTREAM_COMMIT, UPSTREAM_TREE, load_corpus

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "docs" / "baselines" / "com-01-direct-port-differential.v1.json"
EXPECTED_FIXTURES = {
    "primary_xlsx": {"bytes": 63311, "sha256": "f2c4c92f9549e720fff2843df6dc861aca7a503d59b2208898c2b67fa6fc0fc9"},
    "package_warning_csv": {"bytes": 4600, "sha256": "ebf22813b12e12d73bef253197eb747ac71db0bee4aee86a130fcba92dbaf295"},
}


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hex_sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_summary(summary: Any) -> None:
    require(isinstance(summary, dict), "scenario summary malformed")
    if "error_category" in summary:
        require(
            set(summary) == {
                "error_category",
                "stdout_bytes",
                "stdout_sha256",
                "stderr_bytes",
                "stderr_sha256",
            },
            "error summary contains raw payload",
        )
        require(hex_sha(summary["stdout_sha256"]) and hex_sha(summary["stderr_sha256"]), "error summary digest malformed")
        return
    if "projection_sha256" not in summary:
        require(set(summary) == {"stdout_bytes", "stdout_sha256"}, "text summary contains raw payload")
        require(hex_sha(summary["stdout_sha256"]), "text summary digest malformed")
        return
    allowed = {
        "projection_sha256",
        "top_level_keys",
        "parameters",
        "options",
        "package_blocks",
        "profile",
        "schema_version",
        "warnings",
        "materialized",
        "materialized_fingerprint",
        "consumption_summary",
    }
    require(set(summary) <= allowed, "JSON summary contains raw derived payload")
    require(hex_sha(summary["projection_sha256"]), "projection digest malformed")
    require(isinstance(summary.get("top_level_keys"), list), "top-level key inventory missing")
    if "materialized" in summary:
        materialized = summary["materialized"]
        require(
            isinstance(materialized, dict)
            and set(materialized)
            == {"parameter_count", "parameter_keys_sha256", "option_count", "option_keys_sha256"}
            and isinstance(materialized["parameter_count"], int)
            and isinstance(materialized["option_count"], int)
            and hex_sha(materialized["parameter_keys_sha256"])
            and hex_sha(materialized["option_keys_sha256"]),
            "materialized summary malformed",
        )
        require(hex_sha(summary.get("materialized_fingerprint")), "fingerprint summary malformed")
    if "consumption_summary" in summary:
        consumption = summary["consumption_summary"]
        require(
            isinstance(consumption, dict)
            and set(consumption) == {"total", "status_counts"}
            and isinstance(consumption["total"], int)
            and isinstance(consumption["status_counts"], dict)
            and set(consumption["status_counts"])
            == {"implemented", "report_only", "unimplemented", "obsolete", "unverified"},
            "consumption count summary malformed",
        )
        for counts in consumption["status_counts"].values():
            require(
                isinstance(counts, dict)
                and set(counts) == {"parameters", "options", "total"}
                and all(isinstance(counts[key], int) for key in counts),
                "consumption status counts malformed",
            )


def verify(report_path: Path = DEFAULT_REPORT, *, repo_root: Path = ROOT) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    require(report.get("schema") == SCHEMA, "report schema drift")
    require(report.get("work_item") == "COM-01", "report work item drift")
    source = report.get("source")
    require(
        isinstance(source, dict)
        and source.get("commit") == UPSTREAM_COMMIT
        and source.get("tree") == UPSTREAM_TREE,
        "source identity drift",
    )
    candidate = report.get("candidate")
    require(
        isinstance(candidate, dict)
        and isinstance(candidate.get("executable"), str)
        and Path(candidate["executable"]).name == candidate["executable"]
        and candidate.get("path_redacted") is True,
        "candidate path disclosure or identity drift",
    )
    fixtures = report.get("fixtures")
    require(isinstance(fixtures, list) and fixtures, "fixture inventory missing")
    roles = {entry.get("role") for entry in fixtures if isinstance(entry, dict)}
    require({"primary_xlsx", "package_warning_csv"} <= roles, "fixture role coverage missing")
    for entry in fixtures:
        require(
            isinstance(entry, dict)
            and isinstance(entry.get("role"), str)
            and entry.get("extension") in {".xlsx", ".csv"}
            and isinstance(entry.get("bytes"), int)
            and entry["bytes"] > 0
            and re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", ""))) is not None,
            "fixture inventory malformed",
        )
        expected = EXPECTED_FIXTURES.get(entry["role"])
        require(expected is not None and entry["bytes"] == expected["bytes"] and entry["sha256"] == expected["sha256"], "fixture digest drift")
    corpus = load_corpus()
    expected_ids = {scenario["id"] for scenario in corpus["scenarios"]}
    runs = report.get("runs")
    require(isinstance(runs, list) and len(runs) == 2, "two-run report required")
    nonces = set()
    run_ids = set()
    for run in runs:
        require(isinstance(run, dict), "run entry malformed")
        run_id = run.get("run_id")
        nonce = run.get("nonce")
        require(isinstance(run_id, str) and run_id not in run_ids, "run id not distinct")
        require(isinstance(nonce, str) and re.fullmatch(r"[0-9a-f]{64}", nonce), "nonce malformed")
        require(nonce not in nonces, "run nonce not distinct")
        run_ids.add(run_id)
        nonces.add(nonce)
        scenarios = run.get("scenarios")
        require(isinstance(scenarios, list) and {item.get("id") for item in scenarios} == expected_ids, "scenario set drift")
        for item in scenarios:
            require(
                isinstance(item, dict)
                and item.get("comparison")
                in {"passed", "error_code_match", "values_equal_fingerprint_drift", "mismatch", "error_code_mismatch"},
                "comparison status malformed",
            )
            comparison = item["comparison"]
            oracle_exit = item.get("oracle_exit")
            candidate_exit = item.get("candidate_exit")
            oracle_category = item.get("oracle_error_category")
            candidate_category = item.get("candidate_error_category")
            require(
                isinstance(item.get("difference_keys"), list)
                and len(item["difference_keys"]) <= 64
                and all(isinstance(key, str) and key for key in item["difference_keys"]),
                "difference-key summary malformed",
            )
            if comparison == "error_code_match":
                require(
                    oracle_exit == candidate_exit
                    and oracle_exit != 0
                    and isinstance(oracle_category, str)
                    and oracle_category == candidate_category
                    and item.get("value_match") is True,
                    "error parity requires matching exit and category",
                )
            elif comparison == "error_code_mismatch":
                require(
                    oracle_exit != candidate_exit or oracle_category != candidate_category,
                    "error mismatch is not evidenced",
                )
            else:
                require(oracle_exit == candidate_exit == 0, "success comparison hides exit mismatch")
                require(oracle_category is None and candidate_category is None, "success comparison has error category")
            if comparison == "values_equal_fingerprint_drift":
                require(
                    item.get("value_match") is True
                    and item.get("fingerprint_match") is False
                    and item["difference_keys"] == [],
                    "fingerprint-only drift is not isolated",
                )
            for key in ("oracle_summary", "candidate_summary"):
                validate_summary(item.get(key))
                text = json.dumps(item.get(key), sort_keys=True)
                require(not re.search(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\\\/]|/(?:Users|home|tmp|var)/", text), f"local path leaked: {key}")
    expected_status = "passed" if all(
        run.get("passed") and all(
            item.get("comparison") in {"passed", "error_code_match"} for item in run.get("scenarios", [])
        )
        for run in runs
    ) else "open_differential_mismatch"
    require(report.get("status") == expected_status, "report status does not match scenarios")
    report_text = json.dumps(report, sort_keys=True)
    require(not re.search(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\\\/]|/(?:Users|home|tmp|var)/", report_text), "report contains local path")
    return {
        "schema": report["schema"],
        "status": report["status"],
        "run_count": len(runs),
        "scenario_count": len(expected_ids),
        "report_sha256": sha256(report_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    try:
        print(verify(args.report))
    except VerificationError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
