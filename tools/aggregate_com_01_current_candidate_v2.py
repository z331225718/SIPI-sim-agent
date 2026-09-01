"""Aggregate two COM-01 current-candidate replay reports.

The aggregate is a custody and scoped-observation record.  It is deliberately
not a parity or release gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from run_com_01_current_candidate_v2 import (
    CANDIDATE_COMMIT,
    CRATE_RELATIVE,
    CORPUS_RELATIVE,
    FIXTURE_RELATIVE,
    SEMANTIC_RUNNER_RELATIVE,
    UPSTREAM_COMMIT,
    _archive,
    _atomic_json_create,
    _bounded_file,
    _git_inventory,
    _validate_com01_report,
    _exact_keys,
    _hex,
)


ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = "sipi.com-01.current-candidate-replay.v2"
AGGREGATE_SCHEMA = "sipi.com-01.current-candidate-replay.aggregate.v2"
OPEN_STATUS = "scoped_current_candidate_parity_observed"
HEX64 = re.compile(r"^[0-9a-f]{64}$\Z")
PATH_LEAK = re.compile(r"(?i)(?:^|[\s=(\[\{\"'])" r"(?:[a-z]:[\\/]|\\\\|/|file://|\.\.?[\\/])")
EXPECTED_OUTCOMES = {
    "error_code_match": 7,
    "passed": 7,
}


class VerificationError(ValueError):
    """Raised when a report cannot be admitted to the aggregate."""


def validate_aggregate(value: Any) -> None:
    keys = {"schema", "status", "work_item", "leaf", "reports", "fresh_replays", "scenario_count", "outcomes", "values_aligned", "materialized_fingerprint_drift", "candidate_binary_bit_reproducible", "binary_raw_drift_scope", "candidate", "upstream", "toolchain", "harness", "fixtures", "blockers", "matched", "acceptance", "non_claims"}
    item = _exact_keys(value, keys, "COM-01 aggregate")
    if (item["schema"], item["status"], item["work_item"], item["leaf"]) != (AGGREGATE_SCHEMA, OPEN_STATUS, "COM-01", "config-validate"):
        raise VerificationError("COM-01 aggregate identity drift")
    if type(item["reports"]) is not list or len(item["reports"]) != 2:
        raise VerificationError("COM-01 aggregate report list drift")
    for report in item["reports"]:
        report = _exact_keys(report, {"path", "sha256", "run_id", "nonce", "candidate_binary_sha256"}, "COM-01 aggregate report")
        if type(report["path"]) is not str or not all(_hex(report[key]) for key in ("sha256", "run_id", "nonce", "candidate_binary_sha256")):
            raise VerificationError("COM-01 aggregate report identity drift")
    if any(type(item[key]) is not int for key in ("fresh_replays", "scenario_count", "materialized_fingerprint_drift")) or type(item["outcomes"]) is not dict or any(type(value) is not int for value in item["outcomes"].values()) or item["fresh_replays"] != 2 or item["scenario_count"] != 14 or item["outcomes"] != EXPECTED_OUTCOMES or item["values_aligned"] is not True or item["materialized_fingerprint_drift"] != 0:
        raise VerificationError("COM-01 aggregate summary drift")
    if type(item["candidate_binary_bit_reproducible"]) is not bool or item["binary_raw_drift_scope"] != "environment_local_scoped_no_canonical_pe_strategy":
        raise VerificationError("COM-01 aggregate binary scope drift")
    if item["matched"] is not True or item["acceptance"] is not False:
        raise VerificationError("COM-01 aggregate acceptance overclaim")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _read(path: Path) -> tuple[dict[str, Any], str]:
    if path.resolve() == ROOT:
        raise VerificationError("report path is the repository root")
    size, sha = _bounded_file(path, 4 * 1024 * 1024)
    payload = path.read_bytes()
    if len(payload) != size:
        raise VerificationError("report changed while reading")
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise VerificationError("report must be a JSON object")
    _path_free(value)
    try:
        _validate_com01_report(value)
    except ValueError as error:
        raise VerificationError(str(error)) from error
    return value, sha


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
            raise VerificationError("absolute path leaked into COM-01 evidence")


def _stable_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _same_without_binary(left: dict[str, Any], right: dict[str, Any]) -> bool:
    def project(value: dict[str, Any]) -> dict[str, Any]:
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

    return project(left) == project(right)


def aggregate(
    first_path: Path,
    second_path: Path,
    output: Path,
    *,
    candidate_repo: Path | None = None,
    upstream_repo: Path | None = None,
) -> dict[str, Any]:
    if first_path.resolve() == second_path.resolve():
        raise VerificationError("fresh report paths must be distinct")
    first, first_sha = _read(first_path)
    second, second_sha = _read(second_path)
    if first_sha == second_sha:
        raise VerificationError("fresh report digests must be distinct")
    for label, report in (("first", first), ("second", second)):
        if report.get("values_aligned") is not True:
            raise VerificationError(f"{label} value projection is not aligned")
        run_id = report.get("run_id")
        nonce = report.get("nonce")
        if not isinstance(run_id, str) or HEX64.fullmatch(run_id) is None:
            raise VerificationError(f"{label} run id is not lowercase 64-hex")
        if not isinstance(nonce, str) or HEX64.fullmatch(nonce) is None:
            raise VerificationError(f"{label} nonce is not lowercase 64-hex")
    if first["run_id"] == second["run_id"]:
        raise VerificationError("fresh run ids must be distinct")
    if first["nonce"] == second["nonce"]:
        raise VerificationError("fresh nonces must be distinct")
    if not _same_without_binary(first["candidate"], second["candidate"]):
        raise VerificationError("candidate static identity drift")
    for key in ("upstream", "toolchain", "harness", "fixtures", "outcomes", "scenarios"):
        if first[key] != second[key]:
            raise VerificationError(f"{key} drift between fresh replays")
    if candidate_repo is not None:
        archive = _archive(candidate_repo, CANDIDATE_COMMIT)
        if (len(archive), _sha256(archive)) != (first["candidate"]["archive"]["bytes"], first["candidate"]["archive"]["sha256"]):
            raise VerificationError("candidate Git archive identity drift")
        expected = _git_inventory(candidate_repo, CANDIDATE_COMMIT, (CRATE_RELATIVE, CORPUS_RELATIVE, SEMANTIC_RUNNER_RELATIVE))
        if expected != first["candidate"]["inventory"]:
            raise VerificationError("candidate Git inventory drift")
    if upstream_repo is not None:
        archive = _archive(upstream_repo, UPSTREAM_COMMIT)
        if (len(archive), _sha256(archive)) != (first["upstream"]["archive"]["bytes"], first["upstream"]["archive"]["sha256"]):
            raise VerificationError("upstream Git archive identity drift")
        expected = _git_inventory(upstream_repo, UPSTREAM_COMMIT, (Path("src/agent_com"), Path("schemas/r480-config.schema.yaml"), Path("schemas/behavior-presets.yaml"), FIXTURE_RELATIVE))
        if expected != first["upstream"]["inventory"]:
            raise VerificationError("upstream Git inventory drift")
    aggregate_value = {
        "schema": AGGREGATE_SCHEMA,
        "status": OPEN_STATUS,
        "work_item": "COM-01",
        "leaf": "config-validate",
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
        "scenario_count": len(first["scenarios"]),
        "outcomes": first["outcomes"],
        "values_aligned": True,
        "materialized_fingerprint_drift": first["outcomes"].get("values_equal_fingerprint_drift", 0),
        "candidate_binary_bit_reproducible": first["candidate"]["build"]["binary_post"]["sha256"] == second["candidate"]["build"]["binary_post"]["sha256"],
        "binary_raw_drift_scope": "environment_local_scoped_no_canonical_pe_strategy",
        "candidate": first["candidate"],
        "upstream": first["upstream"],
        "toolchain": first["toolchain"],
        "harness": first["harness"],
        "fixtures": first["fixtures"],
        "blockers": [],
        "matched": True,
        "acceptance": False,
        "non_claims": [
            "no_complete_com_parity",
            "no_global_migration_row_close",
            "no_product_capability_promotion",
            "no_release_readiness",
            "no_S_parameter_fit",
            "channel_impulse_only_policy_unchanged",
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
