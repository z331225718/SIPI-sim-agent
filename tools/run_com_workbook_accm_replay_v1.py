"""Preparation runner for a pinned COM workbook/ACCM replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import secrets
import subprocess
import tarfile
import tempfile
import threading
from pathlib import Path, PurePosixPath
from typing import Any

CANDIDATE_COMMIT = "0f38e3e796b2312f476c6c5a181dd83d2752bb43"
CANDIDATE_TREE = "241d86cc898616aa656f50ac47536fe169098115"
CANDIDATE_ARCHIVE_SHA256 = "9d627a57821db2f66e522eedacbefbca06a11eaa4e5b5f4c476b6ea95590cb01"
CANDIDATE_ARCHIVE_BYTES = 44492800
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
SCHEMA = "sipi.com.workbook-accm-replay-prep.v2"
RUN_TIMEOUT_S = 180
BUILD_TIMEOUT_S = 900
IDENTITY_TIMEOUT_S = 15
MAX_RESULT_BYTES = 64 * 1024 * 1024
MAX_CAPTURE_BYTES = 4 * 1024 * 1024
RESULT_KEYS = {"schema_version", "source_revision", "profile", "cases", "provenance", "warnings", "timings_s", "input_manifest", "report_manifest"}
FIXTURES = {
    "workbook": {"path": "matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx", "git_blob_sha1": "22b633b6092b4b0de0ca89273515329b362eabae", "bytes": 67087, "sha256": "e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925"},
    "s4p": {"path": "fixtures/synthetic/kappa_asymmetric_reflective_10db_at_26p56ghz.s4p", "git_blob_sha1": "a1fe8618043b31f63dfb24454ac1d296000010c0", "bytes": 6457063, "sha256": "3a563543ba664fcc04c1ac5603ad305cb0b1d110c3d9020727444b1c3fd2d0ec"},
}
SOURCE_PATHS = ("src/agent_com/api.py", "src/agent_com/_orchestration.py", "src/agent_com/network/package.py", "src/agent_com/network/two_port.py", "src/agent_com/signal/fd_to_td.py", "src/agent_com/equalization/search.py")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def redact(text: str) -> str:
    normalized = text.replace("\\", "/")
    return re.sub(r"(?i)(?<![A-Za-z0-9_])(?:[A-Za-z]:/|\\\\|//|file://|/(?:users|home|opt|tmp|var|etc)/)[^\s,;)]*", "<abs-path>", normalized)


def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or ":" in path.parts[0] or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("unsafe archive path")
    return path


def archive(repo: Path, destination: Path) -> dict[str, Any]:
    command = ["git", "-c", "core.autocrlf=false", "-C", str(repo), "archive", "--format=tar", CANDIDATE_COMMIT]
    with destination.open("xb") as stream:
        completed = subprocess.run(command, stdout=stream, stderr=subprocess.PIPE, timeout=IDENTITY_TIMEOUT_S, check=False)
    payload = destination.read_bytes()
    if completed.returncode or len(payload) != CANDIDATE_ARCHIVE_BYTES or sha256(payload) != CANDIDATE_ARCHIVE_SHA256:
        raise RuntimeError("candidate archive identity mismatch")
    return {"command": "git -c core.autocrlf=false archive --format=tar <candidate>", "exit": completed.returncode, "bytes": len(payload), "sha256": sha256(payload)}


def safe_extract(archive_path: Path, destination: Path) -> None:
    seen: set[str] = set()
    root = destination.resolve()
    with tarfile.open(archive_path, "r") as stream:
        for member in stream.getmembers():
            relative = safe_relative(member.name)
            name = relative.as_posix()
            if name in seen:
                raise ValueError("duplicate archive member")
            seen.add(name)
            if member.issym() or member.islnk() or not (member.isdir() or member.isreg()):
                raise ValueError("archive links and special members are rejected")
            target = (root / Path(*relative.parts)).resolve()
            if root not in target.parents and target != root:
                raise ValueError("archive path escapes root")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                source = stream.extractfile(member)
                if source is None:
                    raise ValueError("archive member has no data")
                output.write(source.read())


def pinned_blob(upstream: Path, fixture: dict[str, Any], destination: Path) -> dict[str, Any]:
    path = fixture["path"]
    blob = subprocess.check_output(["git", "-C", str(upstream), "show", f"{UPSTREAM_COMMIT}:{path}"], timeout=IDENTITY_TIMEOUT_S)
    blob_id = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", f"{UPSTREAM_COMMIT}:{path}"], text=True, timeout=IDENTITY_TIMEOUT_S).strip()
    if blob_id != fixture["git_blob_sha1"] or len(blob) != fixture["bytes"] or sha256(blob) != fixture["sha256"]:
        raise RuntimeError(f"pinned fixture identity mismatch: {path}")
    with destination.open("xb") as output:
        output.write(blob)
    return {"path": path, "basename": Path(path).name, "git_blob_sha1": blob_id, "bytes": len(blob), "sha256": sha256(blob), "source_commit": UPSTREAM_COMMIT}


def source_inventory(upstream: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path in SOURCE_PATHS:
        blob = subprocess.check_output(["git", "-C", str(upstream), "show", f"{UPSTREAM_COMMIT}:{path}"], timeout=IDENTITY_TIMEOUT_S)
        blob_id = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", f"{UPSTREAM_COMMIT}:{path}"], text=True, timeout=IDENTITY_TIMEOUT_S).strip()
        result[path] = {"git_blob_sha1": blob_id, "bytes": len(blob), "sha256": sha256(blob), "license": "MIT"}
    return result


def candidate_inventory(root: Path) -> dict[str, Any]:
    base = root / "crates" / "sipi-agent-com-direct"
    result: dict[str, Any] = {}
    for path in sorted(base.rglob("*")):
        if not path.is_file() or "target" in path.parts:
            continue
        payload = path.read_bytes()
        result[path.relative_to(root).as_posix()] = {"bytes": len(payload), "sha256": sha256(payload)}
    return result


def tool_identity(path: Path, role: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"invalid {role} executable")
    completed = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=IDENTITY_TIMEOUT_S, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{role} version probe failed")
    return {"role": role, "basename": path.name, "file_sha256": sha256(path.read_bytes()), "version_output_sha256": sha256((completed.stdout + completed.stderr).encode()), "version_exit": completed.returncode, "timeout_s": IDENTITY_TIMEOUT_S, "path_redacted": True}


def binary_identity(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"basename": path.name, "exists": False, "bytes": 0, "sha256": None, "canonical_sha256": None}
    payload = path.read_bytes()
    canonical = bytearray(payload)
    valid_pe = False
    if len(canonical) >= 0x40 and canonical[:2] == b"MZ":
        pe_offset = int.from_bytes(canonical[0x3C:0x40], "little")
        if 0 <= pe_offset <= len(canonical) - 24 and canonical[pe_offset:pe_offset + 4] == b"PE\0\0":
            coff = pe_offset + 4
            machine = int.from_bytes(canonical[coff:coff + 2], "little")
            sections = int.from_bytes(canonical[coff + 2:coff + 4], "little")
            optional_size = int.from_bytes(canonical[coff + 16:coff + 18], "little")
            optional = coff + 20
            magic = int.from_bytes(canonical[optional:optional + 2], "little") if optional + 2 <= len(canonical) else 0
            entrypoint = int.from_bytes(canonical[optional + 16:optional + 20], "little") if optional + 20 <= len(canonical) else 0
            size_headers = int.from_bytes(canonical[optional + 60:optional + 64], "little") if optional + 64 <= len(canonical) else 0
            table = optional + optional_size
            valid_pe = machine in {0x14C, 0x8664, 0xAA64} and (int.from_bytes(canonical[coff + 18:coff + 20], "little") & 0x0002) != 0 and 0 < sections <= 96 and magic in {0x10B, 0x20B} and optional_size >= 68 and 0 < entrypoint and 0 < size_headers <= len(canonical) and table + sections * 40 <= len(canonical)
            entry_in_exec = False
            for index in range(sections):
                header = table + index * 40
                virtual_size = int.from_bytes(canonical[header + 8:header + 12], "little")
                virtual_address = int.from_bytes(canonical[header + 12:header + 16], "little")
                raw_size = int.from_bytes(canonical[header + 16:header + 20], "little")
                raw_ptr = int.from_bytes(canonical[header + 20:header + 24], "little")
                valid_pe = valid_pe and (raw_size == 0 or raw_ptr <= len(canonical) and raw_size <= len(canonical) - raw_ptr)
                if (int.from_bytes(canonical[header + 36:header + 40], "little") & 0x20000000) and virtual_address <= entrypoint < virtual_address + max(virtual_size, raw_size):
                    entry_in_exec = True
            valid_pe = valid_pe and entry_in_exec
            if valid_pe:
                canonical[pe_offset + 8:pe_offset + 12] = b"\0" * 4
                canonical[optional + 64:optional + 68] = b"\0" * 4
    if path.suffix.lower() == ".exe" and not valid_pe:
        raise ValueError("binary is not a parseable PE")
    return {"basename": path.name, "exists": True, "bytes": len(payload), "sha256": sha256(payload), "canonical_sha256": sha256(bytes(canonical))}


def env_receipt(env: dict[str, str]) -> dict[str, Any]:
    result = {}
    for key in ("PATH", "LIB", "INCLUDE", "CL", "LINK", "RUSTC", "CARGO_BUILD_RUSTC", "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER"):
        raw = env.get(key, "")
        entries = [Path(item).name for item in raw.split(os.pathsep) if item]
        result[key] = {"entry_basenames": entries, "value_sha256": sha256(raw.encode()), "path_redacted": True}
    return result


def build_env(rustc: Path, linker: Path) -> dict[str, str]:
    inherited = os.environ
    forbidden = tuple(key for key in inherited if key.startswith("CARGO_") or key in {"RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"})
    if any(inherited.get(key) for key in forbidden):
        raise RuntimeError("inherited rust/build flags or wrapper are not admitted")
    allowed = {"SystemRoot", "ComSpec", "TEMP", "TMP", "PATH", "PATHEXT", "WINDIR", "PROGRAMDATA", "PROGRAMFILES", "USERPROFILE", "HOME", "LOCALAPPDATA", "APPDATA", "NUMBER_OF_PROCESSORS"}
    env = {key: value for key, value in inherited.items() if key in allowed}
    env.update({"RUSTC": str(rustc), "CARGO_BUILD_RUSTC": str(rustc), "RUSTC_WRAPPER": "", "RUSTC_WORKSPACE_WRAPPER": "", "CARGO_BUILD_RUSTC_WRAPPER": "", "CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER": str(linker), "CL": "", "LINK": "", "CARGO_INCREMENTAL": "0", "CARGO_NET_OFFLINE": "true"})
    return env


def bounded_run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
    captured: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}

    def drain(name: str, stream: Any) -> None:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                return
            if len(captured[name]) < MAX_CAPTURE_BYTES:
                captured[name].extend(chunk[: MAX_CAPTURE_BYTES - len(captured[name])])

    threads = [threading.Thread(target=drain, args=(name, getattr(process, name)), daemon=True) for name in ("stdout", "stderr")]
    for thread in threads:
        thread.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=IDENTITY_TIMEOUT_S, check=False)
        process.kill()
        process.wait()
        for thread in threads:
            thread.join()
        return subprocess.CompletedProcess(command, 124, bytes(captured["stdout"]).decode("utf-8", "replace"), "timeout: " + bytes(captured["stderr"]).decode("utf-8", "replace"))
    for thread in threads:
        thread.join()
    return subprocess.CompletedProcess(command, process.returncode, bytes(captured["stdout"]).decode("utf-8", "replace"), bytes(captured["stderr"]).decode("utf-8", "replace"))


def parse_result_artifact(payload: bytes, control_vector: list[float]) -> tuple[dict[str, Any], dict[str, dict[str, float]]]:
    if len(payload) == 0 or len(payload) > MAX_RESULT_BYTES:
        raise ValueError("result artifact exceeds bounded size")
    value = json.loads(payload)
    if not isinstance(value, dict) or set(value) != RESULT_KEYS or value["schema_version"] != 1 or value.get("source_revision") != "r480" or not isinstance(value["profile"], dict) or not isinstance(value["provenance"], dict) or not isinstance(value["warnings"], list) or not isinstance(value["timings_s"], dict) or not isinstance(value["input_manifest"], dict) or not isinstance(value["report_manifest"], dict):
        raise ValueError("result artifact schema mismatch")
    cases = value["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("result artifact cases missing")
    result: dict[str, dict[str, float]] = {}
    for case in cases:
        required_case = {"case_index", "channels", "metrics", "diagnostics"}
        if not isinstance(case, dict) or not required_case.issubset(case) or not isinstance(case.get("case_index"), int) or isinstance(case.get("case_index"), bool) or case["case_index"] < 0 or case["case_index"] >= len(control_vector) or not isinstance(case.get("metrics"), dict) or not isinstance(case.get("channels"), dict) or not isinstance(case.get("diagnostics"), dict):
            raise ValueError("result artifact case identity invalid")
        key = str(case["case_index"])
        if key in result:
            raise ValueError("duplicate result artifact case")
        metrics = case["metrics"]
        if not {"FOM", "COM_dB", "sigma_N_V"}.issubset(metrics):
            raise ValueError("result artifact metric schema mismatch")
        selected = {}
        for metric in ("FOM", "COM_dB", "sigma_N_V"):
            number = metrics.get(metric)
            if not isinstance(number, (int, float)) or isinstance(number, bool) or not math.isfinite(number):
                raise ValueError("result artifact metric is not finite")
            selected["FOM_dB" if metric == "FOM" else metric] = float(number)
        result[key] = selected
    if set(result) != {str(index) for index in range(len(control_vector))}:
        raise ValueError("result artifact cases do not match controls")
    return value, result


def canonical_receipt(case_metrics: dict[str, dict[str, float]], control_vector: list[float], raw_value: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for key in sorted(case_metrics, key=int):
        source = next(case for case in raw_value["cases"] if str(case["case_index"]) == key)
        item = {"case_index": int(key), "ac_cm_rms": float(control_vector[int(key)]), "metrics": case_metrics[key]}
        for field in ("case_id", "package_case_index", "channel_identity"):
            if field in source and isinstance(source[field], (str, int, float, bool, type(None))):
                item[field] = source[field]
        cases.append(item)
    return {"schema": "sipi.com.workbook-accm-canonical-metrics.v1", "control_vector": control_vector, "cases": cases, "metric_fields": ["FOM_dB", "COM_dB", "sigma_N_V"], "channel_policy": "single_fd_to_td_impulse"}


def read_result_bytes(path: Path) -> bytes:
    before = path.lstat()
    if not path.is_file() or path.is_symlink() or before.st_size <= 0 or before.st_size > MAX_RESULT_BYTES:
        raise ValueError("result artifact is not a bounded regular file")
    descriptor = os.open(path, os.O_RDONLY)
    try:
        opened = os.fstat(descriptor)
        if opened.st_size != before.st_size or not stat_is_regular(opened.st_mode):
            raise ValueError("result artifact changed before read")
        payload = bytearray()
        while len(payload) <= MAX_RESULT_BYTES:
            chunk = os.read(descriptor, min(1024 * 1024, MAX_RESULT_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if len(payload) > MAX_RESULT_BYTES or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ValueError("result artifact changed while reading")
    return bytes(payload)


def stat_is_regular(mode: int) -> bool:
    return (mode & 0o170000) == 0o100000


def run_one(repo: Path, upstream: Path, cargo: Path, rustc: Path, linker: Path, run_id: str, output: Path) -> dict[str, Any]:
    if len(run_id) != 64 or run_id.lower() != run_id or any(c not in "0123456789abcdef" for c in run_id):
        raise ValueError("run_id must be 64 lowercase hex characters")
    if output.exists():
        raise FileExistsError("report path already exists")
    with tempfile.TemporaryDirectory(prefix=f"com-workbook-accm-{run_id[:12]}-") as temporary:
        root = Path(temporary)
        archive_path = root / "candidate.tar"
        archive_id = archive(repo, archive_path)
        materialized = root / "candidate"
        materialized.mkdir()
        safe_extract(archive_path, materialized)
        before = candidate_inventory(materialized)
        work = root / "inputs"
        work.mkdir()
        fixture_ids = {key: pinned_blob(upstream, value, work / ("pinned-workbook.xlsx" if key == "workbook" else "pinned-channel.s4p")) for key, value in FIXTURES.items()}
        for fixture in fixture_ids.values():
            fixture["pre_sha256"] = fixture["sha256"]
        identities_pre = {"cargo": tool_identity(cargo, "cargo"), "rustc": tool_identity(rustc, "rustc"), "linker": tool_identity(linker, "linker")}
        env = build_env(rustc, linker)
        command = [str(cargo), "build", "--manifest-path", "crates/sipi-agent-com-direct/Cargo.toml", "--bin", "sipi-com-direct-run", "--release", "--locked", "--offline"]
        build = bounded_run(command, cwd=materialized, env=env, timeout=BUILD_TIMEOUT_S)
        binary = materialized / "crates" / "sipi-agent-com-direct" / "target" / "release" / "sipi-com-direct-run.exe"
        binary_before = binary_identity(binary)
        controls = [[0.0, 0.0], [0.0, 0.001]]
        runs: list[dict[str, Any]] = []
        zero_metrics: dict[str, dict[str, float]] | None = None
        for vector in controls:
            out = root / ("out-zero" if vector[1] == 0.0 else "out-nonzero")
            if build.returncode or not binary.is_file():
                runtime = None
            else:
                runtime_command = [str(binary), "run", "--config", str(work / "pinned-workbook.xlsx"), "--thru", str(work / "pinned-channel.s4p"), "--output-dir", str(out), "--override", f"AC_CM_RMS={json.dumps(vector, separators=(',', ':'))}", "--overwrite"]
                runtime = bounded_run(runtime_command, cwd=materialized, env=env, timeout=RUN_TIMEOUT_S)
            stderr = runtime.stderr if runtime else build.stderr
            stdout = runtime.stdout if runtime else ""
            artifact = None
            final_metrics = None
            parse_error = None
            if runtime and runtime.returncode == 0:
                try:
                    result_path = out / "result.json"
                    if not result_path.is_file():
                        raise ValueError("successful COM run did not publish result.json")
                    result_bytes = read_result_bytes(result_path)
                    raw_value, case_metrics = parse_result_artifact(result_bytes, vector)
                    if vector[1] == 0.0:
                        zero_metrics = case_metrics
                    elif zero_metrics is None or "1" not in case_metrics or "1" not in zero_metrics or case_metrics["1"] == zero_metrics["1"]:
                        raise ValueError("nonzero target case did not change consumer metrics")
                    final_metrics = case_metrics
                    output.parent.mkdir(parents=True, exist_ok=True)
                    artifact_path = output.parent / f"{output.stem}-metrics-{len(runs)}.json"
                    receipt = canonical_receipt(case_metrics, vector, raw_value)
                    receipt_bytes = json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
                    with artifact_path.open("xb") as artifact_file:
                        artifact_file.write(receipt_bytes)
                    artifact = {"path": artifact_path.name, "bytes": len(receipt_bytes), "sha256": sha256(receipt_bytes), "raw_bytes": len(result_bytes), "raw_sha256": sha256(result_bytes), "case_metrics": case_metrics}
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    parse_error = str(error)
            success = runtime is not None and runtime.returncode == 0 and artifact is not None and final_metrics is not None
            exit_code = runtime.returncode if runtime else build.returncode
            invalid_artifact = runtime is not None and runtime.returncode == 0 and not success
            status = "matched" if success else "artifact_invalid" if invalid_artifact else "blocked"
            blocker = redact((stderr.strip() if stderr.strip() else parse_error) or "result artifact consumer proof blocked") if not success else None
            runs.append({"control_vector": vector, "status": status, "exit": exit_code, "stdout_sha256": sha256(stdout.encode()), "stderr_sha256": sha256(stderr.encode()), "final_metrics": final_metrics if success else None, "consumer_proof": success, "artifact": artifact, "blocker": blocker})
        after = candidate_inventory(materialized)
        for fixture in fixture_ids.values():
            fixture["post_sha256"] = sha256((work / ("pinned-workbook.xlsx" if fixture["path"].endswith(".xlsx") else "pinned-channel.s4p")).read_bytes())
            if fixture["pre_sha256"] != fixture["post_sha256"]:
                raise RuntimeError("fixture custody drift")
        identities_post = {"cargo": tool_identity(cargo, "cargo"), "rustc": tool_identity(rustc, "rustc"), "linker": tool_identity(linker, "linker")}
        binary_pre = binary_before
        binary_post = binary_identity(binary)
        blocked = any(item["status"] in {"blocked", "artifact_invalid"} for item in runs)
        result = {"schema": SCHEMA, "run_id": run_id, "nonce": secrets.token_hex(32), "candidate": {"commit": CANDIDATE_COMMIT, "tree": CANDIDATE_TREE, "archive": archive_id, "binary_pre": binary_pre, "binary": binary_post}, "upstream": {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE, "runtime": "not_executed_external_only", "source_inventory": source_inventory(upstream)}, "fixtures": fixture_ids, "toolchain": {"pre": identities_pre, "post": identities_post}, "build": {"command": "cargo build --manifest-path crates/sipi-agent-com-direct/Cargo.toml --bin sipi-com-direct-run --release --locked --offline", "exit": build.returncode, "stdout_sha256": sha256(build.stdout.encode()), "stderr_sha256": sha256(build.stderr.encode()), "timeout_s": BUILD_TIMEOUT_S, "env_policy": "explicit_rustc_wrappers_cleared_offline_incremental_zero", "env_receipt": env_receipt(env)}, "execution": {"runtime_timeout_s": RUN_TIMEOUT_S, "source_inventory_before": before, "source_inventory_after": after, "source_inventory_equal": before == after}, "controls": {"ac_cm_rms_vectors": controls, "source": "pinned workbook vector override", "no_sparam_fit": True, "channel_policy": "single_fd_to_td_impulse"}, "runs": runs, "parity": {"status": "blocked" if blocked else "numeric_observation", "matched": False, "acceptance": False}, "non_claims": ["no S-parameter fit", "single FD-to-TD impulse", "no upstream numeric parity", "no global/product/release claim"] + (["no final consumer proof while blocked"] if blocked else [])}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--linker", type=Path, required=True)
    parser.add_argument("--run-id", default=secrets.token_hex(32))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = run_one(args.repo, args.upstream_repo, args.cargo, args.rustc, args.linker, args.run_id, args.report)
    print(json.dumps({"schema": report["schema"], "status": report["parity"]["status"], "run_id": report["run_id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
