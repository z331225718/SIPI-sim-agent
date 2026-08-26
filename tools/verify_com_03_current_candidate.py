"""Verify the bounded two-run COM-03 current-candidate evidence."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from run_com_01_current_candidate import _bounded_file, _safe_file as _custody_safe_file
from run_com_03_current_candidate import _validate_com03_report


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/baselines/com-03-current-candidate-replay.v1.yaml"
REPORT_SCHEMA = "sipi.com-03.current-candidate-replay.v1"
AGGREGATE_SCHEMA = "sipi.com-03.current-candidate-replay.aggregate.v1"
STATUS = "scoped_current_candidate_observed"
CANDIDATE_COMMIT = "bc882d2e5a19c2a844bacc485ede5b874e8f9c37"
CANDIDATE_TREE = "d87cfecea77ccd670073a6c069658e6b4e8c3137"
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
HEX64 = re.compile(r"^[0-9a-f]{64}\Z")
PATH_LEAK = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\|file://|/(?:Users|home|tmp|var)/)")
EXPECTED_OUTCOMES = {"error_match": 16, "matched": 7}
EXPECTED_SCENARIO_SET_SHA256 = "f9124ce5020bb29cca9b28ddeb5b6feda6ff3755b2fb49142254db44ccb46ffd"
EXPECTED_IDS = {
    "identical",
    "schema_version_true_equals_one",
    "schema_version_float_equals_one",
    "provenance_empty_sequence",
    "provenance_pair_sequence_metadata_ignored",
    "non_comparable_metadata_ignored",
    "numeric_within_absolute_atol",
    "numeric_and_nested_mismatch",
    "object_key_mismatch",
    "array_length_mismatch",
    "scalar_string_mismatch",
    "invalid_schema_version",
    "missing_required_key",
    "invalid_profile",
    "empty_cases",
    "non_contiguous_case_index",
    "negative_signal",
    "non_integer_cursor",
    "invalid_eye_width_shape",
    "malformed_json",
    "negative_atol",
    "missing_golden",
    "missing_result",
}


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def is_sha(value: Any) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def _sha256(path: Path) -> str:
    return _bounded_file(path, 128 * 1024 * 1024)[1]


def _path_free(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _path_free(key)
            _path_free(item)
    elif isinstance(value, list):
        for item in value:
            _path_free(item)
    elif isinstance(value, str):
        require(PATH_LEAK.search(value) is None, "local path leaked into evidence")


def _safe_file(repo_root: Path, reference: Any, label: str) -> Path:
    require(isinstance(reference, str) and reference, f"{label} path missing")
    relative = Path(reference)
    require(not relative.is_absolute() and not relative.anchor, f"{label} path must be relative")
    require(".." not in relative.parts, f"{label} path escapes repository")
    try:
        return _custody_safe_file(repo_root, relative)
    except RuntimeError as error:
        raise VerificationError(f"{label}: {error}") from error


def _read_json(repo_root: Path, reference: Any, label: str) -> tuple[dict[str, Any], str]:
    path = _safe_file(repo_root, reference, label)
    size, digest = _bounded_file(path, 4 * 1024 * 1024)
    payload = path.read_bytes()
    require(len(payload) == size, f"{label} changed while reading")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"{label} is not UTF-8 JSON") from error
    require(isinstance(value, dict), f"{label} must be a JSON object")
    _path_free(value)
    return value, digest


def _validate_toolchain(value: Any) -> None:
    require(isinstance(value, dict) and set(value) == {"cargo", "rustc", "python", "uv"}, "toolchain shape drift")
    for role in ("cargo", "rustc", "python", "uv"):
        item = value[role]
        required = {
            "basename", "file_bytes", "file_sha256", "path_redacted", "role", "version_args", "version_exit",
            "version_stderr_sha256", "version_stdout_sha256",
        }
        require(isinstance(item, dict) and set(item) == required, f"{role} identity keys drift")
        basename = item["basename"]
        require(
            item["role"] == role
            and isinstance(basename, str)
            and basename
            and not any(separator in basename for separator in ("/", "\\", ":"))
            and item["path_redacted"] is True
            and type(item["file_bytes"]) is int
            and item["file_bytes"] > 0
            and is_sha(item["file_sha256"])
            and item["version_args"] == ["--version"]
            and item["version_exit"] == 0
            and is_sha(item["version_stderr_sha256"])
            and is_sha(item["version_stdout_sha256"]),
            f"{role} identity invalid",
        )


def _validate_command_result(value: Any) -> None:
    require(isinstance(value, dict), "compare result missing")
    require(set(value) == {"exit_code", "stderr_category", "stdout_bytes", "stdout_sha256"}, "compare result shape drift")
    require(type(value["exit_code"]) is int and 0 <= value["exit_code"] <= 255, "compare exit code drift")
    require(isinstance(value["stderr_category"], str) and value["stderr_category"], "compare diagnostic category missing")
    require(type(value["stdout_bytes"]) is int and value["stdout_bytes"] >= 0 and is_sha(value["stdout_sha256"]), "compare stdout receipt drift")


def _validate_scenarios(value: Any) -> None:
    require(isinstance(value, list) and len(value) == 23, "COM-03 scenario count drift")
    require({item.get("id") for item in value if isinstance(item, dict)} == EXPECTED_IDS, "COM-03 scenario IDs drift")
    outcomes: Counter[str] = Counter()
    for item in value:
        require(isinstance(item, dict), "scenario is not an object")
        required = {"atol", "candidate", "id", "independent_payload_paths", "mode", "oracle", "outcome", "payloads", "semantic_match"}
        require(set(item) == required, "COM-03 scenario shape drift")
        require(item["mode"] in {"compare", "error", "malformed", "negative_atol", "missing_golden", "missing_result"}, "COM-03 mode drift")
        require(
            type(item["atol"]) is float
            and ((item["mode"] == "negative_atol" and item["atol"] < 0.0) or (item["mode"] != "negative_atol" and item["atol"] >= 0.0)),
            "COM-03 tolerance drift",
        )
        require(item["outcome"] in EXPECTED_OUTCOMES, "COM-03 outcome drift")
        outcomes[item["outcome"]] += 1
        require(item["semantic_match"] is True and item["independent_payload_paths"] is True, "COM-03 semantic/isolation drift")
        _validate_command_result(item["candidate"])
        _validate_command_result(item["oracle"])
        require(item["candidate"] == item["oracle"], "COM-03 candidate/oracle result drift")
        payloads = item["payloads"]
        require(isinstance(payloads, dict) and set(payloads) == {"golden", "result"}, "COM-03 payload receipt drift")
        for payload in payloads.values():
            require(
                isinstance(payload, dict)
                and set(payload) == {"basename", "bytes", "path_redacted", "sha256"}
                and isinstance(payload["basename"], str)
                and payload["basename"]
                and type(payload["bytes"]) is int
                and payload["bytes"] >= 0
                and payload["path_redacted"] is True
                and is_sha(payload["sha256"]),
                "COM-03 bounded payload receipt malformed",
            )
    require(dict(outcomes) == EXPECTED_OUTCOMES, "COM-03 outcome inventory drift")


def _validate_report(report: dict[str, Any], label: str, manifest: dict[str, Any]) -> None:
    try:
        _validate_com03_report(report)
    except ValueError as error:
        raise VerificationError(f"{label}: {error}") from error
    require(report.get("schema") == REPORT_SCHEMA, f"{label} schema drift")
    require(report.get("status") == STATUS, f"{label} status drift")
    require(report.get("work_item") == "COM-03" and report.get("leaf") == "compare", f"{label} work-item drift")
    require(report.get("matched") is False and report.get("acceptance") is False, f"{label} acceptance overclaim")
    require(report.get("blockers") == [], f"{label} blocker drift")
    require(report.get("scenario_count") == 23 and report.get("semantic_match_count") == 23, f"{label} summary drift")
    require(report.get("outcomes") == EXPECTED_OUTCOMES, f"{label} outcomes drift")
    require(isinstance(report.get("run_id"), str) and HEX64.fullmatch(report["run_id"]), f"{label} run ID drift")
    require(isinstance(report.get("nonce"), str) and HEX64.fullmatch(report["nonce"]), f"{label} nonce drift")
    candidate = report.get("candidate")
    require(isinstance(candidate, dict), f"{label} candidate missing")
    require(candidate.get("commit") == CANDIDATE_COMMIT and candidate.get("tree") == CANDIDATE_TREE, f"{label} candidate revision drift")
    require(candidate.get("source_mode") == "git_archive_at_immutable_commit", f"{label} candidate source mode drift")
    archive = candidate.get("archive")
    require(isinstance(archive, dict) and archive.get("path_redacted") is True and is_sha(archive.get("sha256")), f"{label} archive receipt drift")
    require(is_sha(candidate.get("cargo_lock_sha256")), f"{label} Cargo.lock receipt drift")
    manifest_candidate = manifest["candidate"]
    require(archive.get("sha256") == manifest_candidate["archive_sha256"], f"{label} candidate archive binding drift")
    require(archive.get("bytes") == manifest_candidate["archive_bytes"], f"{label} candidate archive size drift")
    require(candidate.get("inventory") == manifest_candidate["inventory"], f"{label} candidate inventory drift")
    require(candidate.get("cargo_lock_sha256") == manifest_candidate["cargo_lock_sha256"], f"{label} candidate Cargo.lock drift")
    require(candidate.get("source_date_epoch") == str(manifest_candidate["source_date_epoch"]), f"{label} source date drift")
    build = candidate.get("build")
    require(isinstance(build, dict) and build.get("log_policy") == "stable_event_categories", f"{label} build log policy drift")
    binary = build.get("binary_post")
    require(isinstance(binary, dict) and binary.get("path_redacted") is True and is_sha(binary.get("sha256")), f"{label} binary receipt drift")
    upstream = report.get("upstream")
    require(isinstance(upstream, dict), f"{label} upstream missing")
    require(upstream.get("commit") == UPSTREAM_COMMIT and upstream.get("tree") == UPSTREAM_TREE, f"{label} upstream revision drift")
    require(upstream.get("source_mode") == "git_archive_at_immutable_commit", f"{label} upstream source mode drift")
    manifest_upstream = manifest["upstream"]
    require(upstream.get("archive", {}).get("sha256") == manifest_upstream["archive_sha256"], f"{label} upstream archive binding drift")
    require(upstream.get("archive", {}).get("bytes") == manifest_upstream["archive_bytes"], f"{label} upstream archive size drift")
    require(upstream.get("inventory") == manifest_upstream["inventory"], f"{label} upstream inventory drift")
    runtime = upstream.get("runtime")
    require(isinstance(runtime, dict) and runtime.get("runtime") == "executed_clean_archive_uv_frozen_offline", f"{label} runtime mode drift")
    require(runtime.get("environment", {}).get("direct_python_fallback") is False, f"{label} runtime fallback drift")
    source = runtime.get("source", {})
    require(source.get("module_file", {}).get("relative_path") == "src/agent_com/__init__.py", f"{label} source receipt drift")
    require(source.get("module_file", {}).get("path_redacted") is True and is_sha(source.get("module_file", {}).get("sha256")), f"{label} source digest drift")
    require(source.get("module_file", {}).get("sha256") == manifest_upstream["source_module_sha256"], f"{label} source module binding drift")
    require(report.get("toolchain", {}).get("stable") is True, f"{label} toolchain stability drift")
    harness = report.get("harness")
    require(isinstance(harness, dict), f"{label} harness missing")
    require(harness.get("scenario_count") == 23 and harness.get("same_crate_self_comparison") is False, f"{label} harness isolation drift")
    require(harness.get("independent_payload_paths") is True and harness.get("scenario_set_sha256") == EXPECTED_SCENARIO_SET_SHA256, f"{label} harness drift")
    for key in ("runner", "semantic_runner"):
        require(harness.get(key) == manifest["harness"][key], f"{label} {key} binding drift")
    _validate_scenarios(report.get("scenarios"))


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


def verify(manifest_path: Path = DEFAULT_MANIFEST, *, repo_root: Path = ROOT) -> dict[str, Any]:
    document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    require(isinstance(document, dict), "manifest must be a mapping")
    require(document.get("schema") == "sipi.com-03.current-candidate-replay.v1", "manifest schema drift")
    require(document.get("status") == STATUS, "manifest status drift")
    require(document.get("scope") == {
        "work_item": "COM-03",
        "leaf": "compare",
        "complete_com_parity": False,
        "global_migration_row_closed": False,
        "product_capability_promoted": False,
        "release_ready": False,
    }, "manifest scope overclaim or drift")
    require(document.get("policy") == {
        "s_parameter_fit": "not_in_scope",
        "channel_simulation": "impulse_only",
        "raw_result_payloads_in_evidence": False,
        "same_crate_self_comparison": False,
    }, "manifest policy drift")
    candidate = document.get("candidate")
    require(isinstance(candidate, dict) and candidate.get("commit") == CANDIDATE_COMMIT and candidate.get("tree") == CANDIDATE_TREE, "manifest candidate revision drift")
    require(candidate.get("source_mode") == "git_archive_at_immutable_commit" and is_sha(candidate.get("archive_sha256")) and is_sha(candidate.get("cargo_lock_sha256")), "manifest candidate custody drift")
    require(type(candidate.get("archive_bytes")) is int and candidate["archive_bytes"] > 0, "manifest candidate archive size drift")
    require(isinstance(candidate.get("inventory"), dict) and candidate["inventory"].get("file_count") == 23 and type(candidate["inventory"].get("total_bytes")) is int and is_sha(candidate["inventory"].get("sha256")), "manifest candidate inventory drift")
    upstream = document.get("upstream")
    require(isinstance(upstream, dict) and upstream.get("commit") == UPSTREAM_COMMIT and upstream.get("tree") == UPSTREAM_TREE, "manifest upstream revision drift")
    require(upstream.get("source_mode") == "git_archive_at_immutable_commit" and type(upstream.get("archive_bytes")) is int and upstream["archive_bytes"] > 0 and is_sha(upstream.get("archive_sha256")), "manifest upstream archive drift")
    require(isinstance(upstream.get("inventory"), dict) and upstream["inventory"].get("file_count") == 68 and is_sha(upstream["inventory"].get("sha256")), "manifest upstream inventory drift")
    require(is_sha(upstream.get("source_module_sha256")), "manifest source module drift")
    harness = document.get("harness")
    require(isinstance(harness, dict) and harness.get("scenario_count") == 23 and harness.get("scenario_set_sha256") == EXPECTED_SCENARIO_SET_SHA256, "manifest harness drift")
    require(harness.get("runner") == "tools/run_com_03_current_candidate.py" and is_sha(harness.get("runner_sha256")), "manifest runner drift")
    require(harness.get("aggregate_runner") == "tools/aggregate_com_03_current_candidate.py" and is_sha(harness.get("aggregate_runner_sha256")), "manifest aggregate runner drift")
    require(harness.get("semantic_runner") == "tools/run_com_03_direct_oracle.py" and is_sha(harness.get("semantic_runner_sha256")), "manifest semantic runner drift")
    require(harness.get("no_s_fit") is True and harness.get("channel_impulse_only") is True, "manifest simulation policy drift")
    physical = document.get("physical")
    require(isinstance(physical, list) and physical, "manifest physical map missing")
    for entry in physical:
        require(isinstance(entry, dict) and set(entry) == {"path", "sha256"} and is_sha(entry.get("sha256")), "physical map drift")
        path = _safe_file(repo_root, entry["path"], "physical")
        require(_sha256(path) == entry["sha256"], f"physical hash drift: {entry['path']}")
    audit = document.get("audit")
    require(isinstance(audit, dict) and set(audit) == {"path", "sha256"} and is_sha(audit.get("sha256")), "audit binding drift")
    audit_path = _safe_file(repo_root, audit["path"], "audit")
    require(_sha256(audit_path) == audit["sha256"], "audit content hash drift")
    reports = document.get("reports")
    require(isinstance(reports, list) and len(reports) == 2, "two reports are required")
    seen_paths: set[Path] = set()
    seen_hashes: set[str] = set()
    seen_ids: set[str] = set()
    seen_nonces: set[str] = set()
    report_values: list[dict[str, Any]] = []
    for index, binding in enumerate(reports, 1):
        require(isinstance(binding, dict) and set(binding) == {"path", "sha256", "run_id", "nonce"}, f"report binding {index} drift")
        path = _safe_file(repo_root, binding["path"], f"report {index}")
        require(path not in seen_paths, "report paths are not distinct")
        seen_paths.add(path)
        report, digest = _read_json(repo_root, binding["path"], f"report {index}")
        require(digest == binding["sha256"] and digest not in seen_hashes, f"report {index} hash drift")
        seen_hashes.add(digest)
        require(report.get("run_id") == binding["run_id"] and report.get("nonce") == binding["nonce"], f"report {index} identity drift")
        require(report["run_id"] not in seen_ids and report["nonce"] not in seen_nonces, f"report {index} replay identity is not fresh")
        seen_ids.add(report["run_id"])
        seen_nonces.add(report["nonce"])
        _validate_report(report, f"report {index}", document)
        report_values.append(report)
    require(_without_binary(report_values[0]["candidate"]) == _without_binary(report_values[1]["candidate"]), "candidate static receipt drift between reports")
    require(report_values[0]["upstream"] == report_values[1]["upstream"], "upstream receipt drift between reports")
    require(report_values[0]["toolchain"] == report_values[1]["toolchain"], "toolchain drift between reports")
    require(report_values[0]["scenarios"] == report_values[1]["scenarios"], "scenario projection drift between reports")
    aggregate_binding = document.get("aggregate")
    require(isinstance(aggregate_binding, dict) and set(aggregate_binding) == {"path", "sha256"} and is_sha(aggregate_binding.get("sha256")), "aggregate binding drift")
    aggregate, aggregate_sha = _read_json(repo_root, aggregate_binding["path"], "aggregate")
    require(aggregate_sha == aggregate_binding["sha256"], "aggregate hash drift")
    require(aggregate.get("schema") == AGGREGATE_SCHEMA and aggregate.get("status") == STATUS, "aggregate schema/status drift")
    require(aggregate.get("work_item") == "COM-03" and aggregate.get("leaf") == "compare", "aggregate work-item drift")
    require(aggregate.get("fresh_replays") == 2 and aggregate.get("scenario_count") == 23 and aggregate.get("semantic_match_count") == 23, "aggregate count drift")
    require(aggregate.get("outcomes") == EXPECTED_OUTCOMES and aggregate.get("blockers") == [], "aggregate outcome drift")
    require(aggregate.get("matched") is False and aggregate.get("acceptance") is False, "aggregate acceptance overclaim")
    aggregate_reports = aggregate.get("reports")
    require(isinstance(aggregate_reports, list) and len(aggregate_reports) == 2, "aggregate report bindings missing")
    for expected, actual in zip(reports, aggregate_reports):
        require(actual.get("path") == Path(expected["path"]).as_posix(), "aggregate report path drift")
        require(actual.get("sha256") == expected["sha256"] and actual.get("run_id") == expected["run_id"] and actual.get("nonce") == expected["nonce"], "aggregate report identity drift")
    return {"schema": document["schema"], "status": document["status"], "scenario_count": 23, "fresh_replays": 2}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    try:
        value = verify(args.manifest)
    except (OSError, ValueError, VerificationError, yaml.YAMLError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
