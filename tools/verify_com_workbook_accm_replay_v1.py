"""Fail-closed verifier for the COM workbook/ACCM preparation schema."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any

REPORT_SCHEMA = "sipi.com.workbook-accm-replay-prep.v3"
AGGREGATE_SCHEMA = "sipi.com.workbook-accm-replay-aggregate-prep.v3"
CANDIDATE = {"commit": "2f751b6c5f4387e9f043e7d629fb103945d12fdf", "tree": "6e235fafe6cd77cd7916af67cb370869570d32c6", "archive": {"command": "git -c core.autocrlf=false archive --format=tar <candidate>", "exit": 0, "bytes": 44605440, "sha256": "4ad001e4ea2419bb5cd7c9817eb8a178cea831bd1eeb5f943db916cfccc1c329"}}
UPSTREAM = {"commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "tree": "7094ab6e84989b218730c52432c70da10261f8ea", "runtime": "not_executed_external_only"}
FIXTURE_KEYS = ("workbook", "s4p")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PATH_LEAK = re.compile(r"(?i)(?:^|[\s=(\[\{\"'])(?:[A-Za-z]:[\\/]|\\\\|/|file://|\.\.?[\\/])")
SOURCE_PATHS = ("src/agent_com/api.py", "src/agent_com/_orchestration.py", "src/agent_com/network/package.py", "src/agent_com/network/two_port.py", "src/agent_com/signal/fd_to_td.py", "src/agent_com/equalization/search.py")
EXPECTED_SOURCE_INVENTORY = {
    "src/agent_com/api.py": {"git_blob_sha1": "3e7808982a63123f2bac65a86f3abb627c287be1", "bytes": 21445, "sha256": "b7527f60d55b6f73fb449bc2472f957a6bc2a9ecf1d7bc8808756bf7fba39570", "license": "MIT"},
    "src/agent_com/_orchestration.py": {"git_blob_sha1": "5d260a0aab941f1a1955fe3abef36d85a56034c0", "bytes": 90877, "sha256": "069a5c08f9da6ad5b5be5648723eb05b0e3de8cf0dcb1ae7f54e23df7ab0db69", "license": "MIT"},
    "src/agent_com/network/package.py": {"git_blob_sha1": "55e2aae5669c4f3ba7acd453fba82f4eaebfdb4f", "bytes": 22300, "sha256": "bc3bd4bc3dd01317041a674b88690d6cd94f0589113b44576a1afee4aa8bbd32", "license": "MIT"},
    "src/agent_com/network/two_port.py": {"git_blob_sha1": "6b1484effc18a25fe8c28373b47f55b0b99b0f4b", "bytes": 9600, "sha256": "8889d9695a56d83a59a771d938ba8084dbdfec6a24d79e14d88b83c678ddcd6a", "license": "MIT"},
    "src/agent_com/signal/fd_to_td.py": {"git_blob_sha1": "6f3af024ea20df0011843ea19a090788f1aabbc9", "bytes": 5831, "sha256": "703a360837cbaa18494ee03ba8df8d908dc6bf3c516d80d3dddf83af6637c687", "license": "MIT"},
    "src/agent_com/equalization/search.py": {"git_blob_sha1": "58f6e5e3f8f36b94faddf0248f3df2ff11e1e3cd", "bytes": 53859, "sha256": "924930c43332f169ce1d66048d3f70610c8bf459af2f0210d6995533c277003d", "license": "MIT"},
}
EXPECTED_FIXTURES = {"workbook": {"path": "matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx", "git_blob_sha1": "22b633b6092b4b0de0ca89273515329b362eabae", "bytes": 67087, "sha256": "e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925"}, "s4p": {"path": "fixtures/synthetic/kappa_asymmetric_reflective_10db_at_26p56ghz.s4p", "git_blob_sha1": "a1fe8618043b31f63dfb24454ac1d296000010c0", "bytes": 6457063, "sha256": "3a563543ba664fcc04c1ac5603ad305cb0b1d110c3d9020727444b1c3fd2d0ec"}}
REPORT_KEYS = {"schema", "run_id", "nonce", "candidate", "upstream", "fixtures", "toolchain", "build", "execution", "controls", "runs", "parity", "non_claims"}
RESULT_KEYS = {"schema_version", "source_revision", "profile", "cases", "provenance", "warnings", "timings_s", "input_manifest", "report_manifest"}
ENV_KEYS = ("SystemRoot", "ComSpec", "PATHEXT", "WINDIR", "PATH", "LIB", "LIBPATH", "INCLUDE", "VCINSTALLDIR", "VCToolsInstallDir", "WindowsSdkDir", "WindowsSDKVersion", "UCRTVersion", "UniversalCRTSdkDir", "TEMP", "TMP", "CARGO_HOME", "RUSTC", "CARGO_BUILD_RUSTC", "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "CARGO_BUILD_RUSTC_WRAPPER", "CARGO_INCREMENTAL", "CARGO_NET_OFFLINE", "CL", "LINK")
ENV_ROLES = {"SystemRoot": "system_root", "ComSpec": "cmd", "PATHEXT": "system_path_ext", "WINDIR": "system_root", "TEMP": "fresh_run_temp", "TMP": "fresh_run_temp", "CARGO_HOME": "cargo_home", "RUSTC": "resolved_tool", "CARGO_BUILD_RUSTC": "resolved_tool", "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER": "resolved_tool", "RUSTC_WRAPPER": "cleared_wrapper", "RUSTC_WORKSPACE_WRAPPER": "cleared_wrapper", "CARGO_BUILD_RUSTC_WRAPPER": "cleared_wrapper", "CARGO_INCREMENTAL": "incremental_zero", "CARGO_NET_OFFLINE": "offline", "CL": "cleared_compiler_override", "LINK": "cleared_linker_override"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hex64(value: Any, label: str) -> None:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise ValueError(f"invalid {label}")


def path_free(value: Any) -> None:
    if isinstance(value, str):
        if value == "<abs-path>":
            return
        if value in {"/Bv", "/?", "/nologo", "/d", "/c"}:
            return
        if "<abs-path>" in value:
            raise ValueError("embedded redaction token")
        normalized = value.replace("\\", "/")
        if PATH_LEAK.search(normalized) or "/../" in normalized or normalized.endswith("/.."):
            raise ValueError("absolute path leaked")
    elif isinstance(value, dict):
        for item in value.values():
            path_free(item)
    elif isinstance(value, list):
        for item in value:
            path_free(item)


def exact(value: dict[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise ValueError(f"{label} key set drift")


def stable_candidate(value: dict[str, Any]) -> dict[str, Any]:
    """Cross-run custody keeps canonical PE identity, not volatile raw bytes."""
    result = json.loads(json.dumps(value))
    for name in ("binary_pre", "binary"):
        result[name].pop("sha256", None)
    return result


def verify_report(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    exact(value, REPORT_KEYS, "report")
    if value["schema"] != REPORT_SCHEMA:
        raise ValueError("wrong report schema")
    if not isinstance(value["run_id"], str) or len(value["run_id"]) != 64 or value["run_id"] != value["run_id"].lower() or not HEX64.fullmatch(value["run_id"]):
        raise ValueError("invalid run id")
    hex64(value["nonce"], "nonce")
    candidate = value["candidate"]
    exact(candidate, {"commit", "tree", "archive", "binary_pre", "binary"}, "candidate")
    if candidate["commit"] != CANDIDATE["commit"] or candidate["tree"] != CANDIDATE["tree"] or candidate["archive"] != CANDIDATE["archive"]:
        raise ValueError("candidate identity drift")
    for binary in (candidate["binary_pre"], candidate["binary"]):
        exact(binary, {"basename", "exists", "bytes", "sha256", "canonical_sha256"}, "binary")
        if not isinstance(binary["basename"], str) or Path(binary["basename"]).name != binary["basename"] or not isinstance(binary["exists"], bool) or not isinstance(binary["bytes"], int) or isinstance(binary["bytes"], bool) or binary["bytes"] < 0:
            raise ValueError("binary custody invalid")
        if binary["exists"]:
            hex64(binary["sha256"], "binary sha")
            hex64(binary["canonical_sha256"], "binary canonical sha")
        elif binary["sha256"] is not None:
            raise ValueError("missing binary cannot have sha")
        elif binary["canonical_sha256"] is not None:
            raise ValueError("missing binary cannot have canonical sha")
    if candidate["binary_pre"] != candidate["binary"]:
        raise ValueError("binary custody changed during runtime")
    if value["upstream"] != {**UPSTREAM, "source_inventory": value["upstream"].get("source_inventory")}:
        raise ValueError("upstream identity drift")
    inventory = value["upstream"]["source_inventory"]
    if set(inventory) != set(SOURCE_PATHS):
        raise ValueError("source inventory drift")
    if inventory != EXPECTED_SOURCE_INVENTORY:
        raise ValueError("source inventory is not pinned")
    for item in inventory.values():
        exact(item, {"git_blob_sha1", "bytes", "sha256", "license"}, "source inventory")
        if not isinstance(item["git_blob_sha1"], str) or not re.fullmatch(r"[0-9a-f]{40}", item["git_blob_sha1"]) or item["license"] != "MIT" or not isinstance(item["bytes"], int) or isinstance(item["bytes"], bool) or item["bytes"] < 0:
            raise ValueError("source inventory identity invalid")
        hex64(item["sha256"], "source sha")
    fixtures = value["fixtures"]
    if set(fixtures) != set(FIXTURE_KEYS):
        raise ValueError("fixture key drift")
    for key in FIXTURE_KEYS:
        item = fixtures[key]
        expected_fixture = EXPECTED_FIXTURES[key] | {"basename": Path(EXPECTED_FIXTURES[key]["path"]).name, "source_commit": UPSTREAM["commit"], "pre_sha256": EXPECTED_FIXTURES[key]["sha256"], "post_sha256": EXPECTED_FIXTURES[key]["sha256"]}
        if item != expected_fixture:
            raise ValueError(f"{key} fixture identity drift")
    toolchain = value["toolchain"]
    if set(toolchain) != {"pre", "post", "vcvars64_pre", "vcvars64_post", "native_pre", "native_post"} or toolchain["pre"] != toolchain["post"] or toolchain["vcvars64_pre"] != toolchain["vcvars64_post"] or toolchain["native_pre"] != toolchain["native_post"]:
        raise ValueError("toolchain role drift")
    if set(toolchain["pre"]) != {"cargo", "rustc", "linker", "cmd"}:
        raise ValueError("toolchain roles drift")
    for role, item in toolchain["pre"].items():
        exact(item, {"role", "basename", "file_sha256", "version_args", "version_output_sha256", "version_exit", "timeout_s", "path_redacted"}, f"{role} identity")
        if item["role"] != role or not isinstance(item["basename"], str) or Path(item["basename"]).name != item["basename"] or item["version_exit"] != 0 or item["timeout_s"] != 15 or item["path_redacted"] is not True:
            raise ValueError("tool identity invalid")
        if role == "cmd" and item["basename"].lower() != "cmd.exe":
            raise ValueError("cmd identity must be cmd.exe")
        hex64(item["file_sha256"], "tool file sha")
        hex64(item["version_output_sha256"], "tool version sha")
        expected_args = ["-flavor", "link", "--version"] if role == "linker" and item["basename"].lower() == "rust-lld.exe" else ["/d", "/c", "ver"] if role == "cmd" else ["--version"]
        if item["version_args"] != expected_args:
            raise ValueError("tool version probe args drift")
    vcvars = toolchain["vcvars64_pre"]
    exact(vcvars, {"role", "basename", "bytes", "file_sha256", "path_redacted"}, "vcvars64 identity")
    if vcvars["role"] != "vcvars64" or vcvars["basename"].lower() != "vcvars64.bat" or not isinstance(vcvars["bytes"], int) or isinstance(vcvars["bytes"], bool) or vcvars["bytes"] <= 0 or vcvars["path_redacted"] is not True:
        raise ValueError("vcvars64 identity invalid")
    hex64(vcvars["file_sha256"], "vcvars64 file sha")
    for group_name in ("native_pre", "native_post"):
        group = toolchain[group_name]
        if not isinstance(group, dict) or set(group) != {"cl", "lib", "rc"}:
            raise ValueError("native tool role drift")
        for role, item in group.items():
            exact(item, {"role", "basename", "file_sha256", "version_args", "version_output_sha256", "version_exit", "timeout_s", "path_redacted"}, f"native {role} identity")
            expected_args = ["/nologo", "/?"] if role == "cl" else ["/Bv"] if role == "lib" else ["/?"]
            if item["role"] != role or item["basename"].lower() != f"{role}.exe" or item["version_args"] != expected_args or item["version_exit"] != 0 or item["timeout_s"] != 15 or item["path_redacted"] is not True:
                raise ValueError("native tool identity invalid")
            hex64(item["file_sha256"], "native tool file sha")
            hex64(item["version_output_sha256"], "native tool version sha")
    exact(value["build"], {"command", "exit", "stdout_sha256", "stderr_sha256", "timeout_s", "env_policy", "env_receipt"}, "build")
    if not isinstance(value["build"]["exit"], int) or isinstance(value["build"]["exit"], bool) or not 0 <= value["build"]["exit"] <= 255 or value["build"]["timeout_s"] != 900 or "offline" not in value["build"]["command"] or value["build"]["env_policy"] != "vcvars64_allowlist_rustc_wrappers_cleared_offline_incremental_zero":
        raise ValueError("build policy drift")
    hex64(value["build"]["stdout_sha256"], "build stdout sha")
    hex64(value["build"]["stderr_sha256"], "build stderr sha")
    receipt = value["build"]["env_receipt"]
    if set(receipt) != set(ENV_KEYS):
        raise ValueError("native environment receipt drift")
    for key, item in receipt.items():
        exact(item, {"role", "exists", "entry_basenames", "value_sha256", "path_redacted", "relation"}, "native environment receipt")
        expected_role = ENV_ROLES.get(key, "native_environment")
        if item["role"] != expected_role or item["exists"] is not True or not isinstance(item["entry_basenames"], list) or any(not isinstance(entry, str) or Path(entry).name != entry for entry in item["entry_basenames"]) or item["path_redacted"] is not True:
            raise ValueError("native environment receipt invalid")
        hex64(item["value_sha256"], "environment sha")
        expected_relation = "system_root" if key in {"SystemRoot", "WINDIR"} else "system32_under_system_root" if key == "ComSpec" else None
        if item["relation"] != expected_relation:
            raise ValueError("native environment relation drift")
    if [entry.casefold() for entry in receipt["SystemRoot"]["entry_basenames"]] != ["windows"] or [entry.casefold() for entry in receipt["WINDIR"]["entry_basenames"]] != ["windows"]:
        raise ValueError("system root receipt drift")
    if receipt["SystemRoot"]["value_sha256"] != receipt["WINDIR"]["value_sha256"]:
        raise ValueError("system root value drift")
    if receipt["ComSpec"]["entry_basenames"] != ["cmd.exe"] or receipt["ComSpec"]["relation"] != "system32_under_system_root":
        raise ValueError("cmd environment receipt drift")
    if receipt["CARGO_HOME"]["entry_basenames"] != [".cargo"]:
        raise ValueError("cargo home receipt drift")
    if receipt["RUSTC"]["entry_basenames"] != ["rustc.exe"] or receipt["CARGO_BUILD_RUSTC"]["entry_basenames"] != ["rustc.exe"] or receipt["RUSTC"]["value_sha256"] != receipt["CARGO_BUILD_RUSTC"]["value_sha256"]:
        raise ValueError("rustc environment crosswalk drift")
    if receipt["CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER"]["entry_basenames"] != ["rust-lld.exe"]:
        raise ValueError("linker environment crosswalk drift")
    for key in ("TEMP", "TMP"):
        if receipt[key]["entry_basenames"] != ["<fresh-run-temp>"] or receipt[key]["value_sha256"] != hashlib.sha256(b"<fresh-run-temp>").hexdigest():
            raise ValueError("fresh temp receipt drift")
    for key in ("RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "CARGO_BUILD_RUSTC_WRAPPER", "CL", "LINK"):
        if receipt[key]["entry_basenames"] or receipt[key]["value_sha256"] != hashlib.sha256(b"").hexdigest():
            raise ValueError("cleared override receipt drift")
    if receipt["CARGO_INCREMENTAL"]["entry_basenames"] != ["0"] or receipt["CARGO_NET_OFFLINE"]["entry_basenames"] != ["true"] or receipt["CARGO_INCREMENTAL"]["value_sha256"] != hashlib.sha256(b"0").hexdigest() or receipt["CARGO_NET_OFFLINE"]["value_sha256"] != hashlib.sha256(b"true").hexdigest():
        raise ValueError("cargo policy receipt drift")
    execution = value["execution"]
    exact(execution, {"runtime_timeout_s", "source_inventory_before", "source_inventory_after", "source_inventory_equal"}, "execution")
    if execution["runtime_timeout_s"] != 180 or execution["source_inventory_before"] != execution["source_inventory_after"] or execution["source_inventory_equal"] is not True:
        raise ValueError("execution custody drift")
    controls = value["controls"]
    exact(controls, {"ac_cm_rms_vectors", "source", "no_sparam_fit", "channel_policy"}, "controls")
    if controls["ac_cm_rms_vectors"] != [[0.0, 0.0], [0.0, 0.001]] or controls["source"] != "pinned workbook vector override" or controls["no_sparam_fit"] is not True or controls["channel_policy"] != "single_fd_to_td_impulse":
        raise ValueError("control policy drift")
    if len(value["runs"]) != 2 or len({tuple(run.get("control_vector", [])) for run in value["runs"]}) != 2:
        raise ValueError("run count drift")
    matched_artifacts: list[dict[str, Any]] = []
    for run in value["runs"]:
        exact(run, {"control_vector", "status", "exit", "stdout_sha256", "stderr_sha256", "final_metrics", "consumer_proof", "artifact", "blocker"}, "run")
        if run["control_vector"] not in controls["ac_cm_rms_vectors"] or not isinstance(run["exit"], int) or isinstance(run["exit"], bool) or run["status"] not in {"blocked", "artifact_invalid", "matched"}:
            raise ValueError("run policy drift")
        hex64(run["stdout_sha256"], "run stdout sha")
        hex64(run["stderr_sha256"], "run stderr sha")
        if run["status"] in {"blocked", "artifact_invalid"}:
            if run["status"] == "blocked" and run["exit"] == 0:
                raise ValueError("blocked run cannot have successful exit")
            if run["status"] == "artifact_invalid" and run["exit"] != 0:
                raise ValueError("artifact-invalid run must have successful process exit")
            if run["exit"] == 0 or run["consumer_proof"] is not False or run["final_metrics"] is not None or run["artifact"] is not None or not isinstance(run["blocker"], str):
                if run["status"] == "blocked":
                    raise ValueError("blocked run promotion")
            if run["status"] == "artifact_invalid" and (run["consumer_proof"] is not False or run["final_metrics"] is not None or run["artifact"] is not None or not isinstance(run["blocker"], str)):
                raise ValueError("invalid artifact promotion")
        else:
            if run["exit"] != 0 or run["consumer_proof"] is not True or run["blocker"] is not None or not isinstance(run["final_metrics"], dict) or not run["final_metrics"]:
                raise ValueError("matched run lacks consumer proof")
            if set(run["final_metrics"]) != {str(index) for index in range(len(controls["ac_cm_rms_vectors"]))}:
                raise ValueError("matched metrics are not aligned to all controls")
            for metrics in run["final_metrics"].values():
                if not isinstance(metrics, dict) or set(metrics) != {"FOM_dB", "COM_dB", "sigma_N_V"} or any(not isinstance(metric, (int, float)) or isinstance(metric, bool) or not math.isfinite(metric) for metric in metrics.values()):
                    raise ValueError("non-numeric final metric")
            artifact = run["artifact"]
            if not isinstance(artifact, dict) or set(artifact) != {"path", "bytes", "sha256", "raw_bytes", "raw_sha256", "case_metrics"} or not isinstance(artifact["path"], str) or Path(artifact["path"]).name != artifact["path"] or not isinstance(artifact["bytes"], int) or isinstance(artifact["bytes"], bool) or artifact["bytes"] <= 0 or not isinstance(artifact["raw_bytes"], int) or isinstance(artifact["raw_bytes"], bool) or artifact["raw_bytes"] <= 0 or artifact["raw_bytes"] > 64 * 1024 * 1024:
                raise ValueError("result artifact custody drift")
            hex64(artifact["sha256"], "result artifact sha")
            hex64(artifact["raw_sha256"], "raw result sha")
            artifact_path = path.parent / artifact["path"]
            if not artifact_path.is_file() or artifact_path.stat().st_size != artifact["bytes"] or sha(artifact_path) != artifact["sha256"]:
                raise ValueError("result artifact physical hash drift")
            artifact_value = json.loads(artifact_path.read_text(encoding="utf-8"))
            if not isinstance(artifact_value, dict) or set(artifact_value) != {"schema", "control_vector", "cases", "metric_fields", "channel_policy"} or artifact_value["schema"] != "sipi.com.workbook-accm-canonical-metrics.v1" or artifact_value["metric_fields"] != ["FOM_dB", "COM_dB", "sigma_N_V"] or artifact_value["channel_policy"] != "single_fd_to_td_impulse" or artifact_value["control_vector"] != run["control_vector"] or not isinstance(artifact_value["cases"], list) or not artifact_value["cases"]:
                raise ValueError("result artifact schema drift")
            path_free(artifact_value)
            parsed = {}
            for case in artifact_value["cases"]:
                if not isinstance(case, dict) or not set(case).issubset({"case_index", "ac_cm_rms", "metrics", "case_id", "package_case_index", "channel_identity"}) or not {"case_index", "ac_cm_rms", "metrics"}.issubset(case) or not isinstance(case.get("case_index"), int) or isinstance(case.get("case_index"), bool) or not isinstance(case.get("ac_cm_rms"), (int, float)) or isinstance(case.get("ac_cm_rms"), bool) or not math.isfinite(case["ac_cm_rms"]) or not isinstance(case.get("metrics"), dict):
                    raise ValueError("result artifact case drift")
                for field in ("case_id", "channel_identity"):
                    if field in case and not isinstance(case[field], str):
                        raise ValueError("result artifact identity type drift")
                if "package_case_index" in case and (not isinstance(case["package_case_index"], int) or isinstance(case["package_case_index"], bool) or case["package_case_index"] < 0):
                    raise ValueError("result artifact package index drift")
                key = str(case["case_index"])
                if key in parsed:
                    raise ValueError("duplicate result artifact case")
                parsed[key] = {}
                if case["ac_cm_rms"] != run["control_vector"][case["case_index"]] or set(case["metrics"]) != {"FOM_dB", "COM_dB", "sigma_N_V"}:
                    raise ValueError("result artifact metric schema drift")
                for metric in ("FOM_dB", "COM_dB", "sigma_N_V"):
                    number = case["metrics"].get(metric)
                    if not isinstance(number, (int, float)) or isinstance(number, bool) or not math.isfinite(number):
                        raise ValueError("result artifact metric drift")
                    parsed[key][metric] = float(number)
            if artifact["case_metrics"] != parsed or run["final_metrics"] != parsed:
                raise ValueError("artifact metrics are not mechanically bound")
            if set(parsed) != {str(index) for index in range(len(controls["ac_cm_rms_vectors"]))}:
                raise ValueError("result artifact case/control drift")
            matched_artifacts.append(artifact)
    if len(matched_artifacts) > 1 and (len({item["path"] for item in matched_artifacts}) != len(matched_artifacts) or len({item["sha256"] for item in matched_artifacts}) != len(matched_artifacts)):
        raise ValueError("controls reused one result artifact")
    statuses = {run["status"] for run in value["runs"]}
    expected_status = "numeric_observation" if statuses == {"matched"} else "blocked"
    if value["parity"] != {"status": expected_status, "matched": False, "acceptance": False}:
        raise ValueError("parity promotion")
    expected_non_claims = ["no S-parameter fit", "single FD-to-TD impulse", "no upstream numeric parity", "no global/product/release claim"]
    if expected_status == "blocked":
        expected_non_claims.append("no final consumer proof while blocked")
    if not isinstance(value["non_claims"], list) or value["non_claims"] != expected_non_claims:
        raise ValueError("non-claim drift")
    path_free(value)
    return value


def verify_aggregate(report1: Path, report2: Path, aggregate: Path) -> dict[str, Any]:
    first = verify_report(report1)
    second = verify_report(report2)
    value = json.loads(aggregate.read_text(encoding="utf-8"))
    exact(value, {"schema", "report_slots", "candidate", "fixtures", "upstream", "toolchain", "controls", "parity", "fresh_runs", "non_claims"}, "aggregate")
    if value["schema"] != AGGREGATE_SCHEMA or first["run_id"] == second["run_id"] or first["nonce"] == second["nonce"]:
        raise ValueError("aggregate identity invalid")
    slots = value["report_slots"]
    if len(slots) != 2:
        raise ValueError("aggregate slot count drift")
    for slot, expected, report in zip(slots, ("run1", "run2"), (report1, report2)):
        exact(slot, {"slot", "run_id", "path", "sha256"}, "aggregate slot")
        if slot["slot"] != expected or slot["run_id"] != (first if expected == "run1" else second)["run_id"] or slot["path"] != report.name or slot["path"] != Path(slot["path"]).name:
            raise ValueError("aggregate path/order drift")
        if slot["sha256"] != sha(report):
            raise ValueError("aggregate report hash drift")
        hex64(slot["sha256"], "aggregate report sha")
    build_identity = lambda report: {key: report["build"][key] for key in ("command", "exit", "timeout_s", "env_policy", "env_receipt")}
    if stable_candidate(first["candidate"]) != stable_candidate(second["candidate"]) or value["candidate"] != first["candidate"] or first["fixtures"] != second["fixtures"] or first["upstream"] != second["upstream"] or first["toolchain"] != second["toolchain"] or build_identity(first) != build_identity(second) or first["execution"] != second["execution"] or value["fixtures"] != first["fixtures"] or value["upstream"] != first["upstream"] or value["toolchain"] != first["toolchain"] or value["controls"] != first["controls"]:
        raise ValueError("aggregate identity mismatch")
    expected_aggregate_status = "numeric_observation" if first["parity"]["status"] == second["parity"]["status"] == "numeric_observation" else "blocked"
    if value["parity"] != {"status": expected_aggregate_status, "matched": False, "acceptance": False} or value["fresh_runs"] != 2 or value["non_claims"] != ["no upstream numeric parity", "no global/product/release claim", "aggregate is preparation-only"]:
        raise ValueError("aggregate promotion")
    path_free(value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report1", type=Path, required=True)
    parser.add_argument("--report2", type=Path, required=True)
    parser.add_argument("--aggregate", type=Path, required=True)
    args = parser.parse_args()
    verify_aggregate(args.report1, args.report2, args.aggregate)
    print("verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
