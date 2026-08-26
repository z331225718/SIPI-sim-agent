"""Aggregate two COM-03 current-candidate replay reports.

This is a bounded custody record for the compare leaf.  It intentionally does
not promote the leaf to a release or product-parity gate.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from run_com_01_current_candidate import (
    CRATE_RELATIVE,
    UPSTREAM_COMMIT,
    CANDIDATE_COMMIT,
    _archive,
    _atomic_json_create,
    _bounded_file,
    _git_inventory,
    _exact_keys,
    _hex,
)
from run_com_03_current_candidate import SEMANTIC_RUNNER_RELATIVE, _validate_com03_report


ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = "sipi.com-03.current-candidate-replay.v1"
AGGREGATE_SCHEMA = "sipi.com-03.current-candidate-replay.aggregate.v1"
OPEN_STATUS = "scoped_current_candidate_observed"
CANDIDATE_COMMIT = "bc882d2e5a19c2a844bacc485ede5b874e8f9c37"
CANDIDATE_TREE = "d87cfecea77ccd670073a6c069658e6b4e8c3137"
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
HEX64 = re.compile(r"^[0-9a-f]{64}$\Z")
PATH_LEAK = re.compile(r"(?i)(?:^|[\s=(\[\{\"'])" r"(?:[a-z]:[\\/]|\\\\|/|file://|\.\.?[\\/])")
EXPECTED_OUTCOMES = {"error_match": 16, "matched": 7}


class VerificationError(ValueError):
    """Raised when a report cannot be admitted to the aggregate."""


def validate_aggregate(value: Any) -> None:
    keys = {"schema", "status", "work_item", "leaf", "reports", "fresh_replays", "scenario_count", "semantic_match_count", "outcomes", "candidate_binary_bit_reproducible", "binary_raw_drift_scope", "candidate", "upstream", "toolchain", "harness", "scenarios", "blockers", "matched", "acceptance", "non_claims"}
    item = _exact_keys(value, keys, "COM-03 aggregate")
    if (item["schema"], item["status"], item["work_item"], item["leaf"]) != (AGGREGATE_SCHEMA, OPEN_STATUS, "COM-03", "compare"):
        raise VerificationError("COM-03 aggregate identity drift")
    if type(item["reports"]) is not list or len(item["reports"]) != 2:
        raise VerificationError("COM-03 aggregate report list drift")
    for report in item["reports"]:
        report = _exact_keys(report, {"path", "sha256", "run_id", "nonce", "candidate_binary_sha256"}, "COM-03 aggregate report")
        if type(report["path"]) is not str or not all(_hex(report[key]) for key in ("sha256", "run_id", "nonce", "candidate_binary_sha256")):
            raise VerificationError("COM-03 aggregate report identity drift")
    if any(type(item[key]) is not int for key in ("fresh_replays", "scenario_count", "semantic_match_count")) or type(item["outcomes"]) is not dict or any(type(value) is not int for value in item["outcomes"].values()) or item["fresh_replays"] != 2 or item["scenario_count"] != 23 or item["semantic_match_count"] != 23 or item["outcomes"] != EXPECTED_OUTCOMES:
        raise VerificationError("COM-03 aggregate summary drift")
    if type(item["candidate_binary_bit_reproducible"]) is not bool or item["binary_raw_drift_scope"] != "environment_local_scoped_no_canonical_pe_strategy":
        raise VerificationError("COM-03 aggregate binary scope drift")
    if item["matched"] is not False or item["acceptance"] is not False:
        raise VerificationError("COM-03 aggregate acceptance overclaim")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _path_free(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _path_free(key)
            _path_free(item)
    elif isinstance(value, list):
        for item in value:
            _path_free(item)
    elif isinstance(value, str):
        normalized = value.replace("\\", "/")
        if PATH_LEAK.search(normalized) or normalized.startswith(("/", "../")) or "file://" in normalized.lower():
            raise VerificationError("absolute path leaked into COM-03 evidence")


def _read(path: Path) -> tuple[dict[str, Any], str]:
    size, sha = _bounded_file(path, 4 * 1024 * 1024)
    payload = path.read_bytes()
    if len(payload) != size:
        raise VerificationError("report changed while reading")
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise VerificationError("report must be a JSON object")
    _path_free(value)
    try:
        _validate_com03_report(value)
    except ValueError as error:
        raise VerificationError(str(error)) from error
    return value, sha


def _stable_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _without_binary(value: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(value))
    build = result.get("build")
    if isinstance(build, dict):
        build.pop("binary_pre", None)
        build.pop("binary_post", None)
        build.pop("binary_stable", None)
        build.pop("cargo_source_pre", None)
        build.pop("cargo_source_post", None)
        build.pop("cargo_source_stable", None)
        build.pop("copy_matches_source", None)
    return result


def _validate_report(report: dict[str, Any], label: str) -> None:
    try:
        _validate_com03_report(report)
    except ValueError as error:
        raise VerificationError(f"{label}: {error}") from error
    if report.get("schema") != REPORT_SCHEMA:
        raise VerificationError(f"{label} report schema drift")
    if report.get("status") != OPEN_STATUS:
        raise VerificationError(f"{label} report status drift")
    if report.get("work_item") != "COM-03" or report.get("leaf") != "compare":
        raise VerificationError(f"{label} work-item drift")
    if report.get("candidate", {}).get("commit") != CANDIDATE_COMMIT or report.get("candidate", {}).get("tree") != CANDIDATE_TREE:
        raise VerificationError(f"{label} candidate binding drift")
    if report.get("upstream", {}).get("commit") != UPSTREAM_COMMIT or report.get("upstream", {}).get("tree") != UPSTREAM_TREE:
        raise VerificationError(f"{label} upstream binding drift")
    if report.get("matched") is not False or report.get("acceptance") is not False:
        raise VerificationError(f"{label} acceptance overclaim")
    if report.get("scenario_count") != 23 or report.get("semantic_match_count") != 23:
        raise VerificationError(f"{label} scenario parity summary drift")
    if report.get("outcomes") != EXPECTED_OUTCOMES:
        raise VerificationError(f"{label} outcome inventory drift")
    scenarios = report.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 23:
        raise VerificationError(f"{label} scenario count drift")
    if not all(isinstance(item, dict) and item.get("semantic_match") is True for item in scenarios):
        raise VerificationError(f"{label} scenario semantic mismatch")
    if Counter(item.get("outcome") for item in scenarios) != Counter(EXPECTED_OUTCOMES):
        raise VerificationError(f"{label} scenario outcome drift")
    run_id = report.get("run_id")
    nonce = report.get("nonce")
    if not isinstance(run_id, str) or HEX64.fullmatch(run_id) is None:
        raise VerificationError(f"{label} run id is not lowercase 64-hex")
    if not isinstance(nonce, str) or HEX64.fullmatch(nonce) is None:
        raise VerificationError(f"{label} nonce is not lowercase 64-hex")
    candidate = report.get("candidate")
    upstream = report.get("upstream")
    toolchain = report.get("toolchain")
    harness = report.get("harness")
    if not all(isinstance(item, dict) for item in (candidate, upstream, toolchain, harness)):
        raise VerificationError(f"{label} custody sections missing")
    if harness.get("same_crate_self_comparison") is not False or harness.get("independent_payload_paths") is not True:
        raise VerificationError(f"{label} compare isolation drift")
    if harness.get("scenario_count") != 23 or harness.get("result_schema") != "sipi.com-03-direct-port-oracle.v2":
        raise VerificationError(f"{label} harness drift")


def aggregate(first_path: Path, second_path: Path, output: Path, *, candidate_repo: Path | None = None, upstream_repo: Path | None = None) -> dict[str, Any]:
    if first_path.resolve() == second_path.resolve():
        raise VerificationError("fresh report paths must be distinct")
    if output.resolve() in {first_path.resolve(), second_path.resolve()}:
        raise VerificationError("aggregate output must be separate from input reports")
    first, first_sha = _read(first_path)
    second, second_sha = _read(second_path)
    if first_sha == second_sha:
        raise VerificationError("fresh report digests must be distinct")
    _validate_report(first, "first")
    _validate_report(second, "second")
    if first["run_id"] == second["run_id"]:
        raise VerificationError("fresh run ids must be distinct")
    if first["nonce"] == second["nonce"]:
        raise VerificationError("fresh nonces must be distinct")
    if _without_binary(first["candidate"]) != _without_binary(second["candidate"]):
        raise VerificationError("candidate static identity drift")
    for key in ("upstream", "toolchain", "harness", "outcomes", "scenario_count", "semantic_match_count", "scenarios", "blockers"):
        if first.get(key) != second.get(key):
            raise VerificationError(f"{key} drift between fresh replays")
    if candidate_repo is not None:
        archive = _archive(candidate_repo, CANDIDATE_COMMIT)
        if (len(archive), _sha256(archive)) != (first["candidate"]["archive"]["bytes"], first["candidate"]["archive"]["sha256"]):
            raise VerificationError("candidate Git archive identity drift")
        expected = _git_inventory(candidate_repo, CANDIDATE_COMMIT, (CRATE_RELATIVE, SEMANTIC_RUNNER_RELATIVE))
        if expected != first["candidate"]["inventory"]:
            raise VerificationError("candidate Git inventory drift")
    if upstream_repo is not None:
        archive = _archive(upstream_repo, UPSTREAM_COMMIT)
        if (len(archive), _sha256(archive)) != (first["upstream"]["archive"]["bytes"], first["upstream"]["archive"]["sha256"]):
            raise VerificationError("upstream Git archive identity drift")
        expected = _git_inventory(upstream_repo, UPSTREAM_COMMIT, (Path("src/agent_com"), Path("schemas/result-v1.schema.json")))
        if expected != first["upstream"]["inventory"]:
            raise VerificationError("upstream Git inventory drift")
    aggregate_value = {
        "schema": AGGREGATE_SCHEMA,
        "status": OPEN_STATUS,
        "work_item": "COM-03",
        "leaf": "compare",
        "reports": [
            {
                "path": _stable_path(first_path),
                "sha256": first_sha,
                "run_id": first["run_id"],
                "nonce": first["nonce"],
                "candidate_binary_sha256": first["candidate"]["build"]["binary_post"]["sha256"],
            },
            {
                "path": _stable_path(second_path),
                "sha256": second_sha,
                "run_id": second["run_id"],
                "nonce": second["nonce"],
                "candidate_binary_sha256": second["candidate"]["build"]["binary_post"]["sha256"],
            },
        ],
        "fresh_replays": 2,
        "scenario_count": 23,
        "semantic_match_count": 23,
        "outcomes": EXPECTED_OUTCOMES,
        "candidate_binary_bit_reproducible": first["candidate"]["build"]["binary_post"]["sha256"] == second["candidate"]["build"]["binary_post"]["sha256"],
        "binary_raw_drift_scope": "environment_local_scoped_no_canonical_pe_strategy",
        "candidate": first["candidate"],
        "upstream": first["upstream"],
        "toolchain": first["toolchain"],
        "harness": first["harness"],
        "scenarios": first["scenarios"],
        "blockers": [],
        "matched": False,
        "acceptance": False,
        "non_claims": [
            "no_complete_com_parity",
            "no_global_migration_row_close",
            "no_product_capability_promotion",
            "no_release_readiness",
            "no_S_parameter_fit",
            "channel_impulse_only_policy_unchanged",
            "no_raw_result_payloads_in_evidence",
        ],
    }
    validate_aggregate(aggregate_value)
    _path_free(aggregate_value)
    _atomic_json_create(output, aggregate_value, output_root=output.parent)
    return aggregate_value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--upstream-repo", type=Path, default=Path(r"C:\Users\z3312\code\COM"))
    args = parser.parse_args()
    try:
        value = aggregate(args.first, args.second, args.output, candidate_repo=args.candidate_repo, upstream_repo=args.upstream_repo)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"schema": value["schema"], "status": value["status"], "scenario_count": value["scenario_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
