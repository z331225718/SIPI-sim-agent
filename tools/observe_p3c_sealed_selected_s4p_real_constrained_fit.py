"""Observe two fresh sealed-S4P admissions followed by the fixed P3C fit.

The selected source, temporary roots, and detailed runner report remain
external. This observer records only hashes and aggregate fit identity facts.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNNER = Path("crates/sipi-p3c/tests/p3c_sealed_s4p_external_fit_runner.rs")
INVENTORY_PATHS = (
    Path("Cargo.lock"), Path("crates/sipi-artifacts/src/lib.rs"),
    Path("crates/sipi-channel/src/p3c_fixed_four_port_bench_v1.rs"),
    Path("crates/sipi-channel/src/p3c_real_constrained_fixed_pole_fit_v1.rs"),
    Path("crates/sipi-p3c/Cargo.toml"), Path("crates/sipi-p3c/src/lib.rs"), RUNNER,
    Path("crates/sipi-touchstone/src/selected_four_port_v1.rs"),
)
SCHEMA = "sipi.p3c.sealed-selected-s4p-real-constrained-fit-observation.v1"
RUNNER_SCHEMA = "sipi.p3c.sealed-selected-s4p-real-constrained-fit-runner.v1"
SOURCE_LENGTH = 1_834_156
SOURCE_SHA256 = "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47"


class ObservationError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_external_file(path: Path, kind: str) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or resolved.is_relative_to(ROOT.resolve()):
        raise ObservationError(f"{kind}_must_be_external_regular_file")
    return resolved


def require_external_report(path: Path) -> Path:
    parent = path.parent.resolve(strict=True)
    if parent.is_relative_to(ROOT.resolve()):
        raise ObservationError("report_must_be_outside_worktree")
    return parent / path.name


def source_identity(path: Path) -> tuple[int, str]:
    identity = (path.stat().st_size, sha256_file(path))
    if identity != (SOURCE_LENGTH, SOURCE_SHA256):
        raise ObservationError("selected_source_identity_mismatch")
    return identity


def clean_archive(destination: Path) -> tuple[str, dict[str, str]]:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True, encoding="ascii").stdout.strip()
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=ROOT, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        if not bundle.getnames() or any(Path(name).is_absolute() or ".." in Path(name).parts for name in bundle.getnames()):
            raise ObservationError("clean_archive_path_invalid")
        bundle.extractall(destination, filter="data")
    inventory = {path.as_posix(): sha256_file(destination / path) for path in INVENTORY_PATHS}
    if len(inventory) != len(INVENTORY_PATHS):
        raise ObservationError("clean_archive_inventory_missing")
    return commit, inventory


def parse_runner_report(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObservationError("runner_report_invalid") from error
    required = {"schema", "status", "source_byte_length", "source_sha256", "source_identity_checks", "fresh_runs", "cleanup_status"}
    if not isinstance(value, dict) or set(value) != required or value.get("schema") != RUNNER_SCHEMA or value.get("status") != "observed" or value.get("source_byte_length") != SOURCE_LENGTH or value.get("source_sha256") != SOURCE_SHA256 or value.get("source_identity_checks") != "before_stage_after_equal" or value.get("cleanup_status") != "complete":
        raise ObservationError("runner_report_contract_invalid")
    runs = value["fresh_runs"]
    if not isinstance(runs, list) or len(runs) != 2:
        raise ObservationError("runner_runs_invalid")
    for run in runs:
        if not isinstance(run, dict) or set(run) != {"manifest_sha256", "record_count", "order", "model_sha256", "metrics_sha256"}:
            raise ObservationError("runner_run_shape_invalid")
        for key in ("manifest_sha256", "model_sha256", "metrics_sha256"):
            if not isinstance(run[key], str) or len(run[key]) != 64 or set(run[key]) - set("0123456789abcdef"):
                raise ObservationError("runner_hash_invalid")
        if not isinstance(run["record_count"], int) or isinstance(run["record_count"], bool) or run["record_count"] <= 0 or run["order"] not in (8, 12, 16):
            raise ObservationError("runner_run_value_invalid")
    first, second = runs
    if first["manifest_sha256"] == second["manifest_sha256"] or any(first[key] != second[key] for key in ("record_count", "order", "model_sha256", "metrics_sha256")):
        raise ObservationError("fresh_run_consistency_invalid")
    return value


def run_observation(source: Path, report: Path, cargo: Path) -> dict[str, Any]:
    source, report, cargo = require_external_file(source, "source"), require_external_report(report), require_external_file(cargo, "cargo")
    before = source_identity(source)
    with tempfile.TemporaryDirectory(prefix="sipi-p3c-fit-archive-") as temporary:
        archive_root = Path(temporary) / "archive"
        archive_root.mkdir()
        commit, inventory = clean_archive(archive_root)
        runner_report = Path(temporary) / "runner-report.json"
        environment = os.environ.copy()
        environment.update({"SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE": str(source), "SIPI_P3C_SEALED_S4P_FIT_RUNNER_REPORT": str(runner_report), "CARGO_TARGET_DIR": str(Path(temporary) / "cargo-target"), "CARGO_INCREMENTAL": "0", "CARGO_NET_OFFLINE": "true"})
        completed = subprocess.run([str(cargo), "test", "-p", "sipi-p3c", "--locked", "--offline", "--test", "p3c_sealed_s4p_external_fit_runner", "--", "--ignored", "--exact", "p3c_sealed_s4p_external_fit_runner_v1"], cwd=archive_root, env=environment, capture_output=True, text=False, check=False)
        if completed.returncode != 0:
            raise ObservationError("clean_archive_runner_failed")
        runner = parse_runner_report(runner_report)
        runner_sha256 = sha256_file(runner_report)
    if source_identity(source) != before:
        raise ObservationError("source_changed_during_observation")
    first = runner["fresh_runs"][0]
    return {"schema": SCHEMA, "status": "observed", "custody": "external_only", "report_path_retained": False, "selected_source": {"byte_length": before[0], "sha256": before[1]}, "clean_archive_commit": commit, "product_source_inventory": inventory, "runner": {"source_sha256": inventory[RUNNER.as_posix()], "report_sha256": runner_sha256}, "fresh_custody_runs": 2, "manifest_sha256s": [run["manifest_sha256"] for run in runner["fresh_runs"]], "record_count": first["record_count"], "order": first["order"], "model_sha256": first["model_sha256"], "metrics_sha256": first["metrics_sha256"], "source_identity_checks": "before_stage_after_equal", "cleanup_status": "complete", "non_claims": ["The selected S4P bytes, temporary ArtifactRoots, runner report, and all absolute paths remain outside the worktree.", "This observes only fixed static admission and fit identity, not stepping, waveform, ADS equivalence, receiver, AMI, IBIS, DLL, or release acceptance."]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_observation(args.source, args.report, args.cargo)
    except (ObservationError, OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        result = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    try:
        report = require_external_report(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_bytes((json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii"))
    except (ObservationError, OSError):
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps({"schema": SCHEMA, "status": result["status"]}, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
