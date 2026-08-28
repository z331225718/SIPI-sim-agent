"""Fail-closed verifier for the COM-01 fingerprint current replay lane."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

try:
    from .run_com_01_fingerprint_current_replay import (  # type: ignore[import-not-found]
        CANDIDATE_COMMIT,
        CANDIDATE_TREE,
        CANDIDATE_ARCHIVE_BYTES,
        CANDIDATE_ARCHIVE_SHA256,
        CANDIDATE_INVENTORY,
        CANDIDATE_CARGO_LOCK_SHA256,
        CANDIDATE_SOURCE_DATE_EPOCH,
        PREP_PARENT_COMMIT,
        CONSUMPTION_KEYS,
        CONSUMPTION_OPTIONAL_KEYS,
        CRATE_RELATIVE,
        CUSTODY_COMMIT,
        CUSTODY_FILES,
        CUSTODY_TREE,
        EXPECTED_FINGERPRINT,
        EXPECTED_OPTION_COUNT,
        EXPECTED_PARAMETER_COUNT,
        EXPECTED_WARNING_COUNT,
        FIXTURE_BYTES,
        FIXTURE_RELATIVE,
        FIXTURE_SHA256,
        UPSTREAM_ARCHIVE_BYTES,
        UPSTREAM_ARCHIVE_SHA256,
        UPSTREAM_INVENTORY,
        UPSTREAM_SOURCE_INVENTORY,
        UPSTREAM_INIT_BYTES,
        UPSTREAM_INIT_SHA256,
        FORMAL_ARTIFACT_PREFIXES,
        HARNESS_FILES,
        HEX40,
        HEX64,
        MAX_HARNESS_FILE_BYTES,
        MAX_REPORT_BYTES,
        NON_CLAIMS,
        RAW_BINARY_POLICY,
        ROOT,
        _is_reparse,
        _load_custody,
        _read_bounded_regular,
        _validate_directory_root,
        _finite_json,
        _git as _runner_git,
        GIT_EXECUTABLE,
        GIT_TIMEOUT_SECONDS,
        MAX_GIT_STDOUT_BYTES,
        MAX_GIT_STDERR_BYTES,
    )
except ImportError:  # pragma: no cover - direct script import
    from run_com_01_fingerprint_current_replay import (
        CANDIDATE_COMMIT,
        CANDIDATE_TREE,
        CANDIDATE_ARCHIVE_BYTES,
        CANDIDATE_ARCHIVE_SHA256,
        CANDIDATE_INVENTORY,
        CANDIDATE_CARGO_LOCK_SHA256,
        CANDIDATE_SOURCE_DATE_EPOCH,
        PREP_PARENT_COMMIT,
        CONSUMPTION_KEYS,
        CONSUMPTION_OPTIONAL_KEYS,
        CRATE_RELATIVE,
        CUSTODY_COMMIT,
        CUSTODY_FILES,
        CUSTODY_TREE,
        EXPECTED_FINGERPRINT,
        EXPECTED_OPTION_COUNT,
        EXPECTED_PARAMETER_COUNT,
        EXPECTED_WARNING_COUNT,
        FIXTURE_BYTES,
        FIXTURE_RELATIVE,
        FIXTURE_SHA256,
        UPSTREAM_ARCHIVE_BYTES,
        UPSTREAM_ARCHIVE_SHA256,
        UPSTREAM_INVENTORY,
        UPSTREAM_SOURCE_INVENTORY,
        UPSTREAM_INIT_BYTES,
        UPSTREAM_INIT_SHA256,
        FORMAL_ARTIFACT_PREFIXES,
        HARNESS_FILES,
        HEX40,
        HEX64,
        MAX_HARNESS_FILE_BYTES,
        MAX_REPORT_BYTES,
        NON_CLAIMS,
        RAW_BINARY_POLICY,
        ROOT,
        _is_reparse,
        _load_custody,
        _read_bounded_regular,
        _validate_directory_root,
        _finite_json,
        _git as _runner_git,
        GIT_EXECUTABLE,
        GIT_TIMEOUT_SECONDS,
        MAX_GIT_STDOUT_BYTES,
        MAX_GIT_STDERR_BYTES,
    )


AGGREGATE_SCHEMA = "sipi.com-01.fingerprint-current-replay.aggregate.v1"
AGGREGATE_STATUS = "scoped_exact_materialized_fingerprint_two_fresh_replays"
EXPECTED_ARTIFACT_POLICY = "hash_counts_and_exactness_only_no_configuration_payloads"
EXPECTED_PAYLOAD_RECEIPTS = {
    "oracle": {
        "projection_sha256": "e8a3975d04e8e62316fe0d4f089a59389898f0a12760b6267ab64d26f889eaf1",
        "config_sha256": "f2c4c92f9549e720fff2843df6dc861aca7a503d59b2208898c2b67fa6fc0fc9",
        "materialized_fingerprint": "d6963c122533d58273e4ebf3224bade1dc38b040f740c1cd92d4c9727e4483dc",
        "parameters": {"count": 148, "keys_sha256": "0d5ac58e2807c5cda038371fcb4f3b689359a393fe0053c6f9773927227ad870", "semantic_sha256": "4bd968fef4a4281ba8dd9d2ff7dd90ea5822e4bcdfeaa0e9c66f0d92b42e3ac9"},
        "options": {"count": 90, "keys_sha256": "db2dcb5e7d9b32ee6d2c55e905fe22d28a744581c8c3a88757754b61cfbd0137", "semantic_sha256": "04c57c402183eeb4d9b0147344baa2a9e7fe57fb635ba7676704c68d8ca5f79c"},
        "consumption": {"keys": [*CONSUMPTION_KEYS, *CONSUMPTION_OPTIONAL_KEYS], "semantic_sha256": "a29fc93c371c206ebdacc2d10f8744f7fbab445bf997a47cc1459873533310d6", "common_sha256": "f61982ef0d313fc2d1612d594e37aea6d8291f4dbaa739400819abe158bd055b", "oracle_only_sha256": "b4b661d83b210291ff8254334199a7e92432a45182081d15ea01a6e6f65c846d"},
        "warnings": {"count": 0, "semantic_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"},
    },
    "candidate": {
        "projection_sha256": "7ecc464128d48202b2652d48fc4acfe6d6c57a9f8a4e733c9dfc5980a39290e2",
        "config_sha256": "f2c4c92f9549e720fff2843df6dc861aca7a503d59b2208898c2b67fa6fc0fc9",
        "materialized_fingerprint": "d6963c122533d58273e4ebf3224bade1dc38b040f740c1cd92d4c9727e4483dc",
        "parameters": {"count": 148, "keys_sha256": "0d5ac58e2807c5cda038371fcb4f3b689359a393fe0053c6f9773927227ad870", "semantic_sha256": "4bd968fef4a4281ba8dd9d2ff7dd90ea5822e4bcdfeaa0e9c66f0d92b42e3ac9"},
        "options": {"count": 90, "keys_sha256": "db2dcb5e7d9b32ee6d2c55e905fe22d28a744581c8c3a88757754b61cfbd0137", "semantic_sha256": "04c57c402183eeb4d9b0147344baa2a9e7fe57fb635ba7676704c68d8ca5f79c"},
        "consumption": {"keys": list(CONSUMPTION_KEYS), "semantic_sha256": "f61982ef0d313fc2d1612d594e37aea6d8291f4dbaa739400819abe158bd055b", "common_sha256": "f61982ef0d313fc2d1612d594e37aea6d8291f4dbaa739400819abe158bd055b", "oracle_only_sha256": "711b49e22c6c029019c8a36e79d546afc73deeafebcf7636e03350662d773f80"},
        "warnings": {"count": 0, "semantic_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"},
    },
}
PATH_LEAK = re.compile(
    r"(?i)(?:[a-z]:[\\/]|\\\\|/(?:users|home|tmp|var|private)/|file://|(?:^|[\\/])\.\.?[\\/])"
)
EXPECTED_REPORT_KEYS = {
    "schema", "status", "work_item", "leaf", "run_id", "fresh_run_nonce", "source_mode",
    "candidate", "upstream", "harness", "toolchain", "fixture", "scenario", "expected",
    "exact", "artifact_policy", "acceptance", "non_claims",
}
EXPECTED_AGGREGATE_KEYS = {
    "schema", "status", "work_item", "leaf", "fresh_replays", "reports", "candidate", "upstream",
    "harness", "toolchain", "fixture", "scenario", "expected", "exact", "build_receipts", "binary_bit_reproducible",
    "binary_reproducibility", "raw_binary_sha_equal", "blockers", "acceptance", "artifact_policy", "non_claims",
}
EXPECTED_EXACT = {
    "materialized_fingerprint": True,
    "parameters": True,
    "options": True,
    "consumption": True,
    "warnings": True,
    "all": True,
}
EXPECTED_FACTS = {
    "materialized_fingerprint": EXPECTED_FINGERPRINT,
    "parameter_count": EXPECTED_PARAMETER_COUNT,
    "option_count": EXPECTED_OPTION_COUNT,
    "warning_count": EXPECTED_WARNING_COUNT,
}


class VerificationError(ValueError):
    """Raised when replay evidence cannot be admitted."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def is_sha(value: Any, pattern: re.Pattern[str] = HEX64) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _path_free(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _path_free(key)
            _path_free(item)
    elif isinstance(value, list):
        for item in value:
            _path_free(item)
    elif type(value) is str:
        require(PATH_LEAK.search(value.replace("\\", "/")) is None, "absolute or traversal path leaked into evidence")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(type(key) is str and key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _input_target(path: Path, input_root: Path) -> Path:
    root = _validate_directory_root(input_root)
    target = path if path.is_absolute() else Path.cwd() / path
    require(".." not in target.parts and target.parent == root and bool(target.name), "input must be a direct child of its fixed root")
    require(not _is_reparse(target), "input is a symlink or reparse point")
    return target


def read_json(path: Path, *, input_root: Path | None = None) -> tuple[dict[str, Any], str]:
    target = _input_target(path, input_root or path.parent)
    payload = _read_bounded_regular(target, MAX_REPORT_BYTES)
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON constant: {value}")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError("JSON input is malformed") from error
    require(type(value) is dict, "replay document must be an object")
    _finite_json(value)
    _path_free(value)
    return value, hashlib.sha256(payload).hexdigest()


def _archive(value: Any, label: str) -> None:
    require(type(value) is dict and set(value) == {"bytes", "sha256", "command", "path_redacted"}, f"{label} archive shape drift")
    require(type(value["bytes"]) is int and value["bytes"] > 0 and is_sha(value["sha256"]), f"{label} archive identity drift")
    require(type(value["command"]) is str and bool(value["command"]) and value["path_redacted"] is True, f"{label} archive policy drift")


def _inventory(value: Any, label: str) -> None:
    require(type(value) is dict and set(value) == {"file_count", "total_bytes", "sha256"}, f"{label} inventory shape drift")
    require(type(value["file_count"]) is int and value["file_count"] >= 0 and type(value["total_bytes"]) is int and value["total_bytes"] >= 0 and is_sha(value["sha256"]), f"{label} inventory identity drift")


def _artifact_receipt(value: Any, label: str, *, require_nlink: bool = True) -> None:
    require(type(value) is dict and set(value) == {"basename", "bytes", "sha256", "nlink", "path_redacted"}, f"{label} receipt shape drift")
    require(type(value["basename"]) is str and bool(value["basename"]) and not any(token in value["basename"] for token in ("/", "\\", ":")), f"{label} basename drift")
    require(type(value["bytes"]) is int and value["bytes"] > 0 and is_sha(value["sha256"]), f"{label} identity drift")
    require(type(value["nlink"]) is int and value["nlink"] >= 1 and (not require_nlink or value["nlink"] == 1), f"{label} link count drift")
    require(value["path_redacted"] is True, f"{label} path policy drift")


def _source_receipt(value: Any, label: str) -> None:
    require(type(value) is dict and set(value) == {"module_file", "package_source_inventory"}, f"{label} source receipt drift")
    module = value["module_file"]
    require(type(module) is dict and set(module) == {"relative_path", "basename", "bytes", "sha256", "root_contained", "path_redacted"}, f"{label} module receipt drift")
    require(module["relative_path"] == "src/agent_com/__init__.py" and module["basename"] == "__init__.py", f"{label} module path drift")
    require(type(module["bytes"]) is int and module["bytes"] > 0 and is_sha(module["sha256"]) and module["root_contained"] is True and module["path_redacted"] is True, f"{label} module identity drift")
    _inventory(value["package_source_inventory"], f"{label}.package_source_inventory")
    require(value["package_source_inventory"]["file_count"] > 0 and value["package_source_inventory"]["total_bytes"] > 0, f"{label} package inventory drift")


def _validate_candidate_static(value: Any) -> None:
    require(type(value) is dict and set(value) == {"commit", "tree", "archive", "source_mode", "inventory", "cargo_lock_sha256", "source_date_epoch", "cargo_binary_basename"}, "candidate static binding shape drift")
    require(value["commit"] == CANDIDATE_COMMIT and value["tree"] == CANDIDATE_TREE and value["source_mode"] == "git_archive_at_immutable_commit", "candidate revision/source drift")
    _archive(value["archive"], "candidate")
    require(value["archive"] == {"bytes": CANDIDATE_ARCHIVE_BYTES, "sha256": CANDIDATE_ARCHIVE_SHA256, "command": "git -c core.autocrlf=false archive --format=tar <revision>", "path_redacted": True}, "candidate archive binding drift")
    _inventory(value["inventory"], "candidate")
    require(value["inventory"] == CANDIDATE_INVENTORY, "candidate inventory binding drift")
    require(value["cargo_lock_sha256"] == CANDIDATE_CARGO_LOCK_SHA256 and value["source_date_epoch"] == CANDIDATE_SOURCE_DATE_EPOCH and value["cargo_binary_basename"] == "sipi-com-direct-config-validate.exe", "candidate identity drift")


def _validate_build(build: Any, label: str = "candidate build") -> None:
    require(type(build) is dict and set(build) == {"command", "cargo_source_pre", "binary_pre", "binary_post", "stdout_sha256", "stderr_sha256", "log_policy", "environment", "copy_matches_source", "raw_binary_scope", "dependency_cache_pre", "dependency_cache_post", "dependency_cache_equal", "tool_identities_pre", "tool_identities_post", "tool_identities_equal", "git_identity_pre", "git_identity_post", "git_identity_equal"}, f"{label} receipt shape drift")
    require(type(build["command"]) is str and "cargo build" in build["command"], f"{label} command drift")
    _artifact_receipt(build["cargo_source_pre"], f"{label} Cargo source", require_nlink=False)
    _artifact_receipt(build["binary_pre"], f"{label} execution copy")
    _artifact_receipt(build["binary_post"], f"{label} execution copy post")
    require(build["binary_pre"]["bytes"] == build["binary_post"]["bytes"] and build["binary_pre"]["sha256"] == build["binary_post"]["sha256"], f"{label} execution copy changed")
    require(build["cargo_source_pre"]["bytes"] == build["binary_post"]["bytes"] and build["cargo_source_pre"]["sha256"] == build["binary_post"]["sha256"], f"{label} execution copy is not source-identical")
    require(is_sha(build["stdout_sha256"]) and is_sha(build["stderr_sha256"]) and build["log_policy"] == "stable_event_categories", f"{label} log drift")
    environment = build["environment"]
    expected = {"cleared", "incremental", "offline", "rustc_forced", "wrappers_cleared", "source_path_remapped", "target_is_independent", "cargo_home_policy", "native_linker_overrides_cleared", "linker_forced", "cargo_cache_bound_pre_post"}
    require(type(environment) is dict and set(environment) == expected, f"{label} environment shape drift")
    require(type(environment["cleared"]) is list and all(type(item) is str and item for item in environment["cleared"]) and environment["incremental"] == "0" and environment["offline"] is True and environment["rustc_forced"] is True and environment["wrappers_cleared"] is True and environment["source_path_remapped"] is True and environment["target_is_independent"] is True and environment["cargo_home_policy"] == "host_cargo_home_retained_for_offline_dependency_cache" and environment["native_linker_overrides_cleared"] is True and environment["linker_forced"] is True and environment["cargo_cache_bound_pre_post"] is True, f"{label} environment policy drift")
    require(build["copy_matches_source"] is True and build["raw_binary_scope"] == "execution_copy_only", f"{label} copy policy drift")
    _validate_dependency_cache(build["dependency_cache_pre"], f"{label} dependency cache pre")
    _validate_dependency_cache(build["dependency_cache_post"], f"{label} dependency cache post")
    require(build["dependency_cache_pre"] == build["dependency_cache_post"] and type(build["dependency_cache_equal"]) is bool and build["dependency_cache_equal"] is True, f"{label} dependency cache boundary drift")
    _validate_tool_identity_map(build["tool_identities_pre"], f"{label} tool identities pre")
    _validate_tool_identity_map(build["tool_identities_post"], f"{label} tool identities post")
    require(build["tool_identities_pre"] == build["tool_identities_post"] and type(build["tool_identities_equal"]) is bool and build["tool_identities_equal"] is True, f"{label} tool identity boundary drift")
    _artifact_receipt(build["git_identity_pre"], f"{label} Git identity pre", require_nlink=False)
    _artifact_receipt(build["git_identity_post"], f"{label} Git identity post", require_nlink=False)
    require(build["git_identity_pre"] == build["git_identity_post"] and type(build["git_identity_equal"]) is bool and build["git_identity_equal"] is True, f"{label} Git identity boundary drift")


def _validate_candidate(value: Any, toolchain: Any = None) -> None:
    require(type(value) is dict, "candidate binding must be an object")
    _validate_candidate_static({key: value[key] for key in value if key != "build"})
    require(type(value) is dict and set(value) == {"commit", "tree", "archive", "source_mode", "inventory", "cargo_lock_sha256", "source_date_epoch", "build", "cargo_binary_basename"}, "candidate binding shape drift")
    _validate_build(value["build"])
    if toolchain is not None:
        require(value["build"]["tool_identities_pre"] == {role: toolchain[role] for role in ("cargo", "rustc", "python", "uv", "linker")}, "candidate/toolchain pre identity crossbind drift")


def _validate_dependency_cache(value: Any, label: str) -> None:
    require(type(value) is dict and set(value) == {"scope", "path_redacted", "package_count", "file_count", "total_bytes", "sha256"}, f"{label} shape drift")
    require(value["scope"] == "resolved_locked_dependency_sources" and value["path_redacted"] is True and type(value["package_count"]) is int and value["package_count"] > 0 and type(value["file_count"]) is int and value["file_count"] > 0 and type(value["total_bytes"]) is int and value["total_bytes"] > 0 and is_sha(value["sha256"]), f"{label} identity drift")


def _validate_tool_identity_map(value: Any, label: str) -> None:
    roles = ("cargo", "rustc", "python", "uv", "linker")
    require(type(value) is dict and set(value) == set(roles), f"{label} role set drift")
    expected = {"role", "basename", "file_bytes", "file_sha256", "version_args", "version_exit", "version_stdout_sha256", "version_stderr_sha256", "path_redacted"}
    for role in roles:
        identity = value[role]
        require(type(identity) is dict and set(identity) == expected and identity["role"] == role and type(identity["file_bytes"]) is int and identity["file_bytes"] > 0 and is_sha(identity["file_sha256"]) and type(identity["version_args"]) is list and all(type(item) is str for item in identity["version_args"]) and type(identity["version_exit"]) is int and identity["version_exit"] == 0 and is_sha(identity["version_stdout_sha256"]) and is_sha(identity["version_stderr_sha256"]) and identity["path_redacted"] is True, f"{label} identity drift: {role}")


def _validate_module(module: Any, name: str) -> None:
    require(type(module) is dict and set(module) == {"relative_path", "basename", "bytes", "sha256"}, f"upstream module receipt drift: {name}")
    relative = module["relative_path"]
    require(type(relative) is str and relative and "\\" not in relative and not PurePosixPath(relative).is_absolute() and not PureWindowsPath(relative).is_absolute() and not PureWindowsPath(relative).drive and all(part not in {"", ".", ".."} for part in PurePosixPath(relative).parts), f"upstream module path drift: {name}")
    require(type(module["basename"]) is str and module["basename"] == PurePosixPath(relative).name and "/" not in module["basename"] and "\\" not in module["basename"], f"upstream module basename drift: {name}")
    require(type(module["bytes"]) is int and module["bytes"] > 0 and is_sha(module["sha256"]), f"upstream module identity drift: {name}")


def _validate_upstream(value: Any) -> None:
    require(type(value) is dict and set(value) == {"commit", "tree", "archive", "source_mode", "inventory", "source", "runtime"}, "upstream binding shape drift")
    require(value["commit"] == "5272ffe74702cd585054d975559b06f8afae7b6e" and value["tree"] == "7094ab6e84989b218730c52432c70da10261f8ea" and value["source_mode"] == "git_archive_at_immutable_commit", "upstream revision/source drift")
    _archive(value["archive"], "upstream")
    require(value["archive"] == {"bytes": UPSTREAM_ARCHIVE_BYTES, "sha256": UPSTREAM_ARCHIVE_SHA256, "command": "git -c core.autocrlf=false archive --format=tar <revision>", "path_redacted": True}, "upstream archive binding drift")
    _inventory(value["inventory"], "upstream")
    require(value["inventory"] == UPSTREAM_INVENTORY, "upstream inventory binding drift")
    _source_receipt(value["source"], "upstream")
    require(value["source"]["module_file"]["bytes"] == UPSTREAM_INIT_BYTES and value["source"]["module_file"]["sha256"] == UPSTREAM_INIT_SHA256 and value["source"]["package_source_inventory"] == UPSTREAM_SOURCE_INVENTORY, "upstream source binding drift")
    runtime = value["runtime"]
    require(type(runtime) is dict and set(runtime) == {"runtime", "command", "exit", "stdout_bytes", "stdout_sha256", "stderr_bytes", "stderr_sha256", "source", "environment", "modules"}, "upstream runtime receipt shape drift")
    require(runtime["runtime"] == "executed_clean_archive_uv_frozen_offline" and type(runtime["command"]) is str and "uv run --frozen --offline" in runtime["command"] and type(runtime["exit"]) is int and runtime["exit"] == 0, "upstream runtime policy drift")
    require(type(runtime["stdout_bytes"]) is int and runtime["stdout_bytes"] >= 0 and is_sha(runtime["stdout_sha256"]) and type(runtime["stderr_bytes"]) is int and runtime["stderr_bytes"] >= 0 and is_sha(runtime["stderr_sha256"]), "upstream stream receipt drift")
    _source_receipt(runtime["source"], "upstream runtime")
    require(runtime["source"] == value["source"], "upstream runtime source binding drift")
    environment = runtime["environment"]
    require(type(environment) is dict and set(environment) == {"cleared", "pythonno_user_site", "uv_no_config", "project_venv", "direct_python_fallback", "global_uv_cache", "uv_frozen", "uv_offline", "dependency_modules_scope"}, "upstream environment shape drift")
    require(type(environment["cleared"]) is list and all(type(item) is str and item for item in environment["cleared"]) and environment["pythonno_user_site"] is True and environment["uv_no_config"] is True and environment["project_venv"] == "materialized_inside_archive" and environment["direct_python_fallback"] is False and environment["global_uv_cache"] == "required_path_redacted_environment_local" and environment["uv_frozen"] is True and environment["uv_offline"] is True and environment["dependency_modules_scope"] == "environment_local_recheck_not_replay_artifact", "upstream environment policy drift")
    modules = runtime["modules"]
    require(type(modules) is dict and list(modules) == ["agent_com", "numpy", "openpyxl", "scipy", "yaml"], "upstream module set/order drift")
    for name, module in modules.items():
        _validate_module(module, name)
    require(modules["agent_com"]["relative_path"] == "src/agent_com/__init__.py", "Agent-COM module escaped archive")
    require(modules["agent_com"] == {"relative_path": "src/agent_com/__init__.py", "basename": "__init__.py", "bytes": UPSTREAM_INIT_BYTES, "sha256": UPSTREAM_INIT_SHA256}, "Agent-COM module binding drift")


def _validate_raw_files(value: Any, expected_paths: tuple[str, ...], label: str) -> None:
    require(type(value) is list and len(value) == len(expected_paths) and [entry.get("path") if type(entry) is dict else None for entry in value] == list(expected_paths), f"{label} file order drift")
    for entry in value:
        require(type(entry) is dict and set(entry) == {"path", "git_blob_sha1", "bytes", "content_sha256"}, f"{label} file receipt shape drift")
        require(type(entry["path"]) is str and entry["path"] in expected_paths and is_sha(entry["git_blob_sha1"], HEX40) and type(entry["bytes"]) is int and entry["bytes"] > 0 and is_sha(entry["content_sha256"]), f"{label} file identity drift")


def _validate_harness(value: Any) -> None:
    require(type(value) is dict and set(value) == {"prep_commit", "prep_parent", "prep_tree", "changed_paths", "first_introduction", "formal_artifacts_absent", "files", "shared_custody", "source_mode"}, "harness shape drift")
    require(is_sha(value["prep_commit"], HEX40) and value["prep_parent"] == PREP_PARENT_COMMIT and is_sha(value["prep_tree"], HEX40), "harness commit/tree drift")
    require(type(value["changed_paths"]) is list and value["changed_paths"] == list(HARNESS_FILES) and value["first_introduction"] is True and value["formal_artifacts_absent"] is True and value["source_mode"] == "raw_git_blob_bound_before_execution", "harness custody policy drift")
    _validate_raw_files(value["files"], HARNESS_FILES, "harness")
    custody = value["shared_custody"]
    require(type(custody) is dict and set(custody) == {"commit", "tree", "files"} and custody["commit"] == CUSTODY_COMMIT and custody["tree"] == CUSTODY_TREE, "shared custody identity drift")
    _validate_raw_files(custody["files"], tuple(CUSTODY_FILES), "shared custody")
    for entry in custody["files"]:
        require(entry["git_blob_sha1"] == CUSTODY_FILES[entry["path"]], f"shared custody blob drift: {entry['path']}")


def _validate_toolchain(value: Any) -> None:
    require(type(value) is dict and set(value) == {"cargo", "rustc", "python", "uv", "linker", "timeout_seconds"} and type(value["timeout_seconds"]) is int and value["timeout_seconds"] > 0, "toolchain shape drift")
    expected = {"role", "basename", "file_bytes", "file_sha256", "version_args", "version_exit", "version_stdout_sha256", "version_stderr_sha256", "path_redacted"}
    for role in ("cargo", "rustc", "python", "uv", "linker"):
        identity = value[role]
        require(type(identity) is dict and set(identity) == expected and identity["role"] == role and type(identity["basename"]) is str and bool(identity["basename"]) and not any(token in identity["basename"] for token in ("/", "\\", ":")) and type(identity["file_bytes"]) is int and identity["file_bytes"] > 0 and is_sha(identity["file_sha256"]) and type(identity["version_args"]) is list and bool(identity["version_args"]) and all(type(item) is str for item in identity["version_args"]) and type(identity["version_exit"]) is int and identity["version_exit"] == 0 and is_sha(identity["version_stdout_sha256"]) and is_sha(identity["version_stderr_sha256"]) and identity["path_redacted"] is True, f"{role} identity drift")


def _validate_fixture(value: Any) -> None:
    require(type(value) is dict and set(value) == {"role", "relative_path", "basename", "bytes", "sha256", "path_redacted", "custody"}, "fixture binding shape drift")
    require(value["role"] == "primary_xlsx" and value["relative_path"] == FIXTURE_RELATIVE.as_posix() and value["basename"] == FIXTURE_RELATIVE.name and type(value["bytes"]) is int and value["bytes"] == FIXTURE_BYTES and value["sha256"] == FIXTURE_SHA256 and type(value["path_redacted"]) is bool and value["path_redacted"] is True and value["custody"] == "upstream_git_archive_only", "fixture binding drift")


def _validate_payload_receipt(value: Any, label: str) -> None:
    require(type(value) is dict and set(value) == {"projection_sha256", "config_sha256", "materialized_fingerprint", "parameters", "options", "consumption", "warnings"}, f"{label} payload shape drift")
    require(is_sha(value["projection_sha256"]) and value["config_sha256"] == FIXTURE_SHA256 and value["materialized_fingerprint"] == EXPECTED_FINGERPRINT, f"{label} payload identity drift")
    for name, count in (("parameters", EXPECTED_PARAMETER_COUNT), ("options", EXPECTED_OPTION_COUNT)):
        item = value[name]
        require(type(item) is dict and set(item) == {"count", "keys_sha256", "semantic_sha256"} and type(item["count"]) is int and item["count"] == count and is_sha(item["keys_sha256"]) and is_sha(item["semantic_sha256"]), f"{label} {name} receipt drift")
    consumption = value["consumption"]
    require(type(consumption) is dict and set(consumption) == {"keys", "semantic_sha256", "common_sha256", "oracle_only_sha256"}, f"{label} consumption receipt drift")
    keys = consumption["keys"]
    allowed = (*CONSUMPTION_KEYS, *CONSUMPTION_OPTIONAL_KEYS)
    require(type(keys) is list and keys[: len(CONSUMPTION_KEYS)] == list(CONSUMPTION_KEYS) and all(type(key) is str and key in allowed for key in keys) and len(keys) == len(set(keys)) and keys == list(CONSUMPTION_KEYS) + [key for key in CONSUMPTION_OPTIONAL_KEYS if key in keys] and is_sha(consumption["semantic_sha256"]) and is_sha(consumption["common_sha256"]) and is_sha(consumption["oracle_only_sha256"]), f"{label} consumption identity drift")
    warnings = value["warnings"]
    require(type(warnings) is dict and set(warnings) == {"count", "semantic_sha256"} and type(warnings["count"]) is int and warnings["count"] == EXPECTED_WARNING_COUNT and is_sha(warnings["semantic_sha256"]), f"{label} warning identity drift")
    require(label in EXPECTED_PAYLOAD_RECEIPTS and value == EXPECTED_PAYLOAD_RECEIPTS[label], f"{label} payload receipt is not bound to the real 120G smoke anchor")


def _validate_scenario(value: Any) -> None:
    require(type(value) is dict and set(value) == {"id", "fixture_role", "profile", "output", "oracle", "candidate", "exact", "comparison_mode"} and value["id"] == "xlsx_materialized_json_default" and value["fixture_role"] == "primary_xlsx" and value["profile"] == "r480" and value["output"] == "materialized_json" and value["comparison_mode"] == "parsed_json_semantic_numbers_with_exact_fingerprint", "scenario identity drift")
    for role, runtime in (("oracle", "uv_frozen_offline"), ("candidate", "archive_binary_execution_copy")):
        item = value[role]
        require(type(item) is dict and set(item) == {"exit_code", "payload", "runtime"} and type(item["exit_code"]) is int and item["exit_code"] == 0 and item["runtime"] == runtime, f"{role} scenario execution drift")
        _validate_payload_receipt(item["payload"], role)
    oracle_keys = value["oracle"]["payload"]["consumption"]["keys"]
    candidate_keys = value["candidate"]["payload"]["consumption"]["keys"]
    require(oracle_keys == list(CONSUMPTION_KEYS) + list(CONSUMPTION_OPTIONAL_KEYS), "oracle complete consumption projection drift")
    require(candidate_keys == list(CONSUMPTION_KEYS) or candidate_keys == oracle_keys, "candidate consumption projection drift")
    for key in ("config_sha256", "materialized_fingerprint", "parameters", "options", "warnings"):
        require(value["oracle"]["payload"][key] == value["candidate"]["payload"][key], f"oracle/candidate {key} receipt drift")
    require(value["oracle"]["payload"]["consumption"]["common_sha256"] == value["candidate"]["payload"]["consumption"]["common_sha256"], "oracle/candidate common consumption hash drift")
    exact = value["exact"]
    require(type(exact) is dict and set(exact) == set(EXPECTED_EXACT) and all(type(item) is bool for item in exact.values()) and exact == EXPECTED_EXACT, "scenario exactness drift")


def _git_raw(root: Path, *args: str, maximum: int = MAX_HARNESS_FILE_BYTES) -> bytes:
    require(GIT_EXECUTABLE is not None, "fixed Git executable is unavailable")
    try:
        output = _runner_git(root, *args, raw=True)
    except subprocess.CalledProcessError:
        raise
    require(isinstance(output, bytes) and len(output) <= min(maximum, MAX_GIT_STDOUT_BYTES), "Git output exceeds bound")
    return output


def _git_text(root: Path, *args: str) -> str:
    value = _git_raw(root, *args).decode("ascii").strip()
    require(bool(value) and "\n" not in value and "\r" not in value, "Git identity output drift")
    return value


def _verify_prep_commit(harness: dict[str, Any], repo_root: Path) -> None:
    require(harness.get("prep_parent") == PREP_PARENT_COMMIT and harness.get("changed_paths") == list(HARNESS_FILES) and harness.get("first_introduction") is True and harness.get("formal_artifacts_absent") is True, "prep harness policy drift")
    prep = harness["prep_commit"]
    require(_git_text(repo_root, "rev-parse", f"{prep}^{{commit}}") == prep and _git_text(repo_root, "rev-parse", f"{prep}^{{tree}}") == harness["prep_tree"], "prep commit/tree drift")
    require(_git_text(repo_root, "rev-list", "--parents", "-n", "1", prep).split() == [prep, PREP_PARENT_COMMIT], "prep parent is not the pinned integration head")
    try:
        _git_raw(repo_root, "merge-base", "--is-ancestor", CANDIDATE_COMMIT, prep)
    except subprocess.CalledProcessError:
        raise VerificationError("candidate is not an ancestor of prep")
    candidate_changes = _git_raw(repo_root, "diff", "--name-only", f"{CANDIDATE_COMMIT}..{prep}", "--", CRATE_RELATIVE.as_posix()).decode("utf-8").splitlines()
    require(candidate_changes == [], "candidate COM production paths changed after candidate")
    changes = _git_raw(repo_root, "diff-tree", "--no-commit-id", "--no-renames", "--name-status", "-r", f"{prep}^", prep).decode("utf-8").splitlines()
    require(sorted(changes) == sorted(f"A\t{path}" for path in HARNESS_FILES), "prep changed paths drift")
    require(all(not _git_exists(repo_root, f"{prep}^:{path}") for path in HARNESS_FILES), "prep tools were not first introduced")
    paths = _git_raw(repo_root, "ls-tree", "-r", "--name-only", prep).decode("utf-8").splitlines()
    require(not any(any(path.startswith(prefix) for prefix in FORMAL_ARTIFACT_PREFIXES) for path in paths), "formal artifacts existed at prep")
    for entry in harness["files"]:
        raw = _git_raw(repo_root, "show", f"{prep}:{entry['path']}")
        require(len(raw) == entry["bytes"] and hashlib.sha256(raw).hexdigest() == entry["content_sha256"] and _git_text(repo_root, "rev-parse", f"{prep}:{entry['path']}") == entry["git_blob_sha1"], f"prep raw blob drift: {entry['path']}")
        require(_read_bounded_regular(repo_root / entry["path"], MAX_HARNESS_FILE_BYTES) == raw, f"prep live source drift: {entry['path']}")
    custody = harness["shared_custody"]
    require(_git_text(repo_root, "rev-parse", f"{CUSTODY_COMMIT}^{{tree}}") == CUSTODY_TREE, "e74 custody tree drift")
    for entry in custody["files"]:
        raw = _git_raw(repo_root, "show", f"{CUSTODY_COMMIT}:{entry['path']}")
        require(len(raw) == entry["bytes"] and hashlib.sha256(raw).hexdigest() == entry["content_sha256"] and _git_text(repo_root, "rev-parse", f"{CUSTODY_COMMIT}:{entry['path']}") == entry["git_blob_sha1"], f"custody raw blob drift: {entry['path']}")
        require(_read_bounded_regular(repo_root / entry["path"], MAX_HARNESS_FILE_BYTES) == raw, f"custody live source drift: {entry['path']}")


def _git_exists(root: Path, expression: str) -> bool:
    try:
        _git_raw(root, "cat-file", "-e", expression)
    except (subprocess.CalledProcessError, VerificationError):
        return False
    return True


def _verify_candidate_physical(value: dict[str, Any], repo_root: Path) -> None:
    custody = _load_custody(repo_root)
    require(_git_text(repo_root, "rev-parse", f"{CANDIDATE_COMMIT}^{{commit}}") == CANDIDATE_COMMIT and _git_text(repo_root, "rev-parse", f"{CANDIDATE_COMMIT}^{{tree}}") == CANDIDATE_TREE, "candidate Git identity drift")
    with tempfile.TemporaryDirectory(prefix="com-01-fingerprint-candidate-") as directory:
        archive_path = Path(directory) / "archive"
        info = custody._materialize(repo_root, CANDIDATE_COMMIT, archive_path)
        require(info["commit"] == CANDIDATE_COMMIT and info["tree"] == CANDIDATE_TREE, "candidate archive revision drift")
        require(info["archive"] == value["archive"], "candidate archive identity drift")
        require(custody._inventory(archive_path, (CRATE_RELATIVE,)) == value["inventory"], "candidate inventory drift")
        lock = custody._safe_file(archive_path, CRATE_RELATIVE / "Cargo.lock")
        lock_size, lock_sha = custody._bounded_file(lock)
        raw = _git_raw(repo_root, "show", f"{CANDIDATE_COMMIT}:{(CRATE_RELATIVE / 'Cargo.lock').as_posix()}")
        require(len(raw) == lock_size and hashlib.sha256(raw).hexdigest() == lock_sha == value["cargo_lock_sha256"], "Cargo.lock identity drift")
    require(value["source_date_epoch"] == _git_text(repo_root, "show", "-s", "--format=%ct", CANDIDATE_COMMIT), "source date drift")


def _verify_upstream_physical(value: dict[str, Any], upstream_root: Path, custody_source: Path | None = None) -> None:
    custody = _load_custody(custody_source or ROOT)
    with tempfile.TemporaryDirectory(prefix="com-01-fingerprint-upstream-") as directory:
        archive_path = Path(directory) / "archive"
        info = custody._materialize(upstream_root, value["commit"], archive_path)
        require(info["commit"] == value["commit"] and info["tree"] == value["tree"], "upstream archive revision drift")
        require(info["archive"] == value["archive"], "upstream archive identity drift")
        prefixes = (Path("src/agent_com"), Path("schemas/r480-config.schema.yaml"), Path("schemas/behavior-presets.yaml"), FIXTURE_RELATIVE)
        require(custody._inventory(archive_path, prefixes) == value["inventory"], "upstream inventory drift")
        fixture = custody._safe_file(archive_path, FIXTURE_RELATIVE)
        size, digest = custody._bounded_file(fixture)
        require((size, digest) == (FIXTURE_BYTES, FIXTURE_SHA256), "fixture identity drift")
        require(custody._source_receipt(archive_path) == value["source"], "upstream source receipt drift")
        for name, module in value["runtime"]["modules"].items():
            module_root = archive_path if name == "agent_com" else upstream_root
            try:
                path = custody._safe_file(module_root, Path(module["relative_path"]))
            except RuntimeError:
                # Third-party modules live in the caller's environment rather
                # than the Git archive; their receipts are environment-local.
                if name != "agent_com":
                    continue
                raise
            size, digest = custody._bounded_file(path)
            require((size, digest) == (module["bytes"], module["sha256"]), f"upstream module identity drift: {name}")


def validate_report(value: Any, *, repo_root: Path | None = None, upstream_root: Path | None = None) -> dict[str, Any]:
    require(type(value) is dict and set(value) == EXPECTED_REPORT_KEYS, "report root shape drift")
    require(value["schema"] == "sipi.com-01.fingerprint-current-replay.v1" and value["status"] == "scoped_exact_materialized_fingerprint_replay" and value["work_item"] == "COM-01" and value["leaf"] == "config-validate", "report schema/work-item drift")
    require(type(value["run_id"]) is str and HEX64.fullmatch(value["run_id"]) is not None and type(value["fresh_run_nonce"]) is str and HEX64.fullmatch(value["fresh_run_nonce"]) is not None and value["run_id"] != value["fresh_run_nonce"], "report replay identity drift")
    require(value["source_mode"] == "git_archive_at_immutable_commit", "report source mode drift")
    _validate_toolchain(value["toolchain"])
    _validate_candidate(value["candidate"], value["toolchain"])
    _validate_upstream(value["upstream"])
    _validate_harness(value["harness"])
    _validate_fixture(value["fixture"])
    _validate_scenario(value["scenario"])
    require(type(value["expected"]) is dict and value["expected"] == EXPECTED_FACTS and all(type(value["expected"][key]) is type(EXPECTED_FACTS[key]) for key in EXPECTED_FACTS), "report expected facts drift")
    require(type(value["exact"]) is dict and value["exact"] == EXPECTED_EXACT and all(type(item) is bool for item in value["exact"].values()), "report exactness drift")
    require(value["artifact_policy"] == EXPECTED_ARTIFACT_POLICY and type(value["acceptance"]) is bool and value["acceptance"] is False, "report policy/acceptance drift")
    require(type(value["non_claims"]) is list and value["non_claims"] == list(NON_CLAIMS) and all(type(item) is str for item in value["non_claims"]), "report non-claims drift")
    if repo_root is not None:
        repo_root = _validate_directory_root(repo_root)
        _verify_prep_commit(value["harness"], repo_root)
        _verify_candidate_physical(value["candidate"], repo_root)
    if upstream_root is not None:
        upstream_root = _validate_directory_root(upstream_root)
        _verify_upstream_physical(value["upstream"], upstream_root, repo_root)
    return {"schema": value["schema"], "status": value["status"], "run_id": value["run_id"], "fresh_run_nonce": value["fresh_run_nonce"]}


def _without_build(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("build", None)
    return result


def validate_aggregate(value: Any) -> None:
    require(type(value) is dict and set(value) == EXPECTED_AGGREGATE_KEYS, "aggregate root shape drift")
    require(value["schema"] == AGGREGATE_SCHEMA and value["status"] == AGGREGATE_STATUS and value["work_item"] == "COM-01" and value["leaf"] == "config-validate" and type(value["fresh_replays"]) is int and value["fresh_replays"] == 2, "aggregate identity/count drift")
    reports = value["reports"]
    require(type(reports) is list and len(reports) == 2, "aggregate report list drift")
    for item in reports:
        require(type(item) is dict and set(item) == {"path", "sha256", "run_id", "fresh_run_nonce", "candidate_binary_sha256"} and type(item["path"]) is str and bool(item["path"]) and "/" not in item["path"] and "\\" not in item["path"] and is_sha(item["sha256"]) and is_sha(item["run_id"]) and is_sha(item["fresh_run_nonce"]) and is_sha(item["candidate_binary_sha256"]), "aggregate report identity drift")
    require(type(value["binary_bit_reproducible"]) is bool and value["binary_bit_reproducible"] is False and value["binary_reproducibility"] == RAW_BINARY_POLICY and type(value["raw_binary_sha_equal"]) is bool and value["raw_binary_sha_equal"] == (reports[0]["candidate_binary_sha256"] == reports[1]["candidate_binary_sha256"]), "aggregate binary policy drift")
    _validate_candidate_static(value["candidate"])
    receipts = value["build_receipts"]
    require(type(receipts) is list and len(receipts) == 2, "aggregate build receipt list drift")
    for receipt in receipts:
        _validate_build(receipt, "aggregate build")
    _validate_toolchain(value["toolchain"])
    expected_pre = {role: value["toolchain"][role] for role in ("cargo", "rustc", "python", "uv", "linker")}
    require(all(receipt["tool_identities_pre"] == expected_pre for receipt in receipts), "aggregate/toolchain pre identity drift")
    _validate_upstream(value["upstream"])
    _validate_harness(value["harness"])
    _validate_fixture(value["fixture"])
    _validate_scenario(value["scenario"])
    require(type(value["expected"]) is dict and value["expected"] == EXPECTED_FACTS and all(type(value["expected"][key]) is type(EXPECTED_FACTS[key]) for key in EXPECTED_FACTS), "aggregate expected facts drift")
    require(type(value["exact"]) is dict and value["exact"] == EXPECTED_EXACT and all(type(item) is bool for item in value["exact"].values()) and value["exact"]["all"] is True, "aggregate exactness drift")
    require(type(value["blockers"]) is list and value["blockers"] == [] and type(value["acceptance"]) is bool and value["acceptance"] is False and value["artifact_policy"] == EXPECTED_ARTIFACT_POLICY, "aggregate blocker/policy drift")
    require(type(value["non_claims"]) is list and value["non_claims"] == list(NON_CLAIMS), "aggregate non-claims drift")


def _bundle_root(first_path: Path, second_path: Path, aggregate_path: Path) -> Path:
    paths = [path if path.is_absolute() else Path.cwd() / path for path in (first_path, second_path, aggregate_path)]
    require(len({path.parent for path in paths}) == 1, "bundle inputs must share one fixed output root")
    root = _validate_directory_root(paths[0].parent)
    require(all(path.parent == root and path.name for path in paths) and len({path.name for path in paths}) == 3, "bundle paths must be distinct direct children")
    return root


def verify_bundle(first_path: Path, second_path: Path, aggregate_path: Path, *, repo_root: Path = ROOT, upstream_root: Path | None = None) -> dict[str, Any]:
    root = _bundle_root(first_path, second_path, aggregate_path)
    first, first_sha = read_json(first_path, input_root=root)
    second, second_sha = read_json(second_path, input_root=root)
    validate_report(first, repo_root=repo_root, upstream_root=upstream_root)
    validate_report(second, repo_root=repo_root, upstream_root=upstream_root)
    require(first_sha != second_sha and first["run_id"] != second["run_id"] and first["fresh_run_nonce"] != second["fresh_run_nonce"], "fresh replay identities must be distinct")
    require(_without_build(first["candidate"]) == _without_build(second["candidate"]), "candidate static identity drift")
    for key in ("upstream", "harness", "toolchain", "fixture", "scenario", "expected", "exact"):
        require(first[key] == second[key], f"{key} drift between fresh replays")
    aggregate, aggregate_sha = read_json(aggregate_path, input_root=root)
    validate_aggregate(aggregate)
    require(aggregate["candidate"] == _without_build(first["candidate"]) == _without_build(second["candidate"]), "aggregate candidate static identity is not regenerated from both reports")
    require(aggregate["build_receipts"] == [first["candidate"]["build"], second["candidate"]["build"]], "aggregate build receipts are not regenerated from both reports")
    for key in ("upstream", "harness", "toolchain", "fixture", "scenario", "expected", "exact"):
        require(aggregate[key] == first[key] == second[key], f"aggregate {key} is not regenerated from both reports")
    require(aggregate["reports"][0]["path"] == Path(first_path).name and aggregate["reports"][1]["path"] == Path(second_path).name, "aggregate report path binding drift")
    require(aggregate["reports"][0]["sha256"] == first_sha and aggregate["reports"][1]["sha256"] == second_sha, "aggregate report hash binding drift")
    require(aggregate["reports"][0]["run_id"] == first["run_id"] and aggregate["reports"][1]["run_id"] == second["run_id"] and aggregate["reports"][0]["fresh_run_nonce"] == first["fresh_run_nonce"] and aggregate["reports"][1]["fresh_run_nonce"] == second["fresh_run_nonce"], "aggregate replay identity binding drift")
    require(aggregate["reports"][0]["candidate_binary_sha256"] == first["candidate"]["build"]["binary_post"]["sha256"] and aggregate["reports"][1]["candidate_binary_sha256"] == second["candidate"]["build"]["binary_post"]["sha256"], "aggregate binary binding drift")
    require(aggregate_sha not in {first_sha, second_sha}, "aggregate must be a distinct artifact")
    return {"schema": aggregate["schema"], "status": aggregate["status"], "fresh_replays": 2, "scenario": aggregate["scenario"]["id"]}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--aggregate", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--upstream-repo", type=Path)
    args = parser.parse_args()
    try:
        result = verify_bundle(args.first, args.second, args.aggregate, repo_root=args.repo_root, upstream_root=args.upstream_repo)
    except (OSError, ValueError, VerificationError, json.JSONDecodeError, subprocess.SubprocessError, TypeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
