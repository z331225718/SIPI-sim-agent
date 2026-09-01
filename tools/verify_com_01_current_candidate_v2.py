"""Verify the bounded two-run COM-01 current-candidate evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from run_com_01_current_candidate_v2 import (
    _bounded_file,
    _safe_file as _custody_safe_file,
    _validate_com01_report,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/baselines/com-01-current-candidate-replay.v2.yaml"
REPORT_SCHEMA = "sipi.com-01.current-candidate-replay.v2"
AGGREGATE_SCHEMA = "sipi.com-01.current-candidate-replay.aggregate.v2"
STATUS = "scoped_current_candidate_parity_observed"
CANDIDATE_COMMIT = "5b974ebd799fefd2b89c11a0626dc5c6e555d885"
CANDIDATE_TREE = "329bfc2b08d5593744f498aea18c924c7a41e9dd"
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
HEX64 = re.compile(r"^[0-9a-f]{64}$\Z")
PATH_LEAK = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\|file://|/(?:Users|home|tmp|var)/)")
EXPECTED_OUTCOMES = {
    "error_code_match": 7,
    "passed": 7,
}
EXPECTED_SCENARIO_SET_SHA256 = "abcb4cdecfb67f5de13439baec64cf45f752bc76a7765ace7434b2874523fa96"
EXPECTED_IDS = {
    "xlsx_json_default_r480",
    "xlsx_text_default_r480",
    "xlsx_materialized_json_default",
    "xlsx_experimental_corrected_profile",
    "xlsx_custom_standard_reader",
    "csv_package_warning_json_loader",
    "xlsx_custom_fix_config_defaults",
    "mutually_exclusive_json_modes",
    "custom_profile_without_selector",
    "reader_without_custom_profile",
    "unknown_fix_id",
    "duplicate_override",
    "unsupported_extension",
    "missing_config_path",
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


def _canonical_sha(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
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
    require(isinstance(value, dict), "toolchain missing")
    require(set(value) == {"cargo", "rustc", "python", "uv"}, "toolchain keys drift")
    for role in ("cargo", "rustc", "python", "uv"):
        identity = value[role]
        require(isinstance(identity, dict), f"{role} identity malformed")
        required = {
            "basename",
            "file_bytes",
            "file_sha256",
            "path_redacted",
            "role",
            "version_args",
            "version_exit",
            "version_stderr_sha256",
            "version_stdout_sha256",
        }
        require(set(identity) == required, f"{role} identity keys drift")
        basename = identity["basename"]
        require(
            identity["role"] == role
            and isinstance(basename, str)
            and basename
            and not any(separator in basename for separator in ("/", "\\", ":"))
            and identity["path_redacted"] is True
            and type(identity["file_bytes"]) is int
            and identity["file_bytes"] > 0
            and is_sha(identity["file_sha256"])
            and identity["version_args"] == ["--version"]
            and identity["version_exit"] == 0
            and is_sha(identity["version_stderr_sha256"])
            and is_sha(identity["version_stdout_sha256"]),
            f"{role} identity invalid",
        )


def _validate_summary(value: Any) -> None:
    require(isinstance(value, dict), "scenario summary malformed")
    if "error_category" in value:
        require(
            set(value) == {"error_category", "stderr_bytes", "stderr_sha256", "stdout_bytes", "stdout_sha256"},
            "error summary shape drift",
        )
        require(isinstance(value["error_category"], str) and value["error_category"], "error category missing")
    else:
        require(set(value) <= {
            "projection_sha256", "top_level_keys", "parameters", "options", "package_blocks", "profile",
            "schema_version", "warnings", "materialized", "materialized_fingerprint", "consumption_summary",
            "stdout_bytes", "stdout_sha256",
        }, "summary contains unbounded fields")
    for key in ("stdout_sha256", "stderr_sha256", "projection_sha256", "materialized_fingerprint"):
        if key in value:
            require(is_sha(value[key]), f"summary digest malformed: {key}")


def _validate_scenarios(value: Any) -> None:
    require(isinstance(value, list) and len(value) == 14, "COM-01 scenario count drift")
    require({item.get("id") for item in value if isinstance(item, dict)} == EXPECTED_IDS, "COM-01 scenario IDs drift")
    for item in value:
        require(isinstance(item, dict), "scenario is not an object")
        required = {
            "candidate_error_category", "candidate_exit", "candidate_summary", "comparison", "difference_keys",
            "fingerprint_match", "fixture_role", "id", "oracle_error_category", "oracle_exit", "oracle_summary",
            "output", "value_match",
        }
        require(set(item) == required, "COM-01 scenario shape drift")
        require(item["comparison"] in EXPECTED_OUTCOMES, "COM-01 comparison category drift")
        require(isinstance(item["difference_keys"], list) and len(item["difference_keys"]) <= 64, "difference summary drift")
        require(all(isinstance(key, str) and key for key in item["difference_keys"]), "difference key malformed")
        require(item["candidate_exit"] == item["oracle_exit"], "COM-01 exit code drift")
        require(item["value_match"] is True, "COM-01 value projection mismatch")
        require(item["comparison"] in {"passed", "error_code_match"}, "unexpected comparison")
        if item["comparison"] == "passed" and item["output"] == "materialized_json":
            require(item["fingerprint_match"] is True and item["difference_keys"] == [], "materialized parity drift")
        _validate_summary(item["candidate_summary"])
        _validate_summary(item["oracle_summary"])


def _validate_report(report: dict[str, Any], label: str, manifest: dict[str, Any]) -> None:
    try:
        _validate_com01_report(report)
    except ValueError as error:
        raise VerificationError(f"{label}: {error}") from error
    require(report.get("schema") == REPORT_SCHEMA, f"{label} schema drift")
    require(report.get("status") == STATUS, f"{label} status drift")
    require(report.get("work_item") == "COM-01" and report.get("leaf") == "config-validate", f"{label} work item drift")
    require(report.get("values_aligned") is True, f"{label} value alignment drift")
    require(report.get("outcomes") == EXPECTED_OUTCOMES, f"{label} outcome drift")
    require(report.get("matched") is True and report.get("acceptance") is False, f"{label} acceptance drift")
    require(report.get("blockers") == [], f"{label} blocker drift")
    require(isinstance(report.get("run_id"), str) and HEX64.fullmatch(report["run_id"]), f"{label} run id drift")
    require(isinstance(report.get("nonce"), str) and HEX64.fullmatch(report["nonce"]), f"{label} nonce drift")
    candidate = report.get("candidate")
    require(isinstance(candidate, dict), f"{label} candidate missing")
    require(candidate.get("commit") == CANDIDATE_COMMIT and candidate.get("tree") == CANDIDATE_TREE, f"{label} candidate revision drift")
    require(candidate.get("source_mode") == "git_archive_at_immutable_commit", f"{label} candidate source mode drift")
    require(candidate.get("archive", {}).get("path_redacted") is True, f"{label} archive path policy drift")
    require(is_sha(candidate.get("archive", {}).get("sha256")), f"{label} candidate archive digest missing")
    require(is_sha(candidate.get("cargo_lock_sha256")), f"{label} Cargo.lock digest missing")
    manifest_candidate = manifest["candidate"]
    require(candidate["archive"].get("sha256") == manifest_candidate["archive_sha256"], f"{label} candidate archive binding drift")
    require(candidate["archive"].get("bytes") == manifest_candidate["archive_bytes"], f"{label} candidate archive size drift")
    require(candidate.get("inventory") == manifest_candidate["inventory"], f"{label} candidate inventory drift")
    require(candidate.get("cargo_lock_sha256") == manifest_candidate["cargo_lock_sha256"], f"{label} candidate Cargo.lock drift")
    require(candidate.get("source_date_epoch") == str(manifest_candidate["source_date_epoch"]), f"{label} source date drift")
    build = candidate.get("build")
    require(isinstance(build, dict), f"{label} build missing")
    require(build.get("log_policy") == "stable_event_categories", f"{label} build log policy drift")
    binary = build.get("binary_post")
    require(isinstance(binary, dict) and binary.get("path_redacted") is True and is_sha(binary.get("sha256")), f"{label} binary receipt drift")
    require(isinstance(report.get("upstream"), dict), f"{label} upstream missing")
    require(report["upstream"].get("commit") == UPSTREAM_COMMIT and report["upstream"].get("tree") == UPSTREAM_TREE, f"{label} upstream revision drift")
    require(report["upstream"].get("source_mode") == "git_archive_at_immutable_commit", f"{label} upstream source mode drift")
    manifest_upstream = manifest["upstream"]
    require(report["upstream"].get("archive", {}).get("sha256") == manifest_upstream["archive_sha256"], f"{label} upstream archive binding drift")
    require(report["upstream"].get("archive", {}).get("bytes") == manifest_upstream["archive_bytes"], f"{label} upstream archive size drift")
    require(report["upstream"].get("inventory") == manifest_upstream["inventory"], f"{label} upstream inventory drift")
    runtime = report["upstream"].get("runtime")
    require(isinstance(runtime, dict) and runtime.get("environment", {}).get("direct_python_fallback") is False, f"{label} runtime custody drift")
    source = runtime.get("source", {})
    require(source.get("module_file", {}).get("relative_path") == "src/agent_com/__init__.py", f"{label} source receipt drift")
    require(source.get("module_file", {}).get("path_redacted") is True and is_sha(source.get("module_file", {}).get("sha256")), f"{label} source digest drift")
    require(source.get("module_file", {}).get("sha256") == manifest_upstream["source_module_sha256"], f"{label} source module binding drift")
    require(report.get("toolchain", {}).get("stable") is True, f"{label} toolchain stability drift")
    harness = report.get("harness")
    require(isinstance(harness, dict), f"{label} harness missing")
    require(harness.get("scenario_count") == 14 and harness.get("archive_only_inputs") is True, f"{label} harness drift")
    require(harness.get("scenario_set_sha256") == EXPECTED_SCENARIO_SET_SHA256, f"{label} scenario-set drift")
    for key in ("runner", "semantic_runner"):
        require(harness.get(key) == manifest["harness"][key], f"{label} {key} binding drift")
    _validate_scenarios(report.get("scenarios"))
    expected_fixtures = {(item["role"], item["bytes"], item["sha256"]) for item in manifest["fixtures"]}
    actual_fixtures = {(item.get("role"), item.get("bytes"), item.get("sha256")) for item in report.get("fixtures", [])}
    require(actual_fixtures == expected_fixtures, f"{label} fixture binding drift")


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
    require(document.get("schema") == "sipi.com-01.current-candidate-replay.v2", "manifest schema drift")
    require(document.get("status") == STATUS, "manifest status drift")
    require(document.get("scope") == {
        "work_item": "COM-01",
        "leaf": "config-validate",
        "complete_com_parity": False,
        "global_migration_row_closed": False,
        "product_capability_promoted": False,
        "release_ready": False,
    }, "manifest scope overclaim or drift")
    require(document.get("policy") == {
        "s_parameter_fit": "not_in_scope",
        "channel_simulation": "impulse_only",
        "raw_configuration_values_in_evidence": False,
        "same_crate_self_comparison": False,
    }, "manifest policy drift")
    candidate = document.get("candidate")
    require(isinstance(candidate, dict), "manifest candidate missing")
    require(candidate.get("commit") == CANDIDATE_COMMIT and candidate.get("tree") == CANDIDATE_TREE, "manifest candidate revision drift")
    require(candidate.get("source_mode") == "git_archive_at_immutable_commit", "manifest candidate source drift")
    require(is_sha(candidate.get("archive_sha256")) and is_sha(candidate.get("cargo_lock_sha256")), "manifest candidate digest drift")
    require(type(candidate.get("archive_bytes")) is int and candidate["archive_bytes"] > 0, "manifest candidate archive size drift")
    require(isinstance(candidate.get("inventory"), dict) and candidate["inventory"].get("file_count") == 24 and type(candidate["inventory"].get("total_bytes")) is int and is_sha(candidate["inventory"].get("sha256")), "manifest candidate inventory drift")
    upstream = document.get("upstream")
    require(isinstance(upstream, dict) and upstream.get("commit") == UPSTREAM_COMMIT and upstream.get("tree") == UPSTREAM_TREE, "manifest upstream drift")
    require(upstream.get("source_mode") == "git_archive_at_immutable_commit", "manifest upstream source drift")
    require(type(upstream.get("archive_bytes")) is int and upstream["archive_bytes"] > 0 and is_sha(upstream.get("archive_sha256")), "manifest upstream archive drift")
    require(isinstance(upstream.get("inventory"), dict) and upstream["inventory"].get("file_count") == 70 and is_sha(upstream["inventory"].get("sha256")), "manifest upstream inventory drift")
    require(is_sha(upstream.get("source_module_sha256")), "manifest source module drift")
    harness = document.get("harness")
    require(isinstance(harness, dict), "manifest harness missing")
    require(harness.get("scenario_count") == 14 and harness.get("scenario_set_sha256") == EXPECTED_SCENARIO_SET_SHA256, "manifest harness drift")
    require(harness.get("runner") == "tools/run_com_01_current_candidate_v2.py" and is_sha(harness.get("runner_sha256")), "manifest runner drift")
    require(harness.get("aggregate_runner") == "tools/aggregate_com_01_current_candidate_v2.py" and is_sha(harness.get("aggregate_runner_sha256")), "manifest aggregate runner drift")
    require(harness.get("semantic_runner") == "tools/run_com_01_direct_oracle_v2.py" and is_sha(harness.get("semantic_runner_sha256")), "manifest semantic runner drift")
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
    require(aggregate.get("work_item") == "COM-01" and aggregate.get("leaf") == "config-validate", "aggregate work-item drift")
    require(aggregate.get("fresh_replays") == 2 and aggregate.get("scenario_count") == 14, "aggregate count drift")
    require(aggregate.get("outcomes") == EXPECTED_OUTCOMES and aggregate.get("values_aligned") is True, "aggregate outcome drift")
    require(aggregate.get("matched") is True and aggregate.get("acceptance") is False, "aggregate acceptance drift")
    require(aggregate.get("blockers") == [], "aggregate blocker drift")
    aggregate_reports = aggregate.get("reports")
    require(isinstance(aggregate_reports, list) and len(aggregate_reports) == 2, "aggregate report bindings missing")
    for expected, actual in zip(reports, aggregate_reports):
        require(actual.get("path") == Path(expected["path"]).as_posix(), "aggregate report path drift")
        require(actual.get("sha256") == expected["sha256"] and actual.get("run_id") == expected["run_id"] and actual.get("nonce") == expected["nonce"], "aggregate report identity drift")
    return {"schema": document["schema"], "status": document["status"], "scenario_count": 14, "fresh_replays": 2}


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
