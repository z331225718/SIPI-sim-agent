"""Fail-closed schema and binding verifier for COM v3 exact-profile evidence."""
from __future__ import annotations
import hashlib
import json
import re
import argparse
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pb_03_replay_common import compare_windows_pe_custody, validate_windows_pe_replay_custody

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/com-erl-exact-profile-replay-v3.manifest.json"
SCHEMA = "sipi.com.erl-only.exact-profile-replay.v3.manifest"
FIXTURE_SHA256 = "7a59b41a385a95752d2d1159aab7772a10f7bd2c07e5122d770493151853c7a3"
FIXTURE_BYTES = 830969
FIXTURE_ROWS = 8001
OUTER_KEYS = {"samples_per_ui", "levels", "bin_size", "spec_ber", "rl_norm_test"}
OUTER_VALUES = {"samples_per_ui": 32, "levels": 4, "bin_size": 1.0e-5, "spec_ber": 1.0e-5, "rl_norm_test": True}
CROSSWALK = {
    "runtime_fields": {
        "samples_per_ui": "materialized.parameters.samples_per_ui",
        "levels": "materialized.parameters.levels",
        "bin_size": "materialized.options.BinSize",
        "spec_ber": "materialized.parameters.specBER",
        "rl_norm_test": "materialized.options.RL_norm_test",
        "baud_hz": "materialized.parameters.fb",
        "sample_dt_s": "materialized.parameters.sample_dt",
        "gate_rho_x": "materialized.parameters.rho_x",
        "gate_grr": "materialized.parameters.Grr",
        "gate_beta_x_db_per_s": "materialized.parameters.beta_x",
    },
    "raw_source_fields_not_runtime_controls": ["Z0", "T_r_filter_type", "T_r_meas_point", "T_k", "TDR_duration", "Tukey_Window"],
}

class VerificationError(ValueError):
    pass

def canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def runtime_projection(controls: dict[str, Any]) -> dict[str, Any]:
    fields = tuple(CROSSWALK["runtime_fields"])
    outer = controls.get("outer", {})
    profile = controls.get("tdr_profile", {})
    return {"outer": {key: outer.get(key) for key in OUTER_VALUES}, "tdr_profile": {key: profile.get(key) for key in fields if key in profile}}


def verify_stage(value: Any) -> None:
    if set(value) != {"count", "sha256"} or isinstance(value.get("count"), bool) or not isinstance(value.get("count"), int) or value["count"] <= 0 or not re.fullmatch(r"[0-9a-f]{64}", value.get("sha256", "")):
        raise VerificationError("stage schema")


def verify_library_inventory(value: Any) -> None:
    if set(value) != {"count", "combined_sha256", "files"} or not isinstance(value.get("count"), int) or value["count"] <= 0 or not re.fullmatch(r"[0-9a-f]{64}", value.get("combined_sha256", "")) or not isinstance(value.get("files"), list) or len(value["files"]) != value["count"]:
        raise VerificationError("library inventory schema")
    for item in value["files"]:
        if set(item) != {"path", "sha256"} or not isinstance(item["path"], str) or PurePosixPath(item["path"]).is_absolute() or PureWindowsPath(item["path"]).is_absolute() or not item["path"].lower().endswith(".lib") or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise VerificationError("library inventory entry")
    if canonical_sha(value["files"]) != value["combined_sha256"]:
        raise VerificationError("library inventory digest")


def verify_key_libraries(value: Any) -> None:
    if not isinstance(value, dict):
        raise VerificationError("key library schema")
    for item in value.values():
        if set(item) != {"present", "sha256", "path"} or not isinstance(item.get("present"), bool):
            raise VerificationError("key library entry")
        if item["present"]:
            if not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")) or not isinstance(item.get("path"), str) or PurePosixPath(item["path"]).is_absolute() or PureWindowsPath(item["path"]).is_absolute():
                raise VerificationError("key library identity")
        elif item.get("sha256") is not None or item.get("path") is not None:
            raise VerificationError("missing key library identity")


def candidate_source_projection(candidate: dict[str, Any]) -> dict[str, Any]:
    return {key: candidate.get(key) for key in ("commit", "tree", "archive_sha256", "materialization", "runtime_executed", "cargo_lock_sha256")}


