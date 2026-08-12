"""Observe two fresh external sealed-S4P admissions from a clean archive.

This external-only observer copies no selected S4P bytes into the repository.
It builds an ignored test runner from a clean Git archive, lets that runner
materialize two independent temporary ArtifactRoot instances, and retains only
a hash-only report outside the worktree.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNNER = Path("crates/sipi-p3c/tests/p3c_sealed_s4p_external_runner.rs")
INVENTORY_PATHS = (
    Path("Cargo.lock"),
    Path("crates/sipi-artifacts/src/lib.rs"),
    Path("crates/sipi-channel/src/p3c_fixed_four_port_bench_v1.rs"),
    Path("crates/sipi-p3c/Cargo.toml"),
    Path("crates/sipi-p3c/src/lib.rs"),
    RUNNER,
    Path("crates/sipi-touchstone/src/selected_four_port_v1.rs"),
)
SCHEMA = "sipi.p3c.sealed-selected-s4p-custody-observation.v1"
RUNNER_SCHEMA = "sipi.p3c.sealed-selected-s4p-custody-runner.v2"
SOURCE_LENGTH = 1_834_156
SOURCE_SHA256 = "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"


class ObservationError(RuntimeError):
    """A fail-closed external custody observation error."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_external_file(path: Path, *, kind: str) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or resolved.is_relative_to(ROOT.resolve()):
        raise ObservationError(f"{kind}_must_be_external_regular_file")
    return resolved


def require_external_report(path: Path) -> Path:
    resolved_parent = path.parent.resolve(strict=True)
    if resolved_parent.is_relative_to(ROOT.resolve()):
        raise ObservationError("report_must_be_outside_worktree")
    return resolved_parent / path.name


def source_identity(path: Path) -> tuple[int, str]:
    length = path.stat().st_size
    digest = sha256_file(path)
    if (length, digest) != (SOURCE_LENGTH, SOURCE_SHA256):
        raise ObservationError("selected_source_identity_mismatch")
    return length, digest


def clean_archive(destination: Path) -> tuple[str, dict[str, str]]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True, encoding="ascii"
    ).stdout.strip()
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"], cwd=ROOT, check=True, capture_output=True
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        names = bundle.getnames()
        if not names or any(Path(name).is_absolute() or ".." in Path(name).parts for name in names):
            raise ObservationError("clean_archive_path_invalid")
        bundle.extractall(destination, filter="data")
    inventory: dict[str, str] = {}
    for relative in INVENTORY_PATHS:
        path = destination / relative
        if not path.is_file():
            raise ObservationError("clean_archive_inventory_missing")
        inventory[relative.as_posix()] = sha256_file(path)
    return commit, inventory


def parse_runner_report(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObservationError("runner_report_invalid") from error
    required = {
        "schema", "status", "source_byte_length", "source_sha256", "source_identity_checks", "fresh_runs", "cleanup_status"
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ObservationError("runner_report_shape_invalid")
    runs = value["fresh_runs"]
    if (
        value["schema"] != RUNNER_SCHEMA
        or value["status"] != "observed"
        or value["source_byte_length"] != SOURCE_LENGTH
        or value["source_sha256"] != SOURCE_SHA256
        or value["source_identity_checks"] != "before_stage_after_equal"
        or value["cleanup_status"] != "complete"
        or not isinstance(runs, list)
        or len(runs) != 2
    ):
        raise ObservationError("runner_report_contract_invalid")
    manifests: list[str] = []
    records: list[int] = []
    for run in runs:
        if not isinstance(run, dict) or set(run) != {"manifest_sha256", "record_count"}:
            raise ObservationError("runner_run_shape_invalid")
        manifest = run["manifest_sha256"]
        record_count = run["record_count"]
        if (
            not isinstance(manifest, str)
            or len(manifest) != 64
            or any(character not in "0123456789abcdef" for character in manifest)
            or not isinstance(record_count, int)
            or isinstance(record_count, bool)
            or record_count <= 0
        ):
            raise ObservationError("runner_run_value_invalid")
        manifests.append(manifest)
        records.append(record_count)
    if manifests[0] == manifests[1] or records[0] != records[1]:
        raise ObservationError("fresh_run_consistency_invalid")
    return value


def run_observation(source: Path, report: Path, cargo: Path) -> dict[str, Any]:
    source = require_external_file(source, kind="source")
    report = require_external_report(report)
    cargo = require_external_file(cargo, kind="cargo")
    source_before = source_identity(source)
    with tempfile.TemporaryDirectory(prefix="sipi-p3c-sealed-s4p-archive-") as temporary:
        archive_root = Path(temporary) / "archive"
        archive_root.mkdir()
        commit, inventory = clean_archive(archive_root)
        runner_report = Path(temporary) / "runner-report.json"
        environment = os.environ.copy()
        environment.update(
            {
                "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE": str(source),
                "SIPI_P3C_SEALED_S4P_RUNNER_REPORT": str(runner_report),
                "CARGO_TARGET_DIR": str(Path(temporary) / "cargo-target"),
                "CARGO_INCREMENTAL": "0",
                "CARGO_NET_OFFLINE": "true",
            }
        )
        completed = subprocess.run(
            [str(cargo), "test", "-p", "sipi-p3c", "--locked", "--offline", "--test", "p3c_sealed_s4p_external_runner", "--", "--ignored", "--exact", "p3c_sealed_s4p_external_runner_v2"],
            cwd=archive_root,
            env=environment,
            capture_output=True,
            text=False,
            check=False,
        )
        if completed.returncode != 0:
            raise ObservationError("clean_archive_runner_failed")
        runner = parse_runner_report(runner_report)
        runner_sha256 = sha256_file(runner_report)
        runner_stdout_sha256 = sha256_bytes(completed.stdout)
        runner_stderr_sha256 = sha256_bytes(completed.stderr)
    source_after = source_identity(source)
    if source_before != source_after:
        raise ObservationError("source_changed_during_observation")
    return {
        "schema": SCHEMA,
        "status": "observed",
        "custody": "external_only",
        "report_path_retained": False,
        "selected_source": {"byte_length": source_before[0], "sha256": source_before[1]},
        "clean_archive_commit": commit,
        "product_source_inventory": inventory,
        "runner": {
            "source_sha256": inventory[RUNNER.as_posix()],
            "report_sha256": runner_sha256,
            "stdout_sha256": runner_stdout_sha256,
            "stderr_sha256": runner_stderr_sha256,
        },
        "fresh_custody_runs": 2,
        "manifest_sha256s": [run["manifest_sha256"] for run in runner["fresh_runs"]],
        "record_count": runner["fresh_runs"][0]["record_count"],
        "source_identity_checks": "before_stage_after_equal",
        "cleanup_status": "complete",
        "non_claims": [
            "The selected S4P bytes, temporary ArtifactRoots, runner report, and all absolute paths remain outside the worktree.",
            "This observes only exact selected-S4P static admission, not fit, stepping, waveform, ADS equivalence, receiver, AMI, IBIS, DLL, or release acceptance.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        result = run_observation(arguments.source, arguments.report, arguments.cargo)
    except (ObservationError, OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        result = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    try:
        report = require_external_report(arguments.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n", encoding="ascii")
    except (ObservationError, OSError):
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": result["status"]}, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
