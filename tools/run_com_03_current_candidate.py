"""Run the current COM-03 compare leaf from immutable Git archives.

The pinned Python entry point and an independently built Rust executable are
invoked for the same isolated payloads.  Only hashes, branch outcomes, and
bounded mismatch metadata are retained.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from run_com_01_current_candidate import (
    BUILD_ENV_CLEARED_KEYS,
    CANDIDATE_COMMIT,
    CANDIDATE_TREE,
    CRATE_RELATIVE,
    PATH_LEAK,
    ROOT,
    SHARED_HELPER_SCHEMA,
    ENVIRONMENT_SCOPE,
    UPSTREAM_COMMIT,
    UPSTREAM_TREE,
    _bounded_file,
    _bounded_cargo_source,
    _bounded_run,
    _atomic_json_create,
    _canonical,
    _cargo_dependency_cache_inventory,
    _copy_cargo_binary,
    _clean_build_env,
    _extract_archive,
    _exact_keys,
    _git,
    _inventory,
    _hex,
    _git_inventory,
    _harness_receipt,
    _materialize,
    _path_free,
    _probe_upstream,
    _safe_file,
    _sha256,
    _toolchain,
    _uv_run,
    _source_receipt,
    _normalized_log,
    _validate_archive,
    _validate_harness_source,
    _validate_inventory,
    _validate_runtime,
    _validate_toolchain,
)


SCHEMA = "sipi.com-03.current-candidate-replay.v1"
OPEN_STATUS = "scoped_current_candidate_observed"
SEMANTIC_RUNNER_RELATIVE = Path("tools/run_com_03_direct_oracle.py")
RESULT_SCHEMA = "sipi.com-03-direct-port-oracle.v2"
AGGREGATE_SCHEMA = "sipi.com-03.current-candidate-replay.aggregate.v1"
HEX64 = re.compile(r"^[0-9a-f]{64}$\Z")
COM03_BINARY_BASENAME = (
    "sipi-com-direct-compare.exe" if os.name == "nt" else "sipi-com-direct-compare"
)
COM03_SCENARIO_CONTRACT = {
    "identical": ("compare", "matched"),
    "schema_version_true_equals_one": ("compare", "matched"),
    "schema_version_float_equals_one": ("compare", "matched"),
    "provenance_empty_sequence": ("compare", "matched"),
    "provenance_pair_sequence_metadata_ignored": ("compare", "matched"),
    "non_comparable_metadata_ignored": ("compare", "matched"),
    "numeric_within_absolute_atol": ("compare", "matched"),
    "numeric_and_nested_mismatch": ("compare", "error_match"),
    "object_key_mismatch": ("compare", "error_match"),
    "array_length_mismatch": ("compare", "error_match"),
    "scalar_string_mismatch": ("compare", "error_match"),
    "invalid_schema_version": ("error", "error_match"),
    "missing_required_key": ("error", "error_match"),
    "invalid_profile": ("error", "error_match"),
    "empty_cases": ("error", "error_match"),
    "non_contiguous_case_index": ("error", "error_match"),
    "negative_signal": ("error", "error_match"),
    "non_integer_cursor": ("error", "error_match"),
    "invalid_eye_width_shape": ("error", "error_match"),
    "malformed_json": ("malformed", "error_match"),
    "negative_atol": ("negative_atol", "error_match"),
    "missing_golden": ("missing_golden", "error_match"),
    "missing_result": ("missing_result", "error_match"),
}
EXPECTED_SCENARIO_SET_SHA256 = "f9124ce5020bb29cca9b28ddeb5b6feda6ff3755b2fb49142254db44ccb46ffd"
COM03_PAYLOAD_CONTRACT = {
    "identical": ((327, "cf38d28ec234a65d4eb4485a7a806129f3e128aeb6ae467de0872adea5d6f45f"), (327, "cf38d28ec234a65d4eb4485a7a806129f3e128aeb6ae467de0872adea5d6f45f")),
    "schema_version_true_equals_one": ((330, "afb141ca2ddcbe6d053c24f7fccde4776eb76e7f3d47c314f1994a084722b324"), (330, "afb141ca2ddcbe6d053c24f7fccde4776eb76e7f3d47c314f1994a084722b324")),
    "schema_version_float_equals_one": ((329, "c744c2df10c6cce32f7f444c6c86eee8d451a6c0cdd6a4538ef870619760660d"), (329, "c744c2df10c6cce32f7f444c6c86eee8d451a6c0cdd6a4538ef870619760660d")),
    "provenance_empty_sequence": ((250, "081a2fd6cbc4c3291a78984a0c855449ca24a84caefd994a491066ae501c1138"), (250, "081a2fd6cbc4c3291a78984a0c855449ca24a84caefd994a491066ae501c1138")),
    "provenance_pair_sequence_metadata_ignored": ((313, "e307bdc116957961b9e31d501f3dcafc390485ed8e03f6b4177451784f3614e4"), (315, "8c88013041831e920bd51881ce4b62726b02184f063941603df8bfbb5f7439e8")),
    "non_comparable_metadata_ignored": ((327, "cf38d28ec234a65d4eb4485a7a806129f3e128aeb6ae467de0872adea5d6f45f"), (327, "8e1e385f0f2e46c9853ecf89adc885e1de4e17f2bed94df42161559268e6ab42")),
    "numeric_within_absolute_atol": ((327, "cf38d28ec234a65d4eb4485a7a806129f3e128aeb6ae467de0872adea5d6f45f"), (330, "95e2cb0be4417fa53b31c471f7b74c90bb76b917b8c1928ef08567ef6247f8b6")),
    "numeric_and_nested_mismatch": ((327, "cf38d28ec234a65d4eb4485a7a806129f3e128aeb6ae467de0872adea5d6f45f"), (327, "214bb50684c0c8d266f4715c3227a28ecaf66cc021d05a33f5e4d8bec4cadb8c")),
    "object_key_mismatch": ((327, "cf38d28ec234a65d4eb4485a7a806129f3e128aeb6ae467de0872adea5d6f45f"), (340, "d1fb7aeac2d8f59c6fc975689be1e37eae63166612d7dde79f9f972ba7d94aa6")),
    "array_length_mismatch": ((327, "cf38d28ec234a65d4eb4485a7a806129f3e128aeb6ae467de0872adea5d6f45f"), (323, "d4d7804c97e598a0eabee5ee7fa1f8af5b8fe3e1e67576f0fe0fe90ddb4e6179")),
    "scalar_string_mismatch": ((342, "07656f4846d04afd5b5f8ed5a3d4f788e997e9210a5bcc25a5f06737787ed7b7"), (343, "2d3af6e6687858b66424b154e8c487e2b5cfa1a37213d2c676e20760ef01ea33")),
    "invalid_schema_version": ((327, "a865ae4d1f163c5e15964fa978dae1730adbd6cc3cb06a2a309c96b0779b2846"), (327, "a865ae4d1f163c5e15964fa978dae1730adbd6cc3cb06a2a309c96b0779b2846")),
    "missing_required_key": ((313, "3d61cf45b7d8d120c200e0ece8b7967f088a5a29253efc381d6d0b0a7344e746"), (313, "3d61cf45b7d8d120c200e0ece8b7967f088a5a29253efc381d6d0b0a7344e746")),
    "invalid_profile": ((328, "a5b02ca7e6681b0f4ecc1f6ca5a30c39ab6cd55496beccf4576562d1b8915f82"), (328, "a5b02ca7e6681b0f4ecc1f6ca5a30c39ab6cd55496beccf4576562d1b8915f82")),
    "empty_cases": ((268, "3b3f91873d6d0a4f84e178c62190d1184b89967bbcf7d29895e79fe25bbc5343"), (268, "3b3f91873d6d0a4f84e178c62190d1184b89967bbcf7d29895e79fe25bbc5343")),
    "non_contiguous_case_index": ((327, "b123b7e7129becad6d3a83dce4cb3940a777c364872064b96233828d5f06bb9a"), (327, "b123b7e7129becad6d3a83dce4cb3940a777c364872064b96233828d5f06bb9a")),
    "negative_signal": ((307, "a11f91c0fdba7e45d5d01c9a9fcebadb1582265fa722e0fc1debc6e1f015d2dd"), (307, "a11f91c0fdba7e45d5d01c9a9fcebadb1582265fa722e0fc1debc6e1f015d2dd")),
    "non_integer_cursor": ((322, "0a67cfe6560bbc48dbb5c29739bf8359be1d13b56053267b22ec809c50f62c30"), (322, "0a67cfe6560bbc48dbb5c29739bf8359be1d13b56053267b22ec809c50f62c30")),
    "invalid_eye_width_shape": ((320, "dbf18567d9eb9fb84409ef29a5d8de15a8d1567c9d050b53697710573ad2e80b"), (320, "dbf18567d9eb9fb84409ef29a5d8de15a8d1567c9d050b53697710573ad2e80b")),
    "malformed_json": ((10, "5209035eae69aa562548057a0218a9ce21acd559edc5978540ece05e7c388d61"), (10, "5209035eae69aa562548057a0218a9ce21acd559edc5978540ece05e7c388d61")),
    "negative_atol": ((327, "cf38d28ec234a65d4eb4485a7a806129f3e128aeb6ae467de0872adea5d6f45f"), (327, "cf38d28ec234a65d4eb4485a7a806129f3e128aeb6ae467de0872adea5d6f45f")),
    "missing_golden": ((327, "cf38d28ec234a65d4eb4485a7a806129f3e128aeb6ae467de0872adea5d6f45f"), (327, "cf38d28ec234a65d4eb4485a7a806129f3e128aeb6ae467de0872adea5d6f45f")),
    "missing_result": ((327, "cf38d28ec234a65d4eb4485a7a806129f3e128aeb6ae467de0872adea5d6f45f"), (327, "cf38d28ec234a65d4eb4485a7a806129f3e128aeb6ae467de0872adea5d6f45f")),
}
COM03_RESULT_CONTRACT = {
    "success": (0, "empty", 36, "6c3e6ad4780a4c395ae9cb931fd12c3d5085ccf41b10930b9053830f686e70c1"),
    "numeric_and_nested_mismatch": (3, "empty", 119, "87cf680164e7313654fbf3595bdc478e745336ca17e3f375b899214e3964ef27"),
    "object_key_mismatch": (3, "empty", 70, "745a89a91b206ca189cec9dd3f01b5365125bb91822101eaec9006502d1d9a3f"),
    "array_length_mismatch": (3, "empty", 84, "7c95a5f87413c8cbff5296edc90150b22712bb8f0d4217e28c00ca0d7546bd85"),
    "scalar_string_mismatch": (3, "empty", 82, "c25cc3c76561cae428c8f3f60eff9dde797d3af3174a8868bb05b5f544380985"),
    "invalid": (3, "json_error", 0, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    "malformed_json": (2, "json_error", 0, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    "negative_atol": (3, "config_error", 0, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    "missing": (1, "io_error", 0, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
}


def _validate_com03_scenarios(scenarios: Any) -> None:
    if type(scenarios) is not list or len(scenarios) != len(COM03_SCENARIO_CONTRACT):
        raise ValueError("COM-03 scenario list drift")
    if [item.get("id") for item in scenarios if type(item) is dict] != list(COM03_SCENARIO_CONTRACT):
        raise ValueError("COM-03 scenario order/id drift")
    scenario_keys = {"id", "mode", "atol", "payloads", "oracle", "candidate", "semantic_match", "outcome", "independent_payload_paths"}
    result_keys = {"exit_code", "stdout_bytes", "stdout_sha256", "stderr_category"}
    payload_keys = {"basename", "bytes", "sha256", "path_redacted"}
    for item in scenarios:
        if type(item) is not dict or set(item) != scenario_keys:
            raise ValueError("COM-03 scenario exact schema drift")
        scenario_id = item["id"]
        if type(scenario_id) is not str or scenario_id not in COM03_SCENARIO_CONTRACT:
            raise ValueError("COM-03 scenario id drift")
        mode, outcome = COM03_SCENARIO_CONTRACT[scenario_id]
        if item["mode"] != mode or item["outcome"] != outcome:
            raise ValueError(f"COM-03 mode/outcome drift for {scenario_id}")
        if type(item["atol"]) not in (int, float) or type(item["atol"]) is bool:
            raise ValueError("COM-03 atol exact type drift")
        if type(item["atol"]) is not float:
            raise ValueError("COM-03 atol must be an exact float")
        if type(item["semantic_match"]) is not bool or item["semantic_match"] is not True:
            raise ValueError("COM-03 semantic match drift")
        if type(item["independent_payload_paths"]) is not bool or item["independent_payload_paths"] is not True:
            raise ValueError("COM-03 payload path independence drift")
        if type(item["payloads"]) is not dict or set(item["payloads"]) != {"golden", "result"}:
            raise ValueError("COM-03 payload map drift")
        for role in ("golden", "result"):
            payload = item["payloads"][role]
            if type(payload) is not dict or set(payload) != payload_keys:
                raise ValueError("COM-03 payload receipt schema drift")
            if type(payload["basename"]) is not str or type(payload["bytes"]) is not int or payload["bytes"] <= 0:
                raise ValueError("COM-03 payload receipt type drift")
            if not _hex(payload["sha256"]) or payload["path_redacted"] is not True:
                raise ValueError("COM-03 payload receipt identity drift")
        expected_payloads = COM03_PAYLOAD_CONTRACT[scenario_id]
        actual_payloads = tuple((item["payloads"][role]["bytes"], item["payloads"][role]["sha256"]) for role in ("golden", "result"))
        if actual_payloads != expected_payloads:
            raise ValueError(f"COM-03 payload binding drift for {scenario_id}")
        for role in ("oracle", "candidate"):
            result = item[role]
            if type(result) is not dict or set(result) != result_keys:
                raise ValueError("COM-03 command result schema drift")
            if type(result["exit_code"]) is not int or type(result["stdout_bytes"]) is not int or result["stdout_bytes"] < 0:
                raise ValueError("COM-03 command result type drift")
            if type(result["stderr_category"]) is not str or not _hex(result["stdout_sha256"]):
                raise ValueError("COM-03 command result identity drift")
        expected_atol = -1.0 if scenario_id == "negative_atol" else 0.001 if scenario_id == "numeric_within_absolute_atol" else 0.0 if scenario_id == "numeric_and_nested_mismatch" else 1e-12
        if item["atol"] != expected_atol:
            raise ValueError(f"COM-03 atol binding drift for {scenario_id}")
        if outcome == "matched":
            expected_result = COM03_RESULT_CONTRACT["success"]
        elif scenario_id in {"numeric_and_nested_mismatch", "object_key_mismatch", "array_length_mismatch", "scalar_string_mismatch", "malformed_json", "negative_atol"}:
            expected_result = COM03_RESULT_CONTRACT[scenario_id]
        elif scenario_id in {"missing_golden", "missing_result"}:
            expected_result = COM03_RESULT_CONTRACT["missing"]
        else:
            expected_result = COM03_RESULT_CONTRACT["invalid"]
        expected_command = {"exit_code": expected_result[0], "stderr_category": expected_result[1], "stdout_bytes": expected_result[2], "stdout_sha256": expected_result[3]}
        if item["oracle"] != expected_command or item["candidate"] != expected_command:
            raise ValueError(f"COM-03 command result binding drift for {scenario_id}")


def _validate_com03_report(report: Any) -> None:
    root_keys = {"schema", "status", "work_item", "leaf", "run_id", "nonce", "candidate", "upstream", "toolchain", "harness", "outcomes", "scenario_count", "semantic_match_count", "scenarios", "blockers", "matched", "acceptance", "non_claims"}
    item = _exact_keys(report, root_keys, "COM-03 report")
    if (item["schema"], item["status"], item["work_item"], item["leaf"]) != (SCHEMA, OPEN_STATUS, "COM-03", "compare"):
        raise ValueError("COM-03 root identity drift")
    if not _hex(item["run_id"]) or not _hex(item["nonce"]) or item["run_id"] == item["nonce"]:
        raise ValueError("COM-03 replay identity drift")
    candidate = _exact_keys(item["candidate"], {"commit", "tree", "archive", "source_mode", "inventory", "cargo_lock_sha256", "source_date_epoch", "build"}, "COM-03 candidate")
    if candidate["commit"] != CANDIDATE_COMMIT or candidate["tree"] != CANDIDATE_TREE or candidate["source_mode"] != "git_archive_at_immutable_commit" or not _hex(candidate["cargo_lock_sha256"]) or type(candidate["source_date_epoch"]) is not str:
        raise ValueError("COM-03 candidate source binding drift")
    _validate_archive(candidate["archive"], "candidate.archive")
    _validate_inventory(candidate["inventory"], "candidate.inventory")
    build = _exact_keys(candidate["build"], {"command", "cargo_source_pre", "cargo_source_post", "cargo_source_stable", "binary_pre", "binary_post", "binary_stable", "copy_matches_source", "raw_binary_scope", "stdout_sha256", "stderr_sha256", "log_policy", "environment"}, "candidate.build")
    if type(build["command"]) is not str or build["log_policy"] != "stable_event_categories" or not _hex(build["stdout_sha256"]) or not _hex(build["stderr_sha256"]):
        raise ValueError("COM-03 build command/log receipt drift")
    for key in ("binary_pre", "binary_post"):
        binary = _exact_keys(build[key], {"basename", "bytes", "sha256", "nlink", "path_redacted"}, f"candidate.build.{key}")
        if binary["basename"] != COM03_BINARY_BASENAME or type(binary["bytes"]) is not int or binary["bytes"] <= 0 or not _hex(binary["sha256"]) or type(binary["nlink"]) is not int or binary["nlink"] != 1 or binary["path_redacted"] is not True:
            raise ValueError("COM-03 binary receipt drift")
    for key in ("cargo_source_pre", "cargo_source_post"):
        source = _exact_keys(build[key], {"basename", "bytes", "sha256", "nlink", "path_redacted"}, f"candidate.build.{key}")
        if source["basename"] != COM03_BINARY_BASENAME or type(source["bytes"]) is not int or source["bytes"] <= 0 or not _hex(source["sha256"]) or type(source["nlink"]) is not int or source["nlink"] < 1 or source["path_redacted"] is not True:
            raise ValueError("COM-03 Cargo source receipt drift")
    if build["binary_stable"] is not True or build["cargo_source_stable"] is not True or build["copy_matches_source"] is not True or build["binary_pre"] != build["binary_post"] or build["cargo_source_pre"] != build["cargo_source_post"] or (build["binary_post"]["basename"], build["binary_post"]["bytes"], build["binary_post"]["sha256"]) != (build["cargo_source_post"]["basename"], build["cargo_source_post"]["bytes"], build["cargo_source_post"]["sha256"]) or build["raw_binary_scope"] != ENVIRONMENT_SCOPE:
        raise ValueError("COM-03 binary custody drift")
    environment = _exact_keys(build["environment"], {"cleared", "incremental", "offline", "rustc_forced", "wrappers_cleared", "source_path_remapped", "target_is_independent", "cargo_home_policy", "native_linker_overrides_cleared", "linker_forced", "cargo_cache_bound_pre_post"}, "candidate.build.environment")
    if type(environment["cleared"]) is not list or any(type(key) is not str for key in environment["cleared"]):
        raise ValueError("COM-03 build environment type drift")
    if environment["incremental"] != "0" or environment["cargo_home_policy"] != "host_cargo_home_retained_for_offline_dependency_cache" or any(environment[key] is not True for key in environment if key not in {"cleared", "incremental", "cargo_home_policy"}):
        raise ValueError("COM-03 build environment policy drift")
    upstream = _exact_keys(item["upstream"], {"commit", "tree", "archive", "source_mode", "inventory", "runtime", "uv_lock"}, "COM-03 upstream")
    if upstream["commit"] != UPSTREAM_COMMIT or upstream["tree"] != UPSTREAM_TREE or upstream["source_mode"] != "git_archive_at_immutable_commit":
        raise ValueError("COM-03 upstream source binding drift")
    _validate_archive(upstream["archive"], "upstream.archive")
    _validate_inventory(upstream["inventory"], "upstream.inventory")
    uv_lock = _exact_keys(upstream["uv_lock"], {"bytes", "sha256"}, "upstream.uv_lock")
    if type(uv_lock["bytes"]) is not int or uv_lock["bytes"] <= 0 or not _hex(uv_lock["sha256"]):
        raise ValueError("COM-03 uv.lock identity drift")
    _validate_runtime(upstream["runtime"], "upstream.runtime")
    _validate_toolchain(item["toolchain"])
    harness = _exact_keys(item["harness"], {"runner", "semantic_runner", "result_schema", "scenario_count", "scenario_set_sha256", "independent_payload_paths", "same_crate_self_comparison", "report_policy", "timeout_seconds", "source", "shared_com01_helper"}, "COM-03 harness")
    _validate_harness_source(harness["source"], {"tools/run_com_01_current_candidate.py", "tools/run_com_03_current_candidate.py", "tools/aggregate_com_03_current_candidate.py", "tools/verify_com_03_current_candidate.py", "tools/test_verify_com_03_current_candidate.py"})
    shared = _exact_keys(harness["shared_com01_helper"], {"schema", "path", "sha256"}, "COM-03 shared helper")
    helper = next(entry for entry in harness["source"]["files"] if entry["path"] == shared["path"])
    if shared != {"schema": SHARED_HELPER_SCHEMA, "path": "tools/run_com_01_current_candidate.py", "sha256": helper["sha256"]}:
        raise ValueError("COM-03 shared COM-01 helper binding drift")
    if harness["scenario_set_sha256"] != EXPECTED_SCENARIO_SET_SHA256 or type(harness["scenario_count"]) is not int or harness["scenario_count"] != 23:
        raise ValueError("COM-03 harness scenario binding drift")
    if harness["runner"] != "tools/run_com_03_current_candidate.py" or harness["semantic_runner"] != "tools/run_com_03_direct_oracle.py" or harness["result_schema"] != RESULT_SCHEMA or harness["independent_payload_paths"] is not True or harness["same_crate_self_comparison"] is not False or type(harness["report_policy"]) is not str or type(harness["timeout_seconds"]) is not int or harness["timeout_seconds"] <= 0:
        raise ValueError("COM-03 harness policy drift")
    _validate_com03_scenarios(item["scenarios"])
    if type(item["outcomes"]) is not dict or any(type(value) is not int for value in item["outcomes"].values()) or item["outcomes"] != {"error_match": 16, "matched": 7} or type(item["scenario_count"]) is not int or item["scenario_count"] != 23 or type(item["semantic_match_count"]) is not int or item["semantic_match_count"] != 23:
        raise ValueError("COM-03 outcome drift")
    for key in ("blockers", "non_claims"):
        if type(item[key]) is not list or any(type(value) is not str for value in item[key]):
            raise ValueError(f"COM-03 {key} type drift")
    if item["matched"] is not False or item["acceptance"] is not False:
        raise ValueError("COM-03 acceptance overclaim")


def _load_semantic_runner(path: Path) -> Any:
    name = f"com03_current_semantic_{secrets.token_hex(8)}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load archived COM-03 semantic runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_environment_receipt() -> dict[str, Any]:
    return {
        "cleared": list(BUILD_ENV_CLEARED_KEYS),
        "incremental": "0",
        "offline": True,
        "rustc_forced": True,
        "wrappers_cleared": True,
        "source_path_remapped": True,
        "target_is_independent": True,
        "cargo_home_policy": "host_cargo_home_retained_for_offline_dependency_cache",
        "native_linker_overrides_cleared": True,
        "linker_forced": True,
        "cargo_cache_bound_pre_post": True,
    }


def _build_compare(source_root: Path, target: Path, tools: dict[str, Path], timeout: int, source_date_epoch: str) -> tuple[Path, Path, dict[str, Any]]:
    environment = _clean_build_env(tools, target, source_root, source_date_epoch)
    command = [
        str(tools["cargo"]),
        "build",
        "--manifest-path",
        str(source_root / CRATE_RELATIVE / "Cargo.toml"),
        "--bin",
        "sipi-com-direct-compare",
        "--release",
        "--locked",
        "--offline",
        "--config",
        "build.rustflags=[]",
        "--config",
        "build.rustdocflags=[]",
    ]
    completed = _bounded_run(command, cwd=source_root, env=environment, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError("candidate archive compare build failed")
    cargo_binary = target / "release" / "sipi-com-direct-compare"
    if os.name == "nt":
        cargo_binary = cargo_binary.with_suffix(".exe")
    if not cargo_binary.is_file():
        raise RuntimeError("candidate archive build did not produce compare")
    binary, cargo_source, binary_pre = _copy_cargo_binary(
        cargo_binary, target, target / "sipi-execution"
    )
    return binary, cargo_binary, {
        "command": "cargo build --manifest-path <candidate>/crates/sipi-agent-com-direct/Cargo.toml --bin sipi-com-direct-compare --release --locked --offline",
        "cargo_source_pre": cargo_source,
        "binary_pre": binary_pre,
        "stdout_sha256": _sha256(_normalized_log(completed.stdout).encode("ascii")),
        "stderr_sha256": _sha256(_normalized_log(completed.stderr).encode("ascii")),
        "log_policy": "stable_event_categories",
        "environment": _build_environment_receipt(),
    }


def _diagnostic_category(text: str, exit_code: int) -> str:
    lowered = text.casefold()
    if not text:
        return "empty"
    if "no such file" in lowered or "cannot read" in lowered or "os error 2" in lowered:
        return "io_error"
    if "json" in lowered or "property name" in lowered:
        return "json_error"
    if "schema" in lowered or "tolerance" in lowered or "configuration" in lowered:
        return "config_error"
    if exit_code == 2:
        return "argument_or_input_error"
    return "diagnostic"


def _invoke_candidate(binary: Path, golden: Path, result: Path, atol: float, timeout: int) -> dict[str, Any]:
    completed = _bounded_run(
        [str(binary), "--golden", str(golden), "--result", str(result), "--atol", str(atol)],
        cwd=golden.parent,
        env=None,
        timeout=timeout,
    )
    return {
        "exit_code": completed.returncode,
        "stdout_bytes": len(completed.stdout),
        "stdout_sha256": _sha256(completed.stdout),
        "stderr_category": _diagnostic_category(completed.stderr.decode("utf-8", errors="replace"), completed.returncode),
        "stdout_text": completed.stdout.decode("utf-8", errors="replace"),
    }


def _invoke_upstream(tools: dict[str, Path], root: Path, python: Path, golden: Path, result: Path, atol: float, timeout: int) -> dict[str, Any]:
    # The child captures the CLI streams before emitting one machine-readable
    # envelope, so payload JSON never becomes part of the evidence report.
    script = (
        "import contextlib,io,json,sys\n"
        "from agent_com.cli import main\n"
        "out,err=io.StringIO(),io.StringIO()\n"
        "with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):\n"
        "  try: code=main(['compare','--golden',sys.argv[1],'--result',sys.argv[2],'--atol',sys.argv[3]])\n"
        "  except SystemExit as exc: code=exc.code if isinstance(exc.code,int) else 1\n"
        "  except Exception as exc: code=1; print(str(exc),file=err)\n"
        "payload={'exit_code':code,'stdout':out.getvalue(),'stderr':err.getvalue()}\n"
        "print(json.dumps(payload,ensure_ascii=False,separators=(',',':')))\n"
    )
    completed = _uv_run(
        tools, root, python, script, [str(golden), str(result), str(atol)], timeout
    )
    if completed.returncode != 0:
        raise RuntimeError("pinned Agent-COM compare invocation failed")
    lines = completed.stdout.decode("utf-8", errors="replace").splitlines()
    if not lines:
        raise RuntimeError("pinned Agent-COM compare invocation was empty")
    try:
        value = json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise RuntimeError("pinned Agent-COM compare invocation was not JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError("pinned Agent-COM compare invocation envelope drift")
    stdout = str(value.get("stdout", ""))
    stderr = str(value.get("stderr", ""))
    exit_code = value.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise RuntimeError("pinned Agent-COM compare exit code drift")
    stdout_bytes = stdout.encode("utf-8")
    return {
        "exit_code": exit_code,
        "stdout_bytes": len(stdout_bytes),
        "stdout_sha256": _sha256(stdout_bytes),
        "stderr_category": _diagnostic_category(stderr, exit_code),
        "stdout_text": stdout,
    }


def _scenario_result(
    module: Any,
    scenario: tuple[str, dict[str, Any], dict[str, Any], float, str],
    scratch: Path,
    binary: Path,
    upstream_root: Path,
    tools: dict[str, Path],
    timeout: int,
) -> dict[str, Any]:
    name, golden_document, result_document, atol, mode = scenario
    if mode == "malformed":
        golden_bytes = b"{ not JSON"
        result_bytes = b"{ not JSON"
    else:
        golden_bytes = json.dumps(golden_document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        result_bytes = json.dumps(result_document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    golden = scratch / f"{name}.golden.json"
    result = scratch / f"{name}.result.json"
    if mode != "missing_golden":
        golden.write_bytes(golden_bytes)
    if mode != "missing_result":
        result.write_bytes(result_bytes)
    oracle = _invoke_upstream(tools, upstream_root, tools["python"], golden, result, atol, timeout)
    candidate = _invoke_candidate(binary, golden, result, atol, timeout)
    oracle_projection = {"exit_code": oracle["exit_code"], "stdout": oracle["stdout_text"]}
    candidate_projection = {"exit_code": candidate["exit_code"], "stdout": candidate["stdout_text"]}
    semantic_match = oracle_projection == candidate_projection
    if oracle["exit_code"] == 0 and candidate["exit_code"] == 0:
        outcome = "matched" if semantic_match else "mismatched"
    elif semantic_match:
        outcome = "error_match"
    else:
        outcome = "error_mismatch"
    return {
        "id": name,
        "mode": mode,
        "atol": atol,
        "payloads": {
            "golden": {"basename": golden.name, "bytes": len(golden_bytes), "sha256": _sha256(golden_bytes), "path_redacted": True},
            "result": {"basename": result.name, "bytes": len(result_bytes), "sha256": _sha256(result_bytes), "path_redacted": True},
        },
        "oracle": {key: value for key, value in oracle.items() if key != "stdout_text"},
        "candidate": {key: value for key, value in candidate.items() if key != "stdout_text"},
        "semantic_match": semantic_match,
        "outcome": outcome,
        "independent_payload_paths": golden.name != result.name,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    candidate_repo = args.candidate_repo.resolve()
    upstream_repo = args.upstream_repo.resolve()
    candidate_commit = str(_git(candidate_repo, "rev-parse", f"{args.candidate_commit}^{{commit}}"))
    candidate_tree = str(_git(candidate_repo, "rev-parse", f"{candidate_commit}^{{tree}}"))
    upstream_commit = str(_git(upstream_repo, "rev-parse", f"{args.upstream_commit}^{{commit}}"))
    upstream_tree = str(_git(upstream_repo, "rev-parse", f"{upstream_commit}^{{tree}}"))
    if (candidate_commit, candidate_tree) != (CANDIDATE_COMMIT, CANDIDATE_TREE):
        raise RuntimeError("candidate commit/tree is not the fixed business candidate")
    if (upstream_commit, upstream_tree) != (UPSTREAM_COMMIT, UPSTREAM_TREE):
        raise RuntimeError("upstream commit/tree is not the pinned Agent-COM revision")
    if not HEX64.fullmatch(args.run_id) or not HEX64.fullmatch(args.nonce) or args.run_id == args.nonce:
        raise RuntimeError("run_id and nonce must be distinct lowercase 64-hex values")
    toolchain_pre, tools = _toolchain(args.cargo, args.python, args.uv)
    if tools["python"] != Path(sys.executable).resolve():
        raise RuntimeError("replay Python identity must match the executing interpreter")
    source_date_epoch = str(_git(candidate_repo, "show", "-s", "--format=%ct", candidate_commit))
    harness_source = _harness_receipt(
        candidate_repo,
        args.harness_commit,
        (
            Path("tools/run_com_01_current_candidate.py"),
            Path("tools/run_com_03_current_candidate.py"),
            Path("tools/aggregate_com_03_current_candidate.py"),
            Path("tools/verify_com_03_current_candidate.py"),
            Path("tools/test_verify_com_03_current_candidate.py"),
        ),
    )
    with tempfile.TemporaryDirectory(prefix="sipi-com-03-current-") as directory:
        run_root = Path(directory)
        candidate_root = run_root / "candidate"
        upstream_root = run_root / "upstream"
        target_root = run_root / "candidate-target"
        scratch = run_root / "scratch"
        target_root.mkdir()
        scratch.mkdir()
        candidate_info = _materialize(candidate_repo, candidate_commit, candidate_root)
        upstream_info = _materialize(upstream_repo, upstream_commit, upstream_root)
        toolchain_pre["cargo_cache"] = _cargo_dependency_cache_inventory(candidate_root, tools, args.timeout_seconds)
        candidate_inventory = _inventory(candidate_root, (CRATE_RELATIVE, SEMANTIC_RUNNER_RELATIVE))
        upstream_inventory = _inventory(upstream_root, (Path("src/agent_com"), Path("schemas/result-v1.schema.json")))
        if candidate_inventory != _git_inventory(candidate_repo, candidate_commit, (CRATE_RELATIVE, SEMANTIC_RUNNER_RELATIVE)):
            raise RuntimeError("candidate inventory does not mechanically match Git")
        if upstream_inventory != _git_inventory(upstream_repo, upstream_commit, (Path("src/agent_com"), Path("schemas/result-v1.schema.json"))):
            raise RuntimeError("upstream inventory does not mechanically match Git")
        semantic_runner = _safe_file(candidate_root, SEMANTIC_RUNNER_RELATIVE)
        source_receipt = _probe_upstream(
            upstream_root,
            tools,
            args.timeout_seconds,
            _source_receipt(upstream_root),
        )
        module = _load_semantic_runner(semantic_runner)
        binary, cargo_binary, build = _build_compare(candidate_root, target_root, tools, args.timeout_seconds, source_date_epoch)
        scenarios = [
            _scenario_result(module, scenario, scratch, binary, upstream_root, tools, args.timeout_seconds)
            for scenario in module.scenario_documents()
        ]
        _validate_com03_scenarios(scenarios)
        scenario_set_sha = module.scenario_set_sha256(module.scenario_documents())
        if scenario_set_sha != EXPECTED_SCENARIO_SET_SHA256:
            raise RuntimeError("COM-03 payload scenario-set binding drift")
        binary_bytes, binary_sha = _bounded_file(binary, 512 * 1024 * 1024)
        build["binary_post"] = {"basename": binary.name, "bytes": binary_bytes, "sha256": binary_sha, "nlink": binary.stat(follow_symlinks=False).st_nlink, "path_redacted": True}
        build["binary_stable"] = build["binary_pre"] == build["binary_post"]
        build["cargo_source_post"] = _bounded_cargo_source(cargo_binary, target_root)
        build["cargo_source_stable"] = build["cargo_source_pre"] == build["cargo_source_post"]
        build["copy_matches_source"] = (
            build["binary_post"]["bytes"], build["binary_post"]["sha256"]
        ) == (
            build["cargo_source_post"]["bytes"], build["cargo_source_post"]["sha256"]
        )
        build["raw_binary_scope"] = ENVIRONMENT_SCOPE
        if build["binary_stable"] is not True or build["cargo_source_stable"] is not True or build["copy_matches_source"] is not True:
            raise RuntimeError("candidate source/copy identity changed during replay")
        post_candidate_inventory = _inventory(candidate_root, (CRATE_RELATIVE, SEMANTIC_RUNNER_RELATIVE))
        post_upstream_inventory = _inventory(upstream_root, (Path("src/agent_com"), Path("schemas/result-v1.schema.json")))
        if post_candidate_inventory != candidate_inventory or post_upstream_inventory != upstream_inventory:
            raise RuntimeError("archive source inventory changed during replay")
        candidate_record = {
            **candidate_info,
            "source_mode": "git_archive_at_immutable_commit",
            "inventory": candidate_inventory,
            "cargo_lock_sha256": _sha256(_safe_file(candidate_root, CRATE_RELATIVE / "Cargo.lock").read_bytes()),
            "source_date_epoch": source_date_epoch,
            "build": build,
        }
        upstream_record = {
            **upstream_info,
            "source_mode": "git_archive_at_immutable_commit",
            "inventory": upstream_inventory,
            "runtime": source_receipt,
            "uv_lock": dict(zip(("bytes", "sha256"), _bounded_file(_safe_file(upstream_root, Path("uv.lock"))))),
        }
        harness = {
            "runner": "tools/run_com_03_current_candidate.py",
            "semantic_runner": SEMANTIC_RUNNER_RELATIVE.as_posix(),
            "result_schema": RESULT_SCHEMA,
            "scenario_count": len(scenarios),
            "scenario_set_sha256": scenario_set_sha,
            "independent_payload_paths": True,
            "same_crate_self_comparison": False,
            "report_policy": "bounded_hashes_counts_exit_categories_and_match_flags_only",
            "timeout_seconds": args.timeout_seconds,
            "source": harness_source,
            "shared_com01_helper": {
                "schema": SHARED_HELPER_SCHEMA,
                "path": "tools/run_com_01_current_candidate.py",
                "sha256": next(item["sha256"] for item in harness_source["files"] if item["path"] == "tools/run_com_01_current_candidate.py"),
            },
        }
        toolchain_post, _ = _toolchain(args.cargo, args.python, args.uv)
        toolchain_post["cargo_cache"] = _cargo_dependency_cache_inventory(candidate_root, tools, args.timeout_seconds)
        if toolchain_post != toolchain_pre:
            raise RuntimeError("toolchain identity changed during replay")
    outcome_counts = dict(sorted(Counter(item["outcome"] for item in scenarios).items()))
    semantic_match_count = sum(1 for item in scenarios if item["semantic_match"])
    blockers = []
    if semantic_match_count != len(scenarios):
        blockers.append("candidate_compare_semantic_differences_observed")
    result = {
        "schema": SCHEMA,
        "status": OPEN_STATUS,
        "work_item": "COM-03",
        "leaf": "compare",
        "run_id": args.run_id,
        "nonce": args.nonce,
        "candidate": candidate_record,
        "upstream": upstream_record,
        "toolchain": {"pre": toolchain_pre, "post": toolchain_post, "stable": True},
        "harness": harness,
        "outcomes": outcome_counts,
        "scenario_count": len(scenarios),
        "semantic_match_count": semantic_match_count,
        "scenarios": scenarios,
        "blockers": blockers,
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
    _validate_com03_report(result)
    _path_free(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--candidate-commit", default=CANDIDATE_COMMIT)
    parser.add_argument("--upstream-repo", type=Path, default=Path(r"C:\Users\z3312\code\COM"))
    parser.add_argument("--upstream-commit", default=UPSTREAM_COMMIT)
    parser.add_argument("--harness-commit", required=True)
    parser.add_argument("--cargo", default=str(Path.home() / ".cargo" / "bin" / "cargo.exe"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--run-id", default=secrets.token_hex(32))
    parser.add_argument("--nonce", default=secrets.token_hex(32))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("timeout must be positive")
    try:
        report = run(args)
        _atomic_json_create(args.report, report, output_root=args.report.parent)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"status": report["status"], "run_id": report["run_id"], "scenario_count": report["scenario_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
