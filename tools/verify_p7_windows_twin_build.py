"""Build one pinned SIPI Git tree twice and report Windows binary identity."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TARGET = "x86_64-pc-windows-msvc"
REPORT_SCHEMA = "sipi.p7-windows-twin-build-report.v1"
REPRO_RUSTFLAGS = "-C link-arg=/Brepro"


class GateError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def safe_archive_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and "\\" not in value and not path.is_absolute() and all(
        part not in {"", ".", ".."} for part in path.parts
    )


def require_external(path: Path, root: Path) -> None:
    resolved = path.resolve()
    workspace = root.resolve()
    if resolved == workspace or workspace in resolved.parents:
        raise GateError("external_output_required")


def prepare_report_path(report: Path, root: Path) -> Path:
    resolved = report.resolve()
    require_external(resolved, root)
    if resolved.exists():
        raise GateError("report_already_exists")
    return resolved


def write_report(report: Path, result: dict[str, Any]) -> None:
    try:
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as output:
            output.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    except OSError as error:
        raise GateError("report_write_failed") from error


def git_output(root: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments], check=True, capture_output=True
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise GateError("git_object_unavailable") from error
    return completed.stdout


def archive_commit(root: Path, commit: str) -> bytes:
    return git_output(root, "archive", "--format=tar", commit)


def materialize_archive(archive: bytes, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
            for member in bundle.getmembers():
                if not safe_archive_path(member.name) or member.issym() or member.islnk():
                    raise GateError("unsafe_archive_member")
                target = destination.joinpath(*PurePosixPath(member.name).parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    raise GateError("unsafe_archive_member")
                target.parent.mkdir(parents=True, exist_ok=True)
                payload = bundle.extractfile(member)
                if payload is None:
                    raise GateError("archive_member_unreadable")
                with target.open("xb") as output:
                    shutil.copyfileobj(payload, output)
    except (tarfile.TarError, OSError) as error:
        raise GateError("archive_materialization_failed") from error


def scrubbed_environment(base: dict[str, str], target_dir: Path) -> dict[str, str]:
    environment = dict(base)
    for key in list(environment):
        upper = key.upper()
        if (
            upper in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CARGO_TARGET_DIR", "CARGO_INCREMENTAL", "CARGO_NET_OFFLINE", "RUSTFLAGS"}
            or upper.startswith("CONDA_")
        ):
            environment.pop(key, None)
    environment.update(
        {
            "CARGO_TARGET_DIR": str(target_dir),
            "CARGO_INCREMENTAL": "0",
            "CARGO_NET_OFFLINE": "true",
            "RUSTFLAGS": REPRO_RUSTFLAGS,
        }
    )
    return environment


def command_version(command: list[str], cwd: Path, environment: dict[str, str]) -> str:
    try:
        completed = subprocess.run(command, cwd=cwd, env=environment, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise GateError("toolchain_unavailable") from error
    return sha256_bytes(completed.stdout)


def build_copy(
    source: Path,
    target_dir: Path,
    rustup: Path,
    toolchain: str,
) -> dict[str, Any]:
    if not (source / "Cargo.lock").is_file() or not (source / "rust-toolchain.toml").is_file():
        raise GateError("locked_inputs_missing")
    environment = scrubbed_environment(os.environ, target_dir)
    cargo = [str(rustup), "run", toolchain, "cargo"]
    cargo_version = command_version([*cargo, "--version"], source, environment)
    rustc_version = command_version([str(rustup), "run", toolchain, "rustc", "--version"], source, environment)
    try:
        completed = subprocess.run(
            [*cargo, "build", "-p", "sipi-cli", "--release", "--locked", "--offline", "--target", TARGET],
            cwd=source,
            env=environment,
            capture_output=True,
        )
    except OSError as error:
        raise GateError("toolchain_unavailable") from error
    if completed.returncode != 0:
        raise GateError("build_failed")
    binary = target_dir / TARGET / "release" / "sipi.exe"
    if not binary.is_file():
        raise GateError("binary_missing")
    return {
        "binary_bytes": binary.stat().st_size,
        "binary_sha256": sha256_file(binary),
        "cargo_version_sha256": cargo_version,
        "rustc_version_sha256": rustc_version,
    }


def compare_builds(first: dict[str, Any], second: dict[str, Any]) -> dict[str, bool]:
    return {
        "size_match": first["binary_bytes"] == second["binary_bytes"],
        "digest_match": first["binary_sha256"] == second["binary_sha256"],
    }


def run_gate(root: Path, output_root: Path, rustup: Path, toolchain: str) -> dict[str, Any]:
    if platform.system() != "Windows":
        raise GateError("windows_required")
    root = root.resolve()
    require_external(output_root, root)
    if output_root.exists():
        raise GateError("output_root_already_exists")
    if not rustup.is_file() or not toolchain:
        raise GateError("toolchain_unavailable")

    commit = git_output(root, "rev-parse", "HEAD").decode("ascii").strip()
    tree = git_output(root, "rev-parse", "HEAD^{tree}").decode("ascii").strip()
    archive = archive_commit(root, commit)
    output_root.mkdir(parents=True, exist_ok=False)
    first_source = output_root / "source-a"
    second_source = output_root / "source-b"
    materialize_archive(archive, first_source)
    materialize_archive(archive, second_source)
    first = build_copy(first_source, output_root / "target-a", rustup, toolchain)
    second = build_copy(second_source, output_root / "target-b", rustup, toolchain)
    comparison = compare_builds(first, second)
    return {
        "schema": REPORT_SCHEMA,
        "status": "identical" if all(comparison.values()) else "not_identical",
        "commit": commit,
        "tree": tree,
        "lock_sha256": sha256_file(first_source / "Cargo.lock"),
        "toolchain_sha256": sha256_file(first_source / "rust-toolchain.toml"),
        "rustflags_sha256": sha256_bytes(REPRO_RUSTFLAGS.encode("ascii")),
        "target": TARGET,
        "build_a": first,
        "build_b": second,
        "comparison": comparison,
        "limitations": [
            "provisional reproducibility evidence only",
            "not a release archive, SBOM, signature, PE closure, or fresh-machine certification",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--rustup", type=Path, required=True)
    parser.add_argument("--toolchain", required=True)
    arguments = parser.parse_args()
    report: Path | None = None
    try:
        report = prepare_report_path(arguments.report, ROOT)
        result = run_gate(ROOT, arguments.output_root, arguments.rustup, arguments.toolchain)
    except GateError as error:
        result = {"schema": REPORT_SCHEMA, "status": "rejected", "reason": str(error)}
        if report is None:
            print(json.dumps(result, sort_keys=True, separators=(",", ":")), file=sys.stderr)
            return 2
    try:
        write_report(report, result)
    except GateError as error:
        rejection = {"schema": REPORT_SCHEMA, "status": "rejected", "reason": str(error)}
        print(json.dumps(rejection, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "identical" else 2


if __name__ == "__main__":
    raise SystemExit(main())
