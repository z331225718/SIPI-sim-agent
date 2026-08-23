"""Fail-closed verifier for additive COM ERL v4 replay preparation."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pb_03_replay_common import compare_windows_pe_custody, validate_windows_pe_replay_custody

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/com-erl-exact-profile-replay-v4.prep.manifest.json"
SCHEMA = "sipi.com.erl-only.exact-profile-replay.v4"
AGG_SCHEMA = f"{SCHEMA}.aggregate"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
RUN_IDS = ("com-erl-exact-v4-n800-run1", "com-erl-exact-v4-n800-run2", "com-erl-exact-v4-n1-negative")
METRIC_FIELDS = ("ERL", "ERL11", "ERL_RMS", "ERL_phase_index")


class VerificationError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def path_free(value: Any) -> bool:
    if isinstance(value, dict):
        return all(path_free(k) and path_free(v) for k, v in value.items())
    if isinstance(value, list):
        return all(path_free(v) for v in value)
    if not isinstance(value, str):
        return True
    return not PurePosixPath(value).is_absolute() and not PureWindowsPath(value).is_absolute()


def metric_equal(field: str, left: Any, right: Any) -> bool:
    if field == "ERL_phase_index":
        return left == right
    if left in {"inf", "-inf", "nan"} or right in {"inf", "-inf", "nan"}:
        return left == right
    return isinstance(left, (int, float)) and isinstance(right, (int, float)) and math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)


def verify_stage(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"count", "sha256"}:
        raise VerificationError("stage schema")
    if isinstance(value["count"], bool) or not isinstance(value["count"], int) or value["count"] <= 0 or not HEX64.fullmatch(value["sha256"]):
        raise VerificationError("stage schema")
    if isinstance(value["count"], bool) or not isinstance(value["count"], int) or value["count"] <= 0 or not HEX64.fullmatch(value["sha256"]):
        raise VerificationError("stage schema")


def verify_toolchain(value: Any, manifest: dict[str, Any]) -> None:
    top = {"git", "cargo", "rustc", "uv", "python", "linker", "compiler", "msvc", "sdk", "rustc_wrapper", "cargo_build_rustc_wrapper", "rustc_workspace_wrapper", "cargo_incremental", "cargo_offline", "uv_offline"}
    if set(value) != top or value["rustc_wrapper"] != "cleared" or value["cargo_build_rustc_wrapper"] != "cleared" or value["rustc_workspace_wrapper"] != "cleared" or value["cargo_incremental"] != "0" or value["cargo_offline"] is not True or value["uv_offline"] is not True:
        raise VerificationError("toolchain top-level schema")
    basic = {"basename", "file_sha256", "version_output_sha256", "version_exit", "status", "path_redacted", "timeout_s"}
    for role in ("git", "cargo", "rustc", "uv", "python"):
        item = value[role]
        if set(item) != basic or not isinstance(item["basename"], str) or "/" in item["basename"] or "\\" in item["basename"] or not HEX64.fullmatch(item["file_sha256"]) or not HEX64.fullmatch(item["version_output_sha256"]) or item["status"] != "ok" or item["path_redacted"] is not True or item["version_exit"] != 0 or item["timeout_s"] != 180:
            raise VerificationError(f"toolchain {role}")
    special = basic | {"role", "probe_strategy"}
    for role, expected_role, expected_status in (("linker", "rust-lld", {"ok", "ok_generic_driver"}), ("compiler", "msvc-cl", {"ok_no_source"})):
        item = value[role]
        if set(item) != special or item["role"] != expected_role or item["status"] not in expected_status or item["path_redacted"] is not True or item["timeout_s"] != 180 or not HEX64.fullmatch(item["file_sha256"]) or not HEX64.fullmatch(item["version_output_sha256"]) or "/" in item["basename"] or "\\" in item["basename"]:
            raise VerificationError(f"toolchain {role}")
    if value["linker"]["probe_strategy"] != "rust-lld --version; generic-driver exit 1 admitted" or value["compiler"]["probe_strategy"] != "cl.exe; no-source exit 2 admitted":
        raise VerificationError("toolchain probe strategy")
    if set(value["msvc"]) != {"version", "include_order", "lib_order", "lib_inventory", "key_libs", "compiler"} or set(value["sdk"]) != {"version", "include_order", "lib_inventory", "key_libs"}:
        raise VerificationError("native toolchain schema")
    if value["msvc"]["version"] != "14.44.35207" or value["sdk"]["version"] != "10.0.26100.0" or value["msvc"]["include_order"] != ["msvc", "sdk_ucrt", "sdk_shared", "sdk_um", "sdk_winrt", "sdk_cppwinrt"] or value["msvc"]["lib_order"] != ["msvc", "sdk_ucrt", "sdk_um"] or value["sdk"]["include_order"] != ["sdk_ucrt", "sdk_shared", "sdk_um", "sdk_winrt", "sdk_cppwinrt"]:
        raise VerificationError("native toolchain versions/order")
    for inventory in [value["msvc"]["lib_inventory"], value["sdk"]["lib_inventory"]["ucrt"], value["sdk"]["lib_inventory"]["um"]]:
        if set(inventory) != {"count", "combined_sha256", "files"} or not isinstance(inventory["count"], int) or inventory["count"] <= 0 or len(inventory["files"]) != inventory["count"] or not HEX64.fullmatch(inventory["combined_sha256"]):
            raise VerificationError("library inventory")
        for item in inventory["files"]:
            if set(item) != {"path", "sha256"} or PurePosixPath(item["path"]).is_absolute() or PureWindowsPath(item["path"]).is_absolute() or not HEX64.fullmatch(item["sha256"]):
                raise VerificationError("library inventory entry")
    for group in (value["msvc"]["key_libs"], value["sdk"]["key_libs"]["ucrt"], value["sdk"]["key_libs"]["um"]):
        for item in group.values():
            if set(item) != {"present", "sha256", "path"} or not isinstance(item["present"], bool):
                raise VerificationError("key library inventory")
            if item["present"]:
                if not HEX64.fullmatch(item["sha256"]) or not isinstance(item["path"], str) or PurePosixPath(item["path"]).is_absolute() or PureWindowsPath(item["path"]).is_absolute():
                    raise VerificationError("key library inventory")
            elif item["sha256"] is not None or item["path"] is not None:
                raise VerificationError("missing key library identity")
    if not all(value["msvc"]["key_libs"].get(name, {}).get("present") is True for name in ("vcruntime.lib", "msvcrt.lib", "oldnames.lib")) or not value["sdk"]["key_libs"]["ucrt"].get("ucrt.lib", {}).get("present") or not all(value["sdk"]["key_libs"]["um"].get(name, {}).get("present") for name in ("kernel32.lib", "user32.lib")):
        raise VerificationError("required native libraries")
def runtime_projection(controls: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    fields = tuple(manifest["control_crosswalk"]["runtime_fields"])
    outer = controls.get("outer", {})
    profile = controls.get("tdr_profile", {})
    return {"outer": {key: outer.get(key) for key in manifest["controls"]["outer"]}, "tdr_profile": {key: profile.get(key) for key in fields if key in profile}}


def _verify_exact_profile(document: dict[str, Any]) -> None:
    controls = document["controls"]
    if controls.get("positive_runtime_n_ui") != 800 or controls.get("negative_runtime_n_ui") != 1 or controls.get("profile_observation_duration_ui") != 800:
        raise VerificationError("runtime N controls")
    if controls.get("outer") != {"samples_per_ui": 32, "levels": 4, "bin_size": 1.0e-5, "spec_ber": 1.0e-5, "rl_norm_test": True}:
        raise VerificationError("outer controls")
    profile = controls.get("tdr_profile", {})
    expected_profile = {"name": "r480_s2p_erl_v1", "samples_per_ui": 32, "levels": 4, "bin_size": 1.0e-5, "spec_ber": 1.0e-5, "rl_norm_test": True, "baud_hz": 53125000000, "sample_dt_s": 5.882352941176471e-13, "s_reference_ohm": 100, "zt_ohm": 50, "transition_time_ns": 0.01, "transition_filter_type": 1, "transition_measurement_point": 0, "receiver_cutoff_multiplier": 0.75, "receiver_filter_enabled": True, "tukey_enabled": True, "fixture_delay_s": 0, "tdr_delay_s": 5e-10, "observation_duration_ui": 800, "gate_n_bx": 0, "gate_rho_x": 0.618, "gate_grr": 1, "gate_beta_x_db_per_s": 0, "runtime_n_ui": 800, "tdr_butterworth": True, "fb_bw_cutoff": 0.75, "f_r": 0.75}
    if profile != expected_profile:
        raise VerificationError("profile controls")
    if document["source_constants"] != {"s_reference_ohm": 100.0, "tdr_delay_s": 5.0e-10, "transition_filter_type": 1, "transition_measurement_point": 0}:
        raise VerificationError("source constants")
    crosswalk = document["control_crosswalk"]
    expected_fields = {"runtime_n_ui": "runtime.options.N", "samples_per_ui": "materialized.parameters.samples_per_ui", "levels": "materialized.parameters.levels", "bin_size": "materialized.options.BinSize", "spec_ber": "materialized.parameters.specBER", "rl_norm_test": "materialized.options.RL_norm_test", "baud_hz": "materialized.parameters.fb", "sample_dt_s": "materialized.parameters.sample_dt", "gate_rho_x": "materialized.parameters.rho_x", "gate_grr": "materialized.parameters.Grr", "gate_beta_x_db_per_s": "materialized.parameters.beta_x", "tdr_butterworth": "runtime.options.TDR_Butterworth", "fb_bw_cutoff": "materialized.parameters.fb_BW_cutoff", "f_r": "materialized.parameters.f_r", "tukey_enabled": "materialized.parameters.Tukey_Window"}
    if crosswalk != {"runtime_fields": expected_fields, "raw_source_fields_not_runtime_controls": ["Z0", "T_r_filter_type", "T_r_meas_point", "T_k", "TDR_duration"], "source_constants": document["source_constants"]}:
        raise VerificationError("control crosswalk")


def _tool_binding(manifest: dict[str, Any], key: str, expected_path: str) -> None:
    value = manifest["tools"].get(key)
    path = ROOT / expected_path
    if not isinstance(value, dict) or set(value) != {"path", "sha256"} or value["path"] != expected_path or not path.is_file() or value["sha256"] != sha256(path):
        raise VerificationError(f"tool binding: {key}")


def verify_manifest(document: dict[str, Any]) -> dict[str, Any]:
    expected_top = {"schema", "candidate", "upstream", "fixture", "controls", "source_constants", "control_crosswalk", "stage_mapping", "preflight", "numeric_policy", "execution", "policy", "tools", "reports", "expected", "non_claims"}
    if set(document) != expected_top or document.get("schema") != "sipi.com.erl-only.exact-profile-replay.v4.prep.manifest":
        raise VerificationError("manifest schema")
    if document["candidate"] != {"commit": "955835369c28aacb3f49bd0cf95f3660587739d8", "tree": "fbb415e5582ccf3ee70e4d0d472f1fc6856e0e26", "archive_sha256": "005e06d1ab680a7ddf41a2110c5e8ea9e44b020e04c5d4369a78f05c15ea79f0", "cargo_lock_sha256": "a9dd3fb93ac427c6d6a04538cf38551a8d73bbe35bd4be17ba5e408da2280cbc"}:
        raise VerificationError("candidate identity")
    upstream = document["upstream"]
    if upstream.get("commit") != "5272ffe74702cd585054d975559b06f8afae7b6e" or upstream.get("tree") != "7094ab6e84989b218730c52432c70da10261f8ea" or upstream.get("archive_sha256") != "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf" or upstream.get("required_runtime") != "uv run --frozen --offline --project . --python <pinned-python> python -c <probe>" or upstream.get("required_lock") != "uv.lock" or upstream.get("uv_lock_sha256") != "5495d481034518d4424a55a27aa2319c90d2045bc280705748d66f44e159a00f":
        raise VerificationError("upstream identity")
    fixture = {"relative_path": "crates/sipi-agent-com-direct/tests/fixtures/erl_s2p_10db_at_26p56ghz.s2p", "sha256": "7a59b41a385a95752d2d1159aab7772a10f7bd2c07e5122d770493151853c7a3", "bytes": 830969, "rows": 8001, "copies": {"candidate_sha256": "7a59b41a385a95752d2d1159aab7772a10f7bd2c07e5122d770493151853c7a3", "upstream_sha256": "7a59b41a385a95752d2d1159aab7772a10f7bd2c07e5122d770493151853c7a3"}}
    if document["fixture"] != fixture:
        raise VerificationError("fixture identity")
    _verify_exact_profile(document)
    if document["stage_mapping"] != {"ptdr_gated": {"upstream": "ptdr_gated", "candidate": "gated"}, "ptdr_raw": {"status": "diagnostic_only_upstream_api_does_not_expose_raw_ptdr", "compared": False}}:
        raise VerificationError("stage mapping")
    if document["preflight"] != {"positive": {"upstream_gated": {"count": 2310, "sha256": "a3e274d035c5cdf11af5e43852341a92a315bb8e9c7552b25b74764721f1879a"}, "candidate_gated": {"count": 2310, "sha256": "6b4ca9b5ad5909791917e2eb8bd4079aaaf591b61f8c02af081a9e4f46ed2143"}}, "negative": {"upstream_gated": {"count": 15, "sha256": "9bb66210cade8684e08cfdb260a23763c35dc157dd68a8d6e0edda32716e1463"}}}:
        raise VerificationError("preflight stage gate")
    if document["numeric_policy"] != {"float_fields": ["ERL", "ERL11", "ERL_RMS"], "atol": 1.0e-12, "rtol": 1.0e-12, "phase_field": "ERL_phase_index", "phase_policy": "exact"}:
        raise VerificationError("numeric policy")
    if document["execution"] != {"runtime_timeout_s": 180, "build_timeout_s": 900, "build_profile": "release", "locked": True, "temp_policy": "independent_existing_temp_per_run; path_free_record", "uv_cache_policy": "caller_supplied_external", "inherited_cache_not_claimed": True, "upstream_command": "uv run --frozen --offline --project . --python <pinned-python> python -c <probe>", "upstream_python_env": {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}}:
        raise VerificationError("execution controls")
    for key, path in {"runner": "tools/run_com_erl_exact_profile_replay_v4.py", "verifier": "tools/verify_com_erl_exact_profile_replay_v4.py", "aggregator": "tools/aggregate_com_erl_exact_profile_replay_v4.py", "tests": "tools/test_com_erl_exact_profile_replay_v4.py", "support": "tools/com_erl_exact_profile_replay_v3_support.py", "pe_helper": "tools/pb_03_replay_common.py", "audit": "docs/baselines/audits/2026-08-24-com-erl-exact-profile-replay-v4-prep.md"}.items():
        _tool_binding(document, key, path)
    if document["policy"] != {"s_parameter_fit": "forbidden", "channel": "raw S11 FD-to-TD impulse", "materialization": "clean git archive; no working-tree overlay", "pending_harness": True}:
        raise VerificationError("policy")
    if document["reports"] != {"positive": ["docs/baselines/com-erl-exact-profile-replay-v4-n800-run1.json", "docs/baselines/com-erl-exact-profile-replay-v4-n800-run2.json"], "negative": "docs/baselines/com-erl-exact-profile-replay-v4-n1-negative.json", "aggregate": "docs/baselines/com-erl-exact-profile-replay-v4.aggregate.json", "run_ids": list(RUN_IDS)}:
        raise VerificationError("report paths")
    if document["expected"] != {"positive": {"ERL": 0.014778577737989889, "ERL11": 0.014778577737989889, "ERL_RMS": 23.331117354940236, "ERL_phase_index": 21, "gated_count": 2310}, "positive_candidate": {"ERL": 0.014778577737989889, "ERL11": 0.014778577737989889, "ERL_RMS": 23.331117354940247, "ERL_phase_index": 21}, "negative_upstream": {"ERL": "inf", "ERL11": "inf", "ERL_RMS": 147.69907242031078, "ERL_phase_index": 13, "gated_count": 15}}:
        raise VerificationError("expected payload")
    if document["non_claims"] != ["no_release_or_promotion", "no_global_migration_row_close", "no_numeric_parity_close", "no_s_parameter_fit"]:
        raise VerificationError("manifest non-claims")
    if not path_free(document):
        raise VerificationError("absolute path")
    return {"schema": document["schema"], "manifest_sha256": hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def _verify_identity(report: dict[str, Any], manifest: dict[str, Any]) -> None:
    for side in ("candidate", "upstream"):
        identity = report.get(side, {})
        expected = manifest["candidate" if side == "candidate" else "upstream"]
        for key in ("commit", "tree", "archive_sha256"):
            if identity.get(key) != expected[key]:
                raise VerificationError(f"{side} identity")
    if report["upstream"].get("uv_lock_sha256") != manifest["upstream"]["uv_lock_sha256"]:
        raise VerificationError("upstream lock")


def verify_report(report: dict[str, Any], manifest: dict[str, Any]) -> None:
    expected_keys = {"schema", "run_id", "fresh_run_nonce", "status", "path_policy", "candidate", "upstream", "input", "control_crosswalk", "stage_payload", "upstream_output", "candidate_output", "artifact", "toolchain", "execution", "parity", "non_claims"}
    if set(report) != expected_keys or report.get("schema") != SCHEMA or not path_free(report):
        raise VerificationError("report schema/path")
    run_id = report["run_id"]
    if run_id not in RUN_IDS or not HEX64.fullmatch(report.get("fresh_run_nonce", "")):
        raise VerificationError("run id/nonce")
    if report["path_policy"] != {"mode": "relative identities only", "absolute_paths_emitted": False}:
        raise VerificationError("path policy")
    _verify_identity(report, manifest)
    expected_n = 1 if run_id.endswith("n1-negative") else 800
    expected_candidate_keys = {"commit", "tree", "archive_sha256", "materialization", "runtime_executed", "excluded_from_parity", "cargo_lock_sha256"}
    if expected_n == 800:
        expected_candidate_keys |= {"binary_sha256", "binary_custody"}
    if set(report["candidate"]) != expected_candidate_keys or set(report["upstream"]) != {"commit", "tree", "archive_sha256", "materialization", "runtime_executed", "uv_lock_sha256", "pyproject_sha256"}:
        raise VerificationError("source identity nested keys")
    if report["candidate"]["materialization"] != "git archive; no working-tree overlay" or report["upstream"]["materialization"] != "git archive; no working-tree overlay" or report["candidate"]["cargo_lock_sha256"] != manifest["candidate"]["cargo_lock_sha256"]:
        raise VerificationError("source materialization")
    if report["upstream"]["runtime_executed"] is not True or report["upstream"]["uv_lock_sha256"] != manifest["upstream"]["uv_lock_sha256"] or not HEX64.fullmatch(report["upstream"]["pyproject_sha256"]):
        raise VerificationError("upstream lock/runtime")
    fixture = manifest["fixture"]
    payload = report["input"]
    expected_input_keys = {"fixture_relative", "fixture_sha256", "fixture_bytes", "fixture_rows", "fixture_copies", "config_sha256", "upstream_workbook_sha256", "channel_kind", "s_parameter_fit", "channel_policy", "controls", "runtime_n_ui", "observation_duration_ui"}
    if set(payload) != expected_input_keys:
        raise VerificationError("input nested keys")
    if payload.get("fixture_relative") != fixture["relative_path"] or payload.get("fixture_sha256") != fixture["sha256"] or payload.get("fixture_bytes") != fixture["bytes"] or payload.get("fixture_rows") != fixture["rows"] or payload.get("runtime_n_ui") != expected_n or payload.get("observation_duration_ui") != 800 or payload.get("controls") != manifest["controls"] or payload.get("s_parameter_fit") != "forbidden" or payload.get("channel_policy") != "raw S11 FD-to-TD impulse; no fit":
        raise VerificationError("input binding")
    copies = payload.get("fixture_copies", {})
    if set(copies) != {"pre_sha256", "post_sha256", "independent", "read_only"} or copies.get("independent") is not True or copies.get("read_only") is not True or copies.get("pre_sha256") != copies.get("post_sha256") or copies.get("pre_sha256") != {"candidate": fixture["sha256"], "upstream": fixture["sha256"]}:
        raise VerificationError("fixture custody")
    crosswalk = report["control_crosswalk"]
    expected_profile = {"outer": manifest["controls"]["outer"], "tdr_profile": {**manifest["controls"]["tdr_profile"], "runtime_n_ui": expected_n}}
    if set(crosswalk) != {"candidate_profile", "upstream_materialized", "runtime_projection", "mapping", "status"} or set(crosswalk.get("runtime_projection", {})) != {"candidate", "upstream"} or crosswalk.get("mapping") != manifest["control_crosswalk"]:
        raise VerificationError("candidate crosswalk")
    if (expected_n == 800 and crosswalk.get("candidate_profile") != expected_profile) or (expected_n == 1 and crosswalk.get("candidate_profile") is not None):
        raise VerificationError("candidate profile admission")
    calculated_upstream_projection = runtime_projection(crosswalk["upstream_materialized"], manifest)
    calculated_candidate_projection = runtime_projection(crosswalk["candidate_profile"], manifest) if crosswalk.get("candidate_profile") is not None else None
    if crosswalk["runtime_projection"].get("upstream") != calculated_upstream_projection or crosswalk["runtime_projection"].get("candidate") != calculated_candidate_projection:
        raise VerificationError("mechanical runtime projection")
    candidate_projection = crosswalk.get("runtime_projection", {}).get("candidate")
    upstream_projection = crosswalk.get("runtime_projection", {}).get("upstream")
    if upstream_projection is None or upstream_projection.get("tdr_profile", {}).get("runtime_n_ui") != expected_n:
        raise VerificationError("upstream runtime N")
    if report["non_claims"] != manifest["non_claims"] or set(report["artifact"]) != {"candidate_result_sha256"}:
        raise VerificationError("report non-claims/artifact keys")
    verify_toolchain(report["toolchain"], manifest)
    expected_execution_keys = {"runner", "helper", "pe_helper", "timeout_s", "build_timeout_s", "upstream_elapsed_s", "candidate_timeout_s", "candidate_build_exit", "build_profile", "locked", "upstream_python_env", "upstream_uv_cache_policy", "upstream_command"}
    if set(report["execution"]) != expected_execution_keys or report["execution"]["timeout_s"] != 180 or report["execution"]["build_timeout_s"] != 900 or report["execution"]["upstream_python_env"] != manifest["execution"]["upstream_python_env"] or report["execution"]["upstream_uv_cache_policy"] != "caller_supplied_external" or report["execution"]["upstream_command"] != manifest["execution"]["upstream_command"]:
        raise VerificationError("execution schema")
    if report["execution"]["build_profile"] != "release" or report["execution"]["locked"] is not True:
        raise VerificationError("execution build policy")
    if expected_n == 800 and (report["execution"]["candidate_build_exit"] != 0 or report["execution"]["candidate_timeout_s"] != 180):
        raise VerificationError("candidate execution binding")
    if expected_n == 1 and (report["execution"]["candidate_build_exit"] is not None or report["execution"]["candidate_timeout_s"] is not None):
        raise VerificationError("negative candidate build fabrication")
    for key, manifest_key in (("runner", "runner"), ("helper", "support"), ("pe_helper", "pe_helper")):
        entry = report["execution"][key]
        if set(entry) != {"path", "sha256"} or entry["path"] != manifest["tools"][manifest_key]["path"] or entry["sha256"] != manifest["tools"][manifest_key]["sha256"]:
            raise VerificationError(f"execution helper {key}")
    if expected_n == 1:
        if report["status"] != "upstream_only_guard" or report["candidate"].get("runtime_executed") is not False or report["candidate"].get("excluded_from_parity") is not True or report["candidate_output"] != {} or report["stage_payload"].get("candidate") != {} or candidate_projection is not None or report["control_crosswalk"].get("status") != "excluded_from_parity" or set(report["stage_payload"]) != {"mapping", "upstream", "candidate", "upstream_diagnostic_keys", "candidate_dispatch", "ptdr"} or set(report["stage_payload"]["upstream"]) != {"tdr_time_s", "tdr_impedance_ohm", "ptdr_gated"} or report["parity"].get("status") != "excluded_from_parity" or report["parity"].get("matched") is not False:
            raise VerificationError("negative control admission")
        expected = manifest["expected"]["negative_upstream"]
        if set(report["upstream_output"]) != set(METRIC_FIELDS) or set(report["artifact"]) != {"candidate_result_sha256"} or report["artifact"]["candidate_result_sha256"] is not None:
            raise VerificationError("negative artifact schema")
        if any(not metric_equal(field, report["upstream_output"].get(field), expected[field]) for field in METRIC_FIELDS):
            raise VerificationError("negative metrics")
        verify_stage(report["stage_payload"].get("upstream", {}).get("ptdr_gated", {}))
        if report["stage_payload"]["upstream"]["ptdr_gated"] != manifest["preflight"]["negative"]["upstream_gated"] or report["stage_payload"]["upstream"]["ptdr_gated"]["count"] != expected["gated_count"]:
            raise VerificationError("negative stage")
        return
    if report["status"] != "bound_clean_archive_observation" or report["candidate"].get("runtime_executed") is not True or report["candidate"].get("excluded_from_parity") is not False or candidate_projection != upstream_projection:
        raise VerificationError("positive runtime/crosswalk")
    if set(report["upstream_output"]) != set(METRIC_FIELDS) or set(report["candidate_output"]) != set(METRIC_FIELDS) or set(report["parity"]) != {"fields", "numeric_policy", "matched", "differences", "stage_differences", "controls_equal", "status"} or report["parity"]["fields"] != list(METRIC_FIELDS):
        raise VerificationError("metric/parity nested keys")
    expected_candidate_metrics = manifest["expected"]["positive_candidate"]
    if report["candidate_output"] != expected_candidate_metrics:
        raise VerificationError("positive candidate metrics")
    if report["parity"]["differences"] != {} or report["parity"]["controls_equal"] is not True:
        raise VerificationError("positive metric/control parity")
    if report["candidate"]["binary_sha256"] != report["candidate"]["binary_custody"].get("raw_sha256") or not HEX64.fullmatch(report["candidate"]["binary_sha256"]):
        raise VerificationError("candidate artifact custody")
    expected = manifest["expected"]["positive"]
    for field in METRIC_FIELDS:
        if not metric_equal(field, report["upstream_output"].get(field), expected[field]):
            raise VerificationError(f"positive upstream {field}")
    stages = report["stage_payload"]
    if set(stages) != {"mapping", "upstream", "candidate", "upstream_diagnostic_keys", "candidate_dispatch", "ptdr"} or set(stages["upstream"]) != {"tdr_time_s", "tdr_impedance_ohm", "ptdr_gated"} or set(stages["candidate"]) != {"channel_impulse", "channel_pulse", "erl_impulse", "ptdr", "gated"}:
        raise VerificationError("stage nested keys")
    if stages.get("mapping") != manifest["stage_mapping"]:
        raise VerificationError("stage mapping")
    verify_stage(stages.get("upstream", {}).get("ptdr_gated", {}))
    verify_stage(stages.get("candidate", {}).get("gated", {}))
    expected_preflight = manifest["preflight"]["positive"]
    if stages["upstream"]["ptdr_gated"] != expected_preflight["upstream_gated"] or stages["candidate"]["gated"] != expected_preflight["candidate_gated"] or stages["upstream"]["ptdr_gated"] == stages["candidate"]["gated"]:
        raise VerificationError("exact positive stage gate")
    metrics_equal = all(metric_equal(field, report["upstream_output"].get(field), report["candidate_output"].get(field)) for field in METRIC_FIELDS)
    stages_equal = stages["upstream"]["ptdr_gated"] == stages["candidate"]["gated"]
    expected_status = "matched" if metrics_equal and stages_equal else "numeric_mismatch_open"
    parity = report["parity"]
    if parity.get("numeric_policy") != manifest["numeric_policy"] or parity.get("status") != expected_status or bool(parity.get("matched")) != (expected_status == "matched"):
        raise VerificationError("parity recomputation")
    if parity.get("status") != "numeric_mismatch_open" or parity.get("matched") is not False or parity.get("stage_differences") != {"ptdr_gated": {"upstream": expected_preflight["upstream_gated"], "candidate": expected_preflight["candidate_gated"]}}:
        raise VerificationError("stage mismatch status")
    if report["execution"].get("timeout_s") != 180 or report["execution"].get("build_timeout_s") != 900 or report["execution"].get("upstream_python_env") != manifest["execution"]["upstream_python_env"] or report["execution"].get("upstream_uv_cache_policy") != "caller_supplied_external":
        raise VerificationError("execution binding")
    if report["execution"].get("runner", {}).get("path") != manifest["tools"]["runner"]["path"] or report["execution"].get("helper", {}).get("path") != manifest["tools"]["support"]["path"] or report["execution"].get("pe_helper", {}).get("path") != manifest["tools"]["pe_helper"]["path"]:
        raise VerificationError("execution tools")
    if report["execution"]["runner"].get("sha256") != manifest["tools"]["runner"]["sha256"] or report["execution"]["helper"].get("sha256") != manifest["tools"]["support"]["sha256"] or report["execution"]["pe_helper"].get("sha256") != manifest["tools"]["pe_helper"]["sha256"]:
        raise VerificationError("execution helper hashes")
    if set(report["execution"]) != {"runner", "helper", "pe_helper", "timeout_s", "build_timeout_s", "upstream_elapsed_s", "candidate_timeout_s", "candidate_build_exit", "build_profile", "locked", "upstream_python_env", "upstream_uv_cache_policy", "upstream_command"}:
        raise VerificationError("execution nested keys")
    if set(report["artifact"]) != {"candidate_result_sha256"} or not HEX64.fullmatch(report["artifact"]["candidate_result_sha256"]):
        raise VerificationError("artifact schema")
    if report["non_claims"] != manifest["non_claims"]:
        raise VerificationError("report non-claims")
    custody = report["candidate"].get("binary_custody", {})
    if validate_windows_pe_replay_custody(custody) or custody.get("raw_sha256") != report["candidate"].get("binary_sha256"):
        raise VerificationError("candidate custody")


def verify_report_path(path: Path, manifest_path: Path = MANIFEST) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verify_manifest(manifest)
    verify_report(json.loads(path.read_text(encoding="utf-8")), manifest)


def verify_aggregate(aggregate: dict[str, Any], manifest: dict[str, Any], report_paths: list[Path]) -> None:
    expected_keys = {"schema", "status", "run_ids", "reports", "candidate", "upstream", "fixture", "controls", "stage_mapping", "toolchain_exact_equal", "pe_custody_compare", "parity", "non_claims"}
    if set(aggregate) != expected_keys or aggregate.get("schema") != AGG_SCHEMA or not path_free(aggregate):
        raise VerificationError("aggregate schema/path")
    expected_paths = manifest["reports"]["positive"] + [manifest["reports"]["negative"]]
    if len(report_paths) != 3 or [path.as_posix() for path in report_paths] != expected_paths:
        raise VerificationError("aggregate report order/path")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in report_paths]
    for report in reports:
        verify_report(report, manifest)
    if [report["run_id"] for report in reports] != list(RUN_IDS) or len({report["fresh_run_nonce"] for report in reports}) != 3:
        raise VerificationError("aggregate run binding")
    hashes = [sha256(path) for path in report_paths]
    if len(set(hashes)) != 3:
        raise VerificationError("aggregate report hash collision")
    expected_report_entries = [{"path": path.as_posix(), "sha256": digest, "run_id": report["run_id"], "nonce": report["fresh_run_nonce"]} for path, digest, report in zip(report_paths, hashes, reports, strict=True)]
    if aggregate["reports"] != expected_report_entries:
        raise VerificationError("aggregate report digest")
    if reports[0]["upstream_output"] != reports[1]["upstream_output"] or reports[0]["stage_payload"]["upstream"]["ptdr_gated"] != reports[1]["stage_payload"]["upstream"]["ptdr_gated"]:
        raise VerificationError("positive run drift")
    expected_candidate = {key: reports[0]["candidate"].get(key) for key in ("commit", "tree", "archive_sha256", "materialization", "runtime_executed", "cargo_lock_sha256")}
    if aggregate["status"] != "bound_clean_archive_observation" or aggregate["run_ids"] != list(RUN_IDS) or aggregate["candidate"] != expected_candidate or aggregate["upstream"] != reports[0]["upstream"] or aggregate["fixture"] != manifest["fixture"] or aggregate["controls"] != manifest["controls"] or aggregate["stage_mapping"] != manifest["stage_mapping"] or aggregate["toolchain_exact_equal"] is not True or aggregate["pe_custody_compare"] != {"status": "ok", "errors": []} or aggregate["non_claims"] != manifest["non_claims"]:
        raise VerificationError("aggregate binding")
    if reports[0]["toolchain"] != reports[1]["toolchain"] or reports[0]["toolchain"] != reports[2]["toolchain"]:
        raise VerificationError("toolchain drift")
    for key in ("commit", "tree", "archive_sha256", "materialization", "cargo_lock_sha256"):
        if reports[0]["candidate"].get(key) != reports[1]["candidate"].get(key) or reports[0]["candidate"].get(key) != reports[2]["candidate"].get(key):
            raise VerificationError("candidate source drift")
    if reports[0]["upstream"] != reports[1]["upstream"] or reports[0]["upstream"] != reports[2]["upstream"]:
        raise VerificationError("upstream source drift")
    if compare_windows_pe_custody(reports[0]["candidate"]["binary_custody"], reports[1]["candidate"]["binary_custody"]) or aggregate["pe_custody_compare"] != {"status": "ok", "errors": []}:
        raise VerificationError("PE custody drift")
    expected_parity = {"status": "numeric_mismatch_open", "run_statuses": ["numeric_mismatch_open", "numeric_mismatch_open", "excluded_from_parity"]}
    if aggregate["parity"] != expected_parity:
        raise VerificationError("aggregate parity")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path, nargs="?")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    verify_manifest(manifest)
    if args.report is not None:
        verify_report(json.loads(args.report.read_text(encoding="utf-8")), manifest)
    print("ok")
