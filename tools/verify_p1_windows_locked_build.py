"""Run the P1-11 Windows locked build, install smoke, and schema drift gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TARGET = "x86_64-pc-windows-msvc"
REPORT_SCHEMA = "sipi.p1-windows-locked-build-report.v1"
INVENTORY = ROOT / "crates" / "sipi-contracts" / "schemas" / "schema-inventory.v1.json"


class GateError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def command_output(command: list[str], *, cwd: Path, env: dict[str, str], stdin: bytes | None = None) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, cwd=cwd, env=env, input=stdin, capture_output=True)
    except OSError as error:
        raise GateError("command_unavailable") from error
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout_sha256": sha256(completed.stdout),
        "stderr_sha256": sha256(completed.stderr),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def require_success(record: dict[str, Any]) -> None:
    if record["exit_code"] != 0:
        raise GateError("command_failed")


def require_product_inputs_clean(root: Path) -> None:
    for cached in (False, True):
        command = ["git", "-C", str(root), "diff", "--quiet", "--exit-code"]
        if cached:
            command.append("--cached")
        command.extend(["--", "Cargo.lock", "Cargo.toml", "rust-toolchain.toml", "crates"])
        if subprocess.run(command, capture_output=True).returncode != 0:
            raise GateError("product_inputs_dirty")
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", "Cargo.lock"], capture_output=True
    )
    if tracked.returncode != 0:
        raise GateError("lockfile_not_tracked")


def load_inventory(root: Path) -> list[dict[str, Any]]:
    try:
        document = json.loads((root / INVENTORY.relative_to(ROOT)).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GateError("schema_inventory_unavailable") from error
    entries = document.get("entries") if document.get("schema") == "sipi.product-schema-inventory.v1" else None
    if not isinstance(entries, list) or not entries:
        raise GateError("schema_inventory_invalid")
    ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or entry["id"] in ids:
            raise GateError("schema_inventory_invalid")
        ids.add(entry["id"])
        path = entry.get("path")
        if not isinstance(path, str) or path.startswith("/") or ".." in Path(path).parts:
            raise GateError("schema_inventory_invalid")
        data = (root / path).read_bytes()
        if entry.get("textFileFinalLfNotExported") is True:
            if not data.endswith(b"\n"):
                raise GateError("schema_inventory_invalid")
            data = data[:-1]
        if entry.get("sha256") != sha256(data):
            raise GateError("schema_baseline_hash_mismatch")
    return entries


def parse_cli_response(record: dict[str, Any], expected_status: str) -> dict[str, Any]:
    require_success(record)
    stdout = record["stdout"]
    if not stdout.endswith(b"\n") or b"\n" in stdout[:-1]:
        raise GateError("smoke_stdout_shape")
    if record["stderr"]:
        raise GateError("smoke_stderr_unexpected")
    try:
        response = json.loads(stdout[:-1])
    except json.JSONDecodeError as error:
        raise GateError("smoke_stdout_json") from error
    if response.get("schema") != "sipi.cli.response.v1" or response.get("status") != expected_status:
        raise GateError("smoke_response_status")
    return response


def scrubbed_environment(base: dict[str, str]) -> dict[str, str]:
    environment = dict(base)
    for key in list(environment):
        if key.upper() in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"} or key.upper().startswith("CONDA_"):
            environment.pop(key, None)
    return environment


def verify_installed_cli(executable: Path, root: Path, entries: list[dict[str, Any]], environment: dict[str, str]) -> list[dict[str, Any]]:
    cwd = Path(tempfile.mkdtemp(prefix="sipi-p1-11-smoke-"))
    try:
        records: list[dict[str, Any]] = []
        for args in (["version", "--json"], ["capabilities", "--json"], ["doctor", "--json"]):
            record = command_output([str(executable), *args], cwd=cwd, env=environment)
            parse_cli_response(record, "ok")
            records.append(summary(record))
        listed = command_output([str(executable), "schema", "list", "--json"], cwd=cwd, env=environment)
        listed_response = parse_cli_response(listed, "ok")
        listed_ids = listed_response.get("result", {}).get("schemas")
        expected_ids = [entry["id"] for entry in entries]
        if listed_ids != expected_ids:
            raise GateError("schema_registry_drift")
        records.append(summary(listed))
        for entry in entries:
            shown = command_output([str(executable), "schema", "show", entry["id"], "--json"], cwd=cwd, env=environment)
            response = parse_cli_response(shown, "ok")
            exported = json.dumps(response.get("result"), separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            if sha256(exported) != entry["sha256"]:
                raise GateError("schema_bytes_drift")
            records.append(summary(shown))
        request = json.dumps(
            {
                "schema": "sipi.validation-request.v1",
                "request_id": "p1-11",
                "subject": {
                    "schema": "sipi.contract.v1",
                    "axis": {"encoding": "uniform", "start": 0.0, "step": 1e-12, "count": 1},
                    "samples": [0.0],
                },
            },
            separators=(",", ":"),
        ).encode("utf-8")
        validation = command_output([str(executable), "validate", "--stdin"], cwd=cwd, env=environment, stdin=request)
        parse_cli_response(validation, "ok")
        records.append(summary(validation))
        unsupported = command_output([str(executable), "run", "--json"], cwd=cwd, env=environment)
        if unsupported["exit_code"] != 4:
            raise GateError("unsupported_exit_drift")
        if not unsupported["stderr"].endswith(b"\n"):
            raise GateError("unsupported_diagnostic_drift")
        response = json.loads(unsupported["stdout"][:-1])
        if response.get("status") != "unsupported":
            raise GateError("unsupported_status_drift")
        records.append(summary(unsupported))
        return records
    finally:
        shutil.rmtree(cwd, ignore_errors=True)


def summary(record: dict[str, Any]) -> dict[str, Any]:
    return {key: record[key] for key in ("command", "exit_code", "stdout_sha256", "stderr_sha256")}


def run_gate(root: Path, output_root: Path, cargo_prefix: list[str]) -> dict[str, Any]:
    if platform.system() != "Windows":
        raise GateError("windows_required")
    root = root.resolve()
    output_root = output_root.resolve()
    if output_root == root or root in output_root.parents:
        raise GateError("output_root_inside_workspace")
    require_product_inputs_clean(root)
    entries = load_inventory(root)
    output_root.mkdir(parents=True, exist_ok=False)
    cargo_home = output_root / "cargo-home"
    target_dir = output_root / "target"
    install_root = output_root / "install"
    environment = scrubbed_environment(os.environ)
    environment.update({"CARGO_HOME": str(cargo_home), "CARGO_TARGET_DIR": str(target_dir), "CARGO_INCREMENTAL": "0"})
    commands = [
        [*cargo_prefix, "fmt", "--all", "--", "--check"],
        [*cargo_prefix, "clippy", "--workspace", "--all-targets", "--locked", "--target", TARGET, "--", "-D", "warnings"],
        [*cargo_prefix, "test", "--workspace", "--all-targets", "--locked", "--target", TARGET],
        [*cargo_prefix, "build", "-p", "sipi-cli", "--release", "--locked", "--target", TARGET],
        [
            *cargo_prefix,
            "install",
            "--path",
            "crates/sipi-cli",
            "--locked",
            "--target",
            TARGET,
            "--root",
            str(install_root),
        ],
    ]
    command_reports = []
    for command in commands:
        record = command_output(command, cwd=root, env=environment)
        require_success(record)
        command_reports.append(summary(record))
    executable = install_root / "bin" / "sipi.exe"
    if not executable.is_file():
        raise GateError("installed_executable_missing")
    smoke_environment = scrubbed_environment({"SystemRoot": os.environ.get("SystemRoot", ""), "WINDIR": os.environ.get("WINDIR", ""), "PATH": str(Path(os.environ.get("SystemRoot", "")) / "System32")})
    if not smoke_environment.get("SystemRoot"):
        raise GateError("system_root_unavailable")
    return {
        "schema": REPORT_SCHEMA,
        "status": "passed",
        "commit": subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip(),
        "lock_sha256": sha256((root / "Cargo.lock").read_bytes()),
        "target": TARGET,
        "installed_executable_sha256": sha256(executable.read_bytes()),
        "commands": command_reports,
        "smoke": verify_installed_cli(executable, root, entries, smoke_environment),
        "schema_inventory_sha256": sha256((root / INVENTORY.relative_to(ROOT)).read_bytes()),
        "limitations": ["provisional boundary; not release readiness", "not twin-build, archive, signature, or P1-10 layout evidence"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--rustup", type=Path, required=True)
    parser.add_argument("--toolchain", required=True)
    arguments = parser.parse_args()
    workspace = ROOT.resolve()
    report_path = arguments.report.resolve()
    if report_path == workspace or workspace in report_path.parents:
        parser.error("--report must be outside the workspace")
    report: dict[str, Any]
    try:
        report = run_gate(
            ROOT,
            arguments.output_root,
            [str(arguments.rustup), "run", arguments.toolchain, "cargo"],
        )
    except GateError as error:
        report = {"schema": REPORT_SCHEMA, "status": "rejected", "reason": str(error)}
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
