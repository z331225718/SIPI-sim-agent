"""Install an admitted archive into a same-host external prefix and smoke it."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.isolated-install-admission.v1"
ARCHIVE_SCHEMA = "sipi.release-archive-report.v1"
MODES = {"observe", "release-gate"}
RC_PULSE_REQUEST = (
    b'{"schema":"sipi.tran.rc-pulse-request.v1","request_id":"isolated-rc-pulse",'
    b'"resistance_ohms":1000.0,"capacitance_farads":0.000001,'
    b'"initial_voltage_out_volts":0.0,"output_times_seconds":[0.0,0.000001,0.000002,0.000003],'
    b'"pulse":{"voltage_low_volts":0.0,"voltage_high_volts":1.0,"delay_seconds":0.000001,'
    b'"rise_seconds":0.000000001,"fall_seconds":0.000000001,"width_seconds":0.00001,"period_seconds":0.00002}}'
)


class InstallError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_external(path: Path, root: Path) -> Path:
    candidate = path.absolute()
    resolved = candidate.resolve()
    workspace = root.resolve()
    if resolved == workspace or workspace in resolved.parents:
        raise InstallError("external_path_required")
    return candidate


def load_archive_module(root: Path):
    path = root / "tools" / "verify_p7_release_archive.py"
    specification = importlib.util.spec_from_file_location("p7_archive_gate", path)
    if specification is None or specification.loader is None:
        raise InstallError("archive_gate_unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def parse_prior_report(document: object) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise InstallError("archive_report_invalid")
    required = {
        "schema", "structural_admission", "composition_evidence_status", "promotion_status",
        "archive_sha256", "archive_bytes", "policy_sha256", "composition_report_sha256",
        "source_commit", "entries", "static_pe_binding", "limitations",
    }
    if set(document) != required or document.get("schema") != ARCHIVE_SCHEMA:
        raise InstallError("archive_report_invalid")
    if document.get("structural_admission") != "conformant" or document.get("promotion_status") != "blocked":
        raise InstallError("archive_report_not_admitted")
    for key in ("archive_sha256", "policy_sha256", "composition_report_sha256"):
        if not isinstance(document.get(key), str) or len(document[key]) != 64:
            raise InstallError("archive_report_invalid")
    if not isinstance(document.get("archive_bytes"), int) or document["archive_bytes"] <= 0:
        raise InstallError("archive_report_invalid")
    entries = document.get("entries")
    if not isinstance(entries, list) or {item.get("role") for item in entries if isinstance(item, dict)} != {"main_executable", "mit_license"}:
        raise InstallError("archive_report_invalid")
    return document


def scrubbed_environment(base: dict[str, str], prefix: Path) -> dict[str, str]:
    system_root = base.get("SystemRoot") or base.get("WINDIR")
    if not system_root:
        raise InstallError("system_root_unavailable")
    system_root_path = Path(system_root)
    environment = {
        "SystemRoot": str(system_root_path),
        "WINDIR": str(system_root_path),
        "PATH": str(system_root_path / "System32"),
        "TEMP": str(prefix / "temp"),
        "TMP": str(prefix / "temp"),
    }
    return environment


def sanitization_policy_sha256() -> str:
    policy = {
        "PATH": "SystemRoot/System32",
        "SystemRoot": "host-provided",
        "TEMP": "install-prefix/temp",
        "TMP": "install-prefix/temp",
        "WINDIR": "host-provided",
    }
    return sha256_bytes(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def response_digest(stdout: bytes, stderr: bytes, expected_exit: int, require_diagnostic: bool) -> tuple[str, str]:
    if not stdout.endswith(b"\n") or stdout.count(b"\n") != 1:
        raise InstallError("process_stdout_invalid")
    try:
        envelope = json.loads(stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InstallError("process_stdout_invalid") from error
    if not isinstance(envelope, dict) or envelope.get("schema") != "sipi.cli.response.v1":
        raise InstallError("process_stdout_invalid")
    status = envelope.get("status")
    if expected_exit == 0 and status != "ok":
        raise InstallError("process_status_mismatch")
    if expected_exit != 0 and status == "ok":
        raise InstallError("process_status_mismatch")
    if require_diagnostic:
        if not stderr.endswith(b"\n") or stderr.count(b"\n") != 1:
            raise InstallError("process_diagnostic_invalid")
        try:
            diagnostic = json.loads(stderr)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InstallError("process_diagnostic_invalid") from error
        if not isinstance(diagnostic, dict) or diagnostic.get("schema") != "sipi.cli.diagnostic.v1":
            raise InstallError("process_diagnostic_invalid")
    elif stderr:
        raise InstallError("process_diagnostic_unexpected")
    return sha256_bytes(stdout), sha256_bytes(stderr)


def run_probe(executable: Path, prefix: Path, environment: dict[str, str], probe_id: str, arguments: list[str], stdin: bytes | None, expected_exit: int, diagnostic: bool) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [str(executable), *arguments], cwd=prefix, env=environment, input=stdin,
            capture_output=True, check=False,
        )
    except OSError as error:
        raise InstallError("installed_executable_unavailable") from error
    if completed.returncode != expected_exit:
        raise InstallError("process_exit_mismatch")
    stdout_sha256, stderr_sha256 = response_digest(completed.stdout, completed.stderr, expected_exit, diagnostic)
    return {"id": probe_id, "exit_code": expected_exit, "stdout_sha256": stdout_sha256, "stderr_sha256": stderr_sha256}


def install_entries(archive_bytes: bytes, prefix: Path, report: dict[str, Any]) -> Path:
    prefix.mkdir(parents=True, exist_ok=False)
    (prefix / "temp").mkdir()
    expected = {item["role"]: item for item in report["entries"]}
    names = {"sipi.exe": "main_executable", "LICENSE": "mit_license"}
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            for name, role in names.items():
                data = archive.read(name)
                item = expected[role]
                if len(data) != item["bytes"] or sha256_bytes(data) != item["content_sha256"]:
                    raise InstallError("archive_entry_identity_mismatch")
                destination = prefix / name
                with destination.open("xb") as output:
                    output.write(data)
    except (OSError, zipfile.BadZipFile) as error:
        raise InstallError("install_write_failed") from error
    executable = prefix / "sipi.exe"
    if not executable.is_file() or sha256_bytes(executable.read_bytes()) != expected["main_executable"]["content_sha256"]:
        raise InstallError("installed_binary_identity_mismatch")
    return executable


def build_report(root: Path, archive_path: Path, composition_path: Path, policy_path: Path, prior_path: Path, prefix: Path) -> dict[str, Any]:
    gate = load_archive_module(root)
    archive_report = gate.build_report(root, archive_path, composition_path, policy_path)
    prior_document, prior_sha256 = gate.load_json(prior_path, root)
    prior = parse_prior_report(prior_document)
    if prior["archive_sha256"] != archive_report["archive_sha256"] or prior["archive_bytes"] != archive_report["archive_bytes"]:
        raise InstallError("archive_evidence_mismatch")
    if prior["policy_sha256"] != archive_report["policy_sha256"] or prior["composition_report_sha256"] != archive_report["composition_report_sha256"]:
        raise InstallError("archive_evidence_mismatch")
    if prior["entries"] != archive_report["entries"]:
        raise InstallError("archive_evidence_mismatch")
    prefix = require_external(prefix, root)
    if prefix.exists() or prefix.is_symlink():
        raise InstallError("install_prefix_not_new")
    archive_bytes = gate.read_regular_external(archive_path, root)
    if sha256_bytes(archive_bytes) != archive_report["archive_sha256"]:
        raise InstallError("archive_changed_during_admission")
    executable = install_entries(archive_bytes, prefix, archive_report)
    environment = scrubbed_environment(dict(os.environ), prefix)
    probes = [
        run_probe(executable, prefix, environment, "version", ["version", "--json"], None, 0, False),
        run_probe(executable, prefix, environment, "capabilities", ["capabilities", "--json"], None, 0, False),
        run_probe(executable, prefix, environment, "protocols", ["protocols", "--json"], None, 0, False),
        run_probe(executable, prefix, environment, "tran_run", ["tran", "run", "--stdin", "--artifact-root", "artifacts", "--artifact-id", "isolated-tran"], RC_PULSE_REQUEST, 0, False),
        run_probe(executable, prefix, environment, "report_inspect", ["report", "inspect", "--stdin"], b'{"schema":"sipi.artifact-report-request.v1","artifact_root":"artifacts","artifact_id":"isolated-tran"}', 0, False),
        run_probe(executable, prefix, environment, "channel_unavailable", ["channel", "run"], None, 4, True),
    ]
    return {
        "schema": SCHEMA,
        "status": "isolated_install_smoke_passed",
        "environment_class": "same_host_isolated_prefix",
        "fresh_machine": False,
        "fresh_user": "not_assessed",
        "host_loader_closure": "not_assessed",
        "promotion_status": "blocked",
        "archive_sha256": archive_report["archive_sha256"],
        "archive_report_sha256": prior_sha256,
        "installed_executable_sha256": sha256_bytes(executable.read_bytes()),
        "sanitization_policy_sha256": sanitization_policy_sha256(),
        "probes": probes,
        "limitations": [
            "same-host isolated-prefix evidence only; not fresh-machine or fresh-user certification",
            "not an installer, signature verification, host loader closure, or release approval",
        ],
    }


def write_new_external_report(path: Path, root: Path, report: dict[str, Any]) -> None:
    path = require_external(path, root)
    if path.exists() or path.is_symlink():
        raise InstallError("report_already_exists")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as output:
            output.write(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
    except OSError as error:
        raise InstallError("report_write_failed") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--composition-report", type=Path, required=True)
    parser.add_argument("--archive-policy", type=Path, required=True)
    parser.add_argument("--archive-report", type=Path, required=True)
    parser.add_argument("--install-prefix", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--mode", choices=sorted(MODES), default="release-gate")
    arguments = parser.parse_args()
    try:
        report = build_report(ROOT, arguments.archive, arguments.composition_report, arguments.archive_policy, arguments.archive_report, arguments.install_prefix)
        write_new_external_report(arguments.report, ROOT, report)
    except (InstallError, RuntimeError) as error:
        print(json.dumps({"schema": SCHEMA, "status": "rejected", "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if arguments.mode == "observe" else 2


if __name__ == "__main__":
    raise SystemExit(main())
