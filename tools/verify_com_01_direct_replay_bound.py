"""Verify immutable two-run COM-01 config leaf evidence without closing COM."""

from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/baselines/com-01-direct-replay-bound.v2.yaml"
REPORT_SCHEMA = "sipi.com-01-direct-replay.v1"
AGGREGATE_SCHEMA = "sipi.com-01-direct-replay-aggregate.v1"
OPEN_STATUS = "open_differential_mismatch_fingerprint_only"
CANDIDATE_COMMIT = "8bcfd1d1bc511461615f19338e453f0148e5dcb1"
CANDIDATE_TREE = "ed221a36f2d3325b0aac3f3336a9c8a14d13e99a"
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
LOCAL_PATH = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]|/(?:Users|home|tmp|var)/")
EXPECTED_OUTCOMES = {
    "passed": 6,
    "error_code_match": 7,
    "values_equal_fingerprint_drift": 1,
}
REPORT_KEYS = {
    "schema",
    "status",
    "work_item",
    "run_id",
    "fresh_run_nonce",
    "source_mode",
    "candidate",
    "upstream",
    "harness",
    "toolchain",
    "fixtures",
    "outcomes",
    "values_aligned",
    "fingerprint_drift_count",
    "scenarios",
    "artifact_policy",
    "non_claims",
}
SCENARIO_KEYS = {
    "id",
    "fixture_role",
    "output",
    "oracle_exit",
    "candidate_exit",
    "comparison",
    "value_match",
    "fingerprint_match",
    "difference_keys",
    "oracle_error_category",
    "candidate_error_category",
    "oracle_summary",
    "candidate_summary",
}


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def is_sha(value: Any) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def safe_file(repo_root: Path, reference: Any, label: str) -> Path:
    require(isinstance(reference, str) and reference, f"{label} path missing")
    relative = Path(reference)
    require(not relative.is_absolute() and not relative.anchor, f"{label} path must be relative")
    require(".." not in relative.parts, f"{label} path escapes repository")
    root = repo_root.resolve()
    path = (root / relative).resolve()
    require(root in path.parents and path.is_file(), f"{label} file missing")
    return path


