"""Replay the pinned 8001-point COM ERL-only S2P path twice from clean archives."""

from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import re
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from com_erl_exact_profile_replay_v3_support import (
    archive_materialize,
    canonical_json,
    linker_identity,
    discover_native_msvc,
    json_metric,
    path_free,
    sha256_bytes,
    sha256_file,
    tool_identity,
)
from pb_03_replay_common import windows_pe_replay_custody


CANDIDATE_COMMIT = "955835369c28aacb3f49bd0cf95f3660587739d8"
CANDIDATE_TREE = "fbb415e5582ccf3ee70e4d0d472f1fc6856e0e26"
CANDIDATE_ARCHIVE = "005e06d1ab680a7ddf41a2110c5e8ea9e44b020e04c5d4369a78f05c15ea79f0"
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
UPSTREAM_ARCHIVE = "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf"
FIXTURE_RELATIVE = "crates/sipi-agent-com-direct/tests/fixtures/erl_s2p_10db_at_26p56ghz.s2p"
FIXTURE_SHA256 = "7a59b41a385a95752d2d1159aab7772a10f7bd2c07e5122d770493151853c7a3"
FIXTURE_BYTES = 830969
FIXTURE_ROWS = 8001
RUNTIME_TIMEOUT_S = 180
BUILD_TIMEOUT_S = 900
METRIC_FIELDS = ("ERL", "ERL11", "ERL_RMS", "ERL_phase_index")
PROFILE = {
    "name": "r480_s2p_erl_v1",
    "samples_per_ui": 32,
    "levels": 4,
    "bin_size": 1.0e-5,
    "spec_ber": 1.0e-5,
    "rl_norm_test": True,
    "baud_hz": 53125000000,
    "sample_dt_s": 0.0000000000005882352941176471,
    "s_reference_ohm": 100,
    "zt_ohm": 50,
    "transition_time_ns": 0.01,
    "transition_filter_type": 1,
    "transition_measurement_point": 0,
    "receiver_cutoff_multiplier": 0.75,
    "receiver_filter_enabled": True,
    "tukey_enabled": True,
    "fixture_delay_s": 0,
    "tdr_delay_s": 0.0000000005,
    "observation_duration_ui": 800,
    "gate_n_bx": 0,
    "gate_rho_x": 0.618,
    "gate_grr": 1,
    "gate_beta_x_db_per_s": 0,
}
OUTER_CONTROLS = {key: PROFILE[key] for key in ("samples_per_ui", "levels", "bin_size", "spec_ber", "rl_norm_test")}
CONTROL_CROSSWALK = {
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


def runtime_control_projection(controls: dict[str, Any]) -> dict[str, Any]:
    fields = tuple(CONTROL_CROSSWALK["runtime_fields"])
    return {
        "outer": {key: controls["outer"][key] for key in OUTER_CONTROLS},
        "tdr_profile": {key: controls["tdr_profile"][key] for key in fields if key in controls["tdr_profile"]},
    }


def metric_equal(field: str, left: Any, right: Any) -> bool:
    if field == "ERL_phase_index":
        return left == right
    if left in {"inf", "-inf", "nan"} or right in {"inf", "-inf", "nan"}:
        return left == right
    return isinstance(left, (int, float)) and isinstance(right, (int, float)) and math.isclose(float(left), float(right), rel_tol=1.0e-12, abs_tol=1.0e-12)


def canonical_config(path: Path) -> None:
    document = {
        "parameters": {
            "samples_per_ui": 32.0,
            "LEVELS": 4.0,
            "bin_size": 1.0e-5,
            "A_v": 0.5,
            "R_LM": 50.0,
            "SNR_TX": 30.0,
            "sigma_X": 0.03,
            "sigma_RJ": 1.0e-4,
            "h_J": [0.3, 0.5, 0.2],
            "sigma_N": 0.01,
            "A_DD": 0.4,
            "spec_ber": 1.0e-5,
        },
        "portable": {"erl_only": {**OUTER_CONTROLS, "tdr_profile": PROFILE}},
    }
    path.write_bytes(canonical_json(document) + b"\n")


def write_blocked_report(path: Path, run_id: str, reason: str, toolchain: dict[str, Any] | None = None) -> None:
    report = {
        "schema": "sipi.com.erl-only.exact-profile-replay.v3",
        "run_id": run_id,
        "fresh_run_nonce": secrets.token_hex(32),
        "status": "external_blocked",
        "blocker": {"reason": reason},
        "candidate": {"commit": CANDIDATE_COMMIT, "tree": CANDIDATE_TREE, "archive_sha256": CANDIDATE_ARCHIVE, "materialization": "git archive; no working-tree overlay"},
        "upstream": {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE, "archive_sha256": UPSTREAM_ARCHIVE, "materialization": "git archive; no working-tree overlay"},
        "harness": {"required": True, "materialization": "future prep commit clean archive", "commit": "pending_harness_prep", "tree": "pending_harness_prep", "archive_sha256": "pending_harness_prep"},
        "execution": {"runner": {"path": "tools/run_com_erl_exact_profile_replay_v3.py", "sha256": sha256_file(Path(__file__).resolve())}, "helper": {"path": "tools/com_erl_exact_profile_replay_v3_support.py", "sha256": sha256_file(Path(__file__).with_name("com_erl_exact_profile_replay_v3_support.py"))}, "timeout_s": RUNTIME_TIMEOUT_S, "build_timeout_s": BUILD_TIMEOUT_S},
        "toolchain": toolchain or {},
        "candidate_custody": {"status": "not_available", "reason": "binary was not produced before block"},
        "input": {"fixture_relative": FIXTURE_RELATIVE, "fixture_sha256": FIXTURE_SHA256, "fixture_bytes": FIXTURE_BYTES, "fixture_rows": FIXTURE_ROWS, "fixture_copies": {"independent": True, "read_only": True, "pre_sha256": {"candidate": FIXTURE_SHA256, "upstream": FIXTURE_SHA256}, "post_sha256": {"candidate": FIXTURE_SHA256, "upstream": FIXTURE_SHA256}}, "controls": {"outer": OUTER_CONTROLS, "tdr_profile": PROFILE}},
        "non_claims": ["no_numeric_upstream_parity_claim", "no_release_or_promotion"],
    }
    if not path_free(report):
        raise RuntimeError("absolute path leaked into blocked report")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def upstream_probe(root: Path, fixture: Path, uv: Path, python: Path) -> dict[str, Any]:
    code = r'''
import json
from pathlib import Path
import numpy as np
from agent_com import load_config, run_com, ChannelSet, RunOptions, BehaviorProfile
root = Path.cwd()
fixture = Path(__FIXTURE__)
config = load_config(root / "matlab_src/config_com_ieee8023_93a=3ck_SA_120g_C2M_tp1a_08_17_2022.xlsx", overrides={"ERL_ONLY": 1, "TDR_W_TXPKG": 0, "N": 1})
materialized = config.materialize()
parameters = materialized.parameters
options = materialized.options
result = run_com(config=config, channels=ChannelSet(fixture), options=RunOptions(BehaviorProfile.r480(), diagnostics=True))
case = result.cases[0]
diag = case.diagnostics
def stage(values):
    a = np.asarray(values, dtype="<f8")
    if not np.all(np.isfinite(a)):
        raise RuntimeError("non-finite upstream stage")
    import hashlib
    return {"count": int(a.size), "sha256": hashlib.sha256(a.tobytes(order="C")).hexdigest()}
print(json.dumps({
    "metrics": {key: ("inf" if np.isposinf(case.metrics.get(key)) else "-inf" if np.isneginf(case.metrics.get(key)) else case.metrics.get(key)) for key in __METRICS__},
    "stages": {key: stage(diag[key]) for key in ("tdr_time_s", "tdr_impedance_ohm", "ptdr_gated")},
    "controls": {
        "outer": {"samples_per_ui": int(parameters["samples_per_ui"]), "levels": int(parameters["levels"]), "bin_size": float(options["BinSize"]), "spec_ber": float(parameters["specBER"]), "rl_norm_test": bool(options["RL_norm_test"])},
        "tdr_profile": {"name": "r480_s2p_erl_v1", "samples_per_ui": int(parameters["samples_per_ui"]), "levels": int(parameters["levels"]), "bin_size": float(options["BinSize"]), "spec_ber": float(parameters["specBER"]), "rl_norm_test": bool(options["RL_norm_test"]), "baud_hz": float(parameters["fb"]), "sample_dt_s": float(parameters["sample_dt"]), "s_reference_ohm": float(parameters["Z0"]), "zt_ohm": float(parameters["Z_t"]), "transition_time_ns": float(parameters["TR_TDR"]), "transition_filter_type": float(options["T_r_filter_type"]), "transition_measurement_point": float(options["T_r_meas_point"]), "receiver_cutoff_multiplier": float(parameters["f_r"]), "receiver_filter_enabled": bool(options["INCLUDE_FILTER"]), "tukey_enabled": bool(options.get("Tukey_Window", parameters.get("Tukey_Window", 1))), "fixture_delay_s": float(np.asarray(parameters["tfx"]).reshape(-1)[0]), "tdr_delay_s": float(options["T_k"]), "observation_duration_ui": float(options["TDR_duration"]), "gate_n_bx": int(parameters["N_bx"]), "gate_rho_x": float(parameters["rho_x"]), "gate_grr": float(parameters["Grr"]), "gate_beta_x_db_per_s": float(parameters["beta_x"])}
    },
    "diagnostic_keys": sorted(diag.keys()),
}, sort_keys=True))
'''.replace("__FIXTURE__", repr(str(fixture))).replace("__METRICS__", repr(list(METRIC_FIELDS)))
    env = {"PYTHONPATH": str(root / "src"), "UV_OFFLINE": "1", "PYTHONNOUSERSITE": "1"}
    command = upstream_command(uv, python, code)
    try:
        completed = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=RUNTIME_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "timeout_s": RUNTIME_TIMEOUT_S}
    if completed.returncode != 0:
        return {"status": "failed", "returncode": completed.returncode, "stderr_sha256": sha256_bytes(completed.stderr)}
    lines = completed.stdout.decode(errors="strict").splitlines()
    payload = json.loads(lines[-1])
    payload["status"] = "ok"
    return payload


