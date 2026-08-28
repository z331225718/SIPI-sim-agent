"""Strict, mechanical aggregation for two PB matrix reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


MAX_FILE_BYTES = 16 * 1024 * 1024
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
EXPECTED_CASE_IDS = (
    "pb01_nrz_analytic_line", "pb01_nrz_tx_ffe", "pb01_nrz_rx_dfe",
    "pb01_pam4_analytic_line", "pb01_duo_binary_analytic_line", "pb01_nrz_ctle",
    "pb02_nrz_impulse", "pb02_pam4_impulse", "pb02_duo_binary_impulse",
    "pb02_impulse_tx_rx_equalization", "pb02_impulse_analytic_ctle",
    "pb02_impulse_jitter_bathtub_analysis",
)
PREP_PATHS = (
    "docs/baselines/pb-01-02-portable-matrix-inputs.v1.json",
    "tools/aggregate_pb_01_02_portable_matrix.py",
    "tools/run_pb_01_02_portable_matrix.py",
    "tools/test_verify_pb_01_02_portable_matrix.py",
    "tools/verify_pb_01_02_portable_matrix.py",
)
PB01_ARRAYS = ("chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h", "chnl_s", "tx_out_s", "ctle_out_s", "dfe_out_s", "chnl_p", "tx_out_p", "ctle_out_p", "dfe_out_p")
PB02_MEMBERS = ("channel_impulse_v_per_v.npy", "channel_output_v.npy", "ctle_output_v.npy", "rx_ffe_impulse_v_per_v.npy", "rx_filter_impulse_v_per_v.npy", "rx_input_v.npy", "rx_output_v.npy", "symbols_v.npy", "time_s.npy", "tx_channel_impulse_v_per_v.npy", "tx_waveform_v.npy")
PB01_ITEMS = ("chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h", "chnl_s", "tx_s", "ctle_s", "dfe_s", "tx_out_s", "ctle_out_s", "dfe_out_s", "chnl_p", "tx_out_p", "ctle_out_p", "dfe_out_p", "chnl_H", "tx_H", "ctle_H", "dfe_H", "tx_out_H", "ctle_out_H", "dfe_out_H", "tx_out")
REPORT_KEYS = {"schema", "version", "run_id", "run_nonce", "preparation", "corpus", "source", "toolchain", "build", "oracle_runtime", "custody", "cases", "claims"}
CLAIM_KEYS = {"global_branch_parity", "whole_payload_parity", "release_acceptance", "numeric_parity"}


class AggregateError(RuntimeError):
    pass


def _json_loads(payload: bytes | str) -> Any:
    def reject_constant(value: str) -> Any:
        raise AggregateError(f"non-finite JSON constant rejected: {value}")

    value = json.loads(payload, parse_constant=reject_constant)
    nodes = 0

    def close(item: Any, depth: int = 0) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > 1_000_000 or depth > 128:
            raise AggregateError("JSON structure budget exceeded")
        if item is None or type(item) in (bool, int, str):
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise AggregateError("non-finite JSON number rejected")
            return
        if type(item) is list:
            for child in item:
                close(child, depth + 1)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                close(child, depth + 1)
            return
        raise AggregateError("unsupported JSON value type")

    close(value)
    return value


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise AggregateError("path must be a non-empty string")
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or windows.root or "\\" in value:
        raise AggregateError("absolute/anchored path rejected")
    if any(part in ("", ".", "..") for part in posix.parts):
        raise AggregateError("non-canonical relative path rejected")
    return posix.as_posix()


def secure_read(root: Path, relative: str) -> tuple[bytes, dict[str, Any]]:
    original = root.absolute()
    for component in (*reversed(original.parents), original):
        component_info = os.lstat(component)
        if stat.S_ISLNK(component_info.st_mode) or getattr(component_info, "st_file_attributes", 0) & 0x400:
            raise AggregateError("evidence root has a link/reparse ancestor")
    original_info = os.lstat(original)
    if not stat.S_ISDIR(original_info.st_mode) or stat.S_ISLNK(original_info.st_mode) or getattr(original_info, "st_file_attributes", 0) & 0x400:
        raise AggregateError("evidence root is not a plain directory")
    root = original.resolve(strict=True)
    relative = _safe_relative(relative)
    root_info = os.lstat(root)
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode) or getattr(root_info, "st_file_attributes", 0) & 0x400:
        raise AggregateError("evidence root is not a plain directory")
    target = root
    for part in PurePosixPath(relative).parts:
        target /= part
        info = os.lstat(target)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise AggregateError("link/reparse evidence component rejected")
    resolved = target.resolve(strict=True)
    if root not in resolved.parents:
        raise AggregateError("evidence path escaped root")
    pre = os.lstat(target)
    if not stat.S_ISREG(pre.st_mode) or int(pre.st_nlink) != 1 or pre.st_size > MAX_FILE_BYTES:
        raise AggregateError("evidence must be bounded regular/nonlink/nlink1")
    identity = lambda item: (int(item.st_dev), int(item.st_ino), int(item.st_size), int(item.st_mtime_ns))
    fd = os.open(target, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(fd)
        if identity(opened) != identity(pre) or int(opened.st_nlink) != 1:
            raise AggregateError("evidence changed before read")
        chunks, total = [], 0
        while True:
            chunk = os.read(fd, min(65536, MAX_FILE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise AggregateError("evidence exceeds read budget")
        after_fd = os.fstat(fd)
    finally:
        os.close(fd)
    post = os.lstat(target)
    if identity(pre) != identity(after_fd) or identity(pre) != identity(post) or int(post.st_nlink) != 1:
        raise AggregateError("evidence changed during read")
    payload = b"".join(chunks)
    return payload, {"path": relative, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload), "regular": True, "nonlink": True, "nlink": 1, "single_handle_read": True}


def _exact_mapping(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise AggregateError(f"{label} schema is not exact")
    return value


def _source_identity(value: Any, label: str) -> dict[str, Any]:
    value = _exact_mapping(value, {"commit", "tree", "archive_sha256", "inventory_pre_sha256", "inventory_post_sha256", "inventory_equal"}, label)
    if not HEX40.fullmatch(value["commit"] or "") or not HEX40.fullmatch(value["tree"] or "") or not all(HEX64.fullmatch(value[key] or "") for key in ("archive_sha256", "inventory_pre_sha256", "inventory_post_sha256")):
        raise AggregateError(f"{label} identity invalid")
    if value["inventory_equal"] is not True or value["inventory_pre_sha256"] != value["inventory_post_sha256"]:
        raise AggregateError(f"{label} source inventory drift")
    return value


def _metadata_summary(value: Any) -> dict[str, Any]:
    value = _exact_mapping(value, {"canonical_sha256", "fields"}, "metadata summary")
    if not HEX64.fullmatch(value["canonical_sha256"] or "") or type(value["fields"]) is not dict:
        raise AggregateError("metadata summary invalid")
    for path, field in value["fields"].items():
        if type(path) is not str or type(field) is not dict or type(field.get("type")) is not str:
            raise AggregateError("metadata field summary invalid")
        kind = field["type"]
        expected = {"type", "keys"} if kind == "object" else {"type", "length", "sha256"} if kind == "array" else {"type", "value"}
        if set(field) != expected or kind not in {"object", "array", "null", "bool", "number", "string"}:
            raise AggregateError("metadata field schema invalid")
        if kind == "object" and (type(field["keys"]) is not list or any(type(item) is not str for item in field["keys"])):
            raise AggregateError("metadata object keys invalid")
        if kind == "array" and (type(field["length"]) is not int or field["length"] < 0 or not HEX64.fullmatch(field["sha256"] or "")):
            raise AggregateError("metadata array summary invalid")
        if kind == "null" and field["value"] is not None or kind == "bool" and type(field["value"]) is not bool or kind == "number" and type(field["value"]) not in (int, float) or kind == "string" and type(field["value"]) is not str:
            raise AggregateError("metadata scalar type invalid")
    return value


def _npz_summary(value: Any) -> dict[str, Any]:
    value = _exact_mapping(value, {"bytes", "sha256", "uncompressed_bytes", "logical_members", "logical_sha256"}, "NPZ summary")
    if type(value["bytes"]) is not int or type(value["uncompressed_bytes"]) is not int or not HEX64.fullmatch(value["sha256"] or "") or not HEX64.fullmatch(value["logical_sha256"] or "") or type(value["logical_members"]) is not dict or tuple(sorted(value["logical_members"])) != PB02_MEMBERS:
        raise AggregateError("NPZ summary header invalid")
    for member in value["logical_members"].values():
        member = _exact_mapping(member, {"dtype", "shape", "fortran_order", "count", "f64_sha256"}, "NPY summary")
        if member["dtype"] not in {"<f8", "|f8", ">f8"} or type(member["shape"]) is not list or any(type(item) is not int or item < 0 for item in member["shape"]) or type(member["fortran_order"]) is not bool or type(member["count"]) is not int or not HEX64.fullmatch(member["f64_sha256"] or ""):
            raise AggregateError("NPY summary invalid")
    return value


def _secure_fact(value: Any, label: str, *, exclusive: bool = False) -> dict[str, Any]:
    base_keys = {"path", "sha256", "bytes", "regular", "nonlink", "nlink", "single_handle_read", "pre_identity", "post_identity"}
    value = _exact_mapping(value, base_keys | ({"exclusive_create", "pre_absent", "readback_equal"} if exclusive else set()), label)
    _safe_relative(value["path"])
    if not HEX64.fullmatch(value["sha256"] or "") or type(value["bytes"]) is not int or value["bytes"] < 0:
        raise AggregateError(f"{label} digest/length invalid")
    if value["regular"] is not True or value["nonlink"] is not True or value["nlink"] != 1 or value["single_handle_read"] is not True:
        raise AggregateError(f"{label} custody flags invalid")
    if type(value["pre_identity"]) is not list or type(value["post_identity"]) is not list or value["pre_identity"] != value["post_identity"] or len(value["pre_identity"]) != 4 or any(type(item) is not int for item in value["pre_identity"]):
        raise AggregateError(f"{label} pre/post identity invalid")
    if exclusive and (value["exclusive_create"] is not True or value["pre_absent"] is not True or value["readback_equal"] is not True):
        raise AggregateError(f"{label} exclusive output flags invalid")
    return value


def _cargo_binary_fact(value: Any) -> dict[str, Any]:
    keys = {"path", "sha256", "bytes", "regular", "nonlink", "nlink", "single_handle_read", "pre_identity", "post_identity"}
    value = _exact_mapping(value, keys, "cargo binary source")
    _safe_relative(value["path"])
    if value["regular"] is not True or value["nonlink"] is not True or type(value["nlink"]) is not int or value["nlink"] < 1 or value["single_handle_read"] is not True or value["pre_identity"] != value["post_identity"] or not HEX64.fullmatch(value["sha256"] or ""):
        raise AggregateError("cargo binary source custody invalid")
    return value


def _pb01_rows(value: Any) -> list[dict[str, Any]]:
    if type(value) is not list:
        raise AggregateError("PB-01 rows must be a list")
    rows: list[dict[str, Any]] = []
    names: list[str] = []
    for item in value:
        row = _exact_mapping(item, {"name", "length", "max_abs", "scale", "tolerance", "passed"}, "PB-01 row")
        if type(row["name"]) is not str or row["name"] not in PB01_ARRAYS or row["name"] in names:
            raise AggregateError("PB-01 row name is not unique/in the closed set")
        if type(row["length"]) is not int or row["length"] <= 0:
            raise AggregateError("PB-01 row length must be a positive integer")
        if any(type(row[key]) not in (int, float) or not math.isfinite(row[key]) for key in ("max_abs", "scale", "tolerance")):
            raise AggregateError("PB-01 row numeric fields must be finite numbers")
        if row["max_abs"] < 0 or row["scale"] < 1:
            raise AggregateError("PB-01 row numeric range invalid")
        expected_tolerance = 1e-7 + 1e-6 * row["scale"]
        if row["tolerance"] != expected_tolerance or type(row["passed"]) is not bool or row["passed"] != (row["max_abs"] <= row["tolerance"]):
            raise AggregateError("PB-01 row tolerance/passed gate invalid")
        names.append(row["name"])
        rows.append(row)
    expected_prefix = list(PB01_ARRAYS[: len(names)])
    if names != expected_prefix:
        raise AggregateError("PB-01 rows are not in the canonical closed-set order")
    return rows


def validate_report(value: Any) -> dict[str, Any]:
    report = _exact_mapping(value, REPORT_KEYS, "report")
    if report["schema"] != "sipi.pb-01-02-portable-matrix-report.v2" or type(report["version"]) is not int or report["version"] != 2:
        raise AggregateError("report schema/version invalid")
    if type(report["run_id"]) is not str or not report["run_id"] or not HEX64.fullmatch(report["run_nonce"] or ""):
        raise AggregateError("run identity invalid")
    prep = _exact_mapping(report["preparation"], {"commit", "tree", "parent", "changed_paths", "files"}, "preparation")
    if not all(HEX40.fullmatch(prep[key] or "") for key in ("commit", "tree", "parent")):
        raise AggregateError("preparation Git identity invalid")
    if type(prep["changed_paths"]) is not list or tuple(prep["changed_paths"]) != PREP_PATHS or type(prep["files"]) is not dict or set(prep["files"]) != set(PREP_PATHS):
        raise AggregateError("preparation file binding invalid")
    for path, fact in prep["files"].items():
        _safe_relative(path)
        fact = _exact_mapping(fact, {"blob", "sha256", "bytes", "live_pre", "live_post", "live_equal"}, "preparation file")
        if not HEX40.fullmatch(fact["blob"] or "") or not HEX64.fullmatch(fact["sha256"] or "") or type(fact["bytes"]) is not int or fact["live_equal"] is not True:
            raise AggregateError("preparation file binding invalid")
        pre, post = _secure_fact(fact["live_pre"], "preparation live_pre"), _secure_fact(fact["live_post"], "preparation live_post")
        if pre != post or pre["sha256"] != fact["sha256"] or pre["bytes"] != fact["bytes"] or pre["path"] != path:
            raise AggregateError("preparation live/raw Git cross-binding invalid")
    corpus = _exact_mapping(report["corpus"], {"path", "blob", "sha256", "bytes"}, "corpus")
    _safe_relative(corpus["path"])
    if not HEX40.fullmatch(corpus["blob"] or "") or not HEX64.fullmatch(corpus["sha256"] or "") or type(corpus["bytes"]) is not int or corpus["bytes"] < 0:
        raise AggregateError("corpus binding invalid")
    source = _exact_mapping(report["source"], {"candidate", "upstream"}, "source")
    candidate_source = _source_identity(source["candidate"], "candidate source")
    upstream_source = _source_identity(source["upstream"], "upstream source")
    if candidate_source["commit"] != prep["commit"] or candidate_source["tree"] != prep["tree"]:
        raise AggregateError("candidate source is not the preparation commit/tree")
    if (upstream_source["commit"], upstream_source["tree"]) != (UPSTREAM_COMMIT, UPSTREAM_TREE):
        raise AggregateError("upstream source is not the pinned commit/tree")
    toolchain = _exact_mapping(report["toolchain"], {"cargo", "rustc", "uv", "link"}, "toolchain")
    for role, identity in toolchain.items():
        identity = _exact_mapping(identity, {"role", "executable", "file_sha256", "version_sha256", "version_exit", "path_redacted", "file_custody_pre", "file_custody_post", "file_custody_equal"}, f"toolchain {role}")
        if identity["role"] != role or type(identity["executable"]) is not str or "/" in identity["executable"] or "\\" in identity["executable"]:
            raise AggregateError("toolchain role/path invalid")
        if not HEX64.fullmatch(identity["file_sha256"] or "") or not HEX64.fullmatch(identity["version_sha256"] or ""):
            raise AggregateError("toolchain hash invalid")
        if type(identity["version_exit"]) is not int or identity["version_exit"] != 0 or identity["path_redacted"] is not True:
            raise AggregateError("toolchain provenance invalid")
        custody_fact = _secure_fact(identity["file_custody_pre"], f"toolchain {role} executable pre")
        custody_post = _secure_fact(identity["file_custody_post"], f"toolchain {role} executable post")
        if identity["file_custody_equal"] is not True or custody_fact != custody_post or custody_fact["sha256"] != identity["file_sha256"] or Path(custody_fact["path"]).name != identity["executable"]:
            raise AggregateError("toolchain executable custody/hash mismatch")
    build = _exact_mapping(report["build"], {"process", "cargo_binary_source", "binary", "env"}, "build")
    _cargo_binary_fact(build["cargo_binary_source"])
    build_process = _exact_mapping(build["process"], {"exit_code", "stdout", "stderr"}, "build process")
    if type(build_process["exit_code"]) is not int or build_process["exit_code"] != 0:
        raise AggregateError("build did not exit zero")
    _secure_fact(build_process["stdout"], "build stdout", exclusive=True); _secure_fact(build_process["stderr"], "build stderr", exclusive=True)
    binary = _exact_mapping(build["binary"], {"pre", "post", "equal"}, "build binary")
    binary_pre = _secure_fact(binary["pre"], "binary pre", exclusive=True)
    binary_post = _secure_fact(binary["post"], "binary post")
    if binary["equal"] is not True or {key: value for key, value in binary_pre.items() if key not in {"exclusive_create", "pre_absent", "readback_equal"}} != binary_post:
        raise AggregateError("build binary pre/post drift")
    if build["env"] != {"rustc_explicit": True, "rustc_wrappers_cleared": True, "cargo_target_external": True, "cargo_offline": True, "path_closed": True, "cargo_home_explicit": True, "cargo_config_and_flags_cleared": True, "cargo_cache_lock_bound": True}:
        raise AggregateError("build environment closure invalid")
    runtime = _exact_mapping(report["oracle_runtime"], {"process", "modules", "clean_archive_or_venv_only", "host_pythonpath_absent", "host_virtual_env_absent", "uv_offline_frozen_no_config", "uv_link_mode_copy", "uv_cache_explicit_lock_bound", "host_uv_flags_cleared", "oracle_work_archive_sha256", "oracle_work_started_clean"}, "oracle runtime")
    if any(runtime[key] is not True for key in ("clean_archive_or_venv_only", "host_pythonpath_absent", "host_virtual_env_absent", "uv_offline_frozen_no_config", "uv_link_mode_copy", "uv_cache_explicit_lock_bound", "host_uv_flags_cleared")):
        raise AggregateError("oracle runtime environment closure invalid")
    if runtime["oracle_work_started_clean"] is not True or runtime["oracle_work_archive_sha256"] != source["upstream"]["archive_sha256"]:
        raise AggregateError("oracle work archive is not the pinned pristine upstream archive")
    runtime_process = _exact_mapping(runtime["process"], {"exit_code", "stdout", "stderr"}, "oracle runtime process")
    if type(runtime_process["exit_code"]) is not int or runtime_process["exit_code"] != 0:
        raise AggregateError("oracle runtime probe failed")
    _secure_fact(runtime_process["stdout"], "oracle runtime stdout", exclusive=True); _secure_fact(runtime_process["stderr"], "oracle runtime stderr", exclusive=True)
    modules = _exact_mapping(runtime["modules"], {"pybert", "numpy", "scipy"}, "oracle modules")
    for name, module in modules.items():
        module = _exact_mapping(module, {"owner", "relative_path", "version", "file"}, "oracle module")
        if module["owner"] not in ({"archive", "venv"} if name == "pybert" else {"venv"}) or _safe_relative(module["relative_path"]) != module["relative_path"] or type(module["version"]) is not str or not module["version"]:
            raise AggregateError("oracle module containment invalid")
        fact = _secure_fact(module["file"], "oracle module file")
        if fact["path"] != module["relative_path"]:
            raise AggregateError("oracle module path/fact drift")
    custody = _exact_mapping(report["custody"], {"archive_materialization", "inputs", "artifacts", "output"}, "custody")
    if any(type(custody[key]) is not list for key in ("archive_materialization", "inputs", "artifacts")) or type(custody["output"]) is not dict:
        raise AggregateError("custody field type invalid")
    if len(custody["archive_materialization"]) != 3:
        raise AggregateError("custody needs candidate, pristine-upstream, and oracle-work archive facts")
    archive_roles = {"candidate", "upstream_pristine", "upstream_oracle"}
    seen_archive_roles: set[str] = set()
    for binding in custody["archive_materialization"]:
        binding = _exact_mapping(binding, {"role", "archive_sha256", "fact"}, "archive materialization")
        if binding["role"] not in archive_roles or binding["role"] in seen_archive_roles or not HEX64.fullmatch(binding["archive_sha256"] or ""):
            raise AggregateError("archive materialization role/hash invalid")
        seen_archive_roles.add(binding["role"])
        fact = _secure_fact(binding["fact"], "archive materialization")
        if fact["sha256"] != binding["archive_sha256"]:
            raise AggregateError("archive materialization fact/hash mismatch")
        expected = candidate_source["archive_sha256"] if binding["role"] == "candidate" else upstream_source["archive_sha256"]
        if binding["archive_sha256"] != expected:
            raise AggregateError("archive materialization source cross-binding invalid")
    if seen_archive_roles != archive_roles:
        raise AggregateError("archive materialization roles incomplete")
    for binding in custody["inputs"]:
        if type(binding) is not dict or set(binding) not in ({"lane", "pre", "post", "equal"}, {"case_id", "pre", "post", "equal"}):
            raise AggregateError("input custody schema invalid")
        if "lane" in binding and binding["lane"] not in {"PB-01", "PB-02"}:
            raise AggregateError("input lane invalid")
        if "case_id" in binding and binding["case_id"] not in EXPECTED_CASE_IDS:
            raise AggregateError("input case ID invalid")
        pre = _secure_fact(binding["pre"], "input pre", exclusive="case_id" in binding)
        post = _secure_fact(binding["post"], "input post")
        comparable_pre = {key: value for key, value in pre.items() if key not in {"exclusive_create", "pre_absent", "readback_equal"}}
        if binding["equal"] is not True or comparable_pre != post:
            raise AggregateError("input pre/post drift")
    for artifact in custody["artifacts"]:
        if type(artifact) is not dict or artifact.get("present") is not True:
            if type(artifact) is not dict or set(artifact) not in ({"path", "present", "role", "kind", "case_id"},) or artifact.get("present") is not False:
                raise AggregateError("artifact custody schema invalid")
            _safe_relative(artifact["path"])
            continue
        extra = {key: artifact[key] for key in ("role", "kind", "case_id") if key in artifact}
        base = {key: value for key, value in artifact.items() if key not in extra and key not in {"present", "pre_absent"}}
        _secure_fact(base, "artifact")
        if artifact.get("pre_absent") is not True or set(extra) != {"role", "kind", "case_id"} or extra["case_id"] not in EXPECTED_CASE_IDS or extra["role"] not in {"candidate", "oracle"}:
            raise AggregateError("artifact pre-absence/role binding invalid")
    if custody["output"] != {"fresh_root": True, "exclusive_report": True}:
        raise AggregateError("report output custody invalid")
    if len(custody["inputs"]) != 14 or [item.get("lane") for item in custody["inputs"][:2]] != ["PB-01", "PB-02"] or tuple(item.get("case_id") for item in custody["inputs"][2:]) != EXPECTED_CASE_IDS:
        raise AggregateError("input custody is not the two bases plus closed 12-case set")
    expected_artifacts = {(case_id, role, kind) for case_id in EXPECTED_CASE_IDS[:6] for role in ("candidate", "oracle") for kind in ("legacy_result",)}
    expected_artifacts |= {(case_id, role, kind) for case_id in EXPECTED_CASE_IDS[6:] for role in ("candidate", "oracle") for kind in ("meta", "arrays")}
    actual_artifacts = [(item.get("case_id"), item.get("role"), item.get("kind")) for item in custody["artifacts"]]
    if len(actual_artifacts) != len(expected_artifacts) or set(actual_artifacts) != expected_artifacts:
        raise AggregateError("artifact custody is not the exact per-case closed set")
    claims = _exact_mapping(report["claims"], CLAIM_KEYS, "claims")
    if any(type(value) is not bool or value for value in claims.values()):
        raise AggregateError("all scoped report claims, including numeric parity, must be false")
    if type(report["cases"]) is not list:
        raise AggregateError("cases must be a list")
    ids: list[str] = []
    for case in report["cases"]:
        case = _exact_mapping(case, {"id", "status", "blockers", "comparison"}, "case")
        if type(case["id"]) is not str or type(case["status"]) is not str or type(case["blockers"]) is not list or type(case["comparison"]) is not dict:
            raise AggregateError("case field type invalid")
        if any(type(item) is not str for item in case["blockers"]):
            raise AggregateError("case blockers invalid")
        comparison = case["comparison"]
        if case["id"].startswith("pb01_"):
            comparison = _exact_mapping(comparison, {"kind", "class_pickle_covered_by_matrix", "candidate_schema", "oracle_schema", "rows", "blockers", "candidate_process", "oracle_process"}, "PB-01 comparison")
            if comparison["kind"] != "pb01_selected_numeric_arrays" or comparison["class_pickle_covered_by_matrix"] is not False or type(comparison["rows"]) is not list or type(comparison["blockers"]) is not list:
                raise AggregateError("PB-01 comparison policy invalid")
            rows = _pb01_rows(comparison["rows"])
            if case["status"] == "passed" and (tuple(row["name"] for row in rows) != PB01_ARRAYS or not all(row["passed"] for row in rows) or comparison["blockers"] or case["blockers"]):
                raise AggregateError("PB-01 passed status lacks the exact selected-row proof")
            if case["status"] == "passed":
                candidate_schema = _exact_mapping(comparison["candidate_schema"], {"kind", "schema", "item_names", "array_keys"}, "PB-01 candidate schema")
                oracle_schema = _exact_mapping(comparison["oracle_schema"], {"kind"}, "PB-01 oracle schema")
                if candidate_schema != {"kind": "python_pickle_dict", "schema": "sipi.pybert_data.v1", "item_names": list(PB01_ITEMS), "array_keys": sorted(PB01_ITEMS)} or oracle_schema != {"kind": "PyBertData_class_pickle"}:
                    raise AggregateError("PB-01 passed artifact schema is not exact")
            if sorted(set(comparison["blockers"])) != case["blockers"]:
                raise AggregateError("PB-01 blocker projection drift")
        else:
            comparison = _exact_mapping(comparison, {"kind", "candidate", "oracle", "candidate_process", "oracle_process"}, "PB-02 comparison")
            if comparison["kind"] != "pb02_complete_meta_and_logical_npz" or any(item is not None and type(item) is not dict for item in (comparison["candidate"], comparison["oracle"])):
                raise AggregateError("PB-02 comparison policy invalid")
            for observation in (comparison["candidate"], comparison["oracle"]):
                if observation is not None:
                    observation = _exact_mapping(observation, {"meta", "arrays"}, "PB-02 observation")
                    _metadata_summary(observation["meta"]); _npz_summary(observation["arrays"])
        for role in ("candidate_process", "oracle_process"):
            process = _exact_mapping(comparison[role], {"exit_code", "stdout", "stderr"}, "case process")
            if type(process["exit_code"]) is not int:
                raise AggregateError("case process exit type invalid")
            _secure_fact(process["stdout"], "process stdout", exclusive=True)
            _secure_fact(process["stderr"], "process stderr", exclusive=True)
        exits_zero = comparison["candidate_process"]["exit_code"] == comparison["oracle_process"]["exit_code"] == 0
        if (case["status"] == "passed") != (exits_zero and not case["blockers"]):
            raise AggregateError("case status does not match exits/blockers")
        if case["id"].startswith("pb02_") and case["status"] == "passed":
            if comparison["candidate"] != comparison["oracle"] or comparison["candidate"] is None:
                raise AggregateError("PB-02 passed status lacks complete equal observations")
            for role in ("candidate", "oracle"):
                arrays = comparison[role].get("arrays")
                meta = comparison[role].get("meta")
                if type(arrays) is not dict or tuple(sorted(arrays.get("logical_members", {}))) != PB02_MEMBERS or type(meta) is not dict or not HEX64.fullmatch(meta.get("canonical_sha256", "")):
                    raise AggregateError("PB-02 passed payload schema is not exact")
                artifact = next(item for item in custody["artifacts"] if item.get("case_id") == case["id"] and item.get("role") == role and item.get("kind") == "arrays")
                if artifact.get("sha256") != arrays.get("sha256") or artifact.get("bytes") != arrays.get("bytes"):
                    raise AggregateError("PB-02 arrays observation/artifact cross-binding drift")
        ids.append(case["id"])
    if tuple(ids) != EXPECTED_CASE_IDS or len(ids) != len(set(ids)):
        raise AggregateError("case IDs are not the unique closed matrix")
    return report


def aggregate_documents(first: Any, second: Any) -> dict[str, Any]:
    first, second = validate_report(first), validate_report(second)
    if first["run_id"] == second["run_id"] or first["run_nonce"] == second["run_nonce"]:
        raise AggregateError("fresh reports require distinct run IDs and nonces")
    for key in ("preparation", "corpus", "source", "toolchain"):
        if canonical(first[key]) != canonical(second[key]):
            raise AggregateError(f"report {key} drift")
    def module_observation(report: dict[str, Any]) -> dict[str, Any]:
        return {name: {"owner": item["owner"], "relative_path": item["relative_path"], "version": item["version"], "sha256": item["file"]["sha256"], "bytes": item["file"]["bytes"]} for name, item in report["oracle_runtime"]["modules"].items()}
    if canonical(module_observation(first)) != canonical(module_observation(second)):
        raise AggregateError("oracle module identity drift")
    cases: list[dict[str, Any]] = []
    for left, right in zip(first["cases"], second["cases"], strict=True):
        def observation(case: dict[str, Any]) -> dict[str, Any]:
            comparison = {key: value for key, value in case["comparison"].items() if key not in {"candidate_process", "oracle_process"}}
            return {"id": case["id"], "status": case["status"], "blockers": case["blockers"], "comparison": comparison}
        equal = canonical(observation(left)) == canonical(observation(right))
        passed = left["status"] == "passed" and right["status"] == "passed"
        cases.append({"id": left["id"], "first_status": left["status"], "second_status": right["status"], "observation_equal": equal, "passed_scoped": passed and equal})
    all_passed = all(case["passed_scoped"] for case in cases)
    return {
        "schema": "sipi.pb-01-02-portable-matrix-aggregate.v2",
        "version": 2,
        "status": "passed_scoped" if all_passed else "scoped_matrix_blocked",
        "runs": [{"run_id": first["run_id"], "nonce": first["run_nonce"]}, {"run_id": second["run_id"], "nonce": second["run_nonce"]}],
        "preparation": first["preparation"], "corpus": first["corpus"], "source": first["source"], "toolchain": first["toolchain"],
        "cases": cases,
        "claims": {key: False for key in sorted(CLAIM_KEYS)},
    }


def _load_json(root: Path, relative: str) -> tuple[dict[str, Any], dict[str, Any]]:
    payload, fact = secure_read(root, relative)
    try:
        value = _json_loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AggregateError(f"invalid report JSON: {error}") from error
    if type(value) is not dict:
        raise AggregateError("report must be a JSON object")
    return value, fact


def _exclusive_json(root: Path, relative: str, value: dict[str, Any]) -> None:
    original = root.absolute()
    for component in (*reversed(original.parents), original):
        component_info = os.lstat(component)
        if stat.S_ISLNK(component_info.st_mode) or getattr(component_info, "st_file_attributes", 0) & 0x400:
            raise AggregateError("output root has a link/reparse ancestor")
    info = os.lstat(original)
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise AggregateError("output root must be a plain directory")
    root = original.resolve(strict=True)
    relative = _safe_relative(relative)
    target = root / relative
    if target.parent != root or os.path.lexists(target):
        raise AggregateError("aggregate output must be a new direct child of the output root")
    payload = json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0), 0o600)
    opened = os.fstat(fd)
    try:
        view = memoryview(payload)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise AggregateError("short aggregate write")
            view = view[count:]
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        current = os.lstat(target) if os.path.lexists(target) else None
        if current is not None and (current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino):
            os.unlink(target)
        raise
    else:
        os.close(fd)
    try:
        readback, _ = secure_read(root, relative)
        if readback != payload:
            raise AggregateError("aggregate readback mismatch")
    except BaseException:
        current = os.lstat(target) if os.path.lexists(target) else None
        if current is not None and (current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino):
            os.unlink(target)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--first", required=True)
    parser.add_argument("--second", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--output", default="aggregate.json")
    args = parser.parse_args()
    try:
        first, first_fact = _load_json(args.evidence_root, args.first)
        second, second_fact = _load_json(args.evidence_root, args.second)
        if first_fact["path"] == second_fact["path"] or first_fact["sha256"] == second_fact["sha256"]:
            raise AggregateError("fresh report files and full hashes must be distinct")
        result = aggregate_documents(first, second)
        result["report_files"] = [first_fact, second_fact]
        _exclusive_json(args.output_root, args.output, result)
    except AggregateError as error:
        print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"valid": True, "status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