def read_json(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    text = payload.decode("utf-8")
    require(LOCAL_PATH.search(text) is None, f"local absolute path leaked: {path.name}")
    document = json.loads(text)
    require(isinstance(document, dict), f"JSON document is not an object: {path.name}")
    return document, hashlib.sha256(payload).hexdigest()


def validate_summary(summary: Any) -> None:
    require(isinstance(summary, dict), "scenario summary malformed")
    if "error_category" in summary:
        require(
            set(summary)
            == {"error_category", "stdout_bytes", "stdout_sha256", "stderr_bytes", "stderr_sha256"},
            "error summary contains unbounded payload",
        )
        require(is_sha(summary["stdout_sha256"]) and is_sha(summary["stderr_sha256"]), "error digest malformed")
        return
    if "projection_sha256" not in summary:
        require(set(summary) == {"stdout_bytes", "stdout_sha256"}, "text summary contains unbounded payload")
        require(is_sha(summary["stdout_sha256"]), "text digest malformed")
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
    require(set(summary) <= allowed, "JSON summary contains unbounded payload")
    require(is_sha(summary.get("projection_sha256")), "projection digest malformed")
    require(isinstance(summary.get("top_level_keys"), list), "top-level key summary missing")
    if "materialized" in summary:
        materialized = summary["materialized"]
        require(
            isinstance(materialized, dict)
            and set(materialized)
            == {"parameter_count", "parameter_keys_sha256", "option_count", "option_keys_sha256"}
            and type(materialized["parameter_count"]) is int
            and type(materialized["option_count"]) is int
            and is_sha(materialized["parameter_keys_sha256"])
            and is_sha(materialized["option_keys_sha256"]),
            "materialized count/hash summary malformed",
        )
        require(is_sha(summary.get("materialized_fingerprint")), "fingerprint digest malformed")


def validate_toolchain(value: Any) -> None:
    require(isinstance(value, dict), "toolchain missing")
    require(set(value) == {"cargo", "rustc", "python", "timeout_seconds"}, "toolchain keys drift")
    require(type(value["timeout_seconds"]) is int and value["timeout_seconds"] == 300, "timeout drift")
    for role in ("cargo", "rustc", "python"):
        identity = value[role]
        require(
            isinstance(identity, dict)
            and set(identity)
            == {
                "role",
                "executable",
                "path_redacted",
                "file_sha256",
                "version_exit_code",
                "version_output_sha256",
            },
            f"{role} identity shape drift",
        )
        executable = identity["executable"]
        require(
            identity["role"] == role
            and isinstance(executable, str)
            and executable
            and not any(separator in executable for separator in ("/", "\\", ":"))
            and identity["path_redacted"] is True
            and is_sha(identity["file_sha256"])
            and identity["version_exit_code"] == 0
            and is_sha(identity["version_output_sha256"]),
            f"{role} identity invalid",
        )


def validate_scenarios(scenarios: Any, expected_ids: set[str]) -> None:
    require(isinstance(scenarios, list) and len(scenarios) == 14, "scenario count drift")
    require({item.get("id") for item in scenarios if isinstance(item, dict)} == expected_ids, "scenario ID drift")
    outcomes: Counter[str] = Counter()
    for item in scenarios:
        require(isinstance(item, dict) and set(item) == SCENARIO_KEYS, "scenario shape drift")
        comparison = item["comparison"]
        require(comparison in EXPECTED_OUTCOMES, "unexpected mismatch category")
        outcomes[comparison] += 1
        difference_keys = item["difference_keys"]
        require(
            isinstance(difference_keys, list)
            and len(difference_keys) <= 64
            and all(isinstance(key, str) and key for key in difference_keys),
            "difference-key summary malformed",
        )
        if comparison == "error_code_match":
            require(
                item["oracle_exit"] == item["candidate_exit"]
                and item["oracle_exit"] != 0
                and item["oracle_error_category"] == item["candidate_error_category"]
                and isinstance(item["oracle_error_category"], str)
                and item["value_match"] is True,
                "error parity does not bind exit and category",
            )
        else:
            require(item["oracle_exit"] == item["candidate_exit"] == 0, "success exit drift")
            require(item["oracle_error_category"] is None and item["candidate_error_category"] is None, "success has error category")
        if comparison == "values_equal_fingerprint_drift":
            require(
                item["value_match"] is True
                and item["fingerprint_match"] is False
                and difference_keys == [],
                "fingerprint-only drift is not isolated",
            )
        validate_summary(item["oracle_summary"])
        validate_summary(item["candidate_summary"])
    require(dict(outcomes) == EXPECTED_OUTCOMES, "scenario outcome counts drift")


def git_archive_sha256(root: Path, commit: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(root), "archive", "--format=tar", commit],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return hashlib.sha256(completed.stdout).hexdigest()


def verify(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    repo_root: Path = ROOT,
    candidate_root: Path | None = None,
    upstream_root: Path | None = None,
) -> dict[str, Any]:
    document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    require(isinstance(document, dict), "manifest must be a mapping")
    require(document.get("schema") == "sipi.com-01-direct-replay-bound.v2", "manifest schema drift")
    require(document.get("status") == "immutable_candidate_leaf_replay_bound_open_fingerprint_drift", "manifest status drift")
    scope = document.get("scope")
    require(
        scope
        == {
            "work_item": "COM-01",
            "leaf": "config-validate",
            "complete_com_parity": False,
            "global_migration_row_closed": False,
            "product_capability_promoted": False,
            "release_ready": False,
        },
        "scope overclaim or drift",
    )
    candidate = document.get("candidate")
    require(isinstance(candidate, dict), "candidate binding missing")
    require(candidate.get("commit") == CANDIDATE_COMMIT and candidate.get("tree") == CANDIDATE_TREE, "candidate commit/tree drift")
    require(candidate.get("source_mode") == "git_archive_at_immutable_commit", "candidate source mode drift")
    require(candidate.get("preallocation_preflight_retained") is True, "preflight binding missing")
    require(is_sha(candidate.get("archive_sha256")) and is_sha(candidate.get("cargo_lock_sha256")), "candidate digest malformed")
    upstream = document.get("upstream")
    require(isinstance(upstream, dict), "upstream binding missing")
    require(upstream.get("commit") == UPSTREAM_COMMIT and upstream.get("tree") == UPSTREAM_TREE, "upstream commit/tree drift")
    require(upstream.get("source_mode") == "git_archive_at_immutable_commit", "upstream source mode drift")
    require(upstream.get("archive_policy") == "core_autocrlf_false", "archive normalization drift")

    harness = document.get("harness")
    require(isinstance(harness, dict), "harness binding missing")
    for path_key, hash_key in (
        ("replay_runner", "replay_runner_sha256"),
        ("aggregate_runner", "aggregate_runner_sha256"),
        ("semantic_runner_from_candidate_archive", "semantic_runner_sha256"),
        ("corpus_from_candidate_archive", "corpus_sha256"),
    ):
        path = safe_file(repo_root, harness.get(path_key), path_key)
        require(sha256(path) == harness.get(hash_key), f"{path_key} hash drift")
    require(harness.get("scenario_count") == 14, "harness scenario count drift")
    require(harness.get("process_timeout_seconds") == 300, "harness timeout drift")
    require(harness.get("diagnostic_path_normalization") == "redacted_before_hash", "diagnostic redaction drift")
    require(harness.get("artifact_policy") == "hashes_counts_error_categories_and_bounded_difference_keys_only", "artifact policy drift")
    corpus = json.loads(safe_file(repo_root, harness["corpus_from_candidate_archive"], "corpus").read_text(encoding="utf-8"))
    require(canonical_sha256(corpus["scenarios"]) == harness.get("scenario_set_sha256"), "scenario set digest drift")
    expected_ids = {item["id"] for item in corpus["scenarios"]}

    fixtures = document.get("fixtures")
    require(isinstance(fixtures, list) and len(fixtures) == 2, "fixture manifest drift")
    expected_report_fixtures = [
        {key: item[key] for key in ("role", "extension", "bytes", "sha256")} for item in fixtures
    ]
    replay = document.get("formal_replays")
    require(isinstance(replay, dict), "formal replay binding missing")
    require(replay.get("report_schema") == REPORT_SCHEMA and replay.get("aggregate_schema") == AGGREGATE_SCHEMA, "report schema drift")
    require(replay.get("expected_status") == OPEN_STATUS, "open status drift")
    require(replay.get("expected_outcomes") == EXPECTED_OUTCOMES, "expected outcome drift")
    require(replay.get("values_aligned") is True and replay.get("fingerprint_drift_count") == 1, "fingerprint boundary drift")
    invocations = replay.get("invocations")
    require(isinstance(invocations, list) and len(invocations) == 2, "two formal invocations required")
    reports: list[dict[str, Any]] = []
    report_hashes: set[str] = set()
    run_ids: set[str] = set()
    nonces: set[str] = set()
    for invocation in invocations:
        require(isinstance(invocation, dict), "invocation malformed")
        path = safe_file(repo_root, invocation.get("report"), "replay report")
        report, report_hash = read_json(path)
        require(report_hash == invocation.get("sha256") and report_hash not in report_hashes, "report hash duplicate or drift")
        report_hashes.add(report_hash)
        require(set(report) == REPORT_KEYS, "report top-level shape drift")
        require(report["schema"] == REPORT_SCHEMA and report["status"] == OPEN_STATUS, "report status/schema drift")
        require(report["work_item"] == "COM-01" and report["source_mode"] == "git_archive_at_immutable_commit", "report scope drift")
        require(report["run_id"] == invocation.get("run_id") and report["run_id"] not in run_ids, "run ID drift or duplicate")
        run_ids.add(report["run_id"])
        nonce = report["fresh_run_nonce"]
        require(is_sha(nonce) and nonce == invocation.get("fresh_run_nonce") and nonce not in nonces, "run nonce drift or duplicate")
        nonces.add(nonce)
        report_candidate = report["candidate"]
        for key in ("commit", "tree", "archive_sha256", "inventory", "cargo_lock_sha256", "source_date_epoch"):
            require(report_candidate.get(key) == candidate.get(key), f"report candidate binding drift: {key}")
        require(report_candidate.get("binary_sha256") == invocation.get("candidate_binary_sha256"), "candidate binary hash drift")
        require(is_sha(report_candidate.get("build_stdout_sha256")) and is_sha(report_candidate.get("build_stderr_sha256")), "build summary digest malformed")
        require(report_candidate.get("build_log_policy") == "stable_event_categories", "build log policy drift")
        require(
            report["upstream"]
            == {
                "commit": upstream["commit"],
                "tree": upstream["tree"],
                "archive_sha256": upstream["archive_sha256"],
                "inventory": upstream["inventory"],
            },
            "report upstream binding drift",
        )
        expected_harness = {
            "orchestration_runner_sha256": harness["replay_runner_sha256"],
            "semantic_runner_sha256": harness["semantic_runner_sha256"],
            "corpus_sha256": harness["corpus_sha256"],
            "scenario_set_sha256": harness["scenario_set_sha256"],
            "scenario_count": 14,
            "process_timeout_seconds": 300,
            "diagnostic_path_normalization": "redacted_before_hash",
        }
        require(report["harness"] == expected_harness, "report harness binding drift")
        validate_toolchain(report["toolchain"])
        require(report["fixtures"] == expected_report_fixtures, "fixture digest drift")
        require(report["outcomes"] == EXPECTED_OUTCOMES, "report outcome drift")
        require(report["values_aligned"] is True and report["fingerprint_drift_count"] == 1, "report fingerprint boundary drift")
        require(report["artifact_policy"] == harness["artifact_policy"], "report artifact policy drift")
        validate_scenarios(report["scenarios"], expected_ids)
        reports.append(report)
    require(len(report_hashes) == len(run_ids) == len(nonces) == 2, "formal replay freshness drift")
    require(reports[0]["toolchain"] == reports[1]["toolchain"], "toolchain drift between replays")
    require(reports[0]["scenarios"] == reports[1]["scenarios"], "scenario summaries drift between replays")

    aggregate_path = safe_file(repo_root, replay.get("aggregate"), "aggregate report")
    aggregate, aggregate_hash = read_json(aggregate_path)
    require(aggregate_hash == replay.get("aggregate_sha256"), "aggregate report hash drift")
    require(aggregate.get("schema") == AGGREGATE_SCHEMA and aggregate.get("status") == OPEN_STATUS, "aggregate status/schema drift")
    require(aggregate.get("blockers") == [], "aggregate blockers are not empty")
    require(aggregate.get("outcomes") == EXPECTED_OUTCOMES and aggregate.get("values_aligned") is True, "aggregate outcome drift")
    require(aggregate.get("fingerprint_drift_count") == 1, "aggregate fingerprint drift count changed")
    require(aggregate.get("scenario_summaries_sha256") == canonical_sha256(reports[0]["scenarios"]), "aggregate scenario digest drift")
    require(aggregate.get("scenario_summaries_sha256") == replay.get("scenario_summaries_sha256"), "manifest scenario digest drift")
    require(aggregate.get("binary_bit_reproducible") is replay.get("binary_bit_reproducible") is False, "binary reproducibility overclaim")
    aggregate_invocations = aggregate.get("reports")
    require(isinstance(aggregate_invocations, list) and len(aggregate_invocations) == 2, "aggregate report binding missing")
    for invocation, bound in zip(invocations, aggregate_invocations, strict=True):
        require(
            bound
            == {
                "path": invocation["report"],
                "sha256": invocation["sha256"],
                "run_id": invocation["run_id"],
                "fresh_run_nonce": invocation["fresh_run_nonce"],
                "candidate_binary_sha256": invocation["candidate_binary_sha256"],
            },
            "aggregate invocation binding drift",
        )
    static_candidate = {key: value for key, value in reports[0]["candidate"].items() if key != "binary_sha256"}
    require(aggregate.get("candidate_static_identity") == static_candidate, "aggregate candidate identity drift")
    for key in ("upstream", "harness", "toolchain", "fixtures"):
        require(aggregate.get(key) == reports[0][key], f"aggregate {key} drift")
    require("no_bit_reproducible_binary_claim" in aggregate.get("non_claims", []), "binary non-claim missing")

    verification = document.get("verification")
    require(isinstance(verification, dict), "verification inventory missing")
    for path_key, hash_key in (
        ("verifier", "verifier_sha256"),
        ("mutation_tests", "mutation_tests_sha256"),
        ("runner_tests", "runner_tests_sha256"),
    ):
        path = safe_file(repo_root, verification.get(path_key), path_key)
        require(sha256(path) == verification.get(hash_key), f"{path_key} hash drift")
    audit = document.get("audit")
    require(isinstance(audit, dict), "audit binding missing")
    require(sha256(safe_file(repo_root, audit.get("path"), "audit")) == audit.get("sha256"), "audit hash drift")
    non_claims = document.get("non_claims")
    require(
        isinstance(non_claims, list)
        and {
            "no_complete_com_parity",
            "no_global_migration_row_close",
            "no_product_capability_promotion",
            "no_release_readiness",
            "no_configuration_value_payloads_committed",
            "no_mat_semantic_differential_parity",
            "no_selected_package_block_end_to_end_parity",
            "no_bit_reproducible_binary_claim",
        }
        == set(non_claims),
        "non-claim inventory drift",
    )

    if candidate_root is not None:
        require(git_archive_sha256(candidate_root, CANDIDATE_COMMIT) == candidate["archive_sha256"], "candidate archive hash drift")
        preflight_call = subprocess.check_output(
            ["git", "-C", str(candidate_root), "show", f"{CANDIDATE_COMMIT}:crates/sipi-agent-com-direct/src/config_validate_v1.rs"]
        ).decode("utf-8")
        require("preflight_config_source_v1(path, &extension)?" in preflight_call, "candidate preflight not retained")
    if upstream_root is not None:
        require(git_archive_sha256(upstream_root, UPSTREAM_COMMIT) == upstream["archive_sha256"], "upstream archive hash drift")

    return {
        "schema": document["schema"],
        "status": document["status"],
        "candidate_commit": CANDIDATE_COMMIT,
        "candidate_tree": CANDIDATE_TREE,
        "formal_replays": 2,
        "scenario_count": 14,
        "fingerprint_drift_count": 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--upstream-root", type=Path)
    args = parser.parse_args()
    try:
        print(
            verify(
                args.manifest,
                candidate_root=args.candidate_root,
                upstream_root=args.upstream_root,
            )
        )
    except (OSError, KeyError, ValueError, VerificationError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