def upstream_command(uv: Path, python: Path, code: str) -> list[str]:
    return [str(uv), "run", "--frozen", "--project", ".", "--python", str(python), "python", "-c", code]


def resolve_linker(rustc: Path, requested: Path | None) -> Path:
    completed = subprocess.run([str(rustc.resolve()), "--print", "sysroot"], capture_output=True, timeout=RUNTIME_TIMEOUT_S, check=False)
    if completed.returncode != 0:
        raise RuntimeError("rustc sysroot probe failed")
    sysroot = Path(completed.stdout.decode("utf-8", errors="strict").strip())
    linker = (sysroot / "lib" / "rustlib" / "x86_64-pc-windows-msvc" / "bin" / "rust-lld.exe").resolve()
    if requested is not None and requested.resolve() != linker:
        raise RuntimeError("linker override does not equal rustc-derived rust-lld")
    if not linker.is_file():
        raise RuntimeError("resolved rust-lld linker is missing")
    return linker


def candidate_probe(binary: Path, config: Path, fixture: Path, output: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [str(binary), "run", "--config", str(config), "--thru", str(fixture), "--output-dir", str(output), "--overwrite"],
            capture_output=True,
            timeout=RUNTIME_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "timeout_s": RUNTIME_TIMEOUT_S}
    if completed.returncode != 0:
        return {"status": "failed", "returncode": completed.returncode, "stderr_sha256": sha256_bytes(completed.stderr)}
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    case = result["cases"][0]
    diagnostics = case["diagnostics"]
    branches = diagnostics["portable_branches"]
    erl = branches["erl_only"]
    return {
        "status": "ok",
        "metrics": {key: json_metric(case["metrics"].get(key)) for key in METRIC_FIELDS},
        "stages": {
            "channel_impulse": diagnostics["channel_impulse"],
            "channel_pulse": diagnostics["channel_pulse"],
            "erl_impulse": {"count": erl["impulse_sample_count"], "sha256": erl["impulse_sha256"]},
            "ptdr": {"count": erl["ptdr_sample_count"], "sha256": erl["ptdr_sha256"]},
            "gated": {"count": erl["gated_sample_count"], "sha256": erl["gated_sha256"]},
        },
        "dispatch": erl["dispatch"],
        "artifact_sha256": sha256_file(output / "result.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--agent-com-root", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--linker", type=Path)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--git", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"com-erl-exact-v3-run[12]", args.run_id):
        raise SystemExit("run_id must be com-erl-exact-v3-run1 or com-erl-exact-v3-run2")
    report_relative = Path(args.report)
    if report_relative.is_absolute() or report_relative.as_posix() != f"docs/baselines/com-erl-exact-profile-replay-v3-{args.run_id[-4:]}.json":
        raise SystemExit("report must be the strict repo-relative v3 run path")
    report_path = (args.repo.resolve() / report_relative).resolve()
    if args.repo.resolve() not in report_path.parents:
        raise SystemExit("report escapes repository")
    try:
        native = discover_native_msvc()
        linker = resolve_linker(args.rustc, args.linker)
        preflight_toolchain = {"git": tool_identity(args.git.resolve(), RUNTIME_TIMEOUT_S), "cargo": tool_identity(args.cargo.resolve(), RUNTIME_TIMEOUT_S), "rustc": tool_identity(args.rustc.resolve(), RUNTIME_TIMEOUT_S), "uv": tool_identity(args.uv.resolve(), RUNTIME_TIMEOUT_S), "python": tool_identity(args.python.resolve(), RUNTIME_TIMEOUT_S), "linker": linker_identity(linker, RUNTIME_TIMEOUT_S), "compiler": native["msvc"]["compiler"], "msvc": native["msvc"], "sdk": native["sdk"]}
    except (OSError, subprocess.SubprocessError):
        write_blocked_report(report_path, args.run_id, "tool_identity_unavailable")
        return 2
    identity_roles = ("git", "cargo", "rustc", "uv", "python", "linker", "compiler")
    if any(preflight_toolchain[role].get("status") not in {"ok", "ok_generic_driver", "ok_no_source"} or not preflight_toolchain[role].get("path_redacted") for role in identity_roles):
        write_blocked_report(report_path, args.run_id, "tool_identity_failed", preflight_toolchain)
        return 2
    runner = Path(__file__).resolve()
    helper = runner.with_name("com_erl_exact_profile_replay_v3_support.py")
    with tempfile.TemporaryDirectory(prefix="com-erl-exact-v3-") as directory:
        temp = Path(directory)
        upstream = temp / "upstream"
        candidate = temp / "candidate"
        upstream_sha = archive_materialize(args.git.resolve(), args.agent_com_root.resolve(), UPSTREAM_COMMIT, upstream, UPSTREAM_ARCHIVE)
        candidate_sha = archive_materialize(args.git.resolve(), args.repo.resolve(), CANDIDATE_COMMIT, candidate, CANDIDATE_ARCHIVE)
        fixture = candidate / FIXTURE_RELATIVE
        fixture_bytes = fixture.read_bytes()
        fixture_sha = sha256_bytes(fixture_bytes)
        rows = [line for line in fixture_bytes.decode("ascii").splitlines() if line.strip() and not line.lstrip().startswith(("!", "#"))]
        if fixture_sha != FIXTURE_SHA256 or len(fixture_bytes) != FIXTURE_BYTES or len(rows) != FIXTURE_ROWS:
            raise RuntimeError("pinned 8001-point fixture identity drift")
        candidate_fixture = temp / "candidate-input.s2p"
        upstream_fixture = temp / "upstream-input.s2p"
        candidate_fixture.write_bytes(fixture_bytes)
        upstream_fixture.write_bytes(fixture_bytes)
        for copied_fixture in (candidate_fixture, upstream_fixture):
            copied_fixture.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        copy_pre_sha = {"candidate": sha256_file(candidate_fixture), "upstream": sha256_file(upstream_fixture)}
        config = temp / "config.json"
        canonical_config(config)
        target = candidate / "target"
        compiler_temp = temp / "compiler-temp"
        compiler_temp.mkdir()
        tool_dirs = [args.cargo.resolve().parent, args.rustc.resolve().parent, args.uv.resolve().parent, args.python.resolve().parent, args.git.resolve().parent, linker.parent, native["bin_dir"]]
        windows_root = Path("C:/Windows")
        if not windows_root.is_dir() or not (windows_root / "System32" / "cmd.exe").is_file():
            raise RuntimeError("Windows system root is unavailable")
        env = {"PATH": os.pathsep.join(str(path) for path in tool_dirs), "RUSTC": str(args.rustc.resolve()), "RUSTC_WRAPPER": "", "CARGO_BUILD_RUSTC_WRAPPER": "", "RUSTC_WORKSPACE_WRAPPER": "", "CARGO_INCREMENTAL": "0", "CARGO_NET_OFFLINE": "true", "UV_OFFLINE": "1", "SystemRoot": str(windows_root), "windir": str(windows_root), "ComSpec": str(windows_root / "System32" / "cmd.exe"), "PATHEXT": ".COM;.EXE;.BAT;.CMD"}
        env["RUSTC"] = str(args.rustc.resolve())
        env["RUSTC_WRAPPER"] = ""
        env["CARGO_BUILD_RUSTC_WRAPPER"] = ""
        env["RUSTC_WORKSPACE_WRAPPER"] = ""
        env["CARGO_INCREMENTAL"] = "0"
        env["CARGO_NET_OFFLINE"] = "true"
        env["CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER"] = str(linker)
        env["CC_x86_64-pc-windows-msvc"] = str(native["compiler_path"])
        env["CXX_x86_64-pc-windows-msvc"] = str(native["compiler_path"])
        env["INCLUDE"] = os.pathsep.join(str(path) for path in native["include_dirs"])
        env["LIB"] = os.pathsep.join(str(path) for path in native["lib_dirs"])
        env["TEMP"] = str(compiler_temp)
        env["TMP"] = str(compiler_temp)
        env["CARGO_TARGET_DIR"] = str(target)
        try:
            build = subprocess.run([str(args.cargo.resolve()), "build", "--release", "--offline", "--manifest-path", str(candidate / "crates/sipi-agent-com-direct/Cargo.toml"), "--locked", "--bin", "sipi-com-direct-run"], cwd=candidate, env=env, capture_output=True, timeout=BUILD_TIMEOUT_S, check=False)
        except subprocess.TimeoutExpired:
            build = None
        if build is None:
            write_blocked_report(report_path, args.run_id, "candidate_release_build_timeout", preflight_toolchain)
            return 2
        if build.returncode != 0:
            raise RuntimeError("candidate release build failed: " + build.stderr.decode(errors="replace")[-2000:])
        binary = target / "release" / ("sipi-com-direct-run.exe" if os.name == "nt" else "sipi-com-direct-run")
        upstream_started = time.monotonic()
        upstream_payload = upstream_probe(upstream, upstream_fixture, args.uv.resolve(), args.python.resolve())
        upstream_elapsed = round(time.monotonic() - upstream_started, 6)
        candidate_payload = candidate_probe(binary, config, candidate_fixture, temp / "artifacts")
        copy_post_sha = {"candidate": sha256_file(candidate_fixture), "upstream": sha256_file(upstream_fixture)}
        if upstream_payload.get("status") != "ok" or candidate_payload.get("status") != "ok":
            write_blocked_report(report_path, args.run_id, "runtime_blocked", preflight_toolchain)
            return 2
        stage_mapping = {"ptdr_gated": ("ptdr_gated", "gated")}
        stage_contract = {"ptdr_gated": {"upstream": "ptdr_gated", "candidate": "gated"}, "ptdr_raw": {"status": "diagnostic_only_upstream_api_does_not_expose_raw_ptdr", "compared": False}}
        stage_differences = {
            name: {"upstream": upstream_payload["stages"].get(upstream_name), "candidate": candidate_payload["stages"].get(candidate_name)}
            for name, (upstream_name, candidate_name) in stage_mapping.items()
            if upstream_payload["stages"].get(upstream_name) != candidate_payload["stages"].get(candidate_name)
        }
        differences = {key: {"upstream": upstream_payload["metrics"].get(key), "candidate": candidate_payload["metrics"].get(key)} for key in METRIC_FIELDS if not metric_equal(key, upstream_payload["metrics"].get(key), candidate_payload["metrics"].get(key))}
        candidate_controls = {"outer": OUTER_CONTROLS, "tdr_profile": PROFILE}
        controls_equal = runtime_control_projection(upstream_payload["controls"]) == runtime_control_projection(candidate_controls)
        report = {
            "schema": "sipi.com.erl-only.exact-profile-replay.v3",
            "run_id": args.run_id,
            "fresh_run_nonce": secrets.token_hex(32),
            "path_policy": {"mode": "relative identities only", "absolute_paths_emitted": False},
            "candidate": {"commit": CANDIDATE_COMMIT, "tree": CANDIDATE_TREE, "archive_sha256": candidate_sha, "materialization": "git archive; no working-tree overlay", "binary_sha256": sha256_file(binary), "binary_custody": windows_pe_replay_custody(binary), "runtime_executed": True, "cargo_lock_sha256": sha256_file(candidate / "Cargo.lock")},
            "upstream": {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE, "archive_sha256": upstream_sha, "materialization": "git archive; no working-tree overlay", "runtime_executed": True, "uv_lock_sha256": sha256_file(upstream / "uv.lock"), "pyproject_sha256": sha256_file(upstream / "pyproject.toml")},
            "input": {"fixture_relative": FIXTURE_RELATIVE, "fixture_sha256": fixture_sha, "fixture_bytes": len(fixture_bytes), "fixture_rows": len(rows), "fixture_copies": {"pre_sha256": copy_pre_sha, "post_sha256": copy_post_sha, "independent": True, "read_only": True}, "config_sha256": sha256_file(config), "upstream_workbook_sha256": sha256_file(upstream / "matlab_src/config_com_ieee8023_93a=3ck_SA_120g_C2M_tp1a_08_17_2022.xlsx"), "channel_kind": "exact_s2p_erl_only", "s_parameter_fit": "forbidden", "channel_policy": "raw S11 FD-to-TD impulse; no fit", "controls": {"outer": OUTER_CONTROLS, "tdr_profile": PROFILE}},
            "control_crosswalk": {"candidate_profile": candidate_controls, "upstream_materialized": upstream_payload["controls"], "runtime_projection": {"candidate": runtime_control_projection(candidate_controls), "upstream": runtime_control_projection(upstream_payload["controls"])}, "mapping": CONTROL_CROSSWALK, "status": "matched" if controls_equal else "numeric_mismatch_open"},
            "stage_payload": {"mapping": stage_contract, "upstream": upstream_payload["stages"], "candidate": candidate_payload["stages"], "upstream_diagnostic_keys": upstream_payload["diagnostic_keys"], "candidate_dispatch": candidate_payload["dispatch"], "ptdr": {"status": "diagnostic_only_upstream_api_does_not_expose_raw_ptdr", "compared": False}},
            "upstream_output": upstream_payload["metrics"],
            "candidate_output": candidate_payload["metrics"],
            "artifact": {"candidate_result_sha256": candidate_payload["artifact_sha256"]},
            "toolchain": {"git": tool_identity(args.git.resolve(), RUNTIME_TIMEOUT_S), "cargo": tool_identity(args.cargo.resolve(), RUNTIME_TIMEOUT_S), "rustc": tool_identity(args.rustc.resolve(), RUNTIME_TIMEOUT_S), "uv": tool_identity(args.uv.resolve(), RUNTIME_TIMEOUT_S), "python": tool_identity(args.python.resolve(), RUNTIME_TIMEOUT_S), "linker": linker_identity(linker, RUNTIME_TIMEOUT_S), "compiler": native["msvc"]["compiler"], "msvc": native["msvc"], "sdk": native["sdk"], "rustc_wrapper": "cleared", "cargo_build_rustc_wrapper": "cleared", "rustc_workspace_wrapper": "cleared", "cargo_incremental": "0", "cargo_offline": True, "uv_offline": True},
            "execution": {"runner": {"path": "tools/run_com_erl_exact_profile_replay_v3.py", "sha256": sha256_file(runner)}, "helper": {"path": "tools/com_erl_exact_profile_replay_v3_support.py", "sha256": sha256_file(helper)}, "timeout_s": RUNTIME_TIMEOUT_S, "build_timeout_s": BUILD_TIMEOUT_S, "upstream_elapsed_s": upstream_elapsed, "candidate_timeout_s": RUNTIME_TIMEOUT_S, "candidate_build_exit": build.returncode, "build_profile": "release", "locked": True},
            "parity": {"fields": list(METRIC_FIELDS), "numeric_policy": {"float_fields": ["ERL", "ERL11", "ERL_RMS"], "atol": 1.0e-12, "rtol": 1.0e-12, "phase_field": "ERL_phase_index", "phase_policy": "exact"}, "matched": not differences and not stage_differences and controls_equal, "differences": differences, "stage_differences": stage_differences, "controls_equal": controls_equal, "status": "matched" if not differences and not stage_differences and controls_equal else "numeric_mismatch_open"},
            "non_claims": ["no_s_parameter_fit", "no_release_or_promotion", "no_global_migration_row_close"],
        }
        if not path_free(report):
            raise RuntimeError("absolute path leaked into report")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": report["schema"], "run_id": report["run_id"], "matched": report["parity"]["matched"], "report_sha256": sha256_file(report_path)}, sort_keys=True))
    return 0 if report["parity"]["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
