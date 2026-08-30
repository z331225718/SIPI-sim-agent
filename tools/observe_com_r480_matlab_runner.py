"""Run a bounded, external-only MATLAB built-in version probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.com.matlab-runner-probe-report.v1"
PROBE_ID = "matlab-builtins-version-sentinel-v1"
TIMEOUT_SECONDS = 30
EXPRESSION = "fprintf('SIPI_MATLAB_PROBE|release=%s|version=%s|platform=%s\\n', version('-release'), version, computer);"
SENTINEL = re.compile(r"^SIPI_MATLAB_PROBE\|release=([A-Za-z0-9._-]+)\|version=([A-Za-z0-9. ()_-]+)\|platform=([A-Za-z0-9._-]+)$")


class ProbeError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _outside_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return True
    return False


def _kill_tree(process: subprocess.Popen[bytes]) -> bool:
    if process.poll() is not None:
        return False
    subprocess.run(
        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return True


def _observed_identity(stdout: bytes) -> dict[str, str] | None:
    for raw_line in stdout.splitlines():
        try:
            line = raw_line.decode("ascii")
        except UnicodeDecodeError:
            continue
        match = SENTINEL.fullmatch(line)
        if match is not None:
            return {"release": match.group(1), "version": match.group(2), "platform": match.group(3)}
    return None


def probe(executable: Path) -> dict:
    if os.name != "nt":
        raise ProbeError("windows_runner_probe_required")
    if not executable.is_file():
        raise ProbeError("matlab_executable_missing")
    with tempfile.TemporaryDirectory(prefix="sipi-com-matlab-probe-") as raw_cwd:
        cwd = Path(raw_cwd)
        if not _outside_root(cwd):
            raise ProbeError("temporary_cwd_must_be_outside_worktree")
        prefdir = cwd / "prefdir"
        prefdir.mkdir()
        environment = os.environ.copy()
        environment["MATLABPATH"] = ""
        environment["MATLAB_PREFDIR"] = str(prefdir)
        # R2026a may fault during shutdown while its desktop connector restores
        # state from a shared profile. The probe has no connector dependency.
        environment["MW_DISABLE_CONNECTOR"] = "1"
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        process = subprocess.Popen(
            [str(executable), "-batch", EXPRESSION],
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )
        timed_out = False
        tree_terminated = False
        try:
            stdout, stderr = process.communicate(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            tree_terminated = _kill_tree(process)
            stdout, stderr = process.communicate()
    observed_identity = _observed_identity(stdout)
    return {
        "schema": SCHEMA,
        "status": "indeterminate",
        "runner": {
            "logical_name": "matlab",
            "platform": "windows-x86_64",
            "executable_sha256": _sha256(executable.read_bytes()),
            "executable_byte_length": executable.stat().st_size,
        },
        "probe": {
            "id": PROBE_ID,
            "template_sha256": _sha256(("-batch\0" + EXPRESSION).encode("utf-8")),
            "timeout_seconds": TIMEOUT_SECONDS,
            "cwd": "external_empty_temp",
            "matlabpath": "cleared",
            "matlab_prefdir": "external_temporary",
            "startup_isolation": "unproven",
        },
        "result": {
            "timed_out": timed_out,
            "process_tree_terminated": tree_terminated,
            "exit_code": process.returncode,
            "sentinel_observed": observed_identity is not None,
            "observed_identity": observed_identity,
            "stdout_sha256": _sha256(stdout),
            "stderr_sha256": _sha256(stderr),
            "license_runtime_observation": "unknown",
        },
        "non_claims": [
            "No agent-com, MATLAB source, workbook, fixture, parameter, or R480 input was read or executed.",
            "This report does not establish oracle authorization, R480 execution, a reference result, or parity.",
        ],
    }


def validate_report(report: object) -> None:
    if not isinstance(report, dict) or set(report) != {"schema", "status", "runner", "probe", "result", "non_claims"}:
        raise ProbeError("report_shape_invalid")
    if report["schema"] != SCHEMA or report["status"] != "indeterminate":
        raise ProbeError("report_status_invalid")
    runner = report["runner"]
    if not isinstance(runner, dict) or runner.get("logical_name") != "matlab" or runner.get("platform") != "windows-x86_64" or not isinstance(runner.get("executable_byte_length"), int) or runner["executable_byte_length"] <= 0 or not isinstance(runner.get("executable_sha256"), str) or len(runner["executable_sha256"]) != 64:
        raise ProbeError("runner_identity_invalid")
    probe_record = report["probe"]
    expected_probe = {
        "id": PROBE_ID,
        "template_sha256": _sha256(("-batch\0" + EXPRESSION).encode("utf-8")),
        "timeout_seconds": TIMEOUT_SECONDS,
        "cwd": "external_empty_temp",
        "matlabpath": "cleared",
        "matlab_prefdir": "external_temporary",
        "startup_isolation": "unproven",
    }
    if probe_record != expected_probe:
        raise ProbeError("probe_isolation_invalid")
    result = report["result"]
    if not isinstance(result, dict) or set(result) != {"timed_out", "process_tree_terminated", "exit_code", "sentinel_observed", "observed_identity", "stdout_sha256", "stderr_sha256", "license_runtime_observation"}:
        raise ProbeError("result_shape_invalid")
    identity = result["observed_identity"]
    identity_valid = identity is None or (
        isinstance(identity, dict)
        and set(identity) == {"release", "version", "platform"}
        and isinstance(identity.get("release"), str)
        and re.fullmatch(r"[A-Za-z0-9._-]+", identity["release"])
        and isinstance(identity.get("version"), str)
        and re.fullmatch(r"[A-Za-z0-9. ()_-]+", identity["version"])
        and isinstance(identity.get("platform"), str)
        and re.fullmatch(r"[A-Za-z0-9._-]+", identity["platform"])
    )
    if not isinstance(result["timed_out"], bool) or not isinstance(result["process_tree_terminated"], bool) or not isinstance(result["sentinel_observed"], bool) or (result["sentinel_observed"] != (identity is not None)) or not identity_valid or result["license_runtime_observation"] != "unknown" or not isinstance(result["exit_code"], int) or any(not isinstance(result[key], str) or len(result[key]) != 64 for key in ("stdout_sha256", "stderr_sha256")):
        raise ProbeError("result_identity_invalid")
    if not isinstance(report["non_claims"], list) or len(report["non_claims"]) != 2 or not all(isinstance(item, str) and item for item in report["non_claims"]):
        raise ProbeError("non_claims_invalid")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matlab-executable", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not _outside_root(args.report):
        raise SystemExit("report must be outside the SIPI worktree")
    try:
        report = probe(args.matlab_executable)
        validate_report(report)
        args.report.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    except (OSError, ProbeError, subprocess.SubprocessError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": report["status"], "report_sha256": _sha256(args.report.read_bytes())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