def metric_equal(field: str, left: Any, right: Any) -> bool:
    if field == "ERL_phase_index":
        return left == right
    if left in {"inf", "-inf", "nan"} or right in {"inf", "-inf", "nan"}:
        return left == right
    return isinstance(left, (int, float)) and isinstance(right, (int, float)) and math.isclose(float(left), float(right), rel_tol=1.0e-12, abs_tol=1.0e-12)

def path_free(value: Any) -> bool:
    if isinstance(value, dict):
        return all(path_free(k) and path_free(v) for k, v in value.items())
    if isinstance(value, list):
        return all(path_free(v) for v in value)
    return not isinstance(value, str) or (not PurePosixPath(value).is_absolute() and not PureWindowsPath(value).is_absolute())

def verify_manifest(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema") != SCHEMA:
        raise VerificationError("manifest schema")
    candidate = document.get("candidate", {})
    if candidate != {"commit": "955835369c28aacb3f49bd0cf95f3660587739d8", "tree": "fbb415e5582ccf3ee70e4d0d472f1fc6856e0e26", "archive_sha256": "005e06d1ab680a7ddf41a2110c5e8ea9e44b020e04c5d4369a78f05c15ea79f0"}:
        raise VerificationError("candidate identity")
    upstream = document.get("upstream", {})
    if upstream.get("commit") != "5272ffe74702cd585054d975559b06f8afae7b6e" or upstream.get("tree") != "7094ab6e84989b218730c52432c70da10261f8ea" or upstream.get("archive_sha256") != "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf":
        raise VerificationError("upstream identity")
    runner = document.get("runner", {})
    if runner.get("path") != "tools/run_com_erl_exact_profile_replay_v3.py" or runner.get("helper_path") != "tools/com_erl_exact_profile_replay_v3_support.py" or runner.get("sha256") != hashlib.sha256((ROOT / runner["path"]).read_bytes()).hexdigest() or runner.get("helper_sha256") != hashlib.sha256((ROOT / runner["helper_path"]).read_bytes()).hexdigest():
        raise VerificationError("runner/helper identity")
    audit = document.get("audit", {})
    if audit.get("path") != "docs/baselines/audits/2026-08-24-com-erl-exact-profile-replay-v3-linker-prep.md" or audit.get("sha256") != hashlib.sha256((ROOT / audit["path"]).read_bytes()).hexdigest():
        raise VerificationError("audit identity")
    verification_tools = document.get("verification_tools", {})
    for role in ("aggregator", "verifier", "tests"):
        item = verification_tools.get(role, {})
        if set(item) != {"path", "sha256"} or not item["path"].startswith("tools/") or item["sha256"] != hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest():
            raise VerificationError("verification tool identity")
    harness = document.get("harness", {})
    if harness.get("required") is not True or harness.get("working_tree_overlay") is not False:
        raise VerificationError("harness custody")
    fixture = document.get("fixture", {})
    if fixture != {"relative_path": "crates/sipi-agent-com-direct/tests/fixtures/erl_s2p_10db_at_26p56ghz.s2p", "sha256": FIXTURE_SHA256, "bytes": FIXTURE_BYTES, "rows": FIXTURE_ROWS}:
        raise VerificationError("fixture binding")
    controls = document.get("controls", {})
    if document.get("control_crosswalk") != CROSSWALK:
        raise VerificationError("control crosswalk")
    if set(controls.get("outer", {})) != OUTER_KEYS or controls.get("outer") != OUTER_VALUES:
        raise VerificationError("outer control key set")
    if set(controls.get("tdr_profile", {})) != {"name", "samples_per_ui", "levels", "bin_size", "spec_ber", "rl_norm_test", "baud_hz", "sample_dt_s", "s_reference_ohm", "zt_ohm", "transition_time_ns", "transition_filter_type", "transition_measurement_point", "receiver_cutoff_multiplier", "receiver_filter_enabled", "tukey_enabled", "fixture_delay_s", "tdr_delay_s", "observation_duration_ui", "gate_n_bx", "gate_rho_x", "gate_grr", "gate_beta_x_db_per_s"}:
        raise VerificationError("tdr profile key set")
    if document.get("runtime", {}).get("timeout_s") != 180 or document.get("runtime", {}).get("build_timeout_s") != 900:
        raise VerificationError("runtime timeout")
    runtime = document.get("runtime", {})
    if runtime.get("build_profile") != "release" or not runtime.get("locked") or runtime.get("rustc_wrapper") != "cleared" or runtime.get("cargo_build_rustc_wrapper") != "cleared" or runtime.get("rustc_workspace_wrapper") != "cleared" or runtime.get("cargo_incremental") != "0" or runtime.get("cargo_offline") is not True or runtime.get("uv_offline") is not True or runtime.get("linker") != {"role": "rust-lld", "target": "x86_64-pc-windows-msvc", "resolution": "rustc --print sysroot/lib/rustlib/x86_64-pc-windows-msvc/bin/rust-lld.exe", "probe_strategy": "rust-lld --version; generic-driver exit 1 admitted"} or runtime.get("native_toolchain") != {"target": "x86_64-pc-windows-msvc", "msvc_version": "14.44.35207", "windows_sdk_version": "10.0.26100.0", "include_order": ["msvc", "sdk_ucrt", "sdk_shared", "sdk_um", "sdk_winrt", "sdk_cppwinrt"], "lib_order": ["msvc", "sdk_ucrt", "sdk_um"], "environment": "explicit PATH/INCLUDE/LIB; inherited LIB and INCLUDE forbidden", "required_key_libs": ["vcruntime.lib", "msvcrt.lib", "oldnames.lib", "ucrt.lib", "kernel32.lib", "user32.lib"]}:
        raise VerificationError("release locked build")
    if document.get("policy", {}).get("s_parameter_fit") != "forbidden" or document.get("policy", {}).get("channel") != "raw S11 FD-to-TD impulse":
        raise VerificationError("channel policy")
    if document.get("stage_mapping") != {"ptdr_gated": {"upstream": "ptdr_gated", "candidate": "gated"}, "ptdr_raw": {"status": "diagnostic_only_upstream_api_does_not_expose_raw_ptdr", "compared": False}}:
        raise VerificationError("stage mapping")
    if document.get("numeric_policy") != {"float_fields": ["ERL", "ERL11", "ERL_RMS"], "atol": 1.0e-12, "rtol": 1.0e-12, "phase_field": "ERL_phase_index", "phase_policy": "exact"}:
        raise VerificationError("numeric policy")
    if document.get("reports", {}).get("run_ids") != ["com-erl-exact-v3-run1", "com-erl-exact-v3-run2"]:
        raise VerificationError("run id gate")
    if not path_free(document):
        raise VerificationError("absolute path")
    return {"manifest_sha256": canonical_sha(document), "schema": document["schema"]}

def verify(path: Path = MANIFEST) -> dict[str, Any]:
    return verify_manifest(json.loads(path.read_text(encoding="utf-8")))


def verify_report(report: dict[str, Any], manifest: dict[str, Any]) -> None:
    expected_keys = {"schema", "run_id", "fresh_run_nonce", "path_policy", "candidate", "upstream", "input", "control_crosswalk", "stage_payload", "upstream_output", "candidate_output", "artifact", "toolchain", "execution", "parity", "non_claims"}
    if set(report) != expected_keys or report.get("schema") != "sipi.com.erl-only.exact-profile-replay.v3":
        raise VerificationError("report schema")
    if report.get("run_id") not in manifest["reports"]["run_ids"] or not re.fullmatch(r"[0-9a-f]{64}", report.get("fresh_run_nonce", "")):
        raise VerificationError("report run or nonce")
    if report.get("path_policy") != {"mode": "relative identities only", "absolute_paths_emitted": False}:
        raise VerificationError("report path policy")
    if report.get("status") == "external_blocked" or report.get("parity", {}).get("status") not in {"matched", "numeric_mismatch_open"}:
        raise VerificationError("report status")
    for side in ("candidate", "upstream"):
        if report.get(side, {}).get("commit") != manifest[side]["commit"] or report.get(side, {}).get("tree") != manifest[side]["tree"] or report.get(side, {}).get("archive_sha256") != manifest[side]["archive_sha256"]:
            raise VerificationError(f"{side} identity")
    input_payload = report.get("input", {})
    if input_payload.get("fixture_sha256") != FIXTURE_SHA256 or input_payload.get("fixture_bytes") != FIXTURE_BYTES or input_payload.get("fixture_rows") != FIXTURE_ROWS or input_payload.get("controls") != manifest["controls"]:
        raise VerificationError("report fixture or controls")
    copies = input_payload.get("fixture_copies", {})
    if copies.get("independent") is not True or copies.get("read_only") is not True or copies.get("pre_sha256") != copies.get("post_sha256") or set(copies.get("pre_sha256", {})) != {"candidate", "upstream"} or any(value != FIXTURE_SHA256 for value in copies.get("pre_sha256", {}).values()):
        raise VerificationError("fixture copy custody")
    crosswalk = report.get("control_crosswalk", {})
    if crosswalk.get("mapping") != manifest["control_crosswalk"] or crosswalk.get("candidate_profile") != manifest["controls"] or crosswalk.get("runtime_projection", {}).get("candidate") != runtime_projection(crosswalk.get("candidate_profile", {})) or crosswalk.get("runtime_projection", {}).get("upstream") != runtime_projection(crosswalk.get("upstream_materialized", {})):
        raise VerificationError("report control crosswalk")
    if crosswalk.get("runtime_projection", {}).get("upstream") != crosswalk.get("runtime_projection", {}).get("candidate"):
        raise VerificationError("runtime controls mismatch")
    if report.get("stage_payload", {}).get("mapping") != manifest["stage_mapping"]:
        raise VerificationError("report stage mapping")
    metric_fields = ("ERL", "ERL11", "ERL_RMS", "ERL_phase_index")
    metric_differences = {field for field in metric_fields if not metric_equal(field, report.get("upstream_output", {}).get(field), report.get("candidate_output", {}).get(field))}
    stage = report.get("stage_payload", {})
    stage_differences = {}
    upstream_stage = stage.get("upstream", {})
    candidate_stage = stage.get("candidate", {})
    verify_stage(upstream_stage.get("ptdr_gated", {}))
    verify_stage(candidate_stage.get("gated", {}))
    if upstream_stage.get("ptdr_gated") != candidate_stage.get("gated"):
        stage_differences["ptdr_gated"] = True
    controls_equal = report.get("control_crosswalk", {}).get("runtime_projection", {}).get("upstream") == report.get("control_crosswalk", {}).get("runtime_projection", {}).get("candidate")
    expected_status = "matched" if not metric_differences and not stage_differences and controls_equal else "numeric_mismatch_open"
    parity = report.get("parity", {})
    if parity.get("numeric_policy") != manifest["numeric_policy"]:
        raise VerificationError("report numeric policy")
    if parity.get("status") != expected_status or bool(parity.get("matched")) != (expected_status == "matched"):
        raise VerificationError("parity was not recomputed from payload")
    execution = report.get("execution", {})
    if execution.get("timeout_s") != manifest["runtime"]["timeout_s"] or execution.get("build_timeout_s") != manifest["runtime"]["build_timeout_s"]:
        raise VerificationError("report runtime")
    if execution.get("runner", {}).get("path") != manifest["runner"]["path"] or execution.get("runner", {}).get("sha256") != manifest["runner"]["sha256"] or execution.get("helper", {}).get("path") != manifest["runner"]["helper_path"] or execution.get("helper", {}).get("sha256") != manifest["runner"]["helper_sha256"]:
        raise VerificationError("report harness paths")
    toolchain = report.get("toolchain", {})
    if set(toolchain) != {"git", "cargo", "rustc", "uv", "python", "linker", "compiler", "msvc", "sdk", "rustc_wrapper", "cargo_build_rustc_wrapper", "rustc_workspace_wrapper", "cargo_incremental", "cargo_offline", "uv_offline"} or toolchain.get("rustc_wrapper") != "cleared" or toolchain.get("cargo_build_rustc_wrapper") != "cleared" or toolchain.get("rustc_workspace_wrapper") != "cleared" or toolchain.get("cargo_incremental") != "0" or toolchain.get("cargo_offline") is not True or toolchain.get("uv_offline") is not True:
        raise VerificationError("toolchain top-level schema")
    for role in ("git", "cargo", "rustc", "uv", "python"):
        identity = toolchain.get(role, {})
        if set(identity) != {"basename", "file_sha256", "version_output_sha256", "version_exit", "status", "path_redacted", "timeout_s"} or not isinstance(identity.get("basename"), str) or "/" in identity["basename"] or "\\" in identity["basename"] or not re.fullmatch(r"[0-9a-f]{64}", identity.get("file_sha256", "")) or not re.fullmatch(r"[0-9a-f]{64}", identity.get("version_output_sha256", "")) or identity.get("status") != "ok" or identity.get("path_redacted") is not True or identity.get("version_exit") != 0 or identity.get("timeout_s") != manifest["runtime"]["timeout_s"]:
            raise VerificationError("toolchain identity")
    linker = toolchain.get("linker", {})
    if set(linker) != {"role", "basename", "file_sha256", "version_output_sha256", "version_exit", "probe_strategy", "status", "path_redacted", "timeout_s"} or linker.get("role") != "rust-lld" or linker.get("probe_strategy") != "rust-lld --version; generic-driver exit 1 admitted" or linker.get("status") not in {"ok", "ok_generic_driver"} or linker.get("path_redacted") is not True or linker.get("timeout_s") != manifest["runtime"]["timeout_s"] or not isinstance(linker.get("basename"), str) or "/" in linker["basename"] or "\\" in linker["basename"] or not re.fullmatch(r"[0-9a-f]{64}", linker.get("file_sha256", "")) or not re.fullmatch(r"[0-9a-f]{64}", linker.get("version_output_sha256", "")) or linker.get("version_exit") not in {0, 1}:
        raise VerificationError("linker identity")
    compiler = toolchain.get("compiler", {})
    if set(compiler) != {"role", "basename", "file_sha256", "version_output_sha256", "version_exit", "probe_strategy", "status", "path_redacted", "timeout_s"} or compiler.get("role") != "msvc-cl" or compiler.get("probe_strategy") != "cl.exe; no-source exit 2 admitted" or compiler.get("status") != "ok_no_source" or compiler.get("path_redacted") is not True or compiler.get("timeout_s") != manifest["runtime"]["timeout_s"] or not re.fullmatch(r"cl\.exe", compiler.get("basename", ""), re.IGNORECASE) or not re.fullmatch(r"[0-9a-f]{64}", compiler.get("file_sha256", "")) or not re.fullmatch(r"[0-9a-f]{64}", compiler.get("version_output_sha256", "")) or compiler.get("version_exit") not in {0, 2}:
        raise VerificationError("compiler identity")
    msvc = toolchain.get("msvc", {})
    if set(msvc) != {"version", "include_order", "lib_order", "lib_inventory", "key_libs", "compiler"} or msvc.get("version") != manifest["runtime"]["native_toolchain"]["msvc_version"] or msvc.get("include_order") != ["msvc", "sdk_ucrt", "sdk_shared", "sdk_um", "sdk_winrt", "sdk_cppwinrt"] or msvc.get("lib_order") != ["msvc", "sdk_ucrt", "sdk_um"]:
        raise VerificationError("MSVC binding")
    verify_library_inventory(msvc.get("lib_inventory", {}))
    verify_key_libraries(msvc.get("key_libs", {}))
    if not all(msvc.get("key_libs", {}).get(name, {}).get("present") is True for name in ("vcruntime.lib", "msvcrt.lib", "oldnames.lib")):
        raise VerificationError("MSVC required libraries")
    sdk = toolchain.get("sdk", {})
    if set(sdk) != {"version", "include_order", "lib_inventory", "key_libs"} or sdk.get("version") != manifest["runtime"]["native_toolchain"]["windows_sdk_version"] or sdk.get("include_order") != ["sdk_ucrt", "sdk_shared", "sdk_um", "sdk_winrt", "sdk_cppwinrt"] or set(sdk.get("lib_inventory", {})) != {"ucrt", "um"} or set(sdk.get("key_libs", {})) != {"ucrt", "um"}:
        raise VerificationError("Windows SDK binding")
    verify_library_inventory(sdk["lib_inventory"]["ucrt"])
    verify_library_inventory(sdk["lib_inventory"]["um"])
    verify_key_libraries(sdk["key_libs"]["ucrt"])
    verify_key_libraries(sdk["key_libs"]["um"])
    if not sdk["key_libs"]["ucrt"].get("ucrt.lib", {}).get("present") or not all(sdk["key_libs"]["um"].get(name, {}).get("present") for name in ("kernel32.lib", "user32.lib")):
        raise VerificationError("Windows SDK required libraries")
    custody = report.get("candidate", {}).get("binary_custody")
    if validate_windows_pe_replay_custody(custody) or custody.get("raw_sha256") != report.get("candidate", {}).get("binary_sha256"):
        raise VerificationError("PE custody")
    if not path_free(report):
        raise VerificationError("report absolute path")


def verify_aggregate(aggregate: dict[str, Any], manifest: dict[str, Any], report_paths: list[Path]) -> None:
    expected_keys = {"schema", "status", "fresh_runs", "reports", "candidate", "upstream", "fixture", "controls", "stage_mapping", "toolchain_exact_equal", "binary_custody", "parity", "non_claims"}
    if set(aggregate) != expected_keys or aggregate.get("schema") != "sipi.com.erl-only.exact-profile-replay.v3.aggregate" or aggregate.get("status") != "bound_clean_archive_observation":
        raise VerificationError("aggregate schema/status")
    if len(report_paths) != 2 or len(aggregate.get("reports", [])) != 2:
        raise VerificationError("aggregate report count")
    if [path.as_posix() for path in report_paths] != manifest["reports"]["paths"]:
        raise VerificationError("aggregate report path order")
    report_hashes = []
    reports = []
    for path in report_paths:
        if PurePosixPath(path.as_posix()).is_absolute() or PureWindowsPath(path.as_posix()).is_absolute():
            raise VerificationError("aggregate report path")
        report_hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
        reports.append(json.loads(path.read_text(encoding="utf-8")))
    for report, digest, binding, path in zip(reports, report_hashes, aggregate["reports"], report_paths, strict=True):
        if set(binding) != {"path", "sha256", "run_id", "nonce"} or binding.get("path") != path.as_posix():
            raise VerificationError("aggregate report binding keys/path")
        verify_report(report, manifest)
        if binding.get("sha256") != digest or binding.get("run_id") != report["run_id"] or binding.get("nonce") != report["fresh_run_nonce"]:
            raise VerificationError("aggregate report binding")
    if [report["run_id"] for report in reports] != manifest["reports"]["run_ids"] or [binding["run_id"] for binding in aggregate["reports"]] != manifest["reports"]["run_ids"]:
        raise VerificationError("aggregate run order")
    if reports[0]["fresh_run_nonce"] == reports[1]["fresh_run_nonce"] or report_hashes[0] == report_hashes[1]:
        raise VerificationError("aggregate fresh distinctness")
    if aggregate.get("candidate") != candidate_source_projection(reports[0].get("candidate", {})) or aggregate.get("candidate") != candidate_source_projection(reports[1].get("candidate", {})) or aggregate.get("upstream") != reports[0].get("upstream") or aggregate.get("upstream") != reports[1].get("upstream"):
        raise VerificationError("aggregate source binding")
    if aggregate.get("fixture") != manifest["fixture"] or aggregate.get("controls") != manifest["controls"] or aggregate.get("stage_mapping") != manifest["stage_mapping"] or aggregate.get("toolchain_exact_equal") is not True:
        raise VerificationError("aggregate manifest binding")
    expected_parity = {"status": "open_until_numeric_and_stage_match", "run_statuses": [report["parity"]["status"] for report in reports]}
    if aggregate.get("parity") != expected_parity or aggregate.get("non_claims") != ["no_release_or_promotion", "no_global_migration_row_close"]:
        raise VerificationError("aggregate parity/non-claims")
    if aggregate.get("binary_custody") != [report["candidate"]["binary_custody"] for report in reports]:
        raise VerificationError("aggregate custody binding")
    custody_errors = compare_windows_pe_custody(reports[0]["candidate"]["binary_custody"], reports[1]["candidate"]["binary_custody"])
    if custody_errors:
        raise VerificationError("aggregate PE custody: " + "; ".join(custody_errors))
    if not path_free(aggregate):
        raise VerificationError("aggregate absolute path")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--aggregate", type=Path)
    parser.add_argument("--report", action="append", type=Path)
    args = parser.parse_args()
    manifest_document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    verify_manifest(manifest_document)
    if args.aggregate is not None:
        if args.report is None:
            raise SystemExit("--aggregate requires --report twice")
        verify_aggregate(json.loads(args.aggregate.read_text(encoding="utf-8")), manifest_document, args.report)
    print(json.dumps({"schema": manifest_document["schema"], "formal_reports_verified": args.aggregate is not None}, sort_keys=True))
